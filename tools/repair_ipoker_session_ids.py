"""Repair the iPoker hands stored under their file's session code (#440).

Until the fix of 2026-07-25 the iPoker converter read a hand's id from the
first ``code="..."`` in its text. Every iPoker file opens with
``<session sessioncode="...">``, so the first hand of each file was stored with
the session code as its ``siteHandNo`` instead of its own ``gamecode``. The
parser is fixed; databases imported before it are not:

* if the file was imported again since, the first hand is in the database
  twice -- once under the session code, once under its gamecode -- and every
  report, graph and statistic read from the hands counts it twice;
* if it was not, the hand is there once under the wrong id, and the next
  import of that file will add the duplicate.

This tool finds both cases.

A **duplicate** is a pair of iPoker hands at the same table with the same start
time, the same players in the same seats with the same stacks and results, and
different ids. No two real hands share all of that. The older row is the stale
one: the copy under the right id can only have been written by a later import.
With ``--hh-dir``, the hand history files also give the exact session code ->
gamecode pairs, which confirms the duplicates by id and finds the second case:
a hand stored only under its session code is given its gamecode.

The repair works on the hand tables (Hands, HandsPlayers, HandsActions and
everything else keyed on a hand), drops the analytics aggregates, and rebuilds
HudCache, CardsCache and PositionsCache from the hands (#591). SessionsCache and
TourneysCache have no rebuild: they keep the duplicate's contribution, one extra
hand per affected file.

    python tools/repair_ipoker_session_ids.py                       # report only
    python tools/repair_ipoker_session_ids.py --hh-dir ~/iPokerHH   # report, with the files
    python tools/repair_ipoker_session_ids.py --rehearse            # run it, then roll back
    python tools/repair_ipoker_session_ids.py --apply               # write

``--apply`` copies a SQLite database next to itself first (or to ``--backup``).
PostgreSQL and MySQL cannot be copied from here: back the database up with the
server's own tools, then pass ``--i-have-a-backup``.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_cache  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402
from tools.cleanup_ipoker_anon_players import DELETE_BY_HAND, _sql, ipoker_sites  # noqa: E402

SELECT_GAMETYPE_SITES = "SELECT g.id, s.name FROM Gametypes g JOIN Sites s ON s.id = g.siteId"

# Hands sharing a table and a start time under different ids. Not joined on
# gametypeId: a stale hand and its copy were imported at different times, and
# the iPoker path does not always store the same gametype twice (#592).
SELECT_SAME_START = (
    "SELECT a.id, a.siteHandNo, a.gametypeId, a.tableName, a.startTime, a.tourneyId "
    "FROM Hands a JOIN Hands b ON b.startTime = a.startTime AND b.tableName = a.tableName "
    "AND b.id <> a.id AND b.siteHandNo <> a.siteHandNo "
    "ORDER BY a.id"
)
SELECT_SEATING = (
    "SELECT playerId, seatNo, startCash, totalProfit FROM HandsPlayers WHERE handId = %s ORDER BY seatNo, playerId"
)
SELECT_BY_SITE_HAND_NO = (
    "SELECT id, siteHandNo, gametypeId, tableName, startTime, tourneyId FROM Hands WHERE siteHandNo = %s"
)
RENAME_HAND = "UPDATE Hands SET siteHandNo = %s WHERE id = %s"

SESSION_RE = re.compile(rb'<session\b[^>]*\bsessioncode="(\d+)"')
GAME_RE = re.compile(rb'<game\b[^>]*\bgamecode="(\d+)"')

# Caches whose rebuild from the hands reproduces what the import wrote (#591).
REBUILT_CACHES = ("HudCache", "CardsCache", "PositionsCache")

# The site the converter falls back to when it cannot tell which skin a file
# came from (iPoker/base.py). The configured skins alone would miss those hands.
IPOKER_NETWORK = "iPoker"


@dataclass(frozen=True)
class Hand:
    """The columns of a Hands row this tool reasons about."""

    id: int
    site_hand_no: int
    gametype_id: int
    table: str
    start_time: datetime
    tourney_id: int | None

    @classmethod
    def from_row(cls, row) -> Hand:
        return cls(int(row[0]), int(row[1]), int(row[2]), str(row[3]), row[4], row[5])


@dataclass(frozen=True)
class Duplicate:
    """A stale hand and the correctly numbered copy that makes it redundant."""

    stale: Hand
    twin_id: int
    evidence: str


@dataclass(frozen=True)
class Rename:
    """A hand stored only under its session code, and the gamecode it should carry."""

    hand: Hand
    gamecode: int


@dataclass
class Survey:
    duplicates: list[Duplicate]
    renames: list[Rename]
    ambiguous: list[str]


# ---------------------------------------------------------------------------
# Reading the hand history files.
# ---------------------------------------------------------------------------


def iter_history_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in (".txt", ".xml"))


def session_first_games(paths: Iterable[Path]) -> dict[int, set[int]]:
    """Map each session code to the gamecode(s) of the first hand of its file(s).

    That first hand is the one the old pattern misnumbered. A session exported
    twice maps to the same gamecode both times; one that maps to several is
    reported as ambiguous rather than guessed at.
    """
    first_games: dict[int, set[int]] = defaultdict(set)
    for path in iter_history_files(paths):
        data = path.read_bytes()
        session = SESSION_RE.search(data)
        if session is None:
            continue
        game = GAME_RE.search(data, session.end())
        if game is not None:
            first_games[int(session.group(1))].add(int(game.group(1)))
    return dict(first_games)


# ---------------------------------------------------------------------------
# Finding the stale hands.
# ---------------------------------------------------------------------------


def ipoker_gametype_ids(db, sites: set[str]) -> set[int]:
    cursor = db.get_cursor()
    cursor.execute(SELECT_GAMETYPE_SITES)
    return {int(gametype_id) for gametype_id, site in cursor.fetchall() if site in sites}


def _seating(cursor, ph: str, hand_id: int) -> list[tuple]:
    cursor.execute(_sql(SELECT_SEATING, ph), (hand_id,))
    return [tuple(row) for row in cursor.fetchall()]


def find_identical_twins(db, gametype_ids: set[int], ambiguous: list[str]) -> list[Duplicate]:
    """Pairs of iPoker hands that are the same hand under two ids."""
    ph = db.sql.query["placeholder"]
    cursor = db.get_cursor()
    cursor.execute(SELECT_SAME_START)
    groups: dict[tuple, dict[int, Hand]] = defaultdict(dict)
    for row in cursor.fetchall():
        hand = Hand.from_row(row)
        if hand.gametype_id in gametype_ids:
            groups[(hand.table, hand.start_time)][hand.id] = hand

    duplicates = []
    for (table, start), hands in sorted(groups.items(), key=lambda item: min(item[1])):
        if len(hands) != 2:
            ids = ", ".join(str(h.site_hand_no) for h in sorted(hands.values(), key=lambda h: h.id))
            ambiguous.append(f"{len(hands)} hands at {table} {start} ({ids}): left alone")
            continue
        older, newer = sorted(hands.values(), key=lambda h: h.id)
        if older.tourney_id != newer.tourney_id:
            continue
        if _seating(cursor, ph, older.id) != _seating(cursor, ph, newer.id):
            continue
        duplicates.append(Duplicate(older, newer.id, "identical twin"))
    return duplicates


def _ipoker_hands_numbered(cursor, ph: str, site_hand_no: int, gametype_ids: set[int]) -> list[Hand]:
    cursor.execute(_sql(SELECT_BY_SITE_HAND_NO, ph), (site_hand_no,))
    return [hand for hand in map(Hand.from_row, cursor.fetchall()) if hand.gametype_id in gametype_ids]


def find_by_session_code(
    db, gametype_ids: set[int], first_games: dict[int, set[int]], ambiguous: list[str]
) -> tuple[list[Duplicate], list[Rename]]:
    """Hands stored under a session code the hand history files name."""
    ph = db.sql.query["placeholder"]
    cursor = db.get_cursor()
    duplicates: list[Duplicate] = []
    renames: list[Rename] = []
    for session_code, gamecodes in sorted(first_games.items()):
        stale_hands = _ipoker_hands_numbered(cursor, ph, session_code, gametype_ids)
        if not stale_hands:
            continue
        if len(gamecodes) != 1 or len(stale_hands) != 1:
            codes = ", ".join(str(code) for code in sorted(gamecodes))
            ambiguous.append(
                f"session {session_code}: {len(stale_hands)} hand(s), first gamecode(s) {codes}: left alone"
            )
            continue
        (gamecode,) = gamecodes
        (stale,) = stale_hands
        twins = [hand for hand in _ipoker_hands_numbered(cursor, ph, gamecode, gametype_ids) if hand.id != stale.id]
        if not twins:
            renames.append(Rename(stale, gamecode))
        elif len(twins) == 1 and twins[0].start_time == stale.start_time and twins[0].table == stale.table:
            duplicates.append(Duplicate(stale, twins[0].id, "session file"))
        else:
            ambiguous.append(f"session {session_code}: gamecode {gamecode} matches another hand: left alone")
    return duplicates, renames


def survey(db, sites: set[str], history_paths: list[Path]) -> Survey:
    ambiguous: list[str] = []
    gametype_ids = ipoker_gametype_ids(db, sites | {IPOKER_NETWORK})
    duplicates = {d.stale.id: d for d in find_identical_twins(db, gametype_ids, ambiguous)}
    renames: list[Rename] = []
    if history_paths:
        by_file, renames = find_by_session_code(db, gametype_ids, session_first_games(history_paths), ambiguous)
        # The files are the stronger evidence: they name the session code.
        duplicates.update({d.stale.id: d for d in by_file})
    return Survey(sorted(duplicates.values(), key=lambda d: d.stale.id), renames, ambiguous)


# ---------------------------------------------------------------------------
# Repairing.
# ---------------------------------------------------------------------------


def repair(db, found: Survey, *, commit: bool) -> dict[str, int]:
    """Remove the duplicates and renumber the lone stale hands, in one transaction.

    ``commit=False`` does all of it and rolls it back: the only way to learn
    what the real database says -- a foreign key nobody thought of, a table this
    schema does not have -- without writing to it.
    """
    ph = db.sql.query["placeholder"]
    if commit and found.duplicates:
        # Stored counters were built from the rows about to be deleted, and the
        # watermark cannot see a deletion. Dropping them first means no failure
        # below can leave counters that still include deleted hands; dropping
        # them needlessly only costs a recomputation on the next read. Not done
        # when rehearsing, which must write nothing.
        analytics_cache.invalidate_aggregates(db, "#440: iPoker duplicate hands removed")
    cursor = db.get_cursor()
    changed: dict[str, int] = {}
    try:
        for duplicate in found.duplicates:
            for table, statement in DELETE_BY_HAND:
                cursor.execute(_sql(statement, ph), (duplicate.stale.id,))
                if cursor.rowcount and cursor.rowcount > 0:
                    changed[table] = changed.get(table, 0) + cursor.rowcount
        for rename in found.renames:
            cursor.execute(_sql(RENAME_HAND, ph), (rename.gamecode, rename.hand.id))
            changed["Hands renumbered"] = changed.get("Hands renumbered", 0) + 1
        if found.duplicates:
            # In the same transaction as the deletions: a failure part-way
            # leaves neither removed hands nor a half-rebuilt cache behind.
            for table in REBUILT_CACHES:
                db.rebuild_cache(None, None, table, commit=False)
            changed["Caches rebuilt"] = len(REBUILT_CACHES)
    except Exception:
        db.connection.rollback()
        raise
    if commit:
        db.connection.commit()
    else:
        db.connection.rollback()
    return changed


# ---------------------------------------------------------------------------
# Backups and the command line.
# ---------------------------------------------------------------------------


def backup_sqlite(db, target: Path | None) -> Path:
    """Copy a SQLite database with the online backup API, which is consistent under WAL."""
    source = Path(db.db_path)
    if target is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = source.with_name(f"{source.name}.before-440-{stamp}")
    if target.exists():
        msg = f"refusing to overwrite an existing backup: {target}"
        raise SystemExit(msg)
    with sqlite3.connect(str(target)) as destination:
        db.connection.backup(destination)
    return target


def report(found: Survey) -> None:
    print(f"{len(found.duplicates)} duplicate hand(s), stale copy first:")
    for duplicate in found.duplicates:
        stale = duplicate.stale
        print(
            f"  {stale.site_hand_no} (row {stale.id}) duplicates row {duplicate.twin_id}"
            f"  {stale.table}  {stale.start_time}  [{duplicate.evidence}]"
        )
    print(f"\n{len(found.renames)} hand(s) stored only under their session code:")
    for rename in found.renames:
        hand = rename.hand
        print(f"  {hand.site_hand_no} -> {rename.gamecode} (row {hand.id})  {hand.table}  {hand.start_time}")
    if found.ambiguous:
        print("\nLeft alone:")
        for line in found.ambiguous:
            print(f"  {line}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="HUD_config.xml to read the database from (default: the configured one)")
    parser.add_argument(
        "--hh-dir",
        action="append",
        default=[],
        type=Path,
        help="an iPoker hand history file or directory; repeatable",
    )
    # Mutually exclusive: "--apply --rehearse" would otherwise commit, the
    # opposite of what the person typing --rehearse asked for.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write; without it nothing is changed")
    mode.add_argument("--rehearse", action="store_true", help="run the repair and roll it back")
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

    found = survey(db, ipoker_sites(config), args.hh_dir)
    report(found)
    if not (found.duplicates or found.renames):
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

    changed = repair(db, found, commit=args.apply)
    print("\nChanged:" if args.apply else "\nWould change (rolled back):")
    for table, count in sorted(changed.items()):
        print(f"  {count:>5}  {table}")
    if found.duplicates:
        print(
            "\nHudCache, CardsCache and PositionsCache were rebuilt from the hands. SessionsCache and "
            "TourneysCache have no rebuild and still count each removed hand once more."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
