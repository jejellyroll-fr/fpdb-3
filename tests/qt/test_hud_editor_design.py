"""The Design canvas of the HUD Preferences editor: drag and drop, keyboard, rows and columns, undo (#775).

Drops are synthetic ``QDropEvent``s delivered to the cell widgets: ``QDrag.exec``
needs a real pointer. Each result is checked in the profile, and where it
matters in the saved file.
"""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor, reload_stat_set, select_profile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]

FLAT = (
    '<ss name="flat" rows="2" cols="3">'
    '<stat _rowcol="(1,1)" _stat_name="vpip"/>'
    '<stat _rowcol="(1,2)" _stat_name="pfr"/>'
    '<stat _rowcol="(2,1)" _stat_name="wtsd" colspan="2"/>'
    "</ss>"
)
BLOCKS = (
    '<ss name="blocks" rows="2" cols="2">'
    '<block label="Core" rows="2" cols="2">'
    '<stat _rowcol="(1,1)" _stat_name="vpip"/><stat _rowcol="(1,2)" _stat_name="pfr"/>'
    '<hline _rowcol="(2,1)" colspan="0"/>'
    "</block>"
    '<block label="Post" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="cb1"/></block>'
    "</ss>"
)


# --- Helpers ------------------------------------------------------------------------
def _drop(target, mime) -> bool:
    """Deliver a drop on a cell or chip; True when it was accepted."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDropEvent

    event = QDropEvent(
        QPointF(2, 2), Qt.DropAction.MoveAction | Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    event.ignore()
    target.dropEvent(event)
    return event.isAccepted()


def _stat_mime(key: str):
    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import mime_data_for

    return mime_data_for([key])


def _key(canvas, key, *, alt: bool = False) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    modifiers = Qt.KeyboardModifier.AltModifier if alt else Qt.KeyboardModifier.NoModifier
    canvas.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


def _canvas(container, qtbot):
    from fpdb_3_legacy.modern_hud_preferences.design_canvas import HudDesignCanvas

    canvas = HudDesignCanvas(editable=True)
    qtbot.addWidget(canvas)
    canvas.set_block(0, container)
    return canvas


def _panel():
    a = {"stat": "a", "row": 0, "col": 0}
    b = {"stat": "b", "row": 0, "col": 1}
    wide = {"stat": "wide", "row": 1, "col": 0, "colspan": 2}
    return {"rows": 2, "cols": 3, "stats": [a, b, wide], "texts": [], "hlines": []}, a, b, wide


def _record(signal) -> list:
    seen: list = []
    signal.connect(lambda *args: seen.append(args))
    return seen


# --- The canvas alone ---------------------------------------------------------------
def test_an_editable_canvas_draws_every_free_cell_and_a_row_to_drop_below(qtbot) -> None:
    panel, *_items = _panel()
    canvas = _canvas(panel, qtbot)
    free = sorted((cell.row, cell.col) for cell in canvas.cells)
    assert free == [(0, 2), (1, 2), (2, 0), (2, 1), (2, 2)]
    assert all(cell.new_row for cell in canvas.cells if cell.row == 2)
    assert len(canvas.chips) == 3
    from PySide6.QtWidgets import QPushButton

    assert not [b for b in canvas.findChildren(QPushButton) if b.text() in ("+", "−")]


def test_a_read_only_canvas_keeps_its_row_buttons_and_no_empty_cell(qtbot) -> None:
    from PySide6.QtWidgets import QPushButton

    from fpdb_3_legacy.modern_hud_preferences.design_canvas import HudDesignCanvas

    panel, *_items = _panel()
    canvas = HudDesignCanvas()
    qtbot.addWidget(canvas)
    canvas.set_block(0, panel)
    assert canvas.cells == []
    assert len([b for b in canvas.findChildren(QPushButton) if b.text() in ("+", "−")]) == 4


def test_a_chip_dropped_on_a_free_cell_asks_for_a_move(qtbot) -> None:
    panel, a, _b, _wide = _panel()
    canvas = _canvas(panel, qtbot)
    moves = _record(canvas.item_moved)
    assert _drop(canvas.cell_at(0, 2), canvas.mime_for(a))
    assert moves == [(a, 0, 2)]
    assert (a["row"], a["col"]) == (0, 0)  # the dialog moves it, not the canvas


def test_a_chip_dropped_on_another_asks_for_a_swap(qtbot) -> None:
    panel, a, b, _wide = _panel()
    canvas = _canvas(panel, qtbot)
    moves = _record(canvas.item_moved)
    assert _drop(canvas.chip_for(b), canvas.mime_for(a))
    assert moves == [(a, 0, 1)]


def test_a_drop_that_would_overlap_is_refused_with_a_reason(qtbot) -> None:
    panel, a, _b, wide = _panel()
    canvas = _canvas(panel, qtbot)
    moves, refusals = _record(canvas.item_moved), _record(canvas.drop_refused)
    assert not _drop(canvas.chip_for(a), canvas.mime_for(wide))
    assert not _drop(canvas.cell_at(0, 2), canvas.mime_for(wide))
    assert moves == []
    assert [why for (why,) in refusals] == [
        "No room there: the items would overlap.",
        "The item does not fit: it would leave the panel on the right.",
    ]


def test_a_catalogue_stat_drops_on_a_free_cell_only(qtbot) -> None:
    panel, a, _b, _wide = _panel()
    canvas = _canvas(panel, qtbot)
    added, refusals = _record(canvas.stat_dropped), _record(canvas.drop_refused)
    assert _drop(canvas.cell_at(1, 2), _stat_mime("classic:vpip"))
    assert not _drop(canvas.chip_for(a), _stat_mime("classic:vpip"))
    assert added == [("classic:vpip", 1, 2)]
    assert refusals == [("Cell already used: drop the stat on an empty cell.",)]


def test_a_foreign_drop_is_ignored(qtbot) -> None:
    from PySide6.QtCore import QMimeData

    panel, *_items = _panel()
    canvas = _canvas(panel, qtbot)
    mime = QMimeData()
    mime.setText("vpip")
    refusals = _record(canvas.drop_refused)
    assert not _drop(canvas.cell_at(0, 2), mime)
    assert refusals == []


def test_a_line_moves_only_up_and_down(qtbot) -> None:
    line = {"rowcol": (0, 0), "colspan": 0}
    panel = {"rows": 2, "cols": 2, "stats": [], "texts": [], "hlines": [line]}
    canvas = _canvas(panel, qtbot)
    moves = _record(canvas.item_moved)
    assert _drop(canvas.cell_at(1, 1), canvas.mime_for(line))
    assert moves == [(line, 1, 0)]


def test_dragging_over_a_cell_shows_the_verdict_and_leaving_clears_it(qtbot) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QDragEnterEvent

    panel, a, _b, wide = _panel()
    canvas = _canvas(panel, qtbot)
    cell = canvas.cell_at(0, 2)

    def enter(target, mime):
        event = QDragEnterEvent(
            QPoint(2, 2), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        target.dragEnterEvent(event)
        return event

    assert enter(cell, canvas.mime_for(a)).isAccepted()
    assert "#19e3a0" in cell.styleSheet()
    enter(cell, canvas.mime_for(wide))
    assert "#e05252" in cell.styleSheet()
    cell.dragLeaveEvent(None)
    assert "#e05252" not in cell.styleSheet() and "#19e3a0" not in cell.styleSheet()

    chip = canvas.chip_for(_b)
    enter(chip, canvas.mime_for(a))
    assert "dashed #19e3a0" in chip.styleSheet()
    canvas.clear_highlight()
    assert "dashed" not in chip.styleSheet()


def test_the_keyboard_selects_moves_removes_and_opens(qtbot) -> None:
    from PySide6.QtCore import Qt

    panel, a, b, wide = _panel()
    canvas = _canvas(panel, qtbot)
    selected = _record(canvas.item_selected)
    moves, removed, opened = _record(canvas.item_moved), _record(canvas.item_removed), _record(canvas.item_activated)

    _key(canvas, Qt.Key.Key_Right)  # nothing selected: the first item
    assert canvas.selected_ref is a
    _key(canvas, Qt.Key.Key_Right)
    assert canvas.selected_ref is b
    _key(canvas, Qt.Key.Key_Down)
    assert canvas.selected_ref is wide
    _key(canvas, Qt.Key.Key_Down)  # nothing below: stays
    assert canvas.selected_ref is wide
    assert [payload[2] for (payload,) in selected] == [a, b, wide]

    _key(canvas, Qt.Key.Key_Down, alt=True)
    _key(canvas, Qt.Key.Key_Left, alt=True)  # off the grid: nothing
    _key(canvas, Qt.Key.Key_Delete)
    _key(canvas, Qt.Key.Key_Return)
    assert moves == [(wide, 2, 0)]
    assert removed == [(wide,)] and opened == [(wide,)]


def test_alt_arrow_onto_an_overlap_is_refused(qtbot) -> None:
    from PySide6.QtCore import Qt

    panel, a, _b, _wide = _panel()
    canvas = _canvas(panel, qtbot)
    refusals = _record(canvas.drop_refused)
    canvas.select_ref(a)  # the wide stat below cannot take its place: it would cover b
    _key(canvas, Qt.Key.Key_Down, alt=True)
    assert refusals == [("No room there: the items would overlap.",)]


def test_the_cell_menu_offers_only_what_is_possible(qtbot) -> None:
    panel, *_items = _panel()
    canvas = _canvas(panel, qtbot)
    edits = _record(canvas.grid_edit)

    actions = {action.text(): action for action in canvas.cell_menu(0, 2).actions() if action.text()}
    assert actions["Delete this column"].isEnabled()
    assert not actions["Delete this row"].isEnabled()
    actions["Insert a row below"].trigger()
    actions["Delete this column"].trigger()
    assert edits == [("insert_row", 1), ("delete_col", 2)]
    assert not {a.text(): a for a in canvas.cell_menu(1, 0).actions()}["Delete this column"].isEnabled()


# --- In the editor -------------------------------------------------------------------
def _editor(tmp_path, monkeypatch, *extra_xml: str):
    import defusedxml.minidom

    nodes = [defusedxml.minidom.parseString(xml).documentElement for xml in extra_xml]
    path = config_copy(tmp_path, nodes)
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path


def _save(dialog, modals) -> None:
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages


def _shown(dialog):
    return dialog._design_canvases[0]


def _named(container, name: str) -> dict:
    return next(stat for stat in container["stats"] if stat["stat"] == name)


def test_the_design_canvas_has_no_row_buttons_any_more(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QPushButton

    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    select_profile(dialog, "flat")
    canvas = _shown(dialog)
    assert canvas.editable
    assert not [b for b in canvas.findChildren(QPushButton) if b.text() in ("+", "−")]


def test_dropping_a_chip_moves_it_and_saves_it(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    vpip = _named(profile, "vpip")
    canvas = _shown(dialog)
    assert _drop(canvas.cell_at(0, 2), canvas.mime_for(vpip))

    assert (vpip["row"], vpip["col"]) == (0, 2)
    assert dialog._current_item()[1] is vpip
    assert _shown(dialog).selected_ref is vpip
    assert dialog.has_unsaved_changes()
    _save(dialog, modals)
    saved = reload_stat_set(path, "flat")
    assert saved.stats[(0, 2)].stat_name == "vpip"
    assert (0, 0) not in saved.stats


def test_dropping_on_another_item_swaps_them_in_a_panel(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, BLOCKS)
    profile = select_profile(dialog, "blocks")
    core = profile["blocks"][0]
    vpip, pfr = _named(core, "vpip"), _named(core, "pfr")
    canvas = _shown(dialog)
    assert _drop(canvas.chip_for(pfr), canvas.mime_for(vpip))

    assert ((vpip["row"], vpip["col"]), (pfr["row"], pfr["col"])) == ((0, 1), (0, 0))
    _save(dialog, modals)
    saved = reload_stat_set(path, "blocks").blocks[0]
    assert (saved.stats[(0, 0)].stat_name, saved.stats[(0, 1)].stat_name) == ("pfr", "vpip")


def test_dropping_below_the_last_row_adds_a_row(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, BLOCKS)
    profile = select_profile(dialog, "blocks")
    dialog.group_list.setCurrentRow(1)
    post = profile["blocks"][1]
    cb1 = _named(post, "cb1")
    canvas = _shown(dialog)
    assert canvas.cell_at(1, 1).new_row
    assert _drop(canvas.cell_at(1, 1), canvas.mime_for(cb1))

    assert (post["rows"], cb1["row"], cb1["col"]) == (2, 1, 1)
    _save(dialog, modals)
    saved = reload_stat_set(path, "blocks").blocks[1]
    assert (saved.rows, saved.stats[(1, 1)].stat_name) == (2, "cb1")


def test_a_catalogue_stat_dropped_on_the_canvas_is_added(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    canvas = _shown(dialog)
    assert _drop(canvas.cell_at(0, 2), _stat_mime("classic:cb1"))

    added = _named(profile, "cb1")
    assert (added["row"], added["col"], added["popup"]) == (0, 2, "default")
    assert dialog._current_item()[1] is added
    _save(dialog, modals)
    assert reload_stat_set(path, "flat").stats[(0, 2)].stat_name == "cb1"


def test_a_catalogue_stat_dropped_on_a_taken_cell_says_why(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    canvas = _shown(dialog)
    assert not _drop(canvas.chip_for(_named(profile, "vpip")), _stat_mime("classic:cb1"))
    assert len(profile["stats"]) == 3
    assert "Cell already used" in dialog.status_label.text()
    assert not dialog.has_unsaved_changes()


def test_the_keyboard_moves_and_removes_in_the_editor(tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import Qt

    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    pfr = _named(profile, "pfr")
    dialog._select_item(pfr)
    _key(_shown(dialog), Qt.Key.Key_Right, alt=True)
    assert (pfr["row"], pfr["col"]) == (0, 2)
    assert _shown(dialog).selected_ref is pfr

    _key(_shown(dialog), Qt.Key.Key_Delete)
    assert [s["stat"] for s in profile["stats"]] == ["vpip", "wtsd"]


def test_double_click_opens_the_edit_dialog(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    vpip = _named(profile, "vpip")
    opened = []

    def answer(dlg) -> int:
        opened.append(dlg.stat_input.currentText())
        return 0

    modals.dialogs.append(answer)
    _shown(dialog).item_activated.emit(vpip)
    assert opened == ["vpip"]


def test_rows_and_columns_are_added_and_only_empty_ones_deleted(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    dialog.add_row_btn.click()
    dialog.add_col_btn.click()
    assert (profile["rows"], profile["cols"]) == (3, 4)

    dialog._canvas_grid_edit("delete_row", 0)
    assert profile["rows"] == 3
    assert "Only an empty row or column" in dialog.status_label.text()
    dialog._canvas_grid_edit("insert_col", 0)
    assert [(s["stat"], s["col"]) for s in profile["stats"]] == [("vpip", 1), ("pfr", 2), ("wtsd", 1)]
    dialog._canvas_grid_edit("delete_col", 0)
    dialog._canvas_grid_edit("delete_row", 2)
    assert (profile["rows"], profile["cols"]) == (2, 4)

    _save(dialog, modals)
    saved = reload_stat_set(path, "flat")
    assert (saved.rows, saved.cols) == (2, 4)


def test_undo_and_redo_walk_the_edits_and_keep_the_selection(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    assert not dialog.undo_btn.isEnabled() and not dialog.redo_btn.isEnabled()

    vpip = _named(profile, "vpip")
    canvas = _shown(dialog)
    _drop(canvas.cell_at(0, 2), canvas.mime_for(vpip))
    dialog.add_row_btn.click()
    assert dialog.undo_btn.isEnabled()

    dialog.undo_edit()
    assert profile["rows"] == 2
    dialog.undo_edit()
    restored = _named(profile, "vpip")
    assert (restored["row"], restored["col"]) == (0, 0)
    assert dialog._current_item()[1] is restored
    assert not dialog.has_unsaved_changes()
    assert not dialog.undo_btn.isEnabled() and dialog.redo_btn.isEnabled()

    dialog.undo_edit()
    assert dialog.status_label.text() == "Nothing to undo."
    dialog.redo_edit()
    assert (_named(profile, "vpip")["row"], _named(profile, "vpip")["col"]) == (0, 2)
    dialog.redo_edit()
    assert profile["rows"] == 3
    dialog.redo_edit()
    assert dialog.status_label.text() == "Nothing to redo."
    assert dialog.hud_profiles["flat"] is profile


def test_ctrl_z_undoes_the_last_change(tmp_path, monkeypatch) -> None:
    from PySide6.QtGui import QKeySequence, QShortcut

    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    dialog.add_col_btn.click()
    undo_keys = [
        s for s in dialog.findChildren(QShortcut) if s.key() == QKeySequence(QKeySequence.StandardKey.Undo)
    ]
    assert undo_keys
    undo_keys[0].activated.emit()
    assert profile["cols"] == 3


def test_an_item_property_edit_can_be_undone(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT)
    profile = select_profile(dialog, "flat")
    vpip = _named(profile, "vpip")
    dialog._select_item(vpip)
    dialog.ip_stat.setCurrentText("cb1")
    dialog._item_prop_changed()
    assert vpip["stat"] == "cb1"
    dialog.undo_edit()
    assert [s["stat"] for s in profile["stats"]] == ["vpip", "pfr", "wtsd"]
    assert dialog._current_item()[1]["stat"] == "vpip"
