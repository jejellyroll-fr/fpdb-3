"""The Statistics tab of the HUD Preferences editor: sources, canvas, inspector (#780).

The Design canvas is where a HUD is edited. It sits in the middle of the tab
with the HUD preview right under it; the stat catalogue is on its left and the
selection's properties on its right. These tests show the dialog offscreen and
check that what the editing needs is on screen, at the default size and at the
smallest size the dialog is meant to work in.
"""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor, select_profile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]

#: The smallest window the editor is meant to work in (see test_responsive_layout).
SMALL = (1024, 640)
DEFAULT = (1400, 900)


def _shown(tmp_path, monkeypatch, size: tuple[int, int]):
    from PySide6.QtWidgets import QApplication

    dialog, _modals = open_editor(config_copy(tmp_path, []), monkeypatch)
    dialog.show()
    dialog.resize(*size)
    select_profile(dialog, "holdem_ring")
    QApplication.processEvents()
    QApplication.processEvents()
    return dialog


def _on_screen(dialog, widget) -> bool:
    """The widget is shown and lies inside the dialog's client area."""
    if not widget.isVisibleTo(dialog) or widget.visibleRegion().isEmpty():
        return False
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    return dialog.rect().contains(top_left) and dialog.rect().contains(bottom_right)


def _left_of(dialog, left, right) -> bool:
    return left.mapTo(dialog, left.rect().topRight()).x() <= right.mapTo(dialog, right.rect().topLeft()).x()


@pytest.mark.parametrize("size", [DEFAULT, SMALL], ids=["default", "small"])
def test_the_canvas_its_tools_and_the_preview_are_on_screen(tmp_path, monkeypatch, size) -> None:
    dialog = _shown(tmp_path, monkeypatch, size)
    for widget in (
        dialog.design_scroll,
        dialog.add_item_btn,
        dialog.edit_stat_btn,
        dialog.remove_stat_btn,
        dialog.add_row_btn,
        dialog.undo_btn,
        dialog.preview,
        dialog.stat_catalog_widget,
        dialog.item_props_tabs,
    ):
        assert _on_screen(dialog, widget), f"{type(widget).__name__} is off screen at {size}"
    assert dialog.design_scroll.height() >= 100


def test_catalogue_canvas_and_inspector_sit_side_by_side(tmp_path, monkeypatch) -> None:
    dialog = _shown(tmp_path, monkeypatch, DEFAULT)
    assert _left_of(dialog, dialog.stat_catalog_widget, dialog.design_scroll)
    assert _left_of(dialog, dialog.design_scroll, dialog.item_props_tabs)
    # The preview is under the canvas, in the same column.
    canvas_bottom = dialog.design_scroll.mapTo(dialog, dialog.design_scroll.rect().bottomLeft()).y()
    assert dialog.preview.mapTo(dialog, dialog.preview.rect().topLeft()).y() > canvas_bottom
    # The canvas gets the most width.
    assert dialog.design_scroll.width() > dialog.stat_catalog_widget.width()
    assert dialog.design_scroll.width() > dialog.item_props_tabs.width()


def test_the_inspector_fits_its_column(tmp_path, monkeypatch) -> None:
    dialog = _shown(tmp_path, monkeypatch, SMALL)
    inspector = dialog.stats_splitter.widget(2)
    assert inspector.widget().width() <= inspector.viewport().width()


def test_group_properties_show_only_for_a_profile_made_of_panels(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    dialog = _shown(tmp_path, monkeypatch, DEFAULT)
    assert not dialog.group_props_box.isVisibleTo(dialog)

    from fpdb_3_legacy.modern_hud_preferences import profile_io

    profile_io.ensure_blocks(dialog.hud_profiles["holdem_ring"])
    dialog.on_profile_selected(dialog.profile_combo.currentIndex())
    QApplication.processEvents()
    assert dialog.group_props_box.isVisibleTo(dialog)
    assert dialog.group_props_box.isEnabled()


def test_the_presentation_is_folded_and_says_what_it_holds(tmp_path, monkeypatch) -> None:
    dialog = _shown(tmp_path, monkeypatch, DEFAULT)
    section = dialog.presentation_section
    assert not section.is_expanded()
    assert not dialog.presentation_box.isVisibleTo(dialog)
    assert section.summary().startswith(dialog.presentation_mode_combo.currentText())

    section.set_expanded(True)
    dialog.font_size_spin.setValue(11)
    assert "11" in section.summary()


def test_the_add_menu_adds_each_kind_of_item(tmp_path, monkeypatch) -> None:
    dialog = _shown(tmp_path, monkeypatch, DEFAULT)
    menu = dialog.add_item_btn.menu()
    assert [action.text() for action in menu.actions() if not action.isSeparator()] == [
        "Statistic…",
        "Text label…",
        "Separator line",
        "Panel…",
    ]
    profile = dialog.hud_profiles["holdem_ring"]
    before = len(profile.get("blocks", [{}])[0].get("hlines", [])) if profile.get("blocks") else 0
    dialog.add_hline_action.trigger()
    after = sum(len(block.get("hlines", [])) for block in profile.get("blocks", []))
    assert after == before + 1
