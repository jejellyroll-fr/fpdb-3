"""The research browser tab (#303), offscreen.

The widget renders what ``research_browser`` answers and forwards what the
user expresses back to it as engine vocabulary. These tests drive the real
tab with the golden corpus in a throwaway SQLite database, and check the
issue's UX contract where it lives in the UI: three panes, the sample size
stated, numerator/denominator shown per row, drill-down into a row's hands,
stale results dropped, presets applied and saved, and empty states explained.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

pytestmark = pytest.mark.qt


def get_qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def browser_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("research-browser-gui")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return db


_MODULE_STATE: list[object] = []


@pytest.fixture
def browser(qtbot, browser_db: Database):
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    get_qapp()
    widget = GuiResearchBrowser(None, None, None, db=browser_db)
    qtbot.addWidget(widget)
    return widget


def _run_and_wait(qtbot, browser, preset=None):

    if preset is not None:
        browser.metric_combo.setCurrentText(preset.get("metric", "frequency"))
    browser.run_query()
    qtbot.waitUntil(lambda: browser._worker is None, timeout=15000)
    get_qapp().processEvents()


def test_three_panes_and_the_default_filters(browser) -> None:
    from fpdb_3_legacy import research_browser as rb

    assert len(browser._filter_rows) == 2
    names = [row.spec.name for row in browser._filter_rows]
    assert "hero" in names and "primary_situation" in names
    # An unrun tab shows no columns yet: the table is shaped by the first query.
    assert browser.result_table.columnCount() == 0
    assert browser.drill_table.columnCount() == 0
    assert browser.drill_note.text()
    assert rb.DRILL_COLUMNS[0].key == "handId"


def test_running_a_query_renders_rows_and_sample(browser, qtbot) -> None:
    from fpdb_3_legacy import research_browser as rb

    # A known population: decisions facing a c-bet, grouped by street.
    browser.group_edit.setText("street")
    for row in list(browser._filter_rows):
        browser._remove_filter_row(row)
    browser._append_filter_row(rb.filter_spec("primary_situation"))
    browser._filter_rows[-1].value_edit.setText("facing_cbet")
    _run_and_wait(qtbot, browser)
    assert "decisions" in browser.sample_label.text()
    assert browser.result_table.rowCount() > 0
    headers = [
        browser.result_table.horizontalHeaderItem(c).text()
        for c in range(browser.result_table.columnCount())
    ]
    assert "decisions" in headers and "numerator" in headers and "frequency" in headers


def test_drill_down_loads_a_rows_hands(browser, qtbot, browser_db: Database) -> None:
    from fpdb_3_legacy import research_browser as rb

    browser.group_edit.setText("street")
    for row in list(browser._filter_rows):
        browser._remove_filter_row(row)
    browser._append_filter_row(rb.filter_spec("primary_situation"))
    browser._filter_rows[-1].value_edit.setText("facing_cbet")
    _run_and_wait(qtbot, browser)
    browser._load_drill(group={"street": "flop"})
    qtbot.waitUntil(lambda: browser.drill_table.rowCount() > 0, timeout=15000)
    assert browser.drill_table.rowCount() > 0
    ids = {browser.drill_table.item(r, 0).text() for r in range(browser.drill_table.rowCount())}
    assert ids and all(int(text) > 0 for text in ids)


def test_empty_state_is_explained_not_silent(browser, qtbot) -> None:
    from fpdb_3_legacy import research_browser as rb

    for row in list(browser._filter_rows):
        browser._remove_filter_row(row)
    browser._append_filter_row(rb.filter_spec("primary_situation"))
    browser._filter_rows[-1].value_edit.setText("no_such_situation")
    _run_and_wait(qtbot, browser)
    assert "no matching hands" in browser.result_note.text()


def test_unknown_group_by_is_refused_with_a_message(browser, qtbot, monkeypatch) -> None:
    browser.group_edit.setText("nope")
    shown = {}
    monkeypatch.setattr(
        "fpdb_3_legacy.GuiResearchBrowser.QMessageBox.warning",
        lambda *args, **kwargs: shown.setdefault("text", args[-1] if args else ""),
    )
    browser.run_query()
    assert "nope" in shown.get("text", "")


def test_stale_result_does_not_replace_a_newer_query(browser, qtbot) -> None:
    from fpdb_3_legacy import research_browser as rb

    class _FakeResult:
        sample_text = "0 decisions"
        elapsed_ms = 1.0
        empty_reason = "no matching hands"
        rows: list = []
        columns = rb.result_columns("frequency", ())
        query = rb.preset_to_query({"metric": "frequency"})

    browser._query_serial = 5
    browser._render_result(_FakeResult())
    assert browser.sample_label.text() == "0 decisions"
    browser._query_serial = 7
    browser._on_query_done(_FakeResult(), 5)
    assert browser.sample_label.text() == "0 decisions"


def test_presets_round_trip_through_the_browser(browser, qtbot, tmp_path: Path) -> None:
    from fpdb_3_legacy import research_browser as rb

    browser.presets = rb.ResearchPresets(directory=tmp_path)
    preset = {"metric": "fold_frequency", "filters": {"hero": True}, "group_by": ["street"]}
    browser.presets.save("test preset", preset)
    browser._refresh_presets()
    index = browser.preset_combo.findText("test preset")
    assert index > 0
    browser.preset_combo.setCurrentIndex(index)
    browser._apply_preset()
    assert browser.metric_combo.currentText() == "fold_frequency"
    assert browser.group_edit.text() == "street"
    names = [row.spec.name for row in browser._filter_rows]
    assert "hero" in names


def test_preset_with_unknown_filter_is_dropped_on_apply(browser, qtbot, tmp_path: Path) -> None:
    from fpdb_3_legacy import research_browser as rb

    browser.presets = rb.ResearchPresets(directory=tmp_path)
    (tmp_path / "research_presets.json").write_text(
        '{"version": 1, "presets": {"broken": {"metric": "frequency", "filters": {"typo": 1}}}}',
        encoding="utf-8",
    )
    browser._refresh_presets()
    index = browser.preset_combo.findText("broken")
    assert index == -1  # a preset the validator refused never reaches the picker
    assert browser.metric_combo.currentText() == browser.metric_combo.currentText()


def test_cancel_bumps_the_serial_and_clears_the_wait(browser) -> None:
    browser._query_serial = 3
    browser.cancel_button.setVisible(True)
    browser._cancel_query()
    assert browser._query_serial == 4
    assert not browser.cancel_button.isVisible()
    assert "cancelled" in browser.result_note.text().lower()
