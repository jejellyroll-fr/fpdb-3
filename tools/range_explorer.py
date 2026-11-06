"""Explore a filtered Hold'em range on the 13x13 grid (#301).

The grid answers "with which hands did this population do this?", one cell per
starting-hand class. Cells come from the query engine grouped by class, so a
cell and its hands are the same population:

    python tools/range_explorer.py --filter hero=true --view sample
    python tools/range_explorer.py --metric raise_frequency --filter pot_type=three_bet --view frequency
    python tools/range_explorer.py --filter position=btn --metric fold_frequency --view frequency --min-sample 10
    python tools/range_explorer.py --filter hero=true --view profit
    python tools/range_explorer.py --filter hero=true --cell AA --hand-ids
    python tools/range_explorer.py --filter hero=true --json
    python tools/range_explorer.py --views

Money is in cents, as everywhere. The hands of players who never showed are
never guessed: they are the ``xx`` line, kept apart from the 169 classes. A
population that is not Hold'em is refused, because two cards of an Omaha hand
are not a starting hand. Nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import holdem_classes as hc  # noqa: E402
from fpdb_3_legacy import holdem_ranges as ranges  # noqa: E402
from fpdb_3_legacy.analytics_query import KNOWN_METRICS, Query  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402


def _parse_pairs(pairs: list[str], option: str) -> dict[str, Any]:
    """``k=v`` pairs to a dict, with a little type inference."""
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"{option} needs key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        value: Any = raw
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        elif "," in raw:
            value = [part for part in raw.split(",") if part]
        elif raw.strip().lstrip("-").isdigit():
            value = int(raw)
        out[key.strip()] = value
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--filter", action="append", default=[], help="filter key=value (repeatable)")
    parser.add_argument("--numerator", action="append", default=[], help="numerator key=value (repeatable)")
    parser.add_argument("--metric", default="opportunities", help="metric that defines the population")
    parser.add_argument("--view", default=ranges.DEFAULT_VIEW, choices=sorted(ranges.METRICS), help="what to show per cell")
    parser.add_argument("--min-sample", dest="min_sample", type=int, default=0, help="flag cells below this many decisions")
    parser.add_argument("--hide-small", dest="hide_small", action="store_true", help="blank the flagged cells")
    parser.add_argument("--cell", action="append", default=[], help="one cell (or several, comma separated) to inspect")
    parser.add_argument("--hand-ids", dest="hand_ids", action="store_true", help="list the hands behind --cell")
    parser.add_argument("--json", action="store_true", help="print the matrix as JSON")
    parser.add_argument("--views", action="store_true", help="print what each grid view means and exit")
    return parser.parse_args()


def _print_views() -> int:
    for spec in ranges.METRICS.values():
        print(f"{spec.name} ({spec.unit}): {spec.label}")
        print(f"  {spec.definition}")
    return 0


def _inspect(args: argparse.Namespace, db: Database, query: Query) -> int:
    """Print a cell's raw counts, and its hands when asked."""
    requested: list[str] = []
    for entry in args.cell:
        requested.extend(part.strip() for part in entry.split(",") if part.strip())
    matrix = ranges.build_range(db, query, min_sample=args.min_sample)
    for name in requested:
        cell = matrix.cell(name)
        print(f"-- {cell.label}: {cell.kind}, {cell.combos} combinations ({cell.combos_share * 100:.2f}% of all hands)")
        print(f"   decisions {cell.opportunities}, hands {cell.hands}, players {cell.players}, hand-players {cell.hand_players}")
        for view in sorted(ranges.METRICS):
            shown = cell.metric_value(view)
            print(f"   {view}: {'' if shown is None else shown} {ranges.metric(view).unit}")
        if args.hand_ids:
            ids = ranges.cell_hand_ids(db, query, cell.class_id)
            print(f"   hands ({len(ids)}): {', '.join(str(hand) for hand in ids)}")
    if len(requested) > 1:
        print(f"-- selection covers {hc.combos_of(requested)} combinations ({hc.share_of_dealt(requested) * 100:.2f}% of all hands)")
    return 0


def main() -> int:
    args = _parse_args()
    if args.views:
        return _print_views()
    if args.metric not in KNOWN_METRICS:
        raise SystemExit(f"unknown --metric {args.metric!r}; known: {list(KNOWN_METRICS)}")
    query = Query(
        metric=args.metric,
        filters=_parse_pairs(args.filter, "--filter"),
        numerator=_parse_pairs(args.numerator, "--numerator"),
    )
    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.cell:
            return _inspect(args, db, query)
        try:
            matrix = ranges.build_range(db, query, min_sample=args.min_sample)
        except ranges.NotHoldem as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(matrix.as_dict(args.view), indent=2, default=str))
            return 0
        print(matrix.render(args.view, hide_small=args.hide_small))
        print(
            f"\n{matrix.total_opportunities} decisions, {matrix.total_hands} hands, "
            f"{matrix.total_hand_players} hand-players; "
            f"{matrix.unknown_opportunities()} decisions with unseen cards",
        )
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
