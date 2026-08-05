"""Formatting helpers shared by legacy HUD statistics."""

from __future__ import annotations

from typing import Any, Protocol

from fpdb_3_legacy.localized_formats import format_number

StatTuple = tuple[Any, Any, Any, Any, Any, Any]


class TooltipWidget(Protocol):
    """Minimal widget contract required to attach a HUD tooltip."""

    def setToolTip(self, text: str) -> None: ...


def stat_override(decimals: int, stat_vals: StatTuple) -> StatTuple:
    """Return a stat tuple whose display value uses ``decimals`` places."""
    display = format_number(100.0 * stat_vals[0], decimals, grouping=False)
    return stat_vals[0], display, stat_vals[2], stat_vals[3], stat_vals[4], stat_vals[5]


def format_no_data_stat(
    stat_name: str,
    description: str,
    numerator: int | None = None,
    denominator: int | None = None,
) -> StatTuple:
    """Return the standard HUD tuple used when a statistic has no data."""
    fraction = f"({numerator}/{denominator})" if numerator is not None and denominator is not None else "(-/-)"
    return 0.0, "-", f"{stat_name}=-", f"{stat_name}=-", fraction, description


def do_tip(widget: TooltipWidget, tip: object) -> None:
    """Attach a stringified tooltip to a compatible widget."""
    widget.setToolTip(str(tip))
