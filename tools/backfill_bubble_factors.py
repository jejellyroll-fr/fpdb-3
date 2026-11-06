"""Compute the stored bubble factors for tournaments already in the database (#446).

The study pack's bubble factor bands read ``ActionBubbleFactors``. An import
fills it for the tournaments it touches, and the payouts dialog for the one it
changes; this fills it for everything imported before either existed.

    python tools/backfill_bubble_factors.py
    python tools/backfill_bubble_factors.py --tourney 42

The rows are derived: running it again replaces them. Only sit-and-gos and
Spins with a known payout structure get any (see ``fpdb_3_legacy/bubble_factors.py``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import bubble_factors  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--tourney", type=int, action="append", help="only this tournament id (repeatable)")
    args = parser.parse_args()

    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.tourney:
            stored = bubble_factors.refresh_tourneys(db, args.tourney)
        else:
            stored = bubble_factors.refresh_all(db)
        print(f"{stored} preflop decision(s) priced")
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
