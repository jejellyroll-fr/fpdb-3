"""List, inspect, validate and compare player cohorts (#307).

A cohort is a saved population -- all opponents, one room, one stake, a set of
players, a linked identity, a relative date window -- that composes with every
other analytics filter. This tool serves the packaged library and any extra
directory, and runs a cohort (or two, side by side) against a real database:

    python tools/cohorts.py --list
    python tools/cohorts.py --show all_opponents
    python tools/cohorts.py --dir ~/my_cohorts --validate
    python tools/cohorts.py --cohort all_opponents --metric fold_frequency \\
        --filter street=flop --filter situation=facing_cbet
    python tools/cohorts.py --compare all_opponents nl200_regular_6max \\
        --metric fold_frequency --filter street=flop --weighting player

Nothing is written: cohorts are read from disk and queried. ``--save`` is the
one exception and says so, writing a single validated cohort document that
``--validate`` can read back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import analytics_cohorts as cohorts  # noqa: E402
from fpdb_3_legacy.analytics_query import Query  # noqa: E402
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


def _registry(extra_dirs: list[str]) -> cohorts.CohortRegistry:
    return cohorts.load_default_registry(extra_dirs)


def _save(args: argparse.Namespace) -> int:
    """Write a cohort built from the command line, validated before writing."""
    if not args.save:
        raise SystemExit("--save needs an output path")
    if not args.cohort or len(args.cohort) != 1:
        raise SystemExit("--save needs exactly one --cohort name")
    saved = cohorts.Cohort(
        name=args.cohort[0],
        filters=_parse_filters(args.filter),
        exclude_hero=not args.include_hero,
        window_days=args.window_days,
        window_offset_days=args.window_offset_days,
        description=args.description or "",
        tags=tuple(args.tag),
        source="saved",
    )
    path = cohorts.CohortRegistry().save(saved, args.save)
    print(f"wrote {path}")
    return 0


def _validate(dirs: list[str]) -> int:
    """Load every cohort file, naming any field that is refused."""
    for directory in dirs or [str(cohorts.default_cohorts_dir())]:
        found = cohorts.load_directory(directory)
        print(f"{directory}: {len(found)} cohort(s) valid")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--dir", action="append", default=[], help="extra cohort directory (repeatable)")
    parser.add_argument("--list", action="store_true", help="list every known cohort")
    parser.add_argument("--show", metavar="NAME", default=None, help="print one cohort and its resolved filters")
    parser.add_argument("--validate", action="store_true", help="load every cohort file and report what is refused")
    parser.add_argument("--cohort", action="append", default=[], help="cohort to query or compare (repeatable)")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None, help="two cohorts, side by side")
    parser.add_argument("--metric", default=None, help="metric to measure (default: fold_frequency)")
    parser.add_argument("--filter", action="append", default=[], help="extra filter key=value (repeatable)")
    parser.add_argument("--weighting", default="decision", choices=list(cohorts.WEIGHTINGS), help="how to pool")
    parser.add_argument("--min-player-sample", dest="min_player_sample", type=int, default=0)
    parser.add_argument("--include-hero", dest="include_hero", action="store_true", help="for --save: keep the hero")
    parser.add_argument("--window-days", dest="window_days", type=int, default=None)
    parser.add_argument("--window-offset-days", dest="window_offset_days", type=int, default=0)
    parser.add_argument("--description", default=None)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--save", default=None, metavar="PATH", help="write a cohort document (the only write)")
    return parser.parse_args()


def _list(registry: cohorts.CohortRegistry) -> int:
    for name in registry.names():
        cohort = registry.get(name)
        facts = ["excludes hero" if cohort.exclude_hero else "includes hero"]
        if cohort.window_days:
            facts.append(f"window {cohort.window_days}d (+{cohort.window_offset_days}d)")
        print(f"{name}: {cohort.description or '(no description)'} [{', '.join(facts)}]")
    if not registry.names():
        print("no cohorts found")
    return 0


def _measure(args: argparse.Namespace, chosen: list[cohorts.Cohort]) -> int:
    """Run one or two cohorts against the configured database."""
    metric = args.metric or "fold_frequency"
    query = Query(metric=metric, filters=_parse_filters(args.filter))
    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if args.compare:
            cohort_a, cohort_b = cohorts.comparison_group(chosen[0], chosen[1])
            comparison = cohorts.compare_cohorts(
                db,
                query,
                cohort_a,
                cohort_b,
                weighting=args.weighting,
                min_player_sample=args.min_player_sample,
            )
            print(cohorts.format_comparison(comparison))
            return 0
        for cohort in chosen:
            stat = cohorts.population_stat(
                db,
                query,
                cohort,
                weighting=args.weighting,
                min_player_sample=args.min_player_sample,
            )
            sample = stat.sample
            print(
                f"{cohort.name}: {stat.value_label} "
                f"[{sample.decisions} decisions, {sample.hands} hands, {sample.players} players] "
                f"({stat.weighting}-weighted)",
            )
            if stat.weighting == "player":
                print(f"  players used: {stat.players_used}, skipped: {stat.players_skipped}")
    finally:
        db.disconnect()
    return 0


def main() -> int:
    args = _parse_args()
    registry = _registry(args.dir)
    if args.list:
        for name in registry.names():
            cohort = registry.get(name)
            facts = ["excludes hero" if cohort.exclude_hero else "includes hero"]
            if cohort.window_days:
                facts.append(f"window {cohort.window_days}d (+{cohort.window_offset_days}d)")
        return _list(registry)
    if args.show:
        print(cohorts.format_cohort(registry.get(args.show)))
        return 0
    if args.validate:
        return _validate(args.dir)
    if args.save:
        return _save(args)

    names = args.compare or args.cohort
    if not names:
        raise SystemExit("give --list, --show, --validate, --cohort, --compare or --save")
    return _measure(args, [registry.get(name) for name in names])


if __name__ == "__main__":
    sys.exit(main())
