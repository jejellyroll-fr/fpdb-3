"""Semantics of the visual hand-state composition adapter (#364)."""

from __future__ import annotations

from fpdb_3_legacy.hand_state_composition import CategoryCount, Composition
from fpdb_3_legacy.research_hand_strength import build_hand_strength, category_filter


def composition(dimension: str, rows: tuple[CategoryCount, ...]) -> Composition:
    return Composition(
        dimension=dimension,
        label=dimension.replace("_", " ").title(),
        total=10,
        classified=6,
        unclassified=4,
        rows=rows,
        kind="multi" if dimension in {"draw", "blocker"} else "partition",
        min_sample=7,
        notes=("unknown cards stay outside the categories",),
    )


def test_coverage_and_category_samples_are_kept_exact() -> None:
    distribution = build_hand_strength(
        composition(
            "made_hand",
            (
                CategoryCount("one_pair", "one pair", 4, 6667, True),
                CategoryCount("straight", "straight", 2, 3333, False),
            ),
        ),
    )

    assert distribution.total == 10
    assert distribution.classified == 6
    assert distribution.unclassified == 4
    assert distribution.coverage == 60.0
    assert distribution.categories[0].decisions == 4
    assert distribution.categories[0].share == 66.67
    assert distribution.known_sample_warning == "Low known-card sample: 6 classified decisions (recommended minimum 7)"


def test_multi_label_and_null_categories_map_to_existing_filters() -> None:
    assert category_filter("draw", None) == ("draw_none", True)
    assert category_filter("blocker", None) == ("blocker_none", True)
    assert category_filter("pair_detail", None) == ("pair_detail", {"is_null": True})
    assert category_filter("nutness", "strong") == ("nutness", "strong")
