"""Matrix models for Research position and board visualizations (#363)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .analytics_query import POSITION_CODES
from .board_features import CONNECTIVITIES, PAIRINGS, RANK_BUCKETS, SUIT_STRUCTURES
from .research_distributions import _result_rows
from .research_labels import filter_choices

UNKNOWN_LABEL: Final = "Unknown / unclassified"
POSITION_DIMENSIONS: Final[frozenset[str]] = frozenset({"position", "opponent_position"})
POSITION_AXIS_ORDER: Final[tuple[int, ...]] = (0, 1, 2, 3, 4, 5, 6, -1, -2)
BOARD_DIMENSION_VALUES: Final[dict[str, tuple[str, ...]]] = {
    "board_suit": SUIT_STRUCTURES,
    "board_pairing": PAIRINGS,
    "board_rank": RANK_BUCKETS,
    "board_connectivity": CONNECTIVITIES,
}


def _position_labels() -> dict[Any, str]:
    return {POSITION_CODES[choice.value]: choice.label for choice in filter_choices("position")}


POSITION_LABELS: Final[dict[Any, str]] = _position_labels()


@dataclass(frozen=True)
class MatrixCell:
    """One matrix cell, including enough data to explain and filter it."""

    row_key: Any
    column_key: Any
    row_label: str
    column_label: str
    opportunities: int
    actions: int
    value: float | None
    unit: str
    frequency_bp: int | None
    filter_names: tuple[str, str]
    min_sample: int = 0

    @property
    def percentage(self) -> float | None:
        if self.frequency_bp is not None:
            return self.frequency_bp / 100
        return None

    @property
    def metric_value(self) -> float:
        if self.percentage is not None:
            return self.percentage
        return float(self.value if self.value is not None else self.opportunities)

    @property
    def metric_label(self) -> str:
        if self.percentage is not None:
            return f"{self.percentage:.1f}%"
        return f"{self.metric_value:.0f}"

    @property
    def sample_sufficient(self) -> bool:
        return self.opportunities > 0 and (
            not self.min_sample or self.opportunities >= self.min_sample
        )

    @property
    def sample_label(self) -> str:
        return f"n={self.opportunities}"

    @property
    def is_unknown(self) -> bool:
        return self.row_key is None or self.column_key is None

    def as_dict(self) -> dict[str, Any]:
        return {
            self.filter_names[0]: self.row_key,
            self.filter_names[1]: self.column_key,
            "row_label": self.row_label,
            "column_label": self.column_label,
            "opportunities": self.opportunities,
            "actions": self.actions,
            "value": self.value,
            "unit": self.unit,
            "frequency_bp": self.frequency_bp,
            "metric_value": self.metric_value,
            "metric_label": self.metric_label,
            "sample_sufficient": self.sample_sufficient,
        }


@dataclass(frozen=True)
class MatrixSeries:
    """A complete matrix, including visible empty cells."""

    row_dimension: str
    column_dimension: str
    rows: tuple[Any, ...]
    columns: tuple[Any, ...]
    cells: tuple[MatrixCell, ...]
    metric: str
    total_opportunities: int
    min_sample: int = 0

    def cell(self, row_key: Any, column_key: Any) -> MatrixCell:
        for cell in self.cells:
            if cell.row_key == row_key and cell.column_key == column_key:
                return cell
        raise KeyError((row_key, column_key))

    @property
    def low_sample_cells(self) -> tuple[MatrixCell, ...]:
        return tuple(
            cell for cell in self.cells if cell.opportunities and not cell.sample_sufficient
        )

    @property
    def has_unknown(self) -> bool:
        return any(cell.is_unknown and cell.opportunities for cell in self.cells)

    @property
    def is_rate(self) -> bool:
        return any(cell.frequency_bp is not None for cell in self.cells)

    def as_rows(self) -> list[dict[str, Any]]:
        return [cell.as_dict() for cell in self.cells]


def _label(dimension: str, value: Any) -> str:
    if value is None:
        return UNKNOWN_LABEL
    if dimension in POSITION_DIMENSIONS:
        return POSITION_LABELS.get(value, str(value))
    return str(value).replace("_", " ")


def _ordered_values(dimension: str, present: list[Any]) -> tuple[Any, ...]:
    if dimension in POSITION_DIMENSIONS:
        known: list[Any] = list(POSITION_AXIS_ORDER)
    else:
        known = list(BOARD_DIMENSION_VALUES.get(dimension, ()))
    # A position matrix stays compact to the seats actually present in the
    # spot; board cards use the complete canonical vocabulary so an absent
    # texture remains an explicit empty cell rather than disappearing.
    values = list(known) if dimension not in POSITION_DIMENSIONS else [value for value in known if value in present]
    values.extend(value for value in dict.fromkeys(present) if value not in values)
    return tuple(values)


def _row_number(row: Mapping[str, Any], name: str) -> int:
    value = row.get(name)
    return int(value or 0)


def build_matrix(
    result: Any,
    group_by: tuple[str, str],
    *,
    min_sample: int = 0,
) -> MatrixSeries:
    """Build a complete two-axis matrix from a grouped query result."""
    if len(group_by) != 2:
        raise ValueError(f"A matrix needs exactly two dimensions, got {group_by!r}")
    row_dimension, column_dimension = group_by
    rows = _result_rows(result)
    present_rows = [row.get(row_dimension) for row in rows]
    present_columns = [row.get(column_dimension) for row in rows]
    row_values = _ordered_values(row_dimension, present_rows)
    column_values = _ordered_values(column_dimension, present_columns)
    by_key = {
        (row.get(row_dimension), row.get(column_dimension)): row
        for row in rows
    }
    total = sum(_row_number(row, "opportunities") for row in rows)
    cells: list[MatrixCell] = []

    for row_key in row_values:
        for column_key in column_values:
            raw = by_key.get((row_key, column_key), {})
            frequency_bp = raw.get("frequency_bp")
            if frequency_bp is not None:
                frequency_bp = int(frequency_bp)
            value = raw.get("value")
            cells.append(
                MatrixCell(
                    row_key=row_key,
                    column_key=column_key,
                    row_label=_label(row_dimension, row_key),
                    column_label=_label(column_dimension, column_key),
                    opportunities=_row_number(raw, "opportunities"),
                    actions=_row_number(raw, "actions"),
                    value=float(value) if isinstance(value, (int, float)) else value,
                    unit=str(raw.get("unit") or "count"),
                    frequency_bp=frequency_bp,
                    filter_names=(row_dimension, column_dimension),
                    min_sample=max(0, min_sample),
                ),
            )

    return MatrixSeries(
        row_dimension=row_dimension,
        column_dimension=column_dimension,
        rows=row_values,
        columns=column_values,
        cells=tuple(cells),
        metric=str(getattr(getattr(result, "compiled", None), "metric", "opportunities")),
        total_opportunities=total,
        min_sample=max(0, min_sample),
    )


__all__ = [
    "BOARD_DIMENSION_VALUES",
    "MatrixCell",
    "MatrixSeries",
    "POSITION_DIMENSIONS",
    "POSITION_LABELS",
    "UNKNOWN_LABEL",
    "build_matrix",
]
