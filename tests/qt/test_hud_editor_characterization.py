"""The HUD Preferences dialog as it behaves today, driven offscreen.

Two kinds of test live here:

* the safety net: opening the dialog and saving without editing must leave
  every shipped stat-set as the HUD reads it;
* the known defects of docs/hud-editor-improvement-plan.md (B1-B12, B14, B17), each
  written as the behaviour the editor *should* have and marked
  ``xfail(strict=True)``. A fix makes its test pass, which fails the run until
  the marker is removed -- so no defect is fixed silently or left behind.

Every modal the editor opens is answered through ``tests.helpers.hud_editor``;
an unplanned one fails the test instead of hanging the headless suite.
"""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import (
    EXAMPLE,
    config_copy,
    open_editor,
    reload_stat_set,
    select_profile,
    shipped_stat_sets,
    stat_set_snapshot,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]

ACCEPT = 1


def _parse(xml: str):
    import defusedxml.minidom

    return defusedxml.minidom.parseString(xml).documentElement


def _editor(tmp_path, monkeypatch, *extra_xml: str):
    path = config_copy(tmp_path, [_parse(xml) for xml in extra_xml])
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path


def _save(dialog, modals) -> None:
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages


def _select_table_row(dialog, ref) -> None:
    for row, (_block, _kind, item) in enumerate(dialog._row_items):
        if item is ref:
            dialog.stat_table.setCurrentCell(row, 0)
            return
    raise AssertionError("item not in the editor's table")


def _select_item(dialog, ref) -> None:
    for row, (_kind, item) in enumerate(dialog._group_item_refs):
        if item is ref:
            dialog.group_items_list.setCurrentRow(row)
            return
    raise AssertionError("item not in the Items list")


def _cells(container) -> list[tuple[int, int]]:
    return [(int(s["row"]), int(s["col"])) for s in container.get("stats", [])]


FLAT_WITH_HOLE = (
    '<ss name="hole" rows="2" cols="2">'
    '<stat _rowcol="(1,1)" _stat_name="vpip"/>'
    '<stat _rowcol="(1,2)" _stat_name="pfr"/>'
    '<stat _rowcol="(2,1)" _stat_name="wtsd" stat_loth="12.5" stat_hith="140"/>'
    "</ss>"
)
TWO_BLOCKS = (
    '<ss name="two_blocks" rows="2" cols="2">'
    '<block label="Core" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
    '<block label="Post" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="cb1"/></block>'
    "</ss>"
)


# --- Safety net --------------------------------------------------------------
def test_opening_the_editor_reports_no_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    assert not dialog.has_unsaved_changes()


EXAMPLE_SETS = [pytest.param(node, id=source) for source, node in shipped_stat_sets() if source.startswith("example:")]


@pytest.mark.parametrize("node", EXAMPLE_SETS)
def test_saving_without_editing_keeps_every_example_stat_set(tmp_path, monkeypatch, node) -> None:
    from fpdb_3_legacy import Configuration

    name = node.getAttribute("name")
    before = stat_set_snapshot(Configuration.Stat_sets(node))
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    _save(dialog, modals)
    assert stat_set_snapshot(reload_stat_set(path, name)) == before


PACKAGE_SETS = [
    pytest.param(node, id=source) for source, node in shipped_stat_sets() if not source.startswith("example:")
]


@pytest.mark.parametrize("node", PACKAGE_SETS)
def test_saving_without_editing_keeps_every_package_stat_set(tmp_path, monkeypatch, node) -> None:
    from fpdb_3_legacy import Configuration

    name = node.getAttribute("name")
    before = stat_set_snapshot(Configuration.Stat_sets(node))
    path = config_copy(tmp_path, [node])
    dialog, modals = open_editor(path, monkeypatch)
    _save(dialog, modals)
    assert stat_set_snapshot(reload_stat_set(path, name)) == before


# --- Defects: fixed ones guard their fix, open ones are strict xfail ---------
@pytest.mark.xfail(strict=True, reason="B1: Edit Stat writes default thresholds and colours")
def test_b1_editing_a_stat_without_changes_leaves_it_alone(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    ref = profile["stats"][0]
    original = dict(ref)
    _select_table_row(dialog, ref)
    modals.dialogs.append(lambda _d: ACCEPT)
    dialog.edit_stat()
    assert ref == original


def test_b2_adding_a_stat_to_a_taken_cell_is_refused(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")

    def onto_vpip(d) -> int:
        d.row_input.setCurrentText("0")
        d.col_input.setCurrentText("0")
        d.stat_input.setCurrentText("three_B")
        return ACCEPT

    modals.dialogs.append(onto_vpip)
    before = list(profile["stats"])
    dialog.add_stat()
    assert profile["stats"] == before
    assert [kind for kind, _text in modals.messages] == ["warning"]
    assert "row 1, column 1" in modals.messages[0][1]


def test_b2_editing_a_stat_onto_a_taken_cell_is_refused(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    ref = next(s for s in profile["stats"] if s["stat"] == "wtsd")
    _select_table_row(dialog, ref)

    def onto_pfr(d) -> int:
        d.row_input.setCurrentText("0")
        d.col_input.setCurrentText("1")
        return ACCEPT

    modals.dialogs.append(onto_pfr)
    dialog.edit_stat()
    assert (ref["row"], ref["col"]) == (1, 0)
    assert [kind for kind, _text in modals.messages] == ["warning"]


def test_b2_editing_a_stat_in_place_is_not_a_collision(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    ref = next(s for s in profile["stats"] if s["stat"] == "wtsd")
    _select_table_row(dialog, ref)
    modals.dialogs.append(lambda _d: ACCEPT)
    dialog.edit_stat()
    assert (ref["row"], ref["col"]) == (1, 0)
    assert not modals.messages


@pytest.mark.xfail(strict=True, reason="B3: thresholds are integers capped at 100 and rewritten on any edit")
def test_b3_an_unrelated_edit_keeps_decimal_and_large_thresholds(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    ref = next(s for s in profile["stats"] if s["stat"] == "wtsd")
    _select_item(dialog, ref)
    dialog.ip_align.setCurrentText("left")
    assert ref["align"] == "left"
    assert (ref["stat_loth"], ref["stat_hith"]) == ("12.5", "140")


def test_b4_renaming_a_panel_keeps_its_empty_background(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    dialog.gp_name.setText("Postflop")
    dialog._group_prop_changed()
    dialog.gp_position.setCurrentText("BB")
    assert profile["blocks"][1]["label"] == "Postflop"
    assert profile["blocks"][1]["position"] == "BB"
    assert profile["blocks"][1]["bgcolor"] == ""


def test_b4_the_opacity_slider_still_sets_the_background_alpha(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    dialog.gp_opacity.setValue(100)
    assert profile["blocks"][1]["bgcolor"] == "rgba(0, 0, 0, 100)"


def test_b6_a_label_added_to_a_flat_profile_is_saved(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")
    modals.texts.append(("HEADER", True))
    dialog.add_text_label()
    _save(dialog, modals)
    saved = reload_stat_set(path, "hole")
    assert [t["label"] for block in saved.blocks for t in block.texts] == ["HEADER"]
    # The stats came along into the block, at their cells, and the label took
    # the free one.
    assert sorted(saved.stats) == [(0, 0), (0, 1), (1, 0)]
    assert [t["rowcol"] for t in saved.blocks[0].texts] == [(1, 1)]


def test_a_label_on_a_flat_profile_does_not_untick_show_hero(tmp_path, monkeypatch) -> None:
    """One block shows the hero at the table, so the checkbox must say so."""
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")
    assert dialog.show_hero_checkbox.isChecked()
    modals.texts.append(("HEADER", True))
    dialog.add_text_label()
    assert dialog.show_hero_checkbox.isChecked()


def test_b6_a_line_added_to_a_flat_profile_takes_a_free_row(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")
    dialog.add_hline()
    _save(dialog, modals)
    saved = reload_stat_set(path, "hole")
    assert [h["rowcol"] for block in saved.blocks for h in block.hlines] == [(2, 0)]
    assert saved.blocks[0].rows == 3


def test_b7_cancel_asks_before_discarding_edits(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")["rows"] = 4
    assert dialog.has_unsaved_changes()
    modals.questions.append(QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert not modals.questions, "no confirmation was asked"


def test_b8_a_new_profile_rule_is_an_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    count = len(dialog.profile_rules)
    dialog._add_profile_rule()
    assert len(dialog.profile_rules) == count + 1
    assert dialog.has_unsaved_changes()


def test_b9_a_duplicated_profile_keeps_its_presentation(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "aof_default")
    modals.texts.append(("aof_copy", True))
    dialog.duplicate_profile()
    _save(dialog, modals)
    original, copy = reload_stat_set(path, "aof_default"), reload_stat_set(path, "aof_copy")
    for name in ("rich_text", "font_size", "xpad", "ypad"):
        assert getattr(copy, name) == getattr(original, name), name


def test_b10_the_status_bar_counts_a_stat_added_to_a_panel(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    select_profile(dialog, "two_blocks")
    _select_table_row(dialog, dialog._row_items[0][2])

    def free_cell(d) -> int:
        d.row_input.setCurrentText("0")
        d.col_input.setCurrentText("1")
        d.stat_input.setCurrentText("pfr")
        return ACCEPT

    modals.dialogs.append(free_cell)
    dialog.add_stat()
    assert "Statistics: 3" in dialog.status_label.text()


def _items(dialog) -> list:
    return [item for _kind, item in dialog._group_item_refs]


def _assert_selected(dialog, ref) -> None:
    """The one selection, the same in the Items list, the table and the canvas."""
    assert dialog._current_item()[1] is ref
    assert dialog._selected_row_item()[2] is ref
    assert all(canvas.selected_ref is ref for canvas in dialog._design_canvases)


def test_b11_editing_an_item_keeps_it_selected(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    wtsd = profile["stats"][2]
    _select_item(dialog, wtsd)
    modals.dialogs.append(lambda _d: ACCEPT)
    dialog.edit_stat()
    _assert_selected(dialog, wtsd)
    assert _items(dialog)[0] is not wtsd


def test_b11_a_new_item_becomes_the_selection(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")

    def free_cell(d) -> int:
        d.row_input.setCurrentText("1")
        d.col_input.setCurrentText("1")
        d.stat_input.setCurrentText("cb1")
        return ACCEPT

    modals.dialogs.append(free_cell)
    dialog.add_stat()
    added = profile["stats"][-1]
    assert added["stat"] == "cb1"
    _assert_selected(dialog, added)


def test_b11_picking_an_item_of_another_panel_shows_that_panel(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    assert dialog.group_list.currentRow() == 0
    cb1 = profile["blocks"][1]["stats"][0]
    _select_table_row(dialog, cb1)
    assert dialog.group_list.currentRow() == 1
    _assert_selected(dialog, cb1)


def test_b11_a_chip_click_selects_the_item_everywhere(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    pfr = profile["stats"][1]
    dialog._design_canvases[0].item_selected.emit((0, "stat", pfr))
    _assert_selected(dialog, pfr)


def test_b11_removing_the_selected_item_selects_the_first_one(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    _select_item(dialog, profile["stats"][1])
    dialog.remove_stat()
    assert len(profile["stats"]) == 2
    _assert_selected(dialog, _items(dialog)[0])


def test_b12_editing_an_item_of_a_flat_profile_keeps_the_single_grid_entry(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    assert dialog.group_list.item(0).text() == "(single grid)"
    _select_item(dialog, profile["stats"][0])
    dialog.ip_text.setText("vpip")
    dialog._item_prop_changed()
    assert [dialog.group_list.item(i).text() for i in range(dialog.group_list.count())] == ["(single grid)"]


def test_b12_an_unnamed_panel_is_still_called_so(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    dialog.gp_name.setText("")
    dialog._group_prop_changed()
    assert profile["blocks"][1]["label"] == ""
    assert dialog.group_list.item(1).text() == "(unnamed)"


def test_b14_an_analytics_stat_fills_the_first_free_cell(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    assert dialog.panel_stat_combo.count() > 0
    dialog.panel_stat_combo.setCurrentIndex(0)
    dialog.panel_stat_block_combo.setCurrentIndex(0)
    dialog._add_panel_stat_to_block()
    assert _cells(profile)[-1] == (1, 1)
    assert profile["rows"] == 2


def _name_new_profile(name: str):
    def answer(dialog) -> int:
        from PySide6.QtWidgets import QLineEdit

        dialog.findChild(QLineEdit).setText(name)
        return ACCEPT

    return answer


@pytest.mark.parametrize(
    ("name", "why"), [("", "needs a name"), ("  ", "needs a name"), ("hole", '"hole" already exists')]
)
def test_b17_a_new_profile_that_cannot_be_named_so_says_why(tmp_path, monkeypatch, name, why) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    before = list(dialog.hud_profiles)
    modals.dialogs.append(_name_new_profile(name))
    dialog.add_profile()
    assert list(dialog.hud_profiles) == before
    assert [kind for kind, _text in modals.messages] == ["warning"]
    assert why in modals.messages[0][1]


@pytest.mark.parametrize(("name", "why"), [("", "needs a name"), ("aof_default", '"aof_default" already exists')])
def test_b17_a_duplicate_that_cannot_be_named_so_says_why(tmp_path, monkeypatch, name, why) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")
    before = list(dialog.hud_profiles)
    modals.texts.append((name, True))
    dialog.duplicate_profile()
    assert list(dialog.hud_profiles) == before
    assert [kind for kind, _text in modals.messages] == ["warning"]
    assert why in modals.messages[0][1]


def test_b17_a_new_profile_name_loses_its_surrounding_spaces(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    modals.dialogs.append(_name_new_profile("  bob  "))
    dialog.add_profile()
    assert dialog.profile_combo.currentText() == "bob"
    assert "bob" in dialog.hud_profiles
    assert not modals.messages
