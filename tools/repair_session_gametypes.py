"""Repair the hands whose gametype was overwritten by their session (#595).

Between 734247d8 (2026-07-19) and the fix in #594, importing with session
caching on (``cacheSessions="True"``) wrote each hand's session id into
``Hands.gametypeId`` and left ``Hands.sessionId`` empty, on every site.
``Tourneys.sessionId`` stayed empty as well. Such a hand is filed under the
wrong game in every report, and a re-import of its file does not recognise it
(the duplicate check joins Hands to Gametypes) and stores it a second time.

Nothing else was lost, so the tool rebuilds the three columns from data the bug
did not touch:

* ``Hands.sessionId`` -- the Sessions row whose window contains the hand's
  start time. The damaged ``gametypeId`` holds the same id, which the report
  uses as a cross-check.
* ``Hands.gametypeId`` -- SessionsCache, which was keyed on the right gametype
  and exists exactly when session caching was on. Each player of the hand has a
  SessionsCache row covering its start time; the gametype every player agrees
  on is the hand's. A hand whose players do not agree is reported, not guessed.
* ``Tourneys.sessionId`` -- the session of the tournament's last hand.

It also reports what it cannot repair from the database:

* iPoker 5 card Omaha hands classified under another game before #594 -- every
  hand but the first of a session -- whose amounts were read against invented
  blinds. ``--delete-misclassified`` removes them so that re-importing their
  files stores them again correctly; without it they are only listed.
* game types whose HudCache counts fewer hands than the hands table: the
  tournament hands of a damaged import wrote no HudCache rows. A cache rebuild
  cannot restore them yet (#591); re-importing into a fresh database does.

    python tools/repair_session_gametypes.py              # report only
    python tools/repair_session_gametypes.py --rehearse   # run it, then roll back
    python tools/repair_session_gametypes.py --apply      # write

``--apply`` copies a SQLite database next to itself first (or to ``--backup``).
PostgreSQL and MySQL cannot be copied from here: back the database up with the
server's own tools, then pass ``--i-have-a-backup``.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import accumulate
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_cache  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402
from tools.cleanup_ipoker_anon_players import DELETE_BY_HAND, _sql, ipoker_sites  # noqa: E402

SELECT_UNSESSIONED_HANDS = (
    "SELECT id, gametypeId, startTime, tourneyId, tableName, siteHandNo FROM Hands WHERE sessionId IS NULL ORDER BY id"
)
SELECT_SAME_HAND = "SELECT id FROM Hands WHERE siteHandNo = %s AND gametypeId = %s"
SELECT_UNSESSIONED_SEATS = (
    "SELECT hp.handId, hp.playerId FROM HandsPlayers hp JOIN Hands h ON h.id = hp.handId WHERE h.sessionId IS NULL"
)
SELECT_SESSIONS = "SELECT id, sessionStart, sessionEnd FROM Sessions ORDER BY sessionStart"
SELECT_SESSION_CACHE = "SELECT playerId, gametypeId, startTime, endTime FROM SessionsCache"
SELECT_GAMETYPES = (
    "SELECT g.id, g.type, g.category, g.limitType, g.smallBlind, g.bigBlind, s.name "
    "FROM Gametypes g JOIN Sites s ON s.id = g.siteId"
)
SELECT_UNSESSIONED_TOURNEYS = "SELECT id FROM Tourneys WHERE sessionId IS NULL"
SELECT_TOURNEY_HANDS = "SELECT id, tourneyId, startTime, sessionId FROM Hands WHERE tourneyId IS NOT NULL"
SELECT_HANDS_FOR_TABLES = "SELECT h.id, h.gametypeId, h.tableName, f.file FROM Hands h JOIN Files f ON f.id = h.fileId"
SELECT_SEATS_PER_HAND = "SELECT h.id, h.gametypeId, COUNT(*) FROM HandsPlayers hp JOIN Hands h ON h.id = hp.handId GROUP BY h.id, h.gametypeId"
SELECT_HUD_COUNTS = "SELECT gametypeId, SUM(n) FROM HudCache GROUP BY gametypeId"

UPDATE_HAND = "UPDATE Hands SET gametypeId = %s, sessionId = %s WHERE id = %s"
UPDATE_TOURNEY = "UPDATE Tourneys SET sessionId = %s WHERE id = %s"

FIVE_CARD_OMAHA = "5_omahahi"
# The site the iPoker converter falls back to when it cannot tell the skin.
IPOKER_NETWORK = "iPoker"


@dataclass(frozen=True)
class HandFix:
    hand_id: int
    site_hand_no: int
    stored_gametype: int
    gametype: int
    session: int


@dataclass
class Survey:
    hand_fixes: list[HandFix] = field(default_factory=list)
    # Damaged rows whose hand is already stored under its right gametype --
    # a re-import of the damaged database stored it again.
    reimported: list[HandFix] = field(default_factory=list)
    tourney_fixes: dict[int, int] = field(default_factory=dict)
    misclassified: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    hud_shortfall: dict[int, tuple[int, int]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    cross_check_mismatches: int = 0

    @property
    def writes(self) -> bool:
        return bool(self.hand_fixes or self.reimported or self.tourney_fixes)


# ---------------------------------------------------------------------------
# Reading.
# ---------------------------------------------------------------------------


class SessionWindows:
    """Find the Sessions row whose window contains a time."""

    def __init__(self, rows) -> None:
        self.rows = [(start, end, int(session_id)) for session_id, start, end in rows]
        self.starts = [start for start, _end, _id in self.rows]
        # The latest end among the windows up to each index: once it falls
        # before the moment, no earlier window can contain it.
        self.reach = list(accumulate((end for _start, end, _id in self.rows), max))

    def containing(self, moment: datetime) -> list[int]:
        found = []
        index = bisect_right(self.starts, moment) - 1
        while index >= 0 and self.reach[index] >= moment:
            start, end, session_id = self.rows[index]
            if start <= moment <= end:
                found.append(session_id)
            index -= 1
        return found


def _fetch(db, statement: str, params: tuple = ()) -> list:
    cursor = db.get_cursor()
    cursor.execute(_sql(statement, db.sql.query["placeholder"]), params)
    return cursor.fetchall()


def _session_cache_by_player(db) -> dict[int, list[tuple]]:
    by_player: dict[int, list[tuple]] = defaultdict(list)
    for player_id, gametype_id, start, end in _fetch(db, SELECT_SESSION_CACHE):
        by_player[int(player_id)].append((start, end, int(gametype_id)))
    return by_player


def _agreed_gametype(players: list[int], cache: dict[int, list[tuple]], moment: datetime) -> set[int]:
    agreed: set[int] | None = None
    for player_id in players:
        covering = {gametype for start, end, gametype in cache.get(player_id, ()) if start <= moment <= end}
        agreed = covering if agreed is None else agreed & covering
        if not agreed:
            return set()
    return agreed or set()


def find_hand_fixes(db, found: Survey) -> None:
    """Hands without a session that session caching saw: give back their session and gametype."""
    windows = SessionWindows(_fetch(db, SELECT_SESSIONS))
    if not windows.rows:
        return
    cache = _session_cache_by_player(db)
    seats: dict[int, list[int]] = defaultdict(list)
    for hand_id, player_id in _fetch(db, SELECT_UNSESSIONED_SEATS):
        seats[int(hand_id)].append(int(player_id))

    for hand_id, stored_gametype, start, _tourney, table, site_hand_no in _fetch(db, SELECT_UNSESSIONED_HANDS):
        sessions = windows.containing(start)
        if not sessions:
            # Imported without session caching: nothing was overwritten.
            continue
        if len(sessions) != 1:
            found.unresolved.append(f"hand row {hand_id} ({table} {start}): {len(sessions)} sessions cover it")
            continue
        agreed = _agreed_gametype(seats.get(int(hand_id), []), cache, start)
        if len(agreed) != 1:
            found.unresolved.append(
                f"hand row {hand_id} ({table} {start}): its players' sessions name {len(agreed)} gametypes"
            )
            continue
        (gametype,) = agreed
        (session,) = sessions
        if int(stored_gametype) not in (gametype, session):
            found.cross_check_mismatches += 1
        found.hand_fixes.append(HandFix(int(hand_id), int(site_hand_no), int(stored_gametype), gametype, session))
    _set_aside_reimported(db, found)


def _set_aside_reimported(db, found: Survey) -> None:
    """Keep one row per hand: a damaged row whose hand exists under the right gametype goes.

    Re-importing a damaged database stored those hands again, since the
    duplicate check could not find them. Moving the damaged row onto the
    gametype the other copy already holds would break the siteHandNo unique
    index; the damaged copy is the one to remove.
    """
    damaged = {fix.hand_id for fix in found.hand_fixes}
    groups: dict[tuple[int, int], list[HandFix]] = defaultdict(list)
    for fix in found.hand_fixes:
        groups[(fix.site_hand_no, fix.gametype)].append(fix)
    keep: list[HandFix] = []
    for (site_hand_no, gametype), fixes in groups.items():
        fixes.sort(key=lambda fix: fix.hand_id)
        stored = [int(row[0]) for row in _fetch(db, SELECT_SAME_HAND, (site_hand_no, gametype))]
        if any(hand_id not in damaged for hand_id in stored):
            found.reimported.extend(fixes)
        else:
            keep.append(fixes[0])
            found.reimported.extend(fixes[1:])
    found.hand_fixes = sorted(keep, key=lambda fix: fix.hand_id)
    found.reimported.sort(key=lambda fix: fix.hand_id)


def find_tourney_fixes(db, found: Survey) -> None:
    """A tournament without a session takes the session of its last hand."""
    missing = {int(row[0]) for row in _fetch(db, SELECT_UNSESSIONED_TOURNEYS)}
    if not missing:
        return
    repaired = {fix.hand_id: fix.session for fix in found.hand_fixes}
    removed = {fix.hand_id for fix in found.reimported}
    last: dict[int, tuple[datetime, int]] = {}
    for hand_id, tourney_id, start, session in _fetch(db, SELECT_TOURNEY_HANDS):
        if int(hand_id) in removed:
            continue
        session = repaired.get(int(hand_id), session)
        if int(tourney_id) in missing and session is not None:
            current = last.get(int(tourney_id))
            if current is None or start >= current[0]:
                last[int(tourney_id)] = (start, int(session))
    found.tourney_fixes = {tourney_id: session for tourney_id, (_start, session) in sorted(last.items())}


def find_misclassified_five_card_omaha(db, sites: set[str], found: Survey) -> None:
    """iPoker files whose table holds 5 card Omaha hands and hands under another game.

    The bug only ever split one session file: its first hand was read as 5 card
    Omaha and the rest as something else. Grouping by file as well as table keeps
    a table name reused elsewhere, for another game, out of it.
    """
    gametypes = {int(row[0]): row for row in _fetch(db, SELECT_GAMETYPES)}
    ipoker = {gid for gid, row in gametypes.items() if row[6] in sites | {IPOKER_NETWORK}}
    repaired = {fix.hand_id: fix.gametype for fix in found.hand_fixes}
    removed = {fix.hand_id for fix in found.reimported}
    groups: dict[tuple[str, str], dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for hand_id, stored, table, file_name in _fetch(db, SELECT_HANDS_FOR_TABLES):
        if int(hand_id) in removed:
            continue
        gametype = repaired.get(int(hand_id), int(stored))
        if gametype in ipoker:
            groups[(str(file_name), str(table))][gametype].append(int(hand_id))
    for key, by_gametype in sorted(groups.items()):
        five_card = [gid for gid in by_gametype if gametypes[gid][2] == FIVE_CARD_OMAHA]
        others = [hand for gid, hands in by_gametype.items() if gid not in five_card for hand in hands]
        if five_card and others:
            found.misclassified[key] = sorted(others)


def find_hud_shortfall(db, found: Survey) -> None:
    """Game types whose HudCache counts fewer player-hands than the hands hold, once repaired."""
    hud = {int(gid): int(count or 0) for gid, count in _fetch(db, SELECT_HUD_COUNTS)}
    if not hud:
        # The HUD cache is not kept for this database; nothing to compare.
        return
    repaired = {fix.hand_id: fix.gametype for fix in found.hand_fixes}
    removed = {fix.hand_id for fix in found.reimported}
    seats: dict[int, int] = defaultdict(int)
    for hand_id, stored, count in _fetch(db, SELECT_SEATS_PER_HAND):
        if int(hand_id) not in removed:
            seats[repaired.get(int(hand_id), int(stored))] += int(count)
    for gametype_id, count in sorted(seats.items()):
        cached = hud.get(gametype_id, 0)
        if cached < count:
            found.hud_shortfall[gametype_id] = (count, cached)


def survey(db, sites: set[str]) -> Survey:
    found = Survey()
    find_hand_fixes(db, found)
    find_tourney_fixes(db, found)
    find_misclassified_five_card_omaha(db, sites, found)
    find_hud_shortfall(db, found)
    return found


# ---------------------------------------------------------------------------
# Repairing.
# ---------------------------------------------------------------------------


def repair(db, found: Survey, *, commit: bool, delete_misclassified: bool = False) -> dict[str, int]:
    """Write the fixes in one transaction; ``commit=False`` rolls it back."""
    ph = db.sql.query["placeholder"]
    misclassified = (
        {hand for hands in found.misclassified.values() for hand in hands} if delete_misclassified else set()
    )
    to_delete = sorted(misclassified | {fix.hand_id for fix in found.reimported})
    if commit and (found.hand_fixes or to_delete):
        # Moving or deleting hands changes the rows stored analytics counters
        # were built from; drop them first so no failure below leaves them stale.
        analytics_cache.invalidate_aggregates(db, "#595: hands regrouped by gametype")
    cursor = db.get_cursor()
    changed: dict[str, int] = defaultdict(int)
    try:
        # Deletions first: a re-imported copy's damaged twin must be gone
        # before its key is given back to the row that stays.
        for hand_id in to_delete:
            for table, statement in DELETE_BY_HAND:
                cursor.execute(_sql(statement, ph), (hand_id,))
                if cursor.rowcount and cursor.rowcount > 0:
                    changed[f"{table} deleted"] += cursor.rowcount
        for fix in found.hand_fixes:
            cursor.execute(_sql(UPDATE_HAND, ph), (fix.gametype, fix.session, fix.hand_id))
            changed["Hands repaired"] += 1
            if fix.gametype != fix.stored_gametype:
                changed["Hands moved to their gametype"] += 1
        for tourney_id, session in found.tourney_fixes.items():
            cursor.execute(_sql(UPDATE_TOURNEY, ph), (session, tourney_id))
            changed["Tourneys given their session"] += 1
    except Exception:
        db.connection.rollback()
        raise
    if commit:
        db.connection.commit()
    else:
        db.connection.rollback()
    return dict(changed)


# ---------------------------------------------------------------------------
# Backups and the command line.
# ---------------------------------------------------------------------------


def backup_sqlite(db, target: Path | None) -> Path:
    """Copy a SQLite database with the online backup API, which is consistent under WAL."""
    source = Path(db.db_path)
    if target is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = source.with_name(f"{source.name}.before-595-{stamp}")
    if target.exists():
        msg = f"refusing to overwrite an existing backup: {target}"
        raise SystemExit(msg)
    with sqlite3.connect(str(target)) as destination:
        db.connection.backup(destination)
    return target


def report(found: Survey) -> None:
    moved = [fix for fix in found.hand_fixes if fix.gametype != fix.stored_gametype]
    print(f"{len(found.hand_fixes)} hand(s) without their session; {len(moved)} of them under the wrong gametype.")
    if found.cross_check_mismatches:
        print(f"  {found.cross_check_mismatches} stored gametype(s) were neither the session nor the recovered one.")
    if found.reimported:
        print(
            f"{len(found.reimported)} damaged row(s) whose hand was imported again under its right gametype: "
            "the damaged copy is deleted (the HUD and session caches keep counting it, #591)."
        )
    print(f"{len(found.tourney_fixes)} tournament(s) without their session.")
    if found.unresolved:
        print("\nLeft alone:")
        for line in found.unresolved:
            print(f"  {line}")
    if found.misclassified:
        count = sum(len(hands) for hands in found.misclassified.values())
        print(f"\n{count} iPoker 5 card Omaha hand(s) stored under another game, at:")
        for (file_name, table), table_hands in found.misclassified.items():
            print(f"  {table} (file {file_name}): {len(table_hands)} hand(s)")
        print("  Their amounts are wrong too: delete them (--delete-misclassified) and re-import those files.")
    if found.hud_shortfall:
        print("\nHudCache counts fewer player-hands than the hands table for:")
        for gametype_id, (in_hands, cached) in found.hud_shortfall.items():
            print(f"  gametype {gametype_id}: {in_hands} in the hands, {cached} in HudCache")
        print("  A cache rebuild cannot restore them yet (#591); re-import into a fresh database does.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="HUD_config.xml to read the database from (default: the configured one)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write; without it nothing is changed")
    mode.add_argument("--rehearse", action="store_true", help="run the repair and roll it back")
    parser.add_argument(
        "--delete-misclassified",
        action="store_true",
        help="also delete the misclassified iPoker 5 card Omaha hands, to re-import their files",
    )
    parser.add_argument("--backup", type=Path, help="where --apply copies a SQLite database first")
    parser.add_argument(
        "--i-have-a-backup",
        action="store_true",
        help="PostgreSQL / MySQL: confirm the database was backed up with the server's tools",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = Config(file=args.config) if args.config else Config()
    db = Database(config)
    print(f"Database {db.database}@{db.host}\n")

    found = survey(db, ipoker_sites(config))
    report(found)
    deleting = args.delete_misclassified and bool(found.misclassified)
    if not (found.writes or deleting):
        print("\nNothing to repair.")
        return 0

    if not (args.apply or args.rehearse):
        print("\nDry run: nothing was changed. Re-run with --rehearse to try it, --apply to write.")
        return 0

    if args.apply:
        if db.backend == db.SQLITE:
            print(f"\nBackup: {backup_sqlite(db, args.backup)}")
        elif not args.i_have_a_backup:
            print("\nBack the database up with the server's own tools, then re-run with --i-have-a-backup.")
            return 2

    changed = repair(db, found, commit=args.apply, delete_misclassified=args.delete_misclassified)
    print("\nChanged:" if args.apply else "\nWould change (rolled back):")
    for what, count in sorted(changed.items()):
        print(f"  {count:>5}  {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
