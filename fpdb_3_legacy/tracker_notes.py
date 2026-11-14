"""Bringing player notes over from PokerTracker 4 (#618).

PokerTracker 4 keeps its notes in its own PostgreSQL database: ``notes`` holds
the text (``enum_type`` 'P' for a player, ``id_x`` the player's id), ``tags``
and ``lookup_tags`` the labels such as *Fish* or *Regular*, and ``id_color``
the colour picked for a note. fpdb keeps one manual note per player, in
``Players.comment``, shown as text in the HUD. So an imported note becomes a
text block that names where it came from, its date, and its labels and colour::

    [PokerTracker 4 | 2024-03-01 | Fish | colour 3]
    Calls three bets light from the blinds.

An existing fpdb note is never overwritten: a block is appended to it, or the
player is skipped when the user asked for that. A block already in the note is
not added twice, so importing again only brings what is new. A note on a
player fpdb has no hands of is reported, not created: import the hands first.

PT4's automatic notes (``notes_auto``), on request, go in a section of their
own that the import owns. PT4 rewrites them as it imports hands, so the
section is replaced on each import instead of growing; nothing outside it is
touched::

    [PokerTracker 4 auto-notes]
    - Folds to 3-bet out of position (x4, 2024-03-02)
    [end of PokerTracker 4 auto-notes]

Holdem Manager 3 exports its notes as a ``.playernotes`` file whose format is
not documented; no reader exists for it yet.

This module has no Qt: ``GuiTrackerNotes`` and the command line only render it.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _

__all__ = [
    "AUTO_SECTION_END",
    "AUTO_SECTION_START",
    "PT4_PLAYER_AUTO_NOTES",
    "PT4_PLAYER_NOTES",
    "PT4_PLAYER_TAGS",
    "SOURCE_PT4",
    "NoteOutcome",
    "NotesReport",
    "TrackerNote",
    "apply_notes",
    "auto_section",
    "format_report",
    "group_notes",
    "ipoker_rooms_of",
    "read_pt4_notes",
    "site_candidates",
]

SOURCE_PT4 = "PokerTracker 4"

# ``enum_type`` 'P' marks a player, as in PT4's own ``lookup_tags`` rows (H hand, S session, T tourney).
PT4_PLAYER_NOTES = """
SELECT p.id_site, ls.site_name, p.player_name, n.date_note, n.id_color, n.note
FROM notes n
JOIN player p ON p.id_player = n.id_x
LEFT JOIN lookup_sites ls ON ls.id_site = p.id_site
WHERE n.enum_type = 'P'
ORDER BY p.id_player, n.date_note, n.id_note
"""

PT4_PLAYER_TAGS = """
SELECT p.id_site, ls.site_name, p.player_name, lt.tag
FROM tags t
JOIN lookup_tags lt ON lt.id_tag = t.id_tag
JOIN player p ON p.id_player = t.id_x
LEFT JOIN lookup_sites ls ON ls.id_site = p.id_site
WHERE t.enum_type = 'P'
ORDER BY p.id_player, lt.id_tag
"""

PT4_PLAYER_AUTO_NOTES = """
SELECT p.id_site, ls.site_name, p.player_name, na.date_updated, na.cnt_times, na.note
FROM notes_auto na
JOIN player p ON p.id_player = na.id_player
LEFT JOIN lookup_sites ls ON ls.id_site = p.id_site
ORDER BY p.id_player, na.id_autonote
"""

AUTO_SECTION_START = "[" + SOURCE_PT4 + " auto-notes]"
AUTO_SECTION_END = "[end of " + SOURCE_PT4 + " auto-notes]"

# PT4 room names whose fpdb name is not found by comparing the two (see ``_key``).
_WPN = ("WinningPoker", "Americas Cardroom", "ACR Poker", "BlackChipPoker", "TruePoker", "Ya Poker")
_ALIASES: dict[str, tuple[str, ...]] = {
    "swc": ("SealsWithClubs",),
    "wpn": _WPN,
    "winning": _WPN,
    "acr": _WPN,
    "americascardroom": _WPN,
}

_IPOKER = "ipoker"
# A suffix is dropped only when this much of the name is left: ``iPoker`` stays ``ipoker``.
_MIN_KEY = 3


def _key(name: str) -> str:
    """A room name reduced to what PT4 and fpdb spell alike: ``Party Poker`` and ``PartyPoker`` -> ``party``."""
    key = re.sub(r"[^0-9a-z]", "", name.casefold())
    for suffix in ("network", "poker"):
        if key.endswith(suffix) and len(key) - len(suffix) >= _MIN_KEY:
            key = key[: -len(suffix)]
    return key


@dataclass(frozen=True)
class TrackerNote:
    """One note, or one label, a tracker keeps on a player."""

    site: str
    player: str
    text: str = ""
    labels: tuple[str, ...] = ()
    when: date | datetime | None = None
    source: str = SOURCE_PT4
    auto: bool = False  # a tracker's automatic note: kept in the section the import refreshes
    times: int | None = None  # how often an automatic note's situation was seen

    def line(self) -> str:
        """An automatic note as one line of its section: text, then how often and when last seen."""
        details = []
        if self.times is not None and self.times > 1:
            details.append(f"x{self.times}")
        if self.when is not None:
            details.append(self.when.strftime("%Y-%m-%d"))
        text = " ".join(self.text.split())
        return "- " + text + (" (" + ", ".join(details) + ")" if details else "")

    def block(self) -> str:
        """The note as fpdb shows it: a header naming source, date and labels, then the text."""
        header = [self.source]
        if self.when is not None:
            header.append(self.when.strftime("%Y-%m-%d"))
        header.extend(self.labels)
        lines = ["[" + " | ".join(header) + "]"]
        if self.text.strip():
            lines.append(self.text.strip())
        return "\n".join(lines)


def group_notes(notes: Iterable[TrackerNote]) -> dict[tuple[str, str], list[TrackerNote]]:
    """The notes per (room, player), in the order the tracker gave them."""
    grouped: dict[tuple[str, str], list[TrackerNote]] = {}
    for note in notes:
        grouped.setdefault((note.site, note.player), []).append(note)
    return grouped


def _rows(conn: Any, query: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(query)
        return list(cur.fetchall())


def _pt4_site(id_site: Any, site_name: Any) -> str:
    return str(site_name).strip() if site_name else f"PT4 site {id_site}"


def read_pt4_notes(conn: Any, *, auto_notes: bool = False) -> list[TrackerNote]:
    """Every player note and player label in a PT4 database, as ``TrackerNote``s.

    ``conn`` is a psycopg connection, read-only (``pt4_adapter.connect_pt4``).
    A player's labels go on its first note; a labelled player without a note
    gets a note of its labels alone, so a *Fish* tag is not lost. With
    ``auto_notes``, PT4's automatic notes come too, marked ``auto``.
    """
    notes = _pt4_manual_notes(conn)
    if auto_notes:
        notes.extend(
            TrackerNote(_pt4_site(id_site, site_name), str(player), str(text), (), when, auto=True, times=times)
            for id_site, site_name, player, when, times, text in _rows(conn, PT4_PLAYER_AUTO_NOTES)
            if player and (text or "").strip()
        )
    return notes


def _pt4_manual_notes(conn: Any) -> list[TrackerNote]:
    labels: dict[tuple[str, str], list[str]] = {}
    for id_site, site_name, player, tag in _rows(conn, PT4_PLAYER_TAGS):
        if player and tag:
            tags = labels.setdefault((_pt4_site(id_site, site_name), str(player)), [])
            if str(tag) not in tags:
                tags.append(str(tag))
    notes: list[TrackerNote] = []
    labelled: set[tuple[str, str]] = set()
    for id_site, site_name, player, when, id_color, text in _rows(conn, PT4_PLAYER_NOTES):
        if not player or not (text or "").strip():
            continue
        key = (_pt4_site(id_site, site_name), str(player))
        note_labels = [] if key in labelled else list(labels.get(key, ()))
        labelled.add(key)
        if id_color is not None:
            note_labels.append(f"colour {id_color}")
        notes.append(TrackerNote(key[0], key[1], str(text), tuple(note_labels), when))
    notes.extend(
        TrackerNote(site, player, "", tuple(tags))
        for (site, player), tags in labels.items()
        if (site, player) not in labelled
    )
    return notes


def site_candidates(
    source_site: str,
    fpdb_sites: Mapping[int, str],
    network_rooms: Mapping[str, Sequence[str]] | None = None,
) -> list[int]:
    """The fpdb site ids a tracker's room name may stand for.

    PT4 names a room as its own lookup table does (``Party``, ``iPoker``,
    ``SWCPoker``); fpdb may hold the same room under one or several names
    (``PartyPoker``, ``PartyPoker.fr``). Every fpdb site whose name starts like
    the tracker's is a candidate: the player's name then decides. PT4 files
    every iPoker skin under ``iPoker``, and only the configuration says which
    rooms are skins, so ``network_rooms["ipoker"]`` lists them.
    """
    source = _key(source_site)
    if not source:
        return []
    wanted = {_key(name) for name in _ALIASES.get(source, ())}
    if source == _IPOKER or _IPOKER in wanted:
        wanted.add(_IPOKER)
        wanted.update(_key(name) for name in (network_rooms or {}).get(_IPOKER, ()))
    found = []
    for site_id, name in fpdb_sites.items():
        key = _key(name)
        if key in wanted or key == source or (key.startswith(source) and source != _IPOKER):
            found.append(site_id)
    return sorted(found)


@dataclass(frozen=True)
class NoteOutcome:
    """What happened to one tracker player's notes."""

    site: str
    player: str
    status: str  # added | appended | updated | already | skipped | unknown_player | unknown_site
    fpdb_site: str | None = None
    blocks: int = 0


@dataclass
class NotesReport:
    """What an import of notes did, player by player."""

    outcomes: list[NoteOutcome] = field(default_factory=list)
    dry_run: bool = False

    def count(self, status: str) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == status)

    def of(self, status: str) -> list[NoteOutcome]:
        return [outcome for outcome in self.outcomes if outcome.status == status]


def auto_section(notes: Sequence[TrackerNote]) -> str | None:
    """The section holding a player's automatic notes, or None when there are none."""
    if not notes:
        return None
    return "\n".join([AUTO_SECTION_START, *(note.line() for note in notes), AUTO_SECTION_END])


def _split_section(note: str) -> tuple[str, str | None, str]:
    """The note before the auto-notes section, the section itself (None if absent), and after it."""
    start = note.find(AUTO_SECTION_START)
    end = note.find(AUTO_SECTION_END, start) if start >= 0 else -1
    if end < 0:
        return note, None, ""
    end += len(AUTO_SECTION_END)
    return note[:start], note[start:end], note[end:]


def _join(*parts: str) -> str:
    return "\n\n".join(part.strip("\n") for part in parts if part.strip())


def _merge(existing: str, blocks: Sequence[str], section: str | None, on_existing: str) -> tuple[str, str, int]:
    """What becomes of one fpdb note: its status, its new text and how many blocks it gains.

    ``blocks`` are appended unless the note holds them already; ``section``
    replaces the auto-notes section the note has, or is added. With "skip", a
    note the user wrote (anything outside the section) gains nothing, but a
    section an earlier import added is still refreshed: it is the import's own.
    """
    before, old_section, after = _split_section(existing)
    written = (before + after).strip()
    keep_out = on_existing == "skip" and bool(written)
    new_blocks = [block for block in blocks if block not in before + after]
    add_blocks = [] if keep_out else new_blocks
    held_back = bool(new_blocks and keep_out) or (section is not None and old_section is None and keep_out)
    if old_section is not None:
        merged = before + (section or old_section) + after
    elif section is not None and not keep_out:
        merged = _join(existing, section)
    else:
        merged = existing
    if add_blocks:
        merged = _join(merged, *add_blocks)
    if merged == existing:
        return ("skipped" if held_back else "already"), existing, 0
    gained = len(add_blocks) + (1 if section is not None and section != old_section else 0)
    if not existing.strip():
        return "added", merged, gained
    if old_section is not None and not add_blocks:
        return "updated", merged, gained
    return "appended", merged, gained


# fpdb's own tables; ``%s`` becomes the backend's placeholder, as for ``SQL.query``.
_FPDB_SITES = "SELECT id, name FROM Sites"
_FPDB_PLAYER = "SELECT id, siteId, comment FROM Players WHERE name = %s AND siteId = %s"
_FPDB_SET_COMMENT = "UPDATE Players SET comment = %s, commentTs = CURRENT_TIMESTAMP WHERE id = %s"


def apply_notes(
    connection: Any,
    notes: Iterable[TrackerNote],
    *,
    placeholder: str = "%s",
    on_existing: str = "append",
    network_rooms: Mapping[str, Sequence[str]] | None = None,
    dry_run: bool = False,
) -> NotesReport:
    """Write tracker notes into fpdb's ``Players.comment`` without overwriting any.

    ``connection`` is a DB-API connection to fpdb's database and ``placeholder``
    its bind marker. A note goes to every fpdb player of that name on the
    room's candidate sites (an iPoker name belongs to the whole network). An
    existing note is appended to (``on_existing="append"``) or left alone
    (``"skip"``); blocks it already holds are never added again. Automatic
    notes replace the auto-notes section an earlier import added. With
    ``dry_run`` nothing is written and the report says what would be.
    """
    if on_existing not in ("append", "skip"):
        msg = f"on_existing must be 'append' or 'skip', not {on_existing!r}"
        raise ValueError(msg)
    report = NotesReport(dry_run=dry_run)
    cursor = connection.cursor()
    cursor.execute(_FPDB_SITES)
    fpdb_sites = {int(site_id): str(name) for site_id, name in cursor.fetchall()}
    select_player = _FPDB_PLAYER.replace("%s", placeholder)
    set_comment = _FPDB_SET_COMMENT.replace("%s", placeholder)
    candidates_by_site: dict[str, list[int]] = {}
    for (site, player), player_notes in group_notes(notes).items():
        candidates = candidates_by_site.setdefault(site, site_candidates(site, fpdb_sites, network_rooms))
        rows = []
        for site_id in candidates:
            cursor.execute(select_player, (player, site_id))
            rows.extend(cursor.fetchall())
        if not rows:
            report.outcomes.append(NoteOutcome(site, player, "unknown_player" if candidates else "unknown_site"))
            continue
        blocks = [note.block() for note in player_notes if not note.auto]
        section = auto_section([note for note in player_notes if note.auto])
        for player_id, site_id, comment in rows:
            status, merged, added = _merge(comment or "", blocks, section, on_existing)
            if added and not dry_run:
                cursor.execute(set_comment, (merged, player_id))
            report.outcomes.append(NoteOutcome(site, player, status, fpdb_sites.get(int(site_id)), added))
    if not dry_run:
        connection.commit()
    return report


_STATUS_TEXT = {
    "added": N_("added"),
    "appended": N_("appended to the fpdb note"),
    "updated": N_("auto-notes updated"),
    "already": N_("already in fpdb"),
    "skipped": N_("skipped: fpdb already has a note"),
    "unknown_player": N_("not in fpdb: import the player's hands first"),
    "unknown_site": N_("room unknown to fpdb"),
}


def format_report(report: NotesReport) -> str:
    """The report as plain text, one line per player that was not simply added."""
    counts = {
        "added": report.count("added"),
        "appended": report.count("appended"),
        "updated": report.count("updated"),
        "already": report.count("already"),
        "skipped": report.count("skipped"),
        "unmatched": report.count("unknown_player") + report.count("unknown_site"),
    }
    if report.dry_run:
        headline = _(
            "Preview, nothing written: %(added)d notes to add, %(appended)d to append, %(updated)d to update, "
            "%(already)d already in fpdb, %(skipped)d to skip, %(unmatched)d not matched.",
        )
    else:
        headline = _(
            "%(added)d notes added, %(appended)d appended, %(updated)d updated, %(already)d already in fpdb, "
            "%(skipped)d skipped, %(unmatched)d not matched.",
        )
    lines = [headline % counts]
    for outcome in report.outcomes:
        if outcome.status == "added":
            continue
        where = outcome.site + " / " + outcome.player
        if outcome.fpdb_site:
            where += " -> " + outcome.fpdb_site
        lines.append("  " + where + ": " + _(_STATUS_TEXT[outcome.status]))
    return "\n".join(lines)


def ipoker_rooms_of(config: Any) -> dict[str, list[str]]:
    """The iPoker skins the configuration declares, as ``apply_notes`` takes them."""
    from fpdb_3_legacy import ipoker_rooms

    supported = getattr(config, "supported_sites", None) or {}
    return {_IPOKER: [name for name in supported if ipoker_rooms.is_room(config, name)]}


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m fpdb_3_legacy.tracker_notes``: import PT4 notes into the configured fpdb database."""
    from fpdb_3_legacy.pt4_adapter import Pt4Config, connect_pt4

    parser = argparse.ArgumentParser(description="Import PokerTracker 4 player notes into fpdb.")
    defaults = Pt4Config.from_env()
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--user", default=defaults.user)
    parser.add_argument("--database", default=defaults.database, help="PT4 database name (default: %(default)s)")
    parser.add_argument("--skip-existing", action="store_true", help="leave players who have an fpdb note alone")
    parser.add_argument(
        "--auto-notes",
        action="store_true",
        help="also import PT4's automatic notes, in a section each import refreshes",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args(argv)

    password = os.environ.get("PT4_PASSWORD") or getpass.getpass("PT4 database password: ")
    pt4 = Pt4Config(args.host, args.port, args.user, password, args.database)
    with connect_pt4(pt4) as conn:
        notes = read_pt4_notes(conn, auto_notes=args.auto_notes)

    from fpdb_3_legacy import Configuration, Database

    config = Configuration.Config()
    db = Database.Database(config)
    try:
        report = apply_notes(
            db.connection,
            notes,
            placeholder=db.sql.query["placeholder"],
            on_existing="skip" if args.skip_existing else "append",
            network_rooms=ipoker_rooms_of(config),
            dry_run=args.dry_run,
        )
    finally:
        db.close_connection()
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
