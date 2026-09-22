"""Chart-ready hand-state composition models for Research (#364)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hand_state_composition import DIMENSIONS, CategoryCount, Composition


@dataclass(frozen=True)
class StrengthCategory:
    """One classifier-owned category and its exact known-card sample."""

    key: str | None
    label: str
    decisions: int
    share_bp: int | None
    flagged: bool
    filter_name: str | None
    filter_value: Any = None

    @property
    def share(self) -> float | None:
        return None if self.share_bp is None else self.share_bp / 100

    @property
    def sample_sufficient(self) -> bool:
        return not self.flagged

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "decisions": self.decisions,
            "share": self.share,
            "share_bp": self.share_bp,
            "flagged": self.flagged,
            "filter_name": self.filter_name,
            "filter_value": self.filter_value,
        }


@dataclass(frozen=True)
class HandStrengthDistribution:
    """A visual composition with explicit coverage accounting."""

    dimension: str
    label: str
    total: int
    classified: int
    unclassified: int
    coverage_bp: int
    kind: str
    categories: tuple[StrengthCategory, ...]
    min_sample: int
    notes: tuple[str, ...]

    @property
    def coverage(self) -> float:
        return self.coverage_bp / 100

    @property
    def known_sample_warning(self) -> str | None:
        if self.min_sample and self.classified < self.min_sample:
            return (
                f"Low known-card sample: {self.classified} classified decisions "
                f"(recommended minimum {self.min_sample})"
            )
        return None

    @property
    def overlapping(self) -> bool:
        return self.kind == "multi"

    def as_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "category": category.label,
                "key": category.key,
                "decisions": category.decisions,
                "share": category.share,
                "share_bp": category.share_bp,
                "sample_sufficient": category.sample_sufficient,
                "filter_name": category.filter_name,
                "filter_value": category.filter_value,
            }
            for category in self.categories
        ]


def category_filter(dimension: str, key: str | None) -> tuple[str, Any] | None:
    """Map a classifier category to the existing query filter vocabulary."""
    if key is not None:
        return dimension, key
    if dimension in {"draw", "blocker"}:
        return f"{dimension}_none", True
    if dimension == "pair_detail":
        # ``compile_filters`` accepts this structured null predicate for a
        # grouped value which has no dedicated *_none filter.
        return dimension, {"is_null": True}
    return None


def _category(row: CategoryCount, dimension: str) -> StrengthCategory:
    filter_name, filter_value = category_filter(dimension, row.key) or (None, None)
    return StrengthCategory(
        key=row.key,
        label=row.label,
        decisions=row.decisions,
        share_bp=row.share_bp,
        flagged=row.flagged,
        filter_name=filter_name,
        filter_value=filter_value,
    )


def build_hand_strength(composition: Composition) -> HandStrengthDistribution:
    """Adapt the existing composition report without reinterpreting categories."""
    if composition.dimension not in DIMENSIONS:
        raise ValueError(f"Unsupported hand-state dimension {composition.dimension!r}")
    return HandStrengthDistribution(
        dimension=composition.dimension,
        label=composition.label,
        total=composition.total,
        classified=composition.classified,
        unclassified=composition.unclassified,
        coverage_bp=composition.coverage_bp,
        kind=composition.kind,
        categories=tuple(_category(row, composition.dimension) for row in composition.rows),
        min_sample=composition.min_sample,
        notes=composition.notes,
    )


__all__ = [
    "HandStrengthDistribution",
    "StrengthCategory",
    "build_hand_strength",
    "category_filter",
]
