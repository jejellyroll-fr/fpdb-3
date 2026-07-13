#!/usr/bin/env python3
from __future__ import annotations

"""Maintenance script: find (and optionally delete) draw-game hands whose stored
starting hand was corrupted by the historical ``addShownCards`` ordering bug.

Background
----------
Before the fix in ``Hand.DrawHand.__init__`` (readShowdownActions was called
before readAction), a player's showdown holding could overwrite the *original*
dealt cards on the DEAL street. The corrupted cards were then written to the
``HandsPlayers.card1..card20`` columns, so the hand replayer showed an
incomplete / wrong starting hand for draw games.

The parser is now fixed, but rows already in the database keep the bad cards.
This script locates the affected hands so they can be re-imported.

Detection
---------
* Default: the hero (``HandsPlayers.seatNo == Hands.heroSeat``) has FEWER real
  cards in the DEAL slots than the game's hand size. The hero always sees their
  own full starting hand, so an incomplete DEAL holding is a reliable corruption
  signature (this is the visible "starting hand not full" bug).
* ``--all``: superset — every draw hand where the hero reached showdown. Use
  this to also catch the subtler case where DEAL was overwritten with a *full*
  but wrong 5-card holding (undetectable by card count alone).

Safety
------
* Dry-run by default: only reports. Pass ``--delete`` to remove rows.
* Deletion is transactional and FK-safe (children first, then ``Hands``).
* Deletion does NOT adjust the HUD cache. After re-importing, rebuild it
  (Maintenance → Rebuild HUD cache, or Database.rebuild_cache).

Usage
-----
    uv run python fix_draw_starting_hands.py                 # report (precise)
    uv run python fix_draw_starting_hands.py --all           # report (superset)
    uv run python fix_draw_starting_hands.py --delete        # delete precise set
    uv run python fix_draw_starting_hands.py --hand-id 1234  # inspect one hand
"""

import argparse
import logging
import os
import sys

logging.disable(logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Card
import Configuration
import Database

# Per-hand tables that reference Hands(id); delete children before the parent.
CHILD_TABLES = [
    "RawHands",
    "Boards",
    "HandsActions",
    "HandsCashout",
    "HandsPots",
    "HandsShowdown",
    "HandsStove",
    "HandsPlayers",
]


def draw_categories() -> list[str]:
    """All draw-game categories known to Card.games."""
    return [cat for cat, game in Card.games.items() if game[0] == "draw"]


def deal_handsize(category: str) -> int:
    """Number of cards dealt on the DEAL street for a category (4 for badugi, else 5)."""
    deal_range = Card.games[category][5][0]  # (start, end)
    return deal_range[1] - deal_range[0]


def _ph(db) -> str:
    return db.sql.query["placeholder"]


def find_affected(db, *, include_all: bool, only_hand_id: int | None) -> list[dict]:
    """Return a list of affected hand descriptors."""
    cats = draw_categories()
    if not cats:
        return []

    ph = _ph(db)
    card_cols = ", ".join(f"hp.card{i}" for i in range(1, 11))
    placeholders = ", ".join([ph] * len(cats))

    where = [f"g.category IN ({placeholders})"]
    params: list = list(cats)
    if only_hand_id is not None:
        where.append(f"h.id = {ph}")
        params.append(only_hand_id)

    sql = f"""
        SELECT h.id, h.siteHandNo, g.category, hp.seatNo, hp.sawShowdown,
               {card_cols}, f.file
        FROM Hands h
        JOIN Gametypes g ON h.gametypeId = g.id
        JOIN HandsPlayers hp ON hp.handId = h.id AND hp.seatNo = h.heroSeat
        LEFT JOIN Files f ON h.fileId = f.id
        WHERE {' AND '.join(where)}
        ORDER BY h.id
    """

    c = db.get_cursor()
    c.execute(sql, tuple(params))
    rows = c.fetchall()

    affected: list[dict] = []
    for row in rows:
        hand_id, site_hand_no, category, _seat, saw_sd = row[0], row[1], row[2], row[3], row[4]
        deal_cards = row[5:10]      # card1..card5
        draw_cards = row[10:15]     # card6..card10
        source_file = row[15]

        size = deal_handsize(category)
        deal_present = sum(1 for c_ in deal_cards[:size] if c_)
        draw_present = sum(1 for c_ in draw_cards if c_)

        if include_all:
            # Superset: any draw hand where the hero saw showdown.
            is_affected = bool(saw_sd)
            reason = "hero saw showdown (superset)"
        else:
            # Precise: hero's starting hand is incomplete.
            is_affected = deal_present < size
            reason = f"DEAL has {deal_present}/{size} cards"

        if is_affected:
            affected.append({
                "hand_id": hand_id,
                "site_hand_no": site_hand_no,
                "category": category,
                "deal_present": deal_present,
                "deal_size": size,
                "draw_present": draw_present,
                "file": source_file,
                "reason": reason,
            })
    return affected


def delete_hands(db, hand_ids: list[int]) -> None:
    """Delete every per-hand row for the given hand ids, FK-safe, in one transaction."""
    if not hand_ids:
        return
    ph = _ph(db)
    c = db.get_cursor()
    try:
        in_list = ", ".join([ph] * len(hand_ids))
        params = tuple(hand_ids)
        for table in CHILD_TABLES:
            try:
                c.execute(f"DELETE FROM {table} WHERE handId IN ({in_list})", params)
            except Exception as e:  # noqa: BLE001 - table may not exist on older schemas
                print(f"  ! skipped {table}: {e}")
        c.execute(f"DELETE FROM Hands WHERE id IN ({in_list})", params)
        db.commit()
    except Exception:
        db.rollback()
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true",
                        help="Superset mode: flag every draw hand where the hero saw showdown.")
    parser.add_argument("--delete", action="store_true",
                        help="Actually delete the affected hands (default is dry-run report).")
    parser.add_argument("--hand-id", type=int, default=None,
                        help="Restrict to a single Hands.id (for inspection).")
    parser.add_argument("--config", default=None, help="Path to HUD_config.xml (optional).")
    args = parser.parse_args(argv)

    config = Configuration.Config(file=args.config) if args.config else Configuration.Config()
    db = Database.Database(config)

    affected = find_affected(db, include_all=args.all, only_hand_id=args.hand_id)

    mode = "SUPERSET (all showdown draw hands)" if args.all else "PRECISE (incomplete starting hand)"
    print(f"Detection mode: {mode}")
    print(f"Draw categories scanned: {', '.join(draw_categories())}")
    print(f"Affected hands found: {len(affected)}\n")

    if not affected:
        print("Nothing to do. ✅")
        return 0

    files: set[str] = set()
    for a in affected:
        f = a["file"] or "<unknown source file>"
        files.add(f)
        print(f"  hand {a['hand_id']:>8}  #{a['site_hand_no']:<16} {a['category']:<10} "
              f"deal={a['deal_present']}/{a['deal_size']} draw={a['draw_present']}  [{a['reason']}]")
        print(f"           file: {f}")

    print(f"\nSource files to re-import ({len(files)}):")
    for f in sorted(files):
        print(f"  {f}")

    if not args.delete:
        print("\nDRY-RUN — no changes made. Re-run with --delete to remove these hands,")
        print("then re-import the files above and rebuild the HUD cache.")
        return 0

    print(f"\nDeleting {len(affected)} hand(s)...")
    delete_hands(db, [a["hand_id"] for a in affected])
    print("Done. ✅")
    print("\nNEXT STEPS:")
    print("  1. Re-import the source files listed above (Bulk Import).")
    print("  2. Rebuild the HUD cache (Maintenance → Rebuild HUD cache),")
    print("     since deletion does not adjust aggregate stats.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
