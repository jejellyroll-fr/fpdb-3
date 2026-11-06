"""Offscreen checks for the visual hand-state chart (#364)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.GuiResearchHandStrength import HandStrengthChartWidget
from fpdb_3_legacy.hand_state_composition import CategoryCount, Composition
from fpdb_3_legacy.research_hand_strength import build_hand_strength

pytestmark = pytest.mark.qt


def make_composition(dimension: str, total: int, classified: int) -> Composition:
    return Composition(
        dimension=dimension,
        label="Draw",
        total=total,
        classified=classified,
        unclassified=total - classified,
        rows=(
            CategoryCount("flush_draw", "flush draw", 3, 5000, False),
            CategoryCount(None, "(no draw)", 3, 5000, False),
        ),
        kind="multi",
        min_sample=2,
    )


def test_hand_chart_shows_coverage_comparison_and_clicks_classifier_category(qtbot) -> None:
    widget = HandStrengthChartWidget()
    qtbot.addWidget(widget)
    hero = build_hand_strength(make_composition("draw", 10, 6))
    field = build_hand_strength(make_composition("draw", 20, 6))
    clicked: list[tuple[str, object, str]] = []
    widget.category_clicked.connect(lambda *args: clicked.append(args))

    widget.set_distribution(hero, field)

    assert "Hero: 6/10 classified" in widget.coverage_label.text()
    assert "Field: 6/20 classified" in widget.coverage_label.text()
    assert len(widget.plot.listDataItems()) == 2
    widget.click_category(0)
    assert clicked == [("draw", "flush_draw", "flush draw")]
    widget.close()
