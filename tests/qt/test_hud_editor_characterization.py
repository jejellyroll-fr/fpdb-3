"""The HUD Preferences dialog as it behaves today, driven offscreen.

Two kinds of test live here:

* the safety net: opening the dialog and saving without editing must leave
  every shipped stat-set as the HUD reads it;
* the known defects of docs/hud-editor-improvement-plan.md (B1-B10, B14), each
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


EXAMPLE_SETS = [(source, node) for source, node in shipped_stat_sets() if source.startswith("example:")]


@pytest.mark.parametrize(("source", "node"), EXAMPLE_SETS, ids=[source for source, _node in EXAMPLE_SETS])
def test_saving_without_editing_keeps_every_example_stat_set(tmp_path, monkeypatch, source, node) -> None:
    from fpdb_3_legacy import Configuration

    name = node.getAttribute("name")
    before = stat_set_snapshot(Configuration.Stat_sets(node))
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    _save(dialog, modals)
    assert stat_set_snapshot(reload_stat_set(path, name)) == before


B10_STACKED_SIZE = pytest.mark.xfail(
    strict=True, reason="B10: the <ss> rows/cols of a multi-panel set are rewritten from the stacked total"
)
PACKAGE_SETS = [
    pytest.param(source, node, id=source, marks=[B10_STACKED_SIZE] if node.getElementsByTagName("block") else [])
    for source, node in shipped_stat_sets()
    if not source.startswith("example:")
]


@pytest.mark.parametrize(("source", "node"), PACKAGE_SETS)
def test_saving_without_editing_keeps_every_package_stat_set(tmp_path, monkeypatch, source, node) -> None:
    from fpdb_3_legacy import Configuration

    name = node.getAttribute("name")
    before = stat_set_snapshot(Configuration.Stat_sets(node))
    path = config_copy(tmp_path, [node])
    dialog, modals = open_editor(path, monkeypatch)
    _save(dialog, modals)
    assert stat_set_snapshot(reload_stat_set(path, name)) == before


# --- Known defects -----------------------------------------------------------
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


@pytest.mark.xfail(strict=True, reason="B2: Add Stat accepts a cell that is already taken")
def test_b2_adding_a_stat_to_a_taken_cell_is_refused(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")

    def onto_vpip(d) -> int:
        d.row_input.setCurrentText("0")
        d.col_input.setCurrentText("0")
        d.stat_input.setCurrentText("three_B")
        return ACCEPT

    modals.dialogs.append(onto_vpip)
    dialog.add_stat()
    cells = _cells(profile)
    assert len(cells) == len(set(cells))


@pytest.mark.xfail(strict=True, reason="B3: thresholds are integers capped at 100 and rewritten on any edit")
def test_b3_an_unrelated_edit_keeps_decimal_and_large_thresholds(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    ref = next(s for s in profile["stats"] if s["stat"] == "wtsd")
    _select_item(dialog, ref)
    dialog.ip_align.setCurrentText("left")
    assert ref["align"] == "left"
    assert (ref["stat_loth"], ref["stat_hith"]) == ("12.5", "140")


@pytest.mark.xfail(strict=True, reason="B4: renaming a panel forces an rgba() background")
def test_b4_renaming_a_panel_keeps_its_empty_background(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    dialog.gp_name.setText("Postflop")
    dialog._group_prop_changed()
    assert profile["blocks"][1]["label"] == "Postflop"
    assert profile["blocks"][1]["bgcolor"] == ""


@pytest.mark.xfail(strict=True, reason="B6: Add Label on a flat profile is neither shown nor saved")
def test_b6_a_label_added_to_a_flat_profile_is_saved(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")
    modals.texts.append(("HEADER", True))
    dialog.add_text_label()
    _save(dialog, modals)
    labels = [t["label"] for block in reload_stat_set(path, "hole").blocks for t in block.texts]
    assert labels == ["HEADER"]


@pytest.mark.xfail(strict=True, reason="B7: Cancel discards edits without asking")
def test_b7_cancel_asks_before_discarding_edits(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    select_profile(dialog, "hole")["rows"] = 4
    assert dialog.has_unsaved_changes()
    modals.questions.append(QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert not modals.questions, "no confirmation was asked"


@pytest.mark.xfail(strict=True, reason="B8: profile-rule edits are not counted as unsaved changes")
def test_b8_a_new_profile_rule_is_an_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    count = len(dialog.profile_rules)
    dialog._add_profile_rule()
    assert len(dialog.profile_rules) == count + 1
    assert dialog.has_unsaved_changes()


@pytest.mark.xfail(strict=True, reason="B9: a duplicated profile loses rich_text, font_size and padding")
def test_b9_a_duplicated_profile_keeps_its_presentation(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "aof_default")
    modals.texts.append(("aof_copy", True))
    dialog.duplicate_profile()
    _save(dialog, modals)
    original, copy = reload_stat_set(path, "aof_default"), reload_stat_set(path, "aof_copy")
    for name in ("rich_text", "font_size", "xpad", "ypad"):
        assert getattr(copy, name) == getattr(original, name), name


@pytest.mark.xfail(strict=True, reason="B10: the status bar counts a stale stacked stat list")
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


@pytest.mark.xfail(strict=True, reason="B14: an analytics stat is put on a new row instead of a free cell")
def test_b14_an_analytics_stat_fills_the_first_free_cell(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    assert dialog.panel_stat_combo.count() > 0
    dialog.panel_stat_combo.setCurrentIndex(0)
    dialog.panel_stat_block_combo.setCurrentIndex(0)
    dialog._add_panel_stat_to_block()
    assert _cells(profile)[-1] == (1, 1)
    assert profile["rows"] == 2
