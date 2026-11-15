"""Hands straight from a PokerTracker 4 database, read-only (#814).

PT4 keeps the text of every hand it imported in ``cash_hand_histories`` and
``tourney_hand_histories``: each room's own hand history, iPoker excepted, which
PT4 rewrites as ``GAME #…`` text that ``PokerTrackerToFpdb`` reads (#615). fpdb's
room parsers read that text unchanged, so this module writes it back out as
files, room by room, into a folder of its own. The wizard then scans and
imports that folder exactly as it would a tracker's archive, so duplicates,
hero and iPoker room placement, sessions and the HUD cache behave the same.

What the database changes and the files did not have:

* On macOS PT4 decoded cp1252 files as Mac Roman: ``€`` (0x80) is stored as
  ``Ä``. :func:`repair_mac_roman` turns such a history back into the room's text.
* A history has no file name, and the old Winning format takes the tournament
  number from it. PT4 also appends that number to the hand's first line.
  :func:`restore_winning` takes it off and rebuilds the file name from it.
* PT4 appends ``, Filename: …`` to a Winamax summary's first line;
  :func:`restore_summary` takes it off.
* Tournament results come from summary files, which a database does not hold.
  PT4 keeps the room's summary text in ``tourney_summary.summary`` when it read
  one; those are written out too and go through fpdb's summary parsers.

The connection is ``pt4_adapter.connect_pt4``'s: the server refuses any write.
The password is the caller's to ask for and keep; it is never read from PT4's
settings and never stored.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Callable, Generator
from contextlib import closing, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("pt4_database")

__all__ = [
    "KINDS",
    "DatabaseExport",
    "Pt4Database",
    "export_database",
    "load_marks",
    "repair_mac_roman",
    "restore_summary",
    "restore_winning",
    "save_marks",
    "winning_file_name",
]

KINDS = ("cash", "tourney")
SUMMARIES = "summary"

# One query per kind, joined to the room and, for tournaments, to the tournament
# number. Both are fixed strings: nothing from outside reaches the SQL text.
_HISTORIES = {
    "cash": (
        "SELECT x.id_hand, s.site_name, NULL, x.history "
        "FROM cash_hand_histories x "
        "JOIN cash_hand_summary h ON h.id_hand = x.id_hand "
        "JOIN lookup_sites s ON s.id_site = h.id_site "
        "WHERE x.id_hand > %s ORDER BY x.id_hand"
    ),
    "tourney": (
        "SELECT x.id_hand, s.site_name, t.tourney_no, x.history "
        "FROM tourney_hand_histories x "
        "JOIN tourney_hand_summary h ON h.id_hand = x.id_hand "
        "JOIN lookup_sites s ON s.id_site = h.id_site "
        "LEFT JOIN tourney_summary t ON t.id_tourney = h.id_tourney "
        "WHERE x.id_hand > %s ORDER BY x.id_hand"
    ),
}
_COUNTS = {
    "cash": "SELECT count(*) FROM cash_hand_histories WHERE id_hand > %s",
    "tourney": "SELECT count(*) FROM tourney_hand_histories WHERE id_hand > %s",
}
# Every summary, whatever the marks say: a tournament still running at the last
# import has a summary now, under an id_tourney the marks already passed.
_SUMMARIES = (
    "SELECT t.id_tourney, s.site_name, t.summary "
    "FROM tourney_summary t JOIN lookup_sites s ON s.id_site = t.id_site "
    "WHERE t.summary IS NOT NULL AND t.summary <> '' ORDER BY t.id_tourney"
)

# A hand starts again after blank lines in every room's own files.
HAND_SEPARATOR = "\n\n\n"
# Hands per file: the parsers read a file whole, so this bounds their memory.
HANDS_PER_FILE = 5000
_ROWS_PER_PROGRESS = 1000

_EURO_AS_MAC_ROMAN = re.compile(r"Ä ?\d")
# The old Winning format's first line; " Tournament#<n>" (sometimes "-<m>") is PT4's addition.
_WINNING_V1_FIRST_LINE = re.compile(
    r"\A(?P<head>Game started at: (?P<date>\d{4}/\d{1,2}/\d{1,2}) \d{1,2}:\d{1,2}:\d{1,2})"
    r"(?P<appended> Tournament#(?P<tourno>\d+)(?:-\d+)?)?[ \t]*(?=\r?\n|\Z)"
)
_PT4_FILENAME = re.compile(r"\A(Winamax Poker - Tournament summary : [^\r\n]*?), Filename: [^\r\n]*", re.MULTILINE)
# A byte-order mark or blank lines before the first hand.
_LEADING_JUNK = chr(0xFEFF) + "\r\n "
_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


@dataclass(frozen=True)
class Pt4Database:
    """Where the PT4 database is; the password travels apart and is never kept."""

    host: str = "localhost"
    port: int = 5432
    database: str = "PT4 DB"
    user: str = "postgres"

    @property
    def key(self) -> str:
        """Names this database in the marks file."""
        return f"{self.user}@{self.host}:{self.port}/{self.database}"

    def connect(self, password: str) -> Any:
        from fpdb_3_legacy.pt4_adapter import Pt4Config, connect_pt4

        return connect_pt4(Pt4Config(self.host, self.port, self.user, password, self.database))


@dataclass
class DatabaseExport:
    """What was written out of the database, and where."""

    folder: str
    hands: Counter[tuple[str, str]] = field(default_factory=Counter)  # (kind, PT4 room) -> hands
    summaries: int = 0
    repaired: int = 0
    marks: dict[str, int] = field(default_factory=dict)  # kind -> highest id_hand written

    @property
    def hand_count(self) -> int:
        return sum(self.hands.values())


def repair_mac_roman(history: str) -> tuple[str, bool]:
    """The room's own text of a history PT4 decoded as Mac Roman, and whether it was repaired.

    PT4 on macOS read cp1252 files as Mac Roman, so a euro amount reads ``Ä4.69``.
    Only a history showing that and whose every character Mac Roman can encode is
    re-encoded: a history PT4 read correctly keeps its accents untouched.
    """
    if not _EURO_AS_MAC_ROMAN.search(history):
        return history, False
    try:
        repaired = history.encode("mac_roman").decode("cp1252")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return history, False
    return repaired, True


def restore_winning(history: str, tourney_no: Any) -> tuple[str, str | None]:
    """An old-format Winning hand as the room wrote it, and the file name its parser reads.

    PT4 appends ``Tournament#<n>`` to the hand's first line, which the room's
    files never had. ``WinningToFpdb`` reads the tournament from the file name
    instead: ``HH<yyyymmdd> T<tournament>-G<n>``. The number is the one PT4
    appended, else PT4's ``tourney_no``. Any other hand comes back unchanged,
    with no name.
    """
    match = _WINNING_V1_FIRST_LINE.match(history)
    if match is None:
        return history, None
    if match.group("appended"):
        history = match.group("head") + history[match.end() :]
    number = match.group("tourno") or str(tourney_no or "")
    if not number.isdigit():
        return history, None
    year, month, day = (int(part) for part in match.group("date").split("/"))
    return history, f"HH{year}{month:02d}{day:02d} T{number}-G0"


def winning_file_name(history: str, tourney_no: Any) -> str | None:
    """The file name the old Winning format reads its tournament from, or None for any other hand."""
    return restore_winning(history, tourney_no)[1]


def restore_summary(summary: str) -> str:
    """A tournament summary as the room wrote it: without what PT4 added when it stored it.

    PT4 appends ``, Filename: <the file it read>`` to a Winamax summary's first
    line; fpdb's Winamax summary parser stops there.
    """
    return _PT4_FILENAME.sub(r"\1", summary, count=1)


def _slug(text: str) -> str:
    return _UNSAFE.sub("_", text).strip("_") or "room"


def _as_text(value: Any) -> str:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


class _Writer:
    """Hands of one kind and room, split into files of at most ``HANDS_PER_FILE``."""

    def __init__(self, folder: Path, stem: str, *, single_file: bool = False) -> None:
        self.folder = folder
        self.stem = stem
        self.single_file = single_file
        self.handle: TextIO | None = None
        self.in_file = 0
        self.files = 0

    def write(self, history: str) -> None:
        if self.handle is None or (not self.single_file and self.in_file >= HANDS_PER_FILE):
            self.close()
            self.files += 1
            name = f"{self.stem}.txt" if self.single_file else f"{self.stem}-{self.files:05d}.txt"
            self.handle = (self.folder / name).open("w", encoding="utf-8", newline="\n")
            self.in_file = 0
        elif self.in_file:
            self.handle.write(HAND_SEPARATOR)
        self.handle.write(history)
        self.in_file += 1

    def close(self) -> None:
        if self.handle is not None:
            self.handle.write("\n")
            self.handle.close()
            self.handle = None


def _stream(conn: Any, query: str, params: tuple, name: str) -> Generator[tuple, None, None]:
    """Rows of ``query`` through a server-side cursor: a large table is never held whole."""
    with conn.transaction(), conn.cursor(name=name) as cur:
        cur.itersize = 2000
        cur.execute(query, params)
        yield from cur


def _count(conn: Any, kind: str, since: int) -> int:
    with conn.cursor() as cur:
        cur.execute(_COUNTS[kind], (since,))
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _writer_for(
    root: Path, writers: dict[tuple[bool, str], _Writer], kind: str, room: str, name: str | None
) -> _Writer:
    """The file a hand goes to: its room's current file, or the one its rebuilt name calls for."""
    key = (name is not None, name or room)
    writer = writers.get(key)
    if writer is None:
        if name is None:
            writer = _Writer(root, f"{kind}-{_slug(room)}")
        else:
            writer = _Writer(root, f"{kind}-{_slug(room)} {name}", single_file=True)
        writers[key] = writer
    return writer


def _export_kind(
    conn: Any,
    root: Path,
    kind: str,
    since: int,
    export: DatabaseExport,
    tick: Callable[[], None],
    should_stop: Callable[[], bool] | None,
) -> bool:
    """Write one kind's hands after ``since``; False when ``should_stop`` cut it short."""
    writers: dict[tuple[bool, str], _Writer] = {}
    rows = _stream(conn, _HISTORIES[kind], (since,), f"fpdb_{kind}")
    try:
        for id_hand, pt4_room, tourney_no, value in rows:
            if should_stop and should_stop():
                return False
            tick()
            history = _as_text(value).strip(_LEADING_JUNK)
            if not history:
                continue
            history, repaired = repair_mac_roman(history)
            export.repaired += repaired
            room = str(pt4_room or "unknown")
            history, name = restore_winning(history, tourney_no) if kind == "tourney" else (history, None)
            _writer_for(root, writers, kind, room, name).write(history)
            export.hands[(kind, room)] += 1
            export.marks[kind] = max(export.marks.get(kind, 0), int(id_hand))
    finally:
        rows.close()  # ends the server-side cursor now, not at collection
        for writer in writers.values():
            writer.close()
    return True


def export_database(
    conn: Any,
    folder: str | os.PathLike[str],
    marks: dict[str, int] | None = None,
    *,
    progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> DatabaseExport:
    """Write every hand PT4 holds after ``marks`` as files under ``folder``, room by room.

    ``marks`` maps a kind to the last ``id_hand`` already imported; hands at or
    below it are skipped. ``progress(done, total)`` is called as rows are read.
    Nothing is written to the PT4 database: ``conn`` should be read-only anyway.
    """
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    export = DatabaseExport(str(root), marks={kind: int(v) for kind, v in (marks or {}).items() if kind in KINDS})
    since = {kind: export.marks.get(kind, 0) for kind in KINDS}
    total = sum(_count(conn, kind, since[kind]) for kind in KINDS)
    done = 0

    def tick() -> None:
        nonlocal done
        done += 1
        if progress and done % _ROWS_PER_PROGRESS == 0:
            progress(done, total)

    if progress:
        progress(0, total)
    for kind in KINDS:
        if not _export_kind(conn, root, kind, since[kind], export, tick, should_stop):
            return export
    with closing(_stream(conn, _SUMMARIES, (), "fpdb_summaries")) as summaries:
        for id_tourney, room, value in summaries:
            if should_stop and should_stop():
                return export
            _write_summary(root, export, id_tourney, room, value)
    if progress:
        progress(total, total)
    return export


def _write_summary(root: Path, export: DatabaseExport, id_tourney: Any, room: Any, value: Any) -> None:
    """One tournament's summary text, as the room wrote it, in a file of its own."""
    summary = _as_text(value).strip(_LEADING_JUNK)
    if not summary:
        return
    summary, repaired = repair_mac_roman(restore_summary(summary))
    export.repaired += repaired
    path = root / f"summary-{_slug(str(room or 'unknown'))}-{int(id_tourney)}.txt"
    path.write_text(summary + "\n", encoding="utf-8", newline="\n")
    export.summaries += 1


# --- what was already imported --------------------------------------------------

MARKS_FILE = "pt4_import_marks.json"


def _marks_path(config: Any) -> Path | None:
    config_file = getattr(config, "file", None)
    return Path(config_file).parent / MARKS_FILE if config_file else None


def load_marks(config: Any, database: Pt4Database) -> dict[str, int]:
    """The last ``id_hand`` of each kind imported from ``database``, or nothing yet."""
    path = _marks_path(config)
    if path is None:
        return {}
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    marks = stored.get(database.key) if isinstance(stored, dict) else None
    if not isinstance(marks, dict):
        return {}
    return {kind: int(value) for kind, value in marks.items() if kind in KINDS and str(value).isdigit()}


def save_marks(config: Any, database: Pt4Database, marks: dict[str, int]) -> None:
    """Remember what ``database`` gave up to now, next to the configuration file."""
    path = _marks_path(config)
    if path is None:
        return
    stored: dict[str, Any] = {}
    with suppress(OSError, ValueError):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            stored = loaded
    stored[database.key] = {kind: int(marks[kind]) for kind in KINDS if kind in marks}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
