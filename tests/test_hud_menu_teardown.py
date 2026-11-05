#!/usr/bin/env python3
"""Regression tests for tearing the HUD config popup down with its table.

SimpleTablePopupMenu is a parentless top-level window, and its instance used to
be discarded at the call site, so nothing could close it. When a table closed,
Aux_Base.destroy() took the HUD windows down but left the popup on screen over a
dead HUD -- and since menu_is_popped stayed True on the discarded parent, the
rebuilt HUD opened a second popup on top of the stale one. Closing the front
menu then merely uncovered the one behind it, so Close looked inoperative.
"""

from __future__ import annotations

import os
import sys
from operator import attrgetter
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from fpdb_3_legacy.Aux_Hud import SimpleTableMW, SimpleTablePopupMenu

pytestmark = pytest.mark.qt

_HUD_PARAMS = {
    "new_max_seats": 0,
    "agg_bb_mult": 1,
    "seats_style": "A",
    "seats_cust_nums_low": 6,
    "seats_cust_nums_high": 10,
    "stat_range": "A",
    "hud_days": 30,
    "h_agg_bb_mult": 1,
    "h_seats_style": "A",
    "h_seats_cust_nums_low": 6,
    "h_seats_cust_nums_high": 10,
    "h_stat_range": "A",
    "h_hud_days": 90,
}


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    # Read when the application is created, so these menus stay off a developer's screen.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class _Parent(SimpleTableMW):
    """A real SimpleTableMW, minus an __init__ that needs a live HUD and table.

    Subclassing (rather than borrowing the method) keeps destroy()'s zero-arg
    super() call resolving through the real MRO.
    """

    def __init__(self) -> None:
        QWidget.__init__(self)  # bypass SimpleTableMW.__init__
        self.menu_is_popped = False
        self.popup_menu = None
        self.menu_label = "fpdb menu"
        self.hud = MagicMock()
        self.hud.table.x = 100
        self.hud.table.y = 100
        self.hud.layout_set.layout = {6: None}
        self.hud.config.get_stat_sets.return_value = ["set_a", "set_b"]
        self.hud.hud_params = _HUD_PARAMS
        self.aw = MagicMock()
        self.aw.xshift = 0
        self.aw.yshift = 0
        self.aw.game_params.name = "omaha_cg_expert"


def _popped_menu(parent):
    parent.menu_is_popped = True
    parent.popup_menu = SimpleTablePopupMenu(parent)
    return parent.popup_menu


def _button(menu, text):
    return next(b for b in menu.findChildren(QPushButton) if b.text() == text)


@pytest.fixture
def slot_errors(monkeypatch):
    """Collect what Qt would otherwise swallow from a slot."""
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda _type, value, _tb: errors.append(value))
    return errors


def test_close_button_click_closes_the_popup(slot_errors):
    # Clicked for real: PySide6 connects the partial to the argument-less clicked()
    # overload, which calling callback() directly does not exercise.
    parent = _Parent()
    menu = _popped_menu(parent)

    QTest.mouseClick(_button(menu, "Close"), Qt.MouseButton.LeftButton)

    assert slot_errors == []
    assert not menu.isVisible()
    assert parent.menu_is_popped is False


@pytest.mark.parametrize(
    ("label", "called"),
    [
        ("Save HUD Layout", "save_layout"),
        ("Restart This HUD", "parent.kill_hud"),
        ("Stop this HUD", "parent.blacklist_hud"),
    ],
)
def test_action_buttons_run_their_action_when_clicked(slot_errors, label, called):
    parent = _Parent()
    menu = _popped_menu(parent)

    QTest.mouseClick(_button(menu, label), Qt.MouseButton.LeftButton)

    assert slot_errors == []
    attrgetter(called)(parent.hud).assert_called_once()
    assert not menu.isVisible()


def test_restart_button_survives_the_hud_closing_the_popup_first(slot_errors):
    # kill_hud() takes the parent down, which closes the popup before callback()
    # gets to close it again.
    parent = _Parent()
    menu = _popped_menu(parent)
    parent.hud.parent.kill_hud.side_effect = lambda *_args: parent.destroy()

    QTest.mouseClick(_button(menu, "Restart This HUD"), Qt.MouseButton.LeftButton)

    assert slot_errors == []
    assert not menu.isVisible()
    assert parent.menu_is_popped is False
    assert parent.popup_menu is None


def test_popup_reopens_after_a_window_manager_close():
    # Alt+F4 reaches the widget through its QWindow, never through delete_event().
    parent = _Parent()
    menu = _popped_menu(parent)

    menu.windowHandle().close()

    assert not menu.isVisible()
    assert parent.menu_is_popped is False
    assert parent.popup_menu is None

    parent.button_press_right(None)

    assert parent.popup_menu is not None
    assert parent.popup_menu is not menu
    assert parent.popup_menu.isVisible()
    parent.popup_menu.close()


def test_closed_popup_is_deleted():
    parent = _Parent()
    menu = _popped_menu(parent)

    menu.callback(data="close")
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    with pytest.raises(RuntimeError):  # the wrapper outlives the deleted C++ object
        menu.isVisible()


def test_closing_the_table_takes_the_popup_down():
    parent = _Parent()
    menu = _popped_menu(parent)
    assert menu.isVisible()

    parent.destroy()  # Aux_Base.destroy() calls this on table close

    assert not menu.isVisible()


def test_closing_the_table_clears_menu_is_popped():
    # Left True, the rebuilt HUD refuses to open a menu -- or stacks a second one
    # over the orphan, depending on which parent object survives.
    parent = _Parent()
    _popped_menu(parent)

    parent.destroy()

    assert parent.menu_is_popped is False
    assert parent.popup_menu is None


def test_close_button_drops_the_popup_reference():
    parent = _Parent()
    menu = _popped_menu(parent)

    menu.callback(False, data="close")

    assert not menu.isVisible()
    assert parent.menu_is_popped is False
    assert parent.popup_menu is None


def test_close_button_works_after_the_parent_is_gone():
    parent = _Parent()
    menu = _popped_menu(parent)
    parent.deleteLater()
    QApplication.processEvents()

    menu.callback(False, data="close")  # must not raise

    assert not menu.isVisible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
