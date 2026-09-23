"""Offscreen checks for the clickable Research heatmap (#363)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.analytics_query import QueryRow
from fpdb_3_legacy.GuiResearchMatrices import MatrixHeatmapWidget
from fpdb_3_legacy.research_matrices import build_matrix

pytestmark = pytest.mark.qt


def fake_result(rows: list[QueryRow]) -> SimpleNamespace:
    return SimpleNamespace(rows=rows, compiled=SimpleNamespace(metric="opportunities"))


def test_heatmap_shows_numeric_samples_and_clicks_exact_matchup(qtbot) -> None:
    hero = build_matrix(
        fake_result([
            QueryRow({"position": 0, "opponent_position": 1}, 12, 12, 12, "count"),
            QueryRow({"position": 0, "opponent_position": 0}, 3, 3, 3, "count"),
        ]),
        ("position", "opponent_position"),
    )
    field = build_matrix(
        fake_result([
            QueryRow({"position": 0, "opponent_position": 1}, 5, 5, 5, "count"),
        ]),
        ("position", "opponent_position"),
    )
    widget = MatrixHeatmapWidget()
    qtbot.addWidget(widget)
    clicked: list[tuple[str, object, str, object, str]] = []
    widget.cell_clicked.connect(lambda *args: clicked.append(args))

    widget.set_comparison(hero, field)

    assert widget.table.rowCount() == 1
    assert widget.table.columnCount() == 2
    assert "Δ" in widget.table.item(0, 1).text()
    assert "opportunities=12" in widget.table.item(0, 1).toolTip()

    widget.click_cell(0, 1)
    assert clicked == [("position", 0, "opponent_position", 1, "BTN × CO")]


def test_comparison_keeps_hero_only_cells_in_comparison_semantics(qtbot) -> None:
    hero = build_matrix(
        fake_result([QueryRow({"position": 0, "opponent_position": 1}, 12, 12, 12, "count")]),
        ("position", "opponent_position"),
    )
    field = build_matrix(
        fake_result([QueryRow({"position": 0, "opponent_position": 0}, 5, 5, 5, "count")]),
        ("position", "opponent_position"),
    )
    widget = MatrixHeatmapWidget()
    qtbot.addWidget(widget)

    widget.set_comparison(hero, field)

    text = widget.table.item(0, widget._column_values.index(1)).text()
    assert "H 12 · F —" in text and "Δ +12.0" in text


def test_comparison_cell_keeps_percent_units_and_uses_percentage_points(qtbot) -> None:
    hero = build_matrix(
        fake_result([QueryRow({"position": 0, "opponent_position": 1}, 100, 84, 84, "bp", 8421)]),
        ("position", "opponent_position"),
    )
    field = build_matrix(
        fake_result([QueryRow({"position": 0, "opponent_position": 1}, 100, 65, 65, "bp", 6587)]),
        ("position", "opponent_position"),
    )
    widget = MatrixHeatmapWidget()
    qtbot.addWidget(widget)

    widget.set_comparison(hero, field)

    text = widget.table.item(0, 0).text()
    assert "H 84.2% · F 65.9%" in text
    assert "Δ +18.3 pp" in text
    assert "Hero: 84.21%" in widget.table.item(0, 0).toolTip()
