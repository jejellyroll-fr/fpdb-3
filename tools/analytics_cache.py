"""Inspect or invalidate the analytics aggregate cache (#304).

The cache keeps additive query counters current by scanning only the hands
that arrived since the last refresh. Its watermarks live in ``AnalyticsMeta``
and its rows in ``AnalyticsAggregates``; both are derived, so this tool only
reads them -- except for ``--invalidate``, which drops them.

    python tools/analytics_cache.py --stats
    python tools/analytics_cache.py --invalidate "reimported hands"

Invalidate after anything that moves or reuses hand ids (a delete, a
reimport) or that changes the player dimension (an alias merge): the
watermark cannot see either, so the next read would otherwise add new hands
to counters built over the old ones.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_cache  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--stats", action="store_true", help="print the cache's version, rows and watermarks")
    parser.add_argument("--invalidate", metavar="REASON", default=None, help="drop every cached row and watermark")
    args = parser.parse_args()

    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.invalidate is not None:
            removed = analytics_cache.invalidate_aggregates(db, args.invalidate)
            print(f"invalidated {removed} cached row(s): {args.invalidate}")
        if args.stats or args.invalidate is None:
            stats = analytics_cache.aggregate_stats(db)
            print(f"version: {stats.version} (current {analytics_cache.ANALYTICS_CACHE_VERSION})")
            print(f"rows: {stats.rows} across {stats.queries} cached quer{'y' if stats.queries == 1 else 'ies'}")
            for key, watermark in sorted(stats.watermarks.items()):
                print(f"  {key[:12]}… watermark {watermark}")
            print(f"cacheable metrics: {', '.join(analytics_cache.cache_metrics())}")
            print(f"not cached (means cannot be combined): {', '.join(sorted(analytics_cache.NON_CACHEABLE_METRICS))}")
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
