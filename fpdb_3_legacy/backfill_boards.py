#!/usr/bin/env python3
"""Backfill run-it-twice/three boards for hands already imported in the database.

Hands imported before run-it boards were stored only have the first board (in
Hands.boardcard1-5) and no Boards rows, so the replayer / hand viewer cannot
show the extra runs. This tool re-parses hand-history files, recovers every run
board, matches each hand to its existing DB id by (siteHandNo, siteId), sets the
Hands.runItTwice flag and (re)writes the Boards rows.

Usage:
    python -m fpdb_3_legacy.backfill_boards PATH [PATH ...] [--commit]
                                            [--config HUD_config.xml]

PATH may be a file or a directory (scanned recursively). Without --commit the
run is a dry run that only reports what it would write.
"""

from __future__ import annotations

import argparse
import os

from fpdb_3_legacy import Card, Configuration, Database, IdentifySite
from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as get_ipoker_parser_class_for_path
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.parser_registry import get_parser_class

log = get_logger("backfill_boards")

_HH_EXTENSIONS = (".txt", ".xml", ".hh", ".log")


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(_HH_EXTENSIONS):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def boards_from_hand(hand):
    """Build [[boardId, c1..c5], ...] for each run from the parsed hand."""
    try:
        runs = int(hand.runItTimes)
    except (TypeError, ValueError):
        runs = 0
    if runs < 2:
        return []
    streets = getattr(hand, "communityStreets", ["FLOP", "TURN", "RIVER"])
    boards = []
    for run in range(1, runs + 1):
        cards = []
        for street in streets:
            cards += hand.board.get(f"{street}{run}", [])
        cards = [*cards, "0x", "0x", "0x", "0x", "0x"]
        try:
            enc = [Card.encodeCard(c) for c in cards[:5]]
        except (IndexError, KeyError):
            enc = [0, 0, 0, 0, 0]
        boards.append([run, *enc])
    return boards


def _lookup_hand_ids(db, site_hand_no, site_id):
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    q = (
        "SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id "
        f"WHERE H.siteHandNo={placeholder} AND G.siteId={placeholder}"
    )
    try:
        key = int(site_hand_no)
    except (TypeError, ValueError):
        key = site_hand_no
    c.execute(q, (key, site_id))
    return [r[0] for r in c.fetchall()]


def backfill(paths, commit=False, config_file="HUD_config.xml", db=None):
    config = Configuration.Config(file=config_file)
    if db is None:
        db = Database.Database(config)
    idsite = IdentifySite.IdentifySite(config)
    placeholder = db.sql.query["placeholder"]
    store_q = db.sql.query["store_boards"].replace("%s", placeholder)

    stats = {"files": 0, "files_skipped": 0, "runit_hands": 0, "matched": 0, "boards": 0}

    for path in iter_files(paths):
        try:
            idsite.processFile(path)
            fobj = idsite.get_fobj(path)
        except Exception as e:  # noqa: BLE001
            log.debug(f"identify failed {path}: {e}")
            fobj = None
        if not fobj or not getattr(fobj, "site", None):
            stats["files_skipped"] += 1
            continue

        filter_name = fobj.site.filter_name
        obj = get_parser_class(filter_name)
        if filter_name == "iPoker":
            obj = get_ipoker_parser_class_for_path(path)
        if not callable(obj):
            stats["files_skipped"] += 1
            continue
        try:
            hhc = obj(config, in_path=path, autostart=False, sitename=fobj.site.name)
            hhc.start()
        except Exception as e:  # noqa: BLE001
            log.debug(f"parse failed {path}: {e}")
            stats["files_skipped"] += 1
            continue
        stats["files"] += 1

        for hand in hhc.getProcessedHands():
            boards = boards_from_hand(hand)
            if not boards:
                continue
            stats["runit_hands"] += 1
            site_id = getattr(hand, "siteId", None)
            site_hand_no = getattr(hand, "handid", None)
            if site_id is None or site_hand_no is None:
                continue
            for dbid in _lookup_hand_ids(db, site_hand_no, site_id):
                stats["matched"] += 1
                stats["boards"] += len(boards)
                if commit:
                    c = db.get_cursor()
                    c.execute(f"UPDATE Hands SET runItTwice={placeholder} WHERE id={placeholder}", (True, dbid))
                    c.execute(f"DELETE FROM Boards WHERE handId={placeholder}", (dbid,))
                    for b in boards:
                        c.execute(store_q, [dbid, *b])

    if commit:
        db.commit()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill run-it boards from hand-history files.")
    parser.add_argument("paths", nargs="+", help="Hand-history file(s) or directory(ies).")
    parser.add_argument("--commit", action="store_true", help="Write to the DB (default: dry run).")
    parser.add_argument("--config", default="HUD_config.xml", help="fpdb config file.")
    args = parser.parse_args(argv)

    stats = backfill(args.paths, commit=args.commit, config_file=args.config)
    mode = "WROTE" if args.commit else "DRY RUN (use --commit to write)"
    print(
        f"[{mode}] files={stats['files']} skipped={stats['files_skipped']} "
        f"runit_hands={stats['runit_hands']} matched={stats['matched']} boards={stats['boards']}",
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
