#!/usr/bin/env python3
"""CLI for rebuilding the analytics-derived rows in place (#305).

The importer derives events, board features and situations while it parses;
a database imported before those layers existed has hands but none of the
derived rows. This tool re-derives them from the rows the database already
stores -- no hand-history files needed -- one transaction per hand, so a
cancelled run leaves every finished hand complete and the rest untouched.

Examples::

    uv run tools/analytics_rebuild.py --status
    uv run tools/analytics_rebuild.py --all
    uv run tools/analytics_rebuild.py --subsystems board_features
    uv run tools/analytics_rebuild.py --all --site PokerStars.COM --limit 500
    uv run tools/analytics_rebuild.py --all --hand-id 42 --hand-id 43

Use ``--config`` to point at a non-default HUD_config.xml, and ``--dry-run``
to list what would be rebuilt without writing.
"""

from __future__ import annotations

import argparse
import sys

from fpdb_3_legacy import analytics_lifecycle as lifecycle
from fpdb_3_legacy.analytics_rebuild import RebuildScope, rebuild_subsystems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild analytics-derived rows (events, situations, board features) in place.",
    )
    parser.add_argument("--config", default="HUD_config.xml", help="Path to the fpdb configuration file")
    parser.add_argument(
        "--status", action="store_true", help="Show recorded extractor versions and staleness, then exit"
    )
    parser.add_argument("--all", action="store_true", help="Rebuild every implemented subsystem")
    parser.add_argument(
        "--subsystems",
        nargs="+",
        choices=["action_events", "situations", "board_features", "sizing_buckets"],
        help="Which subsystems to rebuild (sizing_buckets refreshes with action_events)",
    )
    parser.add_argument("--site", default=None, help="Restrict the rebuild to one site name")
    parser.add_argument("--from", dest="date_from", default=None, help="Inclusive lower bound on hand start time")
    parser.add_argument("--to", dest="date_to", default=None, help="Inclusive upper bound on hand start time")
    parser.add_argument("--hand-id", type=int, nargs="+", default=None, help="Restrict to these hand ids")
    parser.add_argument("--limit", type=int, default=None, help="At most this many hands (smallest ids first)")
    parser.add_argument("--dry-run", action="store_true", help="Report scope size and staleness without writing")
    return parser


def _scope_from_args(args: argparse.Namespace) -> RebuildScope:
    return RebuildScope(
        site=args.site,
        date_from=args.date_from,
        date_to=args.date_to,
        hand_ids=args.hand_id,
        limit=args.limit,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.status and not args.all and not args.subsystems:
        parser.error("choose --status, --all or --subsystems")

    from fpdb_3_legacy import Configuration, Database

    config = Configuration.Config(file=args.config)
    db = Database.Database(config)

    if args.status or args.dry_run:
        scope = _scope_from_args(args)
        from fpdb_3_legacy.analytics_rebuild import _count_scope_hands

        print("Analytics data lifecycle status")
        print(f"  schema version: {lifecycle.schema_status(db)}")
        for name, status in lifecycle.subsystem_statuses(db).items():
            state = "stale" if status.is_stale else "current"
            if status.code_version == 0:
                state = "not implemented yet"
            print(f"  {name:16s} recorded={status.recorded_version:2d} code={status.code_version:2d} -> {state}")
        print(f"  hands in scope: {_count_scope_hands(db, scope)}")
        if args.status or args.dry_run:
            return 0

    subsystems = (
        list(args.subsystems)
        if args.subsystems
        else ["action_events", "situations", "board_features", "sizing_buckets"]
    )

    def progress(done: int, total: int, hand_id: int) -> None:
        print(f"\r[{done}/{total}] hand {hand_id}", end="", flush=True)

    result = rebuild_subsystems(
        db,
        config,
        subsystems,
        scope=_scope_from_args(args),
        progress=progress,
    )
    print()
    print(f"  scanned:  {result.scanned}")
    print(f"  rebuilt:  {result.rebuilt}")
    print(f"  skipped:  {result.skipped}")
    print(f"  failed:   {result.failed}")
    if result.cancelled:
        print("  CANCELLED: finished hands are committed; the rest remain stale")
        return 130
    for failure in result.failures[:10]:
        print(f"  failure: {failure}")
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
