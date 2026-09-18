#!/usr/bin/env python3
"""What a filtered population was holding when it acted (#302).

    python tools/hand_composition.py --filter primary_situation=cbet
    python tools/hand_composition.py --dimension nutness --filter street=flop
    python tools/hand_composition.py --dimension draw --filter hero=true
    python tools/hand_composition.py --dimension made_hand --as-of face_cbet --json
    python tools/hand_composition.py --dimension nutness --hands near_nuts
    python tools/hand_composition.py --dimensions        # every dimension, with its categories

The population is the query engine's: the same ``--filter`` names, the same
semantics. Every count comes from the stored hand states (#302), so a category
that was never classified -- no postflop board, or cards nobody showed -- is
reported as its own number and never spread over the categories that were.
Nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import hand_state_composition as composition  # noqa: E402
from fpdb_3_legacy.analytics_query import FILTERS, Query  # noqa: E402
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
        if key.strip() not in FILTERS:
            raise SystemExit(f"unknown --filter {key.strip()!r}; known: {sorted(FILTERS)}")
        filters[key.strip()] = value
    return filters


def _as_of(filters: dict[str, Any], situation: str | None) -> dict[str, Any]:
    """``--as-of`` names the decision a state is read at, as a filter."""
    if situation:
        filters = {**filters, "primary_situation": [situation]}
    return filters


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--filter", action="append", default=[], help="filter key=value (repeatable)")
    parser.add_argument("--dimension", default="made_hand", help="what to compose the population by")
    parser.add_argument("--as-of", dest="as_of", default=None, help="narrow to one named situation")
    parser.add_argument("--min-sample", dest="min_sample", type=int, default=0, help="flag rows below this many decisions")
    parser.add_argument("--limit", type=int, default=None, help="rows to print (the population is unchanged)")
    parser.add_argument("--hands", default=None, help="list the hands behind one category and exit")
    parser.add_argument("--hand-limit", dest="hand_limit", type=int, default=50)
    parser.add_argument("--sql", action="store_true", help="print the compiled statements and exit")
    parser.add_argument("--json", action="store_true", help="print the composition as JSON")
    parser.add_argument("--dimensions", action="store_true", help="print the dimensions and exit")
    return parser.parse_args()


def _print_dimensions() -> int:
    for spec in composition.DIMENSIONS.values():
        adds_up = "rows add up" if spec.kind == "partition" else (
            "rows overlap" if spec.kind == "multi" else "one bucket is a real answer"
        )
        print(f"{spec.name} ({spec.label}): {adds_up}")
        if spec.none_means:
            print(f"  a missing value means {spec.none_means}")
    print()
    for name, values in composition.categories().items():
        print(f"{name}: {', '.join(values)}")
    return 0


def main() -> int:
    args = _parse_args()
    if args.dimensions:
        return _print_dimensions()
    if args.dimension not in composition.DIMENSIONS:
        raise SystemExit(
            f"unknown --dimension {args.dimension!r}; known: {sorted(composition.DIMENSIONS)}",
        )

    query = Query(metric="opportunities", filters=_as_of(_parse_filters(args.filter), args.as_of))
    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.hands is not None:
            key = None if args.hands in ("", "-", "none") else args.hands
            try:
                hand_ids = composition.compose_hands(db, args.dimension, key, query, limit=args.hand_limit)
            except ValueError as exc:
                print(f"refused: {exc}", file=sys.stderr)
                return 2
            print(f"hands behind {args.dimension}={key!r} ({len(hand_ids)}):")
            print(f"  {', '.join(str(hand) for hand in hand_ids)}")
            return 0

        report = composition.compose(db, query, args.dimension, min_sample=args.min_sample)
        if args.sql:
            for compiled in report.compiled:
                print(f"-- {compiled.description}")
                print(compiled.sql)
                print(f"-- params: {list(compiled.params)}")
            return 0
        if args.json:
            print(json.dumps(report.as_dict(), indent=2, default=str))
            return 0
        print(report.render(limit=args.limit))
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
