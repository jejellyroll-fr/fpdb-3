"""Offscreen UI checks for the synchronized Study dashboard (#361)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database
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
