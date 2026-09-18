"""Inspect the plan and cost of an analytics query against your database.

The engine (#297) compiles a stat to SQL; this runs the backend's EXPLAIN,
times the statement and reports the rows that came back, so an index or a
filter can be judged on a real plan instead of on faith:

    python tools/explain_analytics_query.py --all
    python tools/explain_analytics_query.py --definition fold_to_cbet_flop --plans
    python tools/explain_analytics_query.py --metric fold_frequency --filter street=flop \\
        --filter situation=facing_cbet --group-by position

Nothing is written: EXPLAIN ANALYZE executes the statement, so every profile
runs inside a transaction that is rolled back.

PostgreSQL gives the richest answer (actual rows, buffers); SQLite reports
whether each step used an index, which is what its planner fixes; MySQL gets a
plain EXPLAIN.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_definitions as definitions  # noqa: E402
from fpdb_3_legacy import analytics_profiling as profiling  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def _parse_filters(pairs: list[str]) -> dict[str, object]:
    """``k=v`` pairs to a filter dict, with a little type inference."""
    filters: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--filter needs key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        value: object = raw
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        elif "," in raw:
            value = raw.split(",")
        filters[key.strip()] = value
    return filters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--all", action="store_true", help="profile every bundled definition")
    parser.add_argument("--definition", action="append", default=[], help="definition name (repeatable)")
    parser.add_argument("--metric", default=None, help="a metric, for an ad-hoc query")
    parser.add_argument("--filter", action="append", default=[], help="ad-hoc filter key=value (repeatable)")
    parser.add_argument("--group-by", dest="group_by", action="append", default=[], help="dimension (repeatable)")
    parser.add_argument("--plans", action="store_true", help="print the full plans, not just the findings")
    args = parser.parse_args()

    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        profiles = []
        if args.all or args.definition:
            registry = definitions.get_registry()
            chosen = registry.all() if args.all else [registry.resolve(name) for name in args.definition]
            profiles.extend(profiling.profile_definitions(db, chosen))
        if args.metric:
            from fpdb_3_legacy.analytics_query import Query

            query = Query(metric=args.metric, filters=_parse_filters(args.filter), group_by=tuple(args.group_by))
            profiles.append(profiling.profile_analytics_query(db, query, name="ad-hoc"))
        if not profiles:
            parser.error("nothing to explain: pass --all, --definition or --metric")
        print(profiling.format_profiles(profiles, plans=args.plans))
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
