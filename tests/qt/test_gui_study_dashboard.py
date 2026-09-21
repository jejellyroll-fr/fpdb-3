"""Offscreen UI checks for the synchronized Study dashboard (#361)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiResearchDistributions import DistributionChartWidget
from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import builtin_studies
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import analytics_golden as golden

pytestmark = pytest.mark.qt


@pytest.fixture(scope="module")
def dashboard_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("study-dashboard-gui")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _STATE.append(importer)
    return db


_STATE: list[object] = []


def test_dashboard_has_one_study_context_and_lazy_panel_tabs(qtbot, dashboard_db: Database, tmp_path) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    assert dashboard.title_label.text() == "SRP · PFR IP · Flop"
    assert dashboard.tabs.count() == 7
    assert dashboard.comparison_combo.currentData() == "hero_vs_field"
    assert "position" in dashboard._variable_edits
    dashboard._variable_edits["position"].setText("btn")
    next(button for button in dashboard.findChildren(type(dashboard.refresh_button)) if button.text() == "Apply variables").click()
    assert dashboard.model.panel_query("hands").filters["position"] == "btn"
    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    assert dashboard._pages["overview"][1].rowCount() > 0


def test_cross_filter_is_visible_reversible_and_shared(qtbot, dashboard_db: Database, tmp_path) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)
    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)

    dashboard.add_cross_filter("board_pairing", "paired", "Paired boards")
    assert len(dashboard.model.state.cross_filters) == 1
    assert any("Paired boards" in button.text() for button in dashboard.findChildren(type(dashboard.refresh_button)))
    assert dashboard.model.panel_query("hands").filters["board_pairing"] == "paired"

    dashboard.remove_cross_filter("board_pairing")
    assert dashboard.model.state.cross_filters == ()
    assert "board_pairing" not in dashboard.model.panel_query("hands").filters


def test_distribution_chart_is_real_comparative_and_clickable(qtbot) -> None:
    from fpdb_3_legacy.research_distributions import build_distribution

    def fake_result(count: int, response: str = "fold"):
        row = type(
            "Row",
            (),
            {
                "as_dict": lambda self: {
                    "response": response,
                    "opportunities": count,
                    "actions": 0,
                    "value": count,
                    "unit": "count",
                    "frequency_bp": None,
                },
            },
        )()
        return type(
            "Result",
            (),
            {"rows": [row], "compiled": type("Compiled", (), {"metric": "opportunities"})()},
        )()

    chart = DistributionChartWidget()
    qtbot.addWidget(chart)
    hero = build_distribution(fake_result(3), "response")
    field = build_distribution(fake_result(1, "call"), "response")
    clicked: list[tuple[str, object, str]] = []
    chart.bin_clicked.connect(lambda name, value, label: clicked.append((name, value, label)))

    chart.set_comparison(hero, field)
    assert len(chart._bar_items) == 2
    assert [item.label for item in chart._bins] == ["fold", "call"]
    assert "Hero: 3 decisions" in chart.summary_label.text()
    assert "Field: 1 decisions" in chart.summary_label.text()

    chart.click_bin(0)
    assert clicked == [("response", "fold", "fold")]


def test_dashboard_renders_response_chart_and_turns_bar_click_into_shared_filter(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_defender_oop_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    chart = dashboard._distribution_widgets["overview"]
    assert len(chart._bar_items) == 2
    assert chart._bins

    expected_response = chart._bins[0].filter_value
    chart.click_bin(0)
    assert dashboard.model.state.cross_filters[0].name == "response"
    assert dashboard.model.state.cross_filters[0].value == expected_response
