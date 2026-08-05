"""Regression tests for silent PyQt5 -> PySide6 migration bugs.

See docs/pyside6_migration_audit.md:
  * 1.1 QComboBox.currentIndexChanged is no longer an overloaded signal in Qt6,
        so the bare (non-subscripted) signal must connect and fire.
  * 1.2 ModernSubmenu.mouseMoveEvent must test the left button with a bitwise AND
        on the buttons() flag, not a strict equality, so the drag keeps working
        when a second mouse button is also held.

PySide6 and the legacy GUI modules are imported *inside* the tests (not at module
level) so collection succeeds even when PySide6 is not installed -- the suite then
deselects these ``qt``-marked tests via ``-m "not qt"`` (see pytest.ini). This
mirrors tests/qt/test_gui_bulk_import.py.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.qt


def test_combo_currentindexchanged_without_subscript_fires(qtbot) -> None:
    """1.1 - the Qt6 single-signature signal connects and emits the new index."""
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["a", "b", "c"])

    received: list[int] = []
    combo.currentIndexChanged.connect(received.append)
    combo.setCurrentIndex(2)

    assert received == [2]


class _FakeGlobalPos:
    """Stand-in for QPointF returned by event.globalPosition()."""

    def __init__(self, point) -> None:
        self._point = point

    def toPoint(self):
        return self._point


def _make_move_event(buttons, global_point) -> Mock:
    event = Mock()
    event.buttons.return_value = buttons
    event.globalPosition.return_value = _FakeGlobalPos(global_point)
    return event


def test_popup_drag_continues_with_extra_button() -> None:
    """1.2 - drag must continue when LeftButton is held together with another button.

    The widget is built with ``__new__`` to avoid the heavy ``Popup.create()`` path
    (which needs a full HUD configuration); only the attributes used by
    ``mouseMoveEvent`` are populated.
    """
    from PySide6.QtCore import QPoint, Qt

    from fpdb_3_legacy.ModernPopup import ModernSubmenu

    submenu = ModernSubmenu.__new__(ModernSubmenu)
    submenu.drag_start_position = QPoint(0, 0)
    submenu.is_dragging = True  # already dragging -> the move branch is exercised

    moved: list[QPoint] = []
    submenu.pos = lambda: QPoint(100, 100)
    submenu.move = moved.append

    both_buttons = Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
    event = _make_move_event(both_buttons, QPoint(50, 50))

    ModernSubmenu.mouseMoveEvent(submenu, event)

    # With the old `buttons() == Qt.LeftButton` check this list would stay empty.
    assert moved, "drag stopped when a second mouse button was held"
    assert moved[-1] == QPoint(100, 100) + (QPoint(50, 50) - QPoint(0, 0))
