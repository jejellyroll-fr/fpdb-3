"""Table-scoped HUD statistics that do not belong to a player."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple


def live_min_stack_bb(table_stats: Mapping[str, Any] | None) -> StatTuple | None:
    """Format the smallest end-of-hand stack in big blinds."""
    value = (table_stats or {}).get("live_min_stack_bb")
    if value is None:
        return None
    return (
        value,
        f"{value:.1f}",
        f"minM={value:.1f}",
        f"live_min_stack_bb={value:.1f}",
        f"{value:.1f}",
        "Live Min Stack (BB)",
    )


TABLE_STAT_FUNCTIONS: dict[str, Callable[[Mapping[str, Any] | None], StatTuple | None]] = {
    "live_min_stack_bb": live_min_stack_bb,
}


def do_table_stat(table_stats: Mapping[str, Any] | None, stat: object) -> StatTuple | None:
    """Format a precomputed table statistic into the standard HUD tuple."""
    if not isinstance(stat, str) or not stat:
        return None
    function = TABLE_STAT_FUNCTIONS.get(stat)
    if function is None:
        return None
    return function(table_stats)
