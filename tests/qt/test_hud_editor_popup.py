"""The Popup Windows tab of the HUD Preferences editor: drag and drop, layout (#782).

A classic popup is a list of stats: a drop on a stat puts the dragged one in
its place, and a stat from Available Stats goes in where it is dropped. An
imported BlockPopup is a grid kept in a JSON sidecar: its cells move as a
Statistics panel's items do. Drops are synthetic ``QDropEvent``s, as in
``test_hud_editor_design``.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]

POPUP = "hold_pre"


def _drop(target, mime) -> bool:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDropEvent

    event = QDropEvent(
        QPointF(2, 2),
        Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
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


def _editor(tmp_path, monkeypatch, path=None):
    path = path or config_copy(tmp_path, [])
    dialog, modals = open_editor(path, monkeypatch)
    dialog.popup_combo.setCurrentText(POPUP)
    assert dialog.popup_combo.currentText() == POPUP
    return dialog, modals, path


def _names(dialog, popup: str = POPUP) -> list[str]:
    return [stat["stat_name"] for stat in dialog.popup_windows[popup]["stats"]]


def _chip(dialog, name: str):
    canvas = dialog.popup_canvas
    return next(chip for chip in canvas.chips if chip.item_ref.get("_popup_stat", {}).get("stat_name") == name)


def _selected_name(dialog) -> str:
    return dialog._popup_selected["stat_name"] if dialog._popup_selected else ""


def _saved_names(path, popup: str = POPUP) -> list[str]:
    from fpdb_3_legacy import Configuration

    return list(Configuration.Config(file=str(path)).popup_windows[popup].pu_stats)


# --- Classic popup -------------------------------------------------------------------
def test_dropping_a_stat_on_another_puts_it_in_its_place(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    before = _names(dialog)
    canvas = dialog.popup_canvas
    assert canvas.list_mode and canvas.editable

    assert _drop(_chip(dialog, before[1]), canvas.mime_for(_chip(dialog, before[4]).item_ref))
    assert _names(dialog) == [before[0], before[4], before[1], before[2], before[3], *before[5:]]
    assert _selected_name(dialog) == before[4]
    assert canvas.selected_ref is _chip(dialog, before[4]).item_ref
    assert dialog.has_unsaved_changes()

    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages
    assert _saved_names(path) == _names(dialog)


def test_alt_arrows_move_the_selected_stat(tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import Qt

    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    before = _names(dialog)
    _chip(dialog, before[2]).clicked.emit()
    _key(dialog.popup_canvas, Qt.Key.Key_Down, alt=True)
    assert _names(dialog)[3] == before[2]
    _key(dialog.popup_canvas, Qt.Key.Key_Up, alt=True)
    _key(dialog.popup_canvas, Qt.Key.Key_Up, alt=True)
    assert _names(dialog)[1] == before[2]
    assert _selected_name(dialog) == before[2]


def test_a_stat_cannot_leave_the_popup_s_column(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    canvas = dialog.popup_canvas
    ref = canvas.chips[0].item_ref
    assert canvas.judge(canvas.mime_for(ref), 2, 1) == (False, "A popup lists its stats in one column.")


def test_a_catalogue_stat_goes_in_where_it_is_dropped(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    before = _names(dialog)
    assert _drop(_chip(dialog, before[2]), _stat_mime("classic:cb1"))
    assert _names(dialog) == [*before[:2], "cb1", *before[2:]]
    assert _selected_name(dialog) == "cb1"

    # Below the last stat, or by double-click: at the end.
    assert _drop(dialog.popup_canvas.cells[-1], _stat_mime("classic:wtsd"))
    dialog.popup_catalog_widget.stat_activated.emit("classic:wmsd")
    assert _names(dialog)[-2:] == ["wtsd", "wmsd"]


def test_an_analytics_stat_is_not_put_in_a_popup(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    key = next((entry.key for entry in dialog._stat_catalog() if entry.origin == "analytics"), None)
    if key is None:
        pytest.skip("no analytics stat installed")
    before = _names(dialog)
    dialog.popup_catalog_widget.stat_activated.emit(key)
    assert _names(dialog) == before
    assert "Analytics stats go in HUD panels" in dialog.status_label.text()


def test_delete_removes_and_double_click_edits(tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import Qt

    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    before = _names(dialog)
    _chip(dialog, before[1]).clicked.emit()
    _key(dialog.popup_canvas, Qt.Key.Key_Delete)
    assert _names(dialog) == [before[0], *before[2:]]
    assert dialog._popup_selected is None

    seen = []

    def answer(dlg) -> int:
        seen.append(dlg.windowTitle())
        return 0

    modals.dialogs.append(answer)
    dialog.popup_canvas.item_activated.emit(_chip(dialog, before[3]).item_ref)
    assert seen and _selected_name(dialog) == before[3]


def test_up_and_down_and_the_row_buttons_are_gone(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QPushButton

    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    assert not hasattr(dialog, "move_up_btn") and not hasattr(dialog, "move_down_btn")
    assert not dialog.popup_canvas._host.findChildren(QPushButton)


# --- BlockPopup -------------------------------------------------------------------
GROUP = {
    "name": "grid",
    "rows": 2,
    "cols": 2,
    "cells": [
        {"kind": "text", "text": "Range", "row": 0, "col": 0, "fg": "#80ffff", "bg": "#000000"},
        {"kind": "text", "text": "22 hands", "row": 1, "col": 0, "fg": "", "bg": ""},
        {"kind": "stat", "text": "vpip", "row": 1, "col": 1, "fg": "", "bg": ""},
    ],
}


def _block_popup_editor(tmp_path, monkeypatch):
    sidecar = tmp_path / "popups.json"
    sidecar.write_text(json.dumps({"popup_groups": [GROUP]}), encoding="utf-8")
    path = config_copy(tmp_path, [])
    text = path.read_text(encoding="utf-8")
    node = f'<pu pu_name="zz_grid" pu_class="BlockPopup" pu_source="{sidecar}" pu_group="grid"/>'
    path.write_text(text.replace("<popup_windows>", "<popup_windows>" + node, 1), encoding="utf-8")
    dialog, modals = open_editor(path, monkeypatch)
    dialog.popup_combo.setCurrentText("zz_grid")
    assert dialog._popup_group is not None
    return dialog, modals, sidecar


def _cells(sidecar) -> dict[str, tuple[int, int]]:
    group = json.loads(sidecar.read_text(encoding="utf-8"))["popup_groups"][0]
    return {cell["text"]: (cell["row"], cell["col"]) for cell in group["cells"]}


def _grid_chip(dialog, text: str):
    return next(chip for chip in dialog.popup_canvas.chips if chip.item_ref["_cell"]["text"] == text)


def _save(dialog, modals) -> None:
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages


def test_a_block_popup_cell_moves_and_is_written_on_save(tmp_path, monkeypatch) -> None:
    dialog, modals, sidecar = _block_popup_editor(tmp_path, monkeypatch)
    canvas = dialog.popup_canvas
    assert not canvas.list_mode
    assert _drop(canvas.cell_at(0, 1), canvas.mime_for(_grid_chip(dialog, "vpip").item_ref))
    assert dialog._popup_selected["text"] == "vpip"
    assert dialog.pi_text.text() == "vpip"
    # Held until Save, like every other edit.
    assert _cells(sidecar)["vpip"] == (1, 1)
    assert dialog.has_unsaved_changes()

    _save(dialog, modals)
    assert _cells(sidecar)["vpip"] == (0, 1)
    assert "block_group" not in dialog.popup_windows["zz_grid"]
    assert not dialog.has_unsaved_changes()


def test_a_block_popup_cell_swaps_with_another(tmp_path, monkeypatch) -> None:
    dialog, modals, sidecar = _block_popup_editor(tmp_path, monkeypatch)
    canvas = dialog.popup_canvas
    assert _drop(_grid_chip(dialog, "Range"), canvas.mime_for(_grid_chip(dialog, "22 hands").item_ref))
    _save(dialog, modals)
    assert (_cells(sidecar)["Range"], _cells(sidecar)["22 hands"]) == ((1, 0), (0, 0))


def test_a_catalogue_stat_goes_in_a_block_popup_cell(tmp_path, monkeypatch) -> None:
    dialog, modals, sidecar = _block_popup_editor(tmp_path, monkeypatch)
    canvas = dialog.popup_canvas
    assert _drop(canvas.cell_at(0, 1), _stat_mime("classic:cb1"))
    group = dialog.popup_windows["zz_grid"]["block_group"]
    added = next(cell for cell in group["cells"] if cell["text"] == "cb1")
    assert (added["kind"], added["stat"], added["row"], added["col"]) == ("stat", "cb1", 0, 1)
    assert dialog._popup_selected is added
    # Double-click: the first free cell, here a new row.
    dialog.popup_catalog_widget.stat_activated.emit("classic:wtsd")
    wtsd = next(cell for cell in group["cells"] if cell["text"] == "wtsd")
    assert (wtsd["row"], wtsd["col"], group["rows"]) == (2, 0, 3)

    _save(dialog, modals)
    assert _cells(sidecar)["cb1"] == (0, 1)
    assert _cells(sidecar)["wtsd"] == (2, 0)


def test_delete_removes_a_block_popup_cell_and_cancel_keeps_the_sidecar(tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import Qt

    dialog, modals, sidecar = _block_popup_editor(tmp_path, monkeypatch)
    _grid_chip(dialog, "vpip").clicked.emit()
    _key(dialog.popup_canvas, Qt.Key.Key_Delete)
    assert "vpip" not in [chip.item_ref["_cell"]["text"] for chip in dialog.popup_canvas.chips]
    # Not saved: the sidecar still has it (Cancel would leave it so).
    assert "vpip" in _cells(sidecar)
    _save(dialog, modals)
    assert "vpip" not in _cells(sidecar)


def test_the_remove_button_and_the_preview_follow_the_grid_in_memory(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QLabel

    dialog, _modals, sidecar = _block_popup_editor(tmp_path, monkeypatch)
    _grid_chip(dialog, "22 hands").clicked.emit()
    dialog.remove_popup_stat()
    shown = [label.text() for label in dialog.popup_preview.findChildren(QLabel)]
    assert "22 hands" not in shown and "Range" in shown
    assert "22 hands" in _cells(sidecar)


def test_the_hud_shows_the_value_of_a_catalogue_stat_cell(monkeypatch) -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy import BlockPopup, Stats

    calls = []

    def do_stat(_stat_dict, player, stat, hand_instance=None):
        calls.append((player, stat))
        return (0.25, "25.0", "v=25.0", "vpip=25.0", "(1/4)", "desc")

    monkeypatch.setattr(Stats, "do_stat", do_stat)
    popup = SimpleNamespace(stat_dict={7: {"seat": 3}}, seat=3, hand_instance=None)
    popup._player_id = lambda: BlockPopup.BlockPopup._player_id(popup)
    value = BlockPopup.BlockPopup._stat_value
    assert value(popup, {"kind": "stat", "text": "vpip", "stat": "vpip"}) == "25.0"
    # A PT4 cell keeps its own text; so does a text cell.
    assert value(popup, {"kind": "stat", "text": "(cnt_x / cnt_y)"}) is None
    assert value(popup, {"kind": "text", "text": "Range", "stat": "vpip"}) is None
    assert calls == [(7, "vpip")]

    widget = BlockPopup.build_block_popup_widget(GROUP, value_of=lambda cell: "42" if cell["text"] == "vpip" else None)
    from PySide6.QtWidgets import QLabel

    texts = [label.text() for label in widget.findChildren(QLabel)]
    assert "42" in texts and "vpip" not in texts and "Range" in texts


# --- Layout ---------------------------------------------------------------------------
@pytest.mark.parametrize("size", [(1400, 900), (1024, 640)], ids=["default", "small"])
def test_the_popup_canvas_and_its_preview_are_on_screen(tmp_path, monkeypatch, size) -> None:
    from PySide6.QtWidgets import QApplication

    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    dialog.show()
    dialog.resize(*size)
    dialog.tabs.setCurrentIndex(1)
    QApplication.processEvents()
    QApplication.processEvents()
    for widget in (
        dialog.popup_canvas,
        dialog.popup_preview,
        dialog.popup_catalog_widget,
        dialog.add_popup_stat_btn,
        dialog.pi_props_box,
    ):
        assert widget.isVisibleTo(dialog) and not widget.visibleRegion().isEmpty(), type(widget).__name__
    canvas = dialog.popup_canvas
    catalog = dialog.popup_catalog_widget
    assert catalog.mapTo(dialog, catalog.rect().topRight()).x() <= canvas.mapTo(dialog, canvas.rect().topLeft()).x()
    preview_top = dialog.popup_preview.mapTo(dialog, dialog.popup_preview.rect().topLeft()).y()
    assert preview_top > canvas.mapTo(dialog, canvas.rect().bottomLeft()).y()
