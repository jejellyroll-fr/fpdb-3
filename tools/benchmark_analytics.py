"""Time the analytics query shapes, optionally on a synthesized dataset (#304).

    python tools/benchmark_analytics.py                       # time against the configured database
    python tools/benchmark_analytics.py --generate 100000 --repeats 5

``--generate N`` clones the richest hand in the database N times before
benchmarking, which is how a small development database becomes a
representative one. That writes to the configured database, so it is opt-in
and never runs by default.

The dataset is reproducible: every clone is derived from the same source hand,
so two runs at the same ``--generate`` produce databases with the same shape.
Latency targets are the ones recorded in docs/analytics-performance.md; the
report marks a run that misses one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_benchmark as benchmark  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--generate", type=int, default=0, metavar="N", help="clone the richest hand N times first (writes!)")
    parser.add_argument("--source-hand", type=int, default=None, help="hand id to clone; default is the richest")
    parser.add_argument("--repeats", type=int, default=3, help="timed runs per query shape")
    args = parser.parse_args()

    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.generate:
            print(f"Cloning the source hand {args.generate} time(s) into the configured database…")
            created = benchmark.synthesize_hands(db, args.generate, args.source_hand)
            print(f"created {created} hand(s)")
        results = benchmark.benchmark_queries(db, repeats=args.repeats)
        print(benchmark.format_results(results))
        missed = [result.name for result in results if not result.within_target]
        if missed:
            print(f"\nover target: {', '.join(missed)}")
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
