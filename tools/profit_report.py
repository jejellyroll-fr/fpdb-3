"""Report the money of a filtered population, with its semantics spelled out (#300).

The query engine answers "how often"; this answers "for how much", and refuses
to answer the one question the data cannot support:

    python tools/profit_report.py --filter primary_situation=cbet --group-by sizing_bucket
    python tools/profit_report.py --filter role=aggressor --group-by street --min-sample 10
    python tools/profit_report.py --filter pot_type=three_bet --hand-ids
    python tools/profit_report.py --filter hero=true --json
    python tools/profit_report.py --semantics
    python tools/profit_report.py --metric immediate_action_ev   # the refusal, on purpose

Money is in cents, as everywhere in fpdb. ``--group-by`` splits the population;
the rows overlap when the split is by a decision attribute, and the report says
so rather than letting them be added up. Nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_profit as profit  # noqa: E402
from fpdb_3_legacy.analytics_query import DIMENSIONS, KNOWN_METRICS, Query  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def _parse_filters(pairs: list[str]) -> dict[str, Any]:
    """``k=v`` pairs to a filter dict, with a little type inference."""
    filters: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--filter needs key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        value: Any = raw
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        elif "," in raw:
            value = [part for part in raw.split(",") if part]
        elif raw.strip().lstrip("-").isdigit():
            value = int(raw)
        filters[key.strip()] = value
    return filters


def _parse_group(pairs: list[str]) -> tuple[str, ...]:
    """``--group-by`` values, comma separated or repeated, checked against the engine."""
    groups: list[str] = []
    for pair in pairs:
        groups.extend(part.strip() for part in pair.split(",") if part.strip())
    unknown = [name for name in groups if name not in DIMENSIONS]
    if unknown:
        raise SystemExit(f"unknown --group-by {unknown}; known: {sorted(DIMENSIONS)}")
    return tuple(groups)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--filter", action="append", default=[], help="filter key=value (repeatable)")
    parser.add_argument("--group-by", action="append", default=[], help="dimension to split by (repeatable)")
    parser.add_argument("--metric", default="total_profit", help="metric that defines the population")
    parser.add_argument("--rake", default="contributed", choices=sorted(profit.RAKE_ATTRIBUTIONS))
    parser.add_argument("--min-sample", dest="min_sample", type=int, default=0, help="flag rows below this many decisions")
    parser.add_argument("--hide-small", dest="hide_small", action="store_true", help="drop the flagged rows")
    parser.add_argument("--limit", type=int, default=None, help="rows to print (the population is unchanged)")
    parser.add_argument("--hand-ids", dest="hand_ids", action="store_true", help="list the hands behind the population")
    parser.add_argument("--sql", action="store_true", help="print the compiled statements and exit")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--semantics", action="store_true", help="print what each money figure means and exit")
    return parser.parse_args()


def _print_semantics() -> int:
    for spec in profit.semantics_catalog():
        state = "computable" if spec.computable else "NOT COMPUTABLE"
        print(f"{spec.name} ({spec.unit}, {state}): {spec.label}")
        print(f"  {spec.definition}")
        if spec.caveat:
            print(f"  caveat: {spec.caveat}")
    return 0


def main() -> int:
    args = _parse_args()
    if args.semantics:
        return _print_semantics()
    if args.metric == "immediate_action_ev":
        # The one figure the data cannot support: say why, from the one place
        # that knows, rather than printing a hand-level result under its name.
        try:
            profit.immediate_action_ev(Query(metric="total_profit"))
        except profit.NotComputable as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
    if args.metric not in KNOWN_METRICS:
        raise SystemExit(f"unknown --metric {args.metric!r}; known: {list(KNOWN_METRICS)}")

    query = Query(metric=args.metric, filters=_parse_filters(args.filter), group_by=_parse_group(args.group_by))
    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        report = profit.profit_report(db, query, rake=args.rake, min_sample=args.min_sample)
        if args.sql:
            for compiled in report.compiled:
                print(f"-- {compiled.description}")
                print(compiled.sql)
                print(f"-- params: {list(compiled.params)}")
            return 0
        if args.json:
            print(json.dumps(report.as_dict(), indent=2, default=str))
            return 0
        print(report.render(limit=args.limit, hide_small=args.hide_small))
        if args.hand_ids:
            print(f"  hands ({len(report.hand_ids)}): {', '.join(str(hand) for hand in report.hand_ids)}")
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
