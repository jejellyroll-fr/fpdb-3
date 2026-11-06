"""Tests for PopupZoomDialog and zoom/real-size functionality."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_popup_zoom_dialog_creation(qtbot):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy.modern_hud_preferences.preview_widgets import PopupZoomDialog

    QApplication.instance() or QApplication([])

    stats = [
        {"stat_name": "VPIP", "category": "general"},
        {"stat_name": "PFR", "category": "general"},
    ]

    dialog = PopupZoomDialog(
        popup_name="test_popup",
        popup_class="CategorizedPopup",
        stats=stats,
        theme_name="material_dark",
        icon_provider_name="emoji",
    )
    qtbot.addWidget(dialog)

    assert dialog.popup_name == "test_popup"
    assert dialog.current_zoom == 1.0
    assert "test_popup" in dialog.windowTitle()

    # Test zoom in
    dialog._zoom_in()
    assert dialog.current_zoom == 1.25
    assert dialog.zoom_label.text() == "125%"

    # Test zoom out
    dialog._zoom_out()
    assert dialog.current_zoom == 1.0

    # Test reset
    dialog._zoom_in()
    dialog._zoom_reset()
    assert dialog.current_zoom == 1.0


def test_popup_preview_double_click_trigger(qtbot):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy.modern_hud_preferences.preview_widgets import PopupPreviewWidget

    QApplication.instance() or QApplication([])

    widget = PopupPreviewWidget()
    qtbot.addWidget(widget)

    called = []
    widget.double_clicked_callback = lambda: called.append(True)

    widget.mouseDoubleClickEvent(None)
    assert called == [True]
