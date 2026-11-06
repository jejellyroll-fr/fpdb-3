"""Offscreen UI checks for the shipped tournament study pack (#369).

One dashboard per module on purpose: a second live ``GuiStudyDashboard`` over
the same database in one interpreter puts several worker threads and their
deferred deletions in the same teardown, and pytest-qt destroys the widgets
between tests rather than at the end. The model-level behaviour this file
would otherwise repeat is covered without a window in
``tests/test_research_studies_mtt.py``.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import builtin_studies
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import mtt_golden as mtt

pytestmark = pytest.mark.qt

_STATE: list[object] = []


@pytest.fixture(scope="module")
def mtt_db(tmp_path_factory) -> Database:
    config = mtt.build_config(tmp_path_factory.mktemp("mtt-dashboard-gui"))
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in mtt.mtt_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _STATE.append(importer)
    return db


def test_the_landing_page_has_a_tournament_entry_point(qtbot, tmp_path) -> None:
    explorer = GuiStudyExplorer(state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)

    values = [explorer.format_combo.itemData(index) for index in range(explorer.format_combo.count())]
    assert values == [None, False, True]

    explorer.format_combo.setCurrentIndex(explorer.format_combo.findData(True))
    listed = [
        explorer.model.registry.get(str(explorer.study_list.item(row).data(256)))
        for row in range(explorer.study_list.count())
    ]
    assert listed
    assert all(study.tournament is True for study in listed)
    assert any(study.id.startswith("mtt_") for study in listed)

    explorer.format_combo.setCurrentIndex(explorer.format_combo.findData(False))
    cash = [
        explorer.model.registry.get(str(explorer.study_list.item(row).data(256)))
        for row in range(explorer.study_list.count())
    ]
    assert cash
    assert all(study.tournament is False for study in cash)


def test_an_mtt_dashboard_opens_on_stack_depth_and_warns_about_mixing_it(
    qtbot,
    mtt_db: Database,
    tmp_path,
) -> None:
    """The declared default panel opens, and a mixed headline says so (#369)."""
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("mtt_shove_spots", remember=False)
    dashboard = GuiStudyDashboard(db=mtt_db, selection=selection)
    qtbot.addWidget(dashboard)
    # A fourteen-hand corpus is under any honest minimum, so ask for every row
    # rather than assert on an empty low-sample screen.
    dashboard.model.set_min_sample(0)

    # Building the tab strip used to overwrite the study's declared default
    # with whichever panel happened to be built first.
    assert dashboard.model.state.active_panel == "stack"
    dashboard.refresh()
    qtbot.waitUntil(lambda: dashboard._pages["stack"][1].rowCount() > 0, timeout=15000)
    # Breaking the bands out is not averaging them, so nothing is warned about.
    assert not dashboard.stack_note_label.isVisibleTo(dashboard)

    dashboard.model.set_active_panel("overview")
    dashboard._load_active_panel()

    # ``isVisibleTo`` rather than ``isVisible``: an offscreen parent is never
    # shown, so the child's own visibility is what the assertion is about.
    qtbot.waitUntil(lambda: dashboard.stack_note_label.isVisibleTo(dashboard), timeout=15000)
    text = dashboard.stack_note_label.text()
    assert "averages stack depths" in text
    assert "10 BB or less" in text
    assert "Depth not recorded" not in text
    dashboard.close()
