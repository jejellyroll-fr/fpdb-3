#!/usr/bin/env python3
"""Backfill the HandsShowdown table for hands already imported in the database.

The database does not keep the raw hand-history text, so showdown combinations
parsed from the original files are not available for hands that were imported
before the HandsShowdown feature existed. This tool re-parses hand-history
files, recovers the combination text (and winning cards when the site prints
them), matches each hand to its existing DB id by (siteHandNo, siteId) and
writes HandsShowdown rows, so the replayer can label/highlight the winning
combination for already-imported hands.

Usage:
    python -m fpdb_3_legacy.backfill_showdown PATH [PATH ...] [--commit]
                                             [--config HUD_config.xml]

PATH may be a file or a directory (scanned recursively). Without --commit the
run is a dry run that only reports what it would write.
"""

from __future__ import annotations

import argparse
import os

from fpdb_3_legacy import Configuration, Database, IdentifySite
from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as get_ipoker_parser_class_for_path
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.parser_registry import get_parser_class

log = get_logger("backfill_showdown")

_HH_EXTENSIONS = (".txt", ".xml", ".hh", ".log")


def iter_files(paths):
    """Yield every candidate hand-history file under the given paths."""
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(_HH_EXTENSIONS):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def _ensure_table(db) -> None:
    """Create HandsShowdown if a pre-existing DB does not have it yet."""
    try:
        c = db.get_cursor()
        c.execute(db.sql.query["createHandsShowdownTable"])
        db.commit()
    except Exception:  # noqa: BLE001 - table already exists: nothing to do.
        pass


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


def _player_ids_for_hand(db, db_hand_id):
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    c.execute(
        "SELECT p.name, hp.playerId FROM HandsPlayers hp JOIN Players p ON hp.playerId=p.id "
        f"WHERE hp.handId={placeholder}",
        (db_hand_id,),
    )
    return {name: pid for name, pid in c.fetchall()}


def _rows_for_hand(hand, pids, db_hand_id):
    sds = getattr(hand, "showdownStrings", {}) or {}
    wh = getattr(hand, "winningHand", {}) or {}
    rows = []
    for name in set(sds) | set(wh):
        pid = pids.get(name)
        if pid is None:
            continue
        combo = sds.get(name)
        cards = wh.get(name)
        cards_str = " ".join(cards) if cards else None
        if combo is None and cards_str is None:
            continue
        rows.append((db_hand_id, pid, combo, cards_str))
    return rows


def backfill(paths, commit=False, config_file="HUD_config.xml", db=None):
    """Backfill HandsShowdown. Returns a stats dict."""
    config = Configuration.Config(file=config_file)
    owns_db = db is None
    if owns_db:
        db = Database.Database(config)
    if hasattr(db, "ensure_feature_tables"):
        db.ensure_feature_tables()
    else:
        _ensure_table(db)
    idsite = IdentifySite.IdentifySite(config)
    placeholder = db.sql.query["placeholder"]
    insert_q = db.sql.query["store_hands_showdown"].replace("%s", placeholder)
    cashout_q = db.sql.query["store_hands_cashout"].replace("%s", placeholder)

    stats = {
        "files": 0,
        "hands_with_combo": 0,
        "matched_hands": 0,
        "rows": 0,
        "cashout_rows": 0,
        "files_skipped": 0,
    }

    for path in iter_files(paths):
        try:
            idsite.processFile(path)
            fobj = idsite.get_fobj(path)
        except Exception as e:  # noqa: BLE001 - unidentifiable file: skip.
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
        except Exception as e:  # noqa: BLE001 - parser failure on this file: skip.
            log.debug(f"parse failed {path}: {e}")
            stats["files_skipped"] += 1
            continue
        stats["files"] += 1

        for hand in hhc.getProcessedHands():
            sds = getattr(hand, "showdownStrings", {}) or {}
            wh = getattr(hand, "winningHand", {}) or {}
            cashouts = getattr(hand, "cashOutAmounts", {}) or {}
            fees = getattr(hand, "cashOutFees", {}) or {}
            if not sds and not wh and not cashouts:
                continue
            if sds or wh:
                stats["hands_with_combo"] += 1
            site_id = getattr(hand, "siteId", None)
            site_hand_no = getattr(hand, "handid", None)
            if site_id is None or site_hand_no is None:
                continue
            for dbid in _lookup_hand_ids(db, site_hand_no, site_id):
                pids = _player_ids_for_hand(db, dbid)
                rows = _rows_for_hand(hand, pids, dbid)
                co_rows = []
                for name in set(cashouts) | set(fees):
                    pid = pids.get(name)
                    if pid is None:
                        continue
                    amt = cashouts.get(name)
                    fee = fees.get(name)
                    co_rows.append(
                        [dbid, pid, str(amt) if amt is not None else None, str(fee) if fee is not None else None],
                    )
                if not rows and not co_rows:
                    continue
                if rows:
                    stats["matched_hands"] += 1
                    stats["rows"] += len(rows)
                stats["cashout_rows"] += len(co_rows)
                if commit:
                    c = db.get_cursor()
                    if rows:
                        c.execute(f"DELETE FROM HandsShowdown WHERE handId={placeholder}", (dbid,))
                        for row in rows:
                            c.execute(insert_q, row)
                    if co_rows:
                        c.execute(f"DELETE FROM HandsCashout WHERE handId={placeholder}", (dbid,))
                        for row in co_rows:
                            c.execute(cashout_q, row)

    if commit:
        db.commit()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill HandsShowdown from hand-history files.")
    parser.add_argument("paths", nargs="+", help="Hand-history file(s) or directory(ies).")
    parser.add_argument("--commit", action="store_true", help="Write to the DB (default: dry run).")
    parser.add_argument("--config", default="HUD_config.xml", help="fpdb config file.")
    args = parser.parse_args(argv)

    stats = backfill(args.paths, commit=args.commit, config_file=args.config)
    mode = "WROTE" if args.commit else "DRY RUN (use --commit to write)"
    print(
        f"[{mode}] files={stats['files']} skipped={stats['files_skipped']} "
        f"hands_with_combo={stats['hands_with_combo']} matched={stats['matched_hands']} "
        f"rows={stats['rows']} cashout_rows={stats['cashout_rows']}",
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
