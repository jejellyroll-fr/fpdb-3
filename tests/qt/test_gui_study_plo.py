"""Offscreen UI checks for the shipped PLO study pack (#368)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import builtin_studies, panel_unavailable_reason
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import plo_golden as plo

pytestmark = pytest.mark.qt

_STATE: list[object] = []


@pytest.fixture(scope="module")
def plo_db(tmp_path_factory) -> Database:
    config = plo.build_config(tmp_path_factory.mktemp("plo-dashboard-gui"))
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in plo.plo_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _STATE.append(importer)
    return db


def test_a_plo_dashboard_runs_on_omaha_and_never_offers_a_holdem_panel(qtbot, plo_db: Database, tmp_path) -> None:
    """A PLO study is a PLO study: no 13x13 grid, no hand-state panel (#368)."""
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("plo_srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=plo_db, selection=selection)
    qtbot.addWidget(dashboard)
    # A fifteen-hand corpus is under any honest minimum, so ask for every row
    # rather than assert on an empty low-sample screen.
    dashboard.model.set_min_sample(0)
    dashboard.refresh()

    kinds = {panel.kind for panel in dashboard.model.study.panels}
    assert "range_grid" not in kinds
    assert "hand_strength" not in kinds
    assert all(dashboard.tabs.isTabEnabled(index) for index in range(dashboard.tabs.count()))
    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)

    # SPR is the axis a four-card game turns on, so it is a panel of its own
    # here rather than an advanced filter.
    dashboard.model.set_active_panel("spr")
    dashboard._load_active_panel()
    qtbot.waitUntil(lambda: dashboard._pages["spr"][1].rowCount() > 0, timeout=15000)
    dashboard.close()


def test_a_holdem_study_opened_on_omaha_explains_its_disabled_panels() -> None:
    """The panels that cannot be right for four cards say so, and stay off (#368)."""
    study = builtin_studies().get("srp_pfr_ip_flop")

    for panel in study.panels:
        reason = panel_unavailable_reason(panel, plo.PLO_GAME)
        if panel.kind == "range_grid":
            assert reason and "two hole cards" in reason
        elif panel.kind == "hand_strength":
            assert reason and "classifier" in reason
        else:
            assert reason is None, panel.id
