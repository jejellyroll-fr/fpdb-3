"""Refile the ACR/WPN cash hands the converter stored under the wrong game type.

The current ACR hand-history format ("Hand #... - Holdem(No Limit) - $0.01/$0.02
- ... UTC") was read with two mistakes, fixed in WinningToFpdb:

* the "$" of the blinds was matched but not captured, so every real-money cash
  hand of this format was stored as play money (currency ``play``);
* the "(Cap)" and "(Short)" of the table name were never read, so cap and short
  tables were stored as ``regular``.

The hands themselves are right; only their Gametypes row is wrong, and a
re-import does not fix it -- the duplicate check finds each hand by its site
and hand number and skips it. This tool moves each hand to the game type a
fresh import gives it.

A play-money hand is told from a real-money one by its file name first (ACR
names a real-money file "... CUR-REAL ..."), then by its table: the play-money
tables of the old format, the only ones seen, are named "PM ...". Real-money
hands of the old format were never affected and are left alone, as are
tournaments.

When every hand of a game type moves to the same corrected one and no such game
type exists yet, the row is corrected in place and the caches, keyed by its id,
stay valid. Otherwise the hands move to the corrected game type and the hand
caches are rebuilt from them.

    python tools/repair_wpn_cash_gametypes.py              # report only
    python tools/repair_wpn_cash_gametypes.py --rehearse   # run it, then roll back
    python tools/repair_wpn_cash_gametypes.py --apply      # write

``--apply`` copies a SQLite database next to itself first (or to ``--backup``).
PostgreSQL and MySQL cannot be copied from here: back the database up with the
server's own tools, then pass ``--i-have-a-backup``.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_cache  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402
from fpdb_3_legacy.WinningToFpdb import Winning  # noqa: E402
from tools.cleanup_ipoker_anon_players import _sql  # noqa: E402
from tools.repair_session_gametypes import backup_sqlite  # noqa: E402

# Every column of a Gametypes row but its id, in the order of the
# "insertGameTypes" query.
GAMETYPE_COLUMNS = (
    "siteId",
    "currency",
    "type",
    "base",
    "category",
    "limitType",
    "hiLo",
    "mix",
    "smallBlind",
    "bigBlind",
    "smallBet",
    "bigBet",
    "maxSeats",
    "ante",
    "buyinType",
    "fast",
    "newToGame",
    "homeGame",
    "split",
)
# The columns "getGametypeNL" looks a game type up by, in its order.
LOOKUP_COLUMNS = (
    "siteId",
    "type",
    "category",
    "limitType",
    "currency",
    "mix",
    "smallBlind",
    "bigBlind",
    "maxSeats",
    "ante",
    "buyinType",
    "fast",
    "newToGame",
    "homeGame",
    "split",
)

SELECT_SITES = "SELECT id, name FROM Sites"
SELECT_RING_GAMETYPES = (
    "SELECT id, siteId, currency, type, base, category, limitType, hiLo, mix, smallBlind, bigBlind, "
    "smallBet, bigBet, maxSeats, ante, buyinType, fast, newToGame, homeGame, split "
    "FROM Gametypes WHERE siteId = %s AND type = 'ring'"
)
SELECT_RING_HANDS = (
    "SELECT h.id, h.gametypeId, h.tableName, h.siteHandNo, f.file "
    "FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId LEFT JOIN Files f ON f.id = h.fileId "
    "WHERE g.siteId = %s AND g.type = 'ring' ORDER BY h.id"
)
UPDATE_GAMETYPE = "UPDATE Gametypes SET currency = %s, buyinType = %s WHERE id = %s"
MOVE_HAND = "UPDATE Hands SET gametypeId = %s WHERE id = %s"

# ACR file names carry the money type: "... CUR-REAL OND-F BUYIN-0.txt".
RE_FILE_CURRENCY = re.compile(r"\bCUR-(?P<CUR>[A-Z]+)\b")


@dataclass(frozen=True)
class Misfiled:
    hand_id: int
    site_hand_no: int
    table: str
    stored: int
    target: tuple  # the corrected row, in GAMETYPE_COLUMNS order


@dataclass
class Survey:
    gametypes: dict[int, tuple] = field(default_factory=dict)
    hands_per_gametype: Counter = field(default_factory=Counter)
    misfiled: list[Misfiled] = field(default_factory=list)

    @property
    def writes(self) -> bool:
        return bool(self.misfiled)


def is_real_money(table: str, file_name: str | None) -> bool:
    """Whether a hand stored as play money was played for real money."""
    if file_name:
        marker = RE_FILE_CURRENCY.search(Path(file_name).name)
        if marker:
            return marker.group("CUR") == "REAL"
    return not table.startswith("PM ")


def corrected(row: tuple, table: str, file_name: str | None) -> tuple:
    """The game type a fresh import gives this hand, in GAMETYPE_COLUMNS order."""
    values = dict(zip(GAMETYPE_COLUMNS, row, strict=True))
    if values["currency"] == "play" and is_real_money(table, file_name):
        values["currency"] = "USD"
    if values["buyinType"] == "regular":
        buyin_type = Winning.re_buyinType.search(table)
        if buyin_type:
            values["buyinType"] = Winning.buyin[buyin_type.group("BUYINTYPE").upper()]
    return tuple(values[column] for column in GAMETYPE_COLUMNS)


def _fetch(db, statement: str, params: tuple = ()) -> list:
    cursor = db.get_cursor()
    cursor.execute(_sql(statement, db.sql.query["placeholder"]), params)
    return cursor.fetchall()


def wpn_sites(config) -> set[str]:
    """Site names whose hands the WPN converter reads: every skin of the network."""
    return {name for name, hhc in config.hhcs.items() if hhc.converter == "WinningToFpdb"}


def survey(db, sites: set[str]) -> Survey:
    """Find the ring hands whose game type a fresh import would not give them."""
    found = Survey()
    site_ids = sorted(int(site_id) for site_id, name in _fetch(db, SELECT_SITES) if name in sites)
    for site_id in site_ids:
        for row in _fetch(db, SELECT_RING_GAMETYPES, (site_id,)):
            found.gametypes[int(row[0])] = tuple(row[1:])
        for hand_id, gametype, table, site_hand_no, file_name in _fetch(db, SELECT_RING_HANDS, (site_id,)):
            gametype = int(gametype)
            found.hands_per_gametype[gametype] += 1
            row = found.gametypes[gametype]
            target = corrected(row, str(table or ""), file_name)
            if target != row:
                found.misfiled.append(Misfiled(int(hand_id), int(site_hand_no), str(table), gametype, target))
    return found


def _lookup(db, target: tuple) -> int | None:
    values = dict(zip(GAMETYPE_COLUMNS, target, strict=True))
    rows = _fetch(db, db.sql.query["getGametypeNL"], tuple(values[column] for column in LOOKUP_COLUMNS))
    return int(rows[0][0]) if rows else None


def _find_or_create(db, target: tuple) -> int:
    existing = _lookup(db, target)
    if existing is not None:
        return existing
    query = _sql(db.sql.query["insertGameTypes"], db.sql.query["placeholder"])
    return int(db.insert_returning_id(db.get_cursor(), query, target))


def _write(db, found: Survey, changed: dict[str, int]) -> bool:
    """Apply the fixes; returns whether hands changed game type id."""
    ph = db.sql.query["placeholder"]
    cursor = db.get_cursor()
    by_gametype: dict[int, list[Misfiled]] = defaultdict(list)
    for fix in found.misfiled:
        by_gametype[fix.stored].append(fix)

    moved = False
    for stored, fixes in sorted(by_gametype.items()):
        targets = {fix.target for fix in fixes}
        whole_row = len(fixes) == found.hands_per_gametype[stored] and len(targets) == 1
        if whole_row and _lookup(db, next(iter(targets))) is None:
            target = dict(zip(GAMETYPE_COLUMNS, next(iter(targets)), strict=True))
            cursor.execute(_sql(UPDATE_GAMETYPE, ph), (target["currency"], target["buyinType"], stored))
            changed["Gametypes corrected in place"] += 1
            changed["Hands refiled"] += len(fixes)
            continue
        # The importer never stores a hand twice on one site, so no copy of a
        # misfiled hand waits under its corrected game type.
        for fix in fixes:
            cursor.execute(_sql(MOVE_HAND, ph), (_find_or_create(db, fix.target), fix.hand_id))
            moved = True
            changed["Hands refiled"] += 1
            changed["Hands moved to another gametype"] += 1
    return moved


def repair(db, found: Survey, *, commit: bool) -> dict[str, int]:
    """Write the fixes in one transaction; ``commit=False`` rolls it back."""
    if commit and found.writes:
        # Stored analytics counters are split by currency and game type.
        analytics_cache.invalidate_aggregates(db, "WPN cash hands refiled by currency and buy-in type")
    changed: dict[str, int] = defaultdict(int)
    try:
        if _write(db, found, changed):
            # The caches are keyed by game type id: rebuild them from the
            # refiled hands, in the same transaction.
            changed["Caches rebuilt"] = len(db.rebuild_hand_caches(commit=False))
    except Exception:
        db.connection.rollback()
        raise
    if commit:
        db.connection.commit()
    else:
        db.connection.rollback()
    return dict(changed)


def report(found: Survey) -> None:
    print(f"WPN cash hands misfiled: {len(found.misfiled)}")
    groups: Counter = Counter()
    for fix in found.misfiled:
        before = dict(zip(GAMETYPE_COLUMNS, found.gametypes[fix.stored], strict=True))
        after = dict(zip(GAMETYPE_COLUMNS, fix.target, strict=True))
        groups[(fix.table, before["currency"], after["currency"], before["buyinType"], after["buyinType"])] += 1
    for (table, old_cur, new_cur, old_buyin, new_buyin), count in sorted(groups.items()):
        print(f"  {count:>6}  {table}: {old_cur}/{old_buyin} -> {new_cur}/{new_buyin}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="HUD_config.xml to read the database from (default: the configured one)")
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

    found = survey(db, wpn_sites(config))
    report(found)
    if not found.writes:
        print("\nNothing to repair.")
        return 0

    if not (args.apply or args.rehearse):
        print("\nDry run: nothing was changed. Re-run with --rehearse to try it, --apply to write.")
        return 0

    if args.apply:
        if db.backend == db.SQLITE:
            target = args.backup
            if target is None:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                source = Path(db.db_path)
                target = source.with_name(f"{source.name}.before-wpn-repair-{stamp}")
            print(f"\nBackup: {backup_sqlite(db, target)}")
        elif not args.i_have_a_backup:
            print("\nBack the database up with the server's own tools, then re-run with --i-have-a-backup.")
            return 2

    changed = repair(db, found, commit=args.apply)
    print("\nChanged:" if args.apply else "\nWould change (rolled back):")
    for what, count in sorted(changed.items()):
        print(f"  {count:>5}  {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
