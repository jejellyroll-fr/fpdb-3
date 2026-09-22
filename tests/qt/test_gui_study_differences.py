"""Offscreen checks for the Biggest Differences discovery page (#365)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.GuiStudyDifferences import GuiStudyDifferences
from fpdb_3_legacy.research_differences import DifferenceReport, DifferenceRow
from fpdb_3_legacy.research_studies import builtin_studies

pytestmark = pytest.mark.qt


def test_report_renders_reviewable_rows_and_opens_a_study(qtbot, tmp_path) -> None:
    widget = GuiStudyDifferences(registry=builtin_studies(), db=object(), state_path=tmp_path / "history.json")
    qtbot.addWidget(widget)
    row = DifferenceRow(
        candidate_id="preflop_rfi:overview",
        study_id="preflop_rfi",
        panel_id="overview",
        spot="Preflop · First in",
        context="Position: BTN",
        hero_value_bp=5500,
        field_value_bp=4200,
        gap_bp=1300,
        hero_sample=40,
        field_sample=100,
        score=52000,
        unit="frequency",
        context_filters={"game": "holdem"},
        cross_filters={"position": 0},
    )

    widget._render_report(
        DifferenceReport(
            rows=(row,),
            candidates_evaluated=1,
            panels_executed=1,
            low_sample_groups=0,
        )
    )

    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "Preflop · First in"
    assert widget.table.item(0, 4).text() == "+13.0 pp"
    assert widget.open_button.isEnabled()

    opened = []
    widget.study_requested.connect(opened.append)
    widget.table.selectRow(0)
    widget.open_button.click()

    assert len(opened) == 1
    assert opened[0].selection.study.id == "preflop_rfi"
    assert opened[0].panel_id == "overview"
    assert opened[0].cross_filters == {"position": 0}


def test_omaha_picker_uses_the_database_game_token(qtbot, tmp_path) -> None:
    widget = GuiStudyDifferences(registry=builtin_studies(), db=object(), state_path=tmp_path / "history.json")
    qtbot.addWidget(widget)

    widget.game_combo.setCurrentText("Omaha")

    assert widget.game_combo.currentData() == "omahahi"
