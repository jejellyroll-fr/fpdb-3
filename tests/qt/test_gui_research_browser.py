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
from PySide6.QtCore import Qt
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
    from fpdb_3_legacy import GuiResearchBrowser as gui
    from fpdb_3_legacy import research_browser as rb

    names = [row.spec.name for row in browser._filter_rows]
    # Hero says who the question is about; game and limit stop the first answer
    # a reader ever sees averaging Hold'em with Omaha and two limits without
    # saying so (#355). All four start empty, so the default question is still
    # the whole database.
    assert names == list(gui._DEFAULT_FILTERS)
    assert {"hero", "game", "limit", "primary_situation"} == set(names)
    assert all(row.value() is None for row in browser._filter_rows)
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


def test_comparison_renders_both_samples_and_offers_both_sides_of_the_drill(browser, qtbot) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("fold_frequency"))
    browser.group_edit.setText("street")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    headers = [
        browser.result_table.horizontalHeaderItem(c).text()
        for c in range(browser.result_table.columnCount())
    ]
    assert {"you", "your sample", "the field", "its sample", "gap"} <= set(headers)
    assert browser.result_table.rowCount() > 0
    # A comparison row has two populations, so it keeps its query and shows
    # both rather than asking for a rerun without the comparison (#366).
    assert browser._current_query is not None
    assert browser.hands_stack.currentWidget() is browser.source_hands
    assert "side by side" in browser.source_hands.note_label.text()


def test_a_comparison_row_opens_hero_and_field_hands_separately(browser, qtbot) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("fold_frequency"))
    browser.group_edit.setText("street")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    row = next(
        index
        for index in range(browser.result_table.rowCount())
        if browser._last_result.rows[index].hero_opportunities
        and browser._last_result.rows[index].field_opportunities
    )

    browser._on_result_clicked(browser.result_table.item(row, 0))
    pane = browser.source_hands
    qtbot.waitUntil(lambda: pane.page is not None and pane.table.rowCount() > 0, timeout=15000)

    comparison_row = browser._last_result.rows[row]
    assert pane.page.side == "hero"
    assert pane.page.total_matches == comparison_row.hero_opportunities
    labels = [button.text() for button in pane._target_buttons.values()]
    assert [label.split(" (")[0] for label in labels] == [
        "Your population", "Your actions", "Field population", "Field actions",
    ]

    pane.select_target("field")
    qtbot.waitUntil(lambda: pane.page is not None and pane.page.side == "field", timeout=15000)
    assert pane.page.total_matches == comparison_row.field_opportunities


def test_a_sorted_comparison_drills_the_row_that_was_clicked(browser, qtbot) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("fold_frequency"))
    browser.group_edit.setText("street")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    # Sorting reorders the view but not the model, so a row number stops
    # naming the row it was drawn from.
    browser.result_table.sortItems(0, Qt.SortOrder.DescendingOrder)
    visual_row = 0
    item = browser.result_table.item(visual_row, 0)
    expected = item.data(Qt.ItemDataRole.UserRole + 1)

    browser._on_result_clicked(item)
    pane = browser.source_hands
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)

    assert pane.page.total_matches == expected.hero_opportunities
    assert item.text() in pane.context_label.text()


def test_leaving_comparison_returns_the_single_population_hand_list(browser, qtbot) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("fold_frequency"))
    browser.group_edit.setText("street")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    assert browser.hands_stack.currentWidget() is browser.source_hands

    browser.compare_check.setChecked(False)
    _run_and_wait(qtbot, browser)
    browser._on_result_clicked(browser.result_table.item(0, 0))

    assert browser.hands_stack.currentIndex() == 0


def test_comparison_is_offered_for_every_metric(browser) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("total_profit"))
    assert browser.compare_check.isEnabled()
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("fold_frequency"))
    assert browser.compare_check.isEnabled()


def test_non_frequency_comparison_shows_sample_counts_without_a_fake_ratio(browser, qtbot) -> None:
    browser.metric_combo.setCurrentIndex(browser.metric_combo.findData("opportunities"))
    browser.group_edit.setText("street")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    sample_column = [
        browser.result_table.horizontalHeaderItem(c).text()
        for c in range(browser.result_table.columnCount())
    ].index("your sample")
    assert "/" not in browser.result_table.item(0, sample_column).text()


def test_editing_a_loaded_preset_discards_its_hidden_numerator(browser) -> None:
    browser._fill_builder(
        {
            "metric": "hand_frequency",
            "group_by": ["position"],
            "numerator": {"response": ["call", "raise"]},
        },
    )
    assert browser.current_preset()["numerator"] == {"response": ["call", "raise"]}
    browser.group_edit.setText("street")
    assert "numerator" not in browser.current_preset()


def test_empty_comparison_explains_that_no_hands_matched(browser, qtbot) -> None:
    from fpdb_3_legacy import research_browser as rb

    browser._append_filter_row(rb.filter_spec("primary_situation"))
    _row(browser, "primary_situation").value_edit.setText("nope")
    browser.compare_check.setChecked(True)
    _run_and_wait(qtbot, browser)
    assert "No matching hands" in browser.result_note.text()


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
    assert browser.metric_combo.currentData() == "fold_frequency"
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


# ---------------------------------------------------------------------------
# #329: tri-state booleans, typed controls, breakdown, modes, onboarding.
# ---------------------------------------------------------------------------


def _row(browser, name: str):
    return next(row for row in browser._filter_rows if row.spec.name == name)


def test_untouched_boolean_means_any_not_false(browser) -> None:
    """The issue's core safety rule, proven on the widget that broke it."""
    hero = _row(browser, "hero")
    assert hero.value() is None
    assert "hero" not in browser.current_preset()["filters"]
    labels = [hero.any_combo.itemText(i) for i in range(hero.any_combo.count())]
    assert labels == ["Any", "Yes", "No"]
    assert [hero.any_combo.itemData(i) for i in range(hero.any_combo.count())] == [None, True, False]


def test_tri_state_boolean_writes_both_explicit_values(browser) -> None:
    hero = _row(browser, "hero")
    hero.any_combo.setCurrentIndex(hero.any_combo.findData(False))
    assert browser.current_preset()["filters"] == {"hero": False}
    hero.any_combo.setCurrentIndex(hero.any_combo.findData(True))
    assert browser.current_preset()["filters"] == {"hero": True}
    hero.any_combo.setCurrentIndex(0)
    assert browser.current_preset()["filters"] == {}


def test_beginner_controls_speak_poker_not_engine(browser) -> None:
    from fpdb_3_legacy import research_labels as rlabels

    situation = _row(browser, "primary_situation")
    assert situation.name_label.text() == "Situation"
    assert situation.spec.name not in situation.name_label.text()
    # A closed domain is a selector: the free-text field is read-only.
    assert situation.value_edit.isReadOnly()
    assert situation.choice_combo is not None
    shown = [situation.choice_combo.itemText(i) for i in range(situation.choice_combo.count())]
    assert any("facing a continuation bet" in text for text in shown)
    assert rlabels.filter_choices("primary_situation")


def test_the_choice_selector_writes_engine_tokens(browser) -> None:
    situation = _row(browser, "primary_situation")
    index = next(
        i for i in range(situation.choice_combo.count())
        if situation.choice_combo.itemData(i) == "facing_cbet"
    )
    situation.choice_combo.setCurrentIndex(index)
    situation.choice_combo.activated[int].emit(index)
    assert situation.value() == "facing_cbet"
    assert browser.current_preset()["filters"]["primary_situation"] == "facing_cbet"
    assert situation.choice_combo.itemText(index).startswith("✔")


def test_breakdown_is_structured_but_still_one_dimension_list(browser) -> None:
    picker = browser.breakdown_picker
    index = picker.add_combo.findData("street")
    assert index >= 0
    picker.add_combo.setCurrentIndex(index)
    picker._add_current()
    # The engine vocabulary stays the single source the query is built from.
    assert browser.group_edit.text() == "street"
    assert browser.current_preset()["group_by"] == ("street",)
    picker._remove("street")
    assert browser.group_edit.text() == ""
    assert browser.current_preset()["group_by"] == ()


def test_the_expert_text_field_and_the_picker_mirror_each_other(browser) -> None:
    browser.group_edit.setText("street, position")
    assert browser.breakdown_picker.dimensions() == ("street", "position")
    # An invalid dimension typed in technical vocabulary is not adopted by the picker.
    browser.group_edit.setText("nope")
    assert browser.breakdown_picker.dimensions() == ()


def test_technical_vocabulary_keeps_the_engine_names_and_the_query(browser) -> None:
    browser.group_edit.setText("street")
    _row(browser, "hero").any_combo.setCurrentIndex(_row(browser, "hero").any_combo.findData(False))
    before = browser.current_preset()
    browser.vocabulary_combo.setCurrentIndex(browser.vocabulary_combo.findData(True))
    assert not browser.group_edit.isHidden()
    assert _row(browser, "hero").name_label.text() == "hero"
    assert _row(browser, "primary_situation").name_label.text() == "primary_situation"
    assert _row(browser, "primary_situation").value_edit.isReadOnly() is False
    assert browser.current_preset() == before
    # Technical names offer every dimension; poker labels keep a curated subset.
    expert_dims = browser.breakdown_picker.add_combo.count()
    browser.vocabulary_combo.setCurrentIndex(browser.vocabulary_combo.findData(False))
    assert browser.breakdown_picker.add_combo.count() < expert_dims
    assert browser.group_edit.isHidden()


def test_the_active_question_is_stated_in_plain_language(browser) -> None:
    browser.metric_combo.setCurrentText("fold_frequency")
    browser.group_edit.setText("street")
    _row(browser, "primary_situation").value_edit.setText("facing_cbet")
    browser._on_filters_changed()
    summary = browser.summary_label.text()
    assert "facing a continuation bet" in summary
    assert "fold frequency" in summary
    assert "broken down by street" in summary
    for token in ("primary_situation", "facing_cbet", "group_by", "filters"):
        assert token not in summary


def test_the_first_open_screen_explains_itself(browser) -> None:
    from PySide6.QtWidgets import QLabel

    assert browser._has_run is False
    assert browser.empty_state.isVisibleTo(browser)
    assert browser.example_layout.count() > 0
    text = " ".join(label.text() for label in browser.empty_state.findChildren(QLabel))
    assert "Research Browser" in text
    assert "Run" in text
    assert "technical query controls" in text
    # The rebuild note is only shown when there is something to rebuild.
    assert browser.stale_note.isVisibleTo(browser) is False


def test_a_missing_analytics_subsystem_is_announced(browser, monkeypatch) -> None:
    monkeypatch.setattr(
        "fpdb_3_legacy.analytics_lifecycle.stale_subsystems",
        lambda _db: ("situations", "hand_strength"),
    )
    browser._refresh_empty_state()
    assert browser.stale_note.isVisibleTo(browser)
    assert "situations" in browser.stale_note.text()


def test_loading_a_first_run_question_runs_it(browser, qtbot, tmp_path) -> None:
    from fpdb_3_legacy import research_browser as rb

    browser.presets = rb.ResearchPresets(directory=tmp_path)
    question = rb.example_questions()[0]
    browser._load_example(question.preset)
    qtbot.waitUntil(lambda: browser._worker is None, timeout=15000)
    assert browser._has_run is True
    assert not browser.empty_state.isVisibleTo(browser)
    assert browser.sample_label.text()
    assert browser.metric_combo.currentData() == question.preset["metric"]


def test_the_advanced_shortcut_switches_vocabulary(browser) -> None:
    browser._open_advanced_mode()
    assert browser._expert is True
    assert browser.vocabulary_combo.currentData() is True


# ---------------------------------------------------------------------------
# #330: the shipped preset library in the picker.
# ---------------------------------------------------------------------------


def _builtin_indexes(browser) -> list[int]:
    out = []
    for index in range(browser.preset_combo.count()):
        data = browser.preset_combo.itemData(index)
        if isinstance(data, dict) and data.get("kind") == "builtin":
            out.append(index)
    return out


def test_the_picker_offers_the_shipped_library_without_a_user_file(browser, tmp_path) -> None:
    from fpdb_3_legacy import research_presets as rp
    from fpdb_3_legacy.research_browser import ResearchPresets

    # A brand-new install: no research_presets.json at all.
    browser.presets = ResearchPresets(directory=tmp_path / "empty")
    browser._refresh_presets()
    indexes = _builtin_indexes(browser)
    assert len(indexes) >= 20
    assert not (tmp_path / "empty" / "research_presets.json").exists()
    # Grouped by poker topic, with a non-selectable header per pass.
    headers = [
        browser.preset_combo.itemText(index)
        for index in range(browser.preset_combo.count())
        if browser.preset_combo.itemData(index) is None
    ]
    assert any("built-in presets" in text for text in headers)
    assert any("Preflop" in text for text in headers)
    assert any("saved presets" in text.lower() for text in headers)
    shown = {browser.preset_combo.itemData(index)["id"] for index in indexes}
    assert shown == {preset.id for preset in rp.load_library()}


def test_choosing_a_builtin_preset_fills_the_builder_and_says_what_to_adjust(browser, qtbot, tmp_path) -> None:
    from fpdb_3_legacy import research_presets as rp
    from fpdb_3_legacy.research_browser import ResearchPresets

    browser.presets = ResearchPresets(directory=tmp_path)
    browser._refresh_presets()
    target = rp.find_preset(rp.load_library(), "fold_vs_flop_cbet_by_size")
    index = next(
        i for i in _builtin_indexes(browser) if browser.preset_combo.itemData(i)["id"] == target.id
    )
    browser.preset_combo.setCurrentIndex(index)
    qtbot.waitUntil(lambda: browser._worker is None, timeout=15000)
    assert browser.metric_combo.currentData() == target.metric
    assert browser.current_preset()["group_by"] == target.group_by
    assert browser.current_preset()["filters"] == dict(target.filters)
    assert "Adjust" in browser.preset_note.text()
    # The question is restated in poker language, not engine vocabulary.
    assert "fold frequency" in browser.summary_label.text()


def test_saving_under_a_builtin_name_keeps_the_shipped_preset(browser, qtbot, tmp_path, monkeypatch) -> None:
    from fpdb_3_legacy import research_presets as rp
    from fpdb_3_legacy.research_browser import ResearchPresets

    browser.presets = ResearchPresets(directory=tmp_path)
    browser._refresh_presets()
    shipped = rp.load_library()[0]
    monkeypatch.setattr(
        "fpdb_3_legacy.GuiResearchBrowser.QInputDialog.getText",
        lambda *args, **kwargs: (shipped.name, True),
    )
    browser._save_preset()
    saved = browser.presets.load()
    assert shipped.name not in saved
    assert f"{shipped.name} (mine)" in saved
    # The shipped definition is untouched and still offered.
    still_shipped = rp.find_preset(rp.load_library(), shipped.id)
    assert still_shipped is not None and still_shipped.group_by == shipped.group_by
    assert any(
        browser.preset_combo.itemData(i)["id"] == shipped.id for i in _builtin_indexes(browser)
    )


def test_a_builtin_preset_cannot_be_deleted(browser, tmp_path) -> None:
    from fpdb_3_legacy.research_browser import ResearchPresets

    browser.presets = ResearchPresets(directory=tmp_path)
    browser._refresh_presets()
    browser.preset_combo.setCurrentIndex(_builtin_indexes(browser)[0])
    browser._delete_preset()
    assert browser.presets.load() == {}
    assert _builtin_indexes(browser)


# ---------------------------------------------------------------------------
# The named views (#331): one workbench, four shapes of answer.
# ---------------------------------------------------------------------------


def _view_index(browser, view_id: str) -> int:
    for index in range(browser.view_combo.count()):
        if browser.view_combo.currentData() is None and index == 0:
            continue
        if browser.view_combo.itemData(index) == view_id:
            return index
    raise AssertionError(f"the view picker offers no {view_id!r}")


def _choose_view(browser, qtbot, view_id: str) -> None:
    browser.view_combo.setCurrentIndex(_view_index(browser, view_id))
    qtbot.waitUntil(lambda: browser._worker is None, timeout=30000)
    get_qapp().processEvents()


def test_the_view_picker_offers_every_view_and_starts_on_the_landing_state(browser) -> None:
    from fpdb_3_legacy import research_views as rv

    offered = {
        browser.view_combo.itemData(i)
        for i in range(browser.view_combo.count())
        if browser.view_combo.itemData(i) is not None
    }
    assert offered == set(rv.VIEW_IDS)
    # Nothing chosen yet: the tab is the plain browser it was, and the first
    # thing a reader sees is still the explanation.
    assert browser.view_combo.currentData() is None
    assert browser.view_note.isVisibleTo(browser) is False
    assert browser.view_question.text() == ""


def test_choosing_a_view_loads_its_question_into_the_controls(browser, qtbot) -> None:
    from fpdb_3_legacy import research_views as rv

    _choose_view(browser, qtbot, "sizing")
    spec = rv.view("sizing")
    assert browser.current_preset()["metric"] == spec.metric
    assert browser.current_preset()["group_by"] == spec.group_by
    assert browser.current_preset()["filters"] == dict(spec.filters)
    # The question is stated where the controls are, in words.
    assert spec.question in browser.view_question.text()
    assert "per cent of the pot" in browser.view_question.text()
    assert browser.view_note.isVisibleTo(browser) is True


def test_choosing_the_range_view_draws_the_grid(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "range")
    assert browser.result_stack.currentWidget() is browser.range_grid
    matrix = browser.range_grid._matrix
    assert matrix is not None
    assert len(matrix.known_cells()) == 169
    assert "sample" in browser.range_grid.legend.text()
    assert "decisions" in browser.sample_label.text()


def test_a_grid_cell_loads_its_hands(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "range")
    matrix = browser.range_grid._matrix
    populated = next((cell for cell in matrix.known_cells() if cell.opportunities), None)
    if populated is None:
        pytest.skip("the golden corpus opens no starting hand with known cards")
    browser._load_cell_hands(populated.label)
    qtbot.waitUntil(lambda: browser._drill_worker is None, timeout=30000)
    get_qapp().processEvents()
    assert browser.drill_table.rowCount() > 0
    assert "hands" in browser.drill_note.text()


def test_choosing_the_hand_strength_view_shows_the_composition(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "hand_strength")
    assert browser.result_stack.currentWidget() is browser.composition_view
    assert browser.composition_view.table.rowCount() > 0
    headline = browser.composition_view.headline.text()
    assert "classified" in headline and "covered" in headline


def test_choosing_the_profit_view_shows_realized_and_ev_adjusted(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "profit")
    assert browser.result_stack.currentWidget() is browser.money_view
    headings = [
        browser.money_view.table.horizontalHeaderItem(c).text()
        for c in range(browser.money_view.table.columnCount())
    ]
    assert "Realized" in headings and "EV-adjusted" in headings and "Luck" in headings
    assert browser.money_view.table.rowCount() > 0
    assert browser.money_view.notes.text()


def test_choosing_the_hands_view_loads_the_populations_hands(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "hands")
    qtbot.waitUntil(lambda: browser.drill_table.rowCount() > 0, timeout=30000)
    assert browser.drill_table.rowCount() > 0
    assert browser.result_stack.currentIndex() == 0


def test_returning_to_your_own_question_leaves_the_builder_alone(browser, qtbot) -> None:
    _choose_view(browser, qtbot, "position")
    built = browser.current_preset()
    browser.view_combo.setCurrentIndex(0)
    get_qapp().processEvents()
    assert browser.view_note.isVisibleTo(browser) is False
    assert browser.view_question.text() == ""
    # The view filled the controls; going back to "ask your own question" keeps
    # what it filled rather than emptying the pane under the user.
    assert browser.current_preset() == built


def test_leaving_a_shaped_view_drops_its_outstanding_task(browser, qtbot) -> None:
    """A grid on its way back must not be handed to the table renderer.

    A ``RangeMatrix`` has no ``sample_text``: rendering one in the table view
    raises inside the Qt callback and the answer is lost. Leaving the view has
    to make the outstanding answer stale, whether or not its thread is still
    running -- a finished thread whose result has not been delivered yet is the
    case that actually bites.
    """
    browser.view_combo.setCurrentIndex(_view_index(browser, "range"))
    stale = browser._query_serial
    assert browser._worker is not None
    browser.view_combo.setCurrentIndex(0)
    get_qapp().processEvents()
    assert browser._active_view is None
    assert browser._query_serial > stale, "the outstanding answer is not stale"
    # Would raise AttributeError if the serial guard let it through.
    browser._on_query_done(object(), stale)
    qtbot.waitUntil(lambda: browser._worker is None, timeout=30000)


def test_a_shaped_view_runs_the_builders_population_not_the_views_own(browser, qtbot) -> None:
    """Deleting a filter the view preloaded has to delete it from the query.

    Merging the view's own filters back in made that impossible: the query kept
    asking its default situation while the builder above and the plain-language
    summary both said the filter was gone.
    """
    _choose_view(browser, qtbot, "board")
    removed = [row for row in list(browser._filter_rows) if row.spec.name == "primary_situation"]
    assert removed, "the board view preloads a situation filter"
    browser._remove_filter_row(removed[0])
    browser.run_query()
    qtbot.waitUntil(lambda: browser._worker is None, timeout=30000)
    get_qapp().processEvents()
    assert "primary_situation" not in browser._current_query.filters
    assert "primary_situation" not in browser.current_preset()["filters"]


def test_the_range_grid_selector_names_the_reading_it_draws(browser, qtbot) -> None:
    """The control, the legend and the colours describe the same metric."""
    from fpdb_3_legacy import holdem_ranges

    _choose_view(browser, qtbot, "range")
    grid = browser.range_grid
    assert grid._view == holdem_ranges.DEFAULT_VIEW
    assert grid.view_combo.currentData() == holdem_ranges.DEFAULT_VIEW
    assert "Occurrences" in grid.legend.text()

    grid.view_combo.setCurrentIndex(grid.view_combo.findData("frequency"))
    get_qapp().processEvents()
    assert grid._view == "frequency"
    assert "Action frequency" in grid.legend.text()
