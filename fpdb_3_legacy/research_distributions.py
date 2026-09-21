"""Presentation models for Research sizing and response distributions (#362).

The query engine remains the source of truth for counts, denominators and
frequency units.  This module only turns its grouped rows into chart-ready
series: configured sizing buckets are kept in order (including empty ones),
shares are calculated from the reported opportunities, and frequency metrics
keep their response rate rather than pretending it is a population share.

It is deliberately Qt-free so the semantics can be tested against small
fixtures and reused by a future non-Qt Research client.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from .sizing_buckets import DEFAULT_BUCKETS, UNKNOWN_BUCKET

RESPONSE_ORDER: Final[tuple[str, ...]] = (
    "check",
    "bet",
    "fold",
    "call",
    "raise",
    "complete",
    "3bet",
    "4bet",
    "all-in",
    UNKNOWN_BUCKET,
)


@dataclass(frozen=True)
class DistributionBin:
    """One visible bin, retaining the exact query row behind it."""

    key: Any
    label: str
    opportunities: int
    actions: int
    value: float | None
    unit: str
    frequency_bp: int | None
    share_bp: int
    filter_name: str
    filter_value: Any

    @property
    def percentage_bp(self) -> int:
        """The value a chart should plot, in basis points of percentage."""
        if self.frequency_bp is not None:
            return self.frequency_bp
        return self.share_bp

    @property
    def percentage(self) -> float:
        """The chart value as a human percentage (e.g. 42.5)."""
        return self.percentage_bp / 100

    @property
    def is_empty(self) -> bool:
        return self.opportunities == 0

    def as_dict(self) -> dict[str, Any]:
        """Exact, display-friendly row used by the table fallback."""
        return {
            self.filter_name: self.filter_value,
            "label": self.label,
            "opportunities": self.opportunities,
            "actions": self.actions,
            "share": self.share_bp / 100,
            "percentage": self.percentage,
            "value": self.value,
            "unit": self.unit,
            "frequency_bp": self.frequency_bp,
        }


@dataclass(frozen=True)
class DistributionSeries:
    """One side of a sizing/response chart."""

    group_by: str
    metric: str
    bins: tuple[DistributionBin, ...]
    total_opportunities: int
    low_sample_threshold: int = 0

    @property
    def is_rate(self) -> bool:
        return any(bin.frequency_bp is not None for bin in self.bins)

    @property
    def sample_sufficient(self) -> bool:
        return not self.low_sample_warning

    @property
    def low_sample_warning(self) -> str | None:
        if self.low_sample_threshold and self.total_opportunities < self.low_sample_threshold:
            return (
                f"Low sample: {self.total_opportunities} decisions "
                f"(recommended minimum {self.low_sample_threshold})"
            )
        return None

    @property
    def chart_unit(self) -> str:
        return "response rate" if self.is_rate else "share of decisions"

    def as_rows(self) -> list[dict[str, Any]]:
        return [bin.as_dict() for bin in self.bins]


def _result_rows(result: Any) -> list[Mapping[str, Any]]:
    if hasattr(result, "as_dicts"):
        return list(result.as_dicts())
    if hasattr(result, "rows"):
        return [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in result.rows]
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes, Mapping)):
        return [dict(row) for row in result]
    return []


def _metric(result: Any) -> str:
    compiled = getattr(result, "compiled", None)
    return str(getattr(compiled, "metric", "opportunities"))


def _row_value(row: Mapping[str, Any], name: str, default: Any = 0) -> Any:
    value = row.get(name, default)
    return default if value is None else value


def _ordered_keys(group_by: str, rows: list[Mapping[str, Any]]) -> list[Any]:
    present = [row.get(group_by) for row in rows]
    if group_by in {"sizing_bucket", "facing_sizing_bucket"}:
        ordered = [*DEFAULT_BUCKETS.labels, UNKNOWN_BUCKET]
        extras = [key for key in present if key not in ordered]
        return [*ordered, *dict.fromkeys(extras)]
    order = {key: index for index, key in enumerate(RESPONSE_ORDER)}
    return sorted(
        dict.fromkeys(present),
        key=lambda key: (order.get(str(key), len(RESPONSE_ORDER)), str(key)),
    )


def build_distribution(
    result: Any,
    group_by: str,
    *,
    min_sample: int = 0,
) -> DistributionSeries:
    """Build a chart series from one grouped query result.

    A sizing query is always rendered with the configured bucket vocabulary,
    even when SQL returned no row for a bucket.  No raw sizing observation is
    fabricated: raw values are only present in the exact query row when a
    caller explicitly supplies them.
    """
    rows = _result_rows(result)
    metric = _metric(result)
    by_key = {row.get(group_by): row for row in rows}
    keys = _ordered_keys(group_by, rows)
    total = sum(int(_row_value(row, "opportunities")) for row in rows)
    bins: list[DistributionBin] = []
    filter_name = group_by

    for key in keys:
        row = by_key.get(key, {})
        opportunities = int(_row_value(row, "opportunities"))
        actions = int(_row_value(row, "actions"))
        value = row.get("value")
        frequency_bp = row.get("frequency_bp")
        if frequency_bp is not None:
            frequency_bp = int(frequency_bp)
        share_bp = opportunities * 10000 // total if total else 0
        label = "—" if key is None else str(key)
        bins.append(
            DistributionBin(
                key=key,
                label=label,
                opportunities=opportunities,
                actions=actions,
                value=float(value) if isinstance(value, (int, float)) else value,
                unit=str(row.get("unit") or "count"),
                frequency_bp=frequency_bp,
                share_bp=share_bp,
                filter_name=filter_name,
                filter_value=key,
            ),
        )

    return DistributionSeries(
        group_by=group_by,
        metric=metric,
        bins=tuple(bins),
        total_opportunities=total,
        low_sample_threshold=max(0, min_sample),
    )


__all__ = [
    "DistributionBin",
    "DistributionSeries",
    "RESPONSE_ORDER",
    "build_distribution",
]
