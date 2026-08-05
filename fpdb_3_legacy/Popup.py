"""Popup.py.
from __future__ import annotations
Popup windows for the HUD.
"""

import ctypes
import sys
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

#    Copyright 2011-2012,  Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################

#    to do

#    Standard Library modules


try:
    from AppKit import NSView, NSWindowAbove
except ImportError:
    NSView = None

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QVBoxLayout, QWidget

#    FreePokerTools modules
from fpdb_3_legacy import Stats

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("popup")

# Note: modern popup classes (ModernSubmenu, ...) are resolved lazily by
# create_popup_window() below via a runtime import of fpdb_3_legacy.ModernPopup.
# Importing them here at module load causes a circular import (ModernPopup imports
# Popup), which silently disabled the modern popups and logged a misleading
# "Modern popup classes not available" warning.


class Popup(QWidget):
    def __init__(
        self,
        seat=None,
        stat_dict=None,
        win=None,
        pop=None,
        hand_instance=None,
        config=None,
        parent_popup=None,
        anchor_widget=None,
    ) -> None:
        # WindowStaysOnTopHint is required so stat popups appear ABOVE the
        # always-on-top HUD seat windows; without it the popup is created visible
        # but rendered behind them and never seen by the user.
        super().__init__(
            parent_popup or win,
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.seat = seat
        self.stat_dict = stat_dict
        self.win = win
        self.pop = pop
        self.hand_instance = hand_instance
        self.config = config
        self.parent_popup = parent_popup  # parent's instance only used if this popup is a child of another popup
        self.anchor_widget = anchor_widget
        self.submenu_count = 0  # used to keep track of active submenus - only one at once allowed

        self.create()
        self.show()
        # Child popups are chained to their parent window and positioned beside it.
        parent = parent_popup or win
        if config.os_family == "Mac" and NSView is not None:
            try:
                selfwinid = self.effectiveWinId()
                selfcvp = ctypes.c_void_p(int(selfwinid))
                selfview = NSView(c_void_p=selfcvp)
                parentwinid = parent.effectiveWinId()
                parentcvp = ctypes.c_void_p(int(parentwinid))
                parentview = NSView(c_void_p=parentcvp)
                parentview.window().addChildWindow_ordered_(
                    selfview.window(),
                    NSWindowAbove,
                )
            except Exception:
                log.exception("Popup: macOS addChildWindow ordering failed; popup may not stay above parent")
        else:
            self.windowHandle().setTransientParent(self.parent().windowHandle())
        parent.destroyed.connect(lambda: self.destroy())
        self._move_next_to_anchor()

    def _anchor_geometry(self) -> QRect:
        if self.parent_popup is not None:
            return self.parent_popup.frameGeometry()
        if self.win is not None:
            return self.win.frameGeometry()
        if self.anchor_widget is not None:
            top_left = self.anchor_widget.mapToGlobal(self.anchor_widget.rect().topLeft())
            bottom_right = self.anchor_widget.mapToGlobal(self.anchor_widget.rect().bottomRight())
            return QRect(top_left, bottom_right)

        cursor_pos = QCursor.pos()
        return QRect(cursor_pos, cursor_pos)

    def _move_next_to_anchor(self) -> None:
        """Place the popup beside the HUD block instead of covering it."""
        self.adjustSize()
        popup_size = self.size()
        anchor = self._anchor_geometry()
        margin = 8

        x = anchor.right() + margin
        y = anchor.top()

        app = QApplication.instance()
        screen = app.screenAt(anchor.center()) if app is not None else None
        if screen is not None:
            available = screen.availableGeometry()
            if x + popup_size.width() > available.right():
                x = anchor.left() - popup_size.width() - margin
            y = max(available.top(), min(y, available.bottom() - popup_size.height() + 1))

        from fpdb_3_legacy.Aux_Base import clamp_to_screen

        x, y = clamp_to_screen(x, y, popup_size.width(), popup_size.height())
        self.move(x, y)

    #    Every popup window needs one of these
    def mousePressEvent(self, event) -> None:
        """Handle button clicks on the popup window."""
        #    Any button click gets rid of popup.
        self.destroy_pop()

    def create(self) -> None:  # type: ignore[override]
        # popup_count is used by Aux_hud to prevent multiple active popups per player
        # do not increment count if this popup is a child of another popup
        if self.parent_popup:
            self.parent_popup.submenu_count += 1
        else:
            self.win.popup_count += 1

    def destroy_pop(self) -> None:
        if self.parent_popup:
            self.parent_popup.submenu_count -= 1
        else:
            self.win.popup_count -= 1
        self.destroy()


class default(Popup):
    def create(self) -> None:  # type: ignore[override]
        super().create()
        player_id = None
        for id in list(self.stat_dict.keys()):
            if self.seat == self.stat_dict[id]["seat"]:
                player_id = id
        if player_id is None:
            self.destroy_pop()
            return

        self.lab = QLabel()
        self.setLayout(QVBoxLayout())
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self.lab)

        text, tip_text = "", ""
        for stat in self.pop.pu_stats:
            number = Stats.do_stat(
                self.stat_dict,
                player=int(player_id),
                stat=stat,
                hand_instance=self.hand_instance,
            )
            if number:
                text += number[3] + "\n"
                tip_text += number[5] + " " + number[4] + "\n"
            else:
                text += "xxx" + "\n"
                tip_text += "xxx" + " " + "xxx" + "\n"

        # trim final \n
        tip_text = tip_text[:-1]
        text = text[:-1]

        self.lab.setText(text)
        Stats.do_tip(self.lab, tip_text)


class Submenu(Popup):
    # fixme refactor this class, too much repeat code
    def create(self) -> None:  # type: ignore[override]
        super().create()

        player_id = None
        for id in list(self.stat_dict.keys()):
            if self.seat == self.stat_dict[id]["seat"]:
                player_id = id
        if player_id is None:
            self.destroy_pop()
            return

        number_of_items = len(self.pop.pu_stats)
        if number_of_items < 1:
            self.destroy_pop()
            return

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.setLayout(self.grid)

        grid_line: dict[int, dict[str, Any]] = {}
        row = 1

        for stat, submenu_to_run in self.pop.pu_stats_submenu:
            grid_line[row] = {}
            grid_line[row]["lab"] = QLabel()

            number = Stats.do_stat(
                self.stat_dict,
                player=int(player_id),
                stat=stat,
                hand_instance=self.hand_instance,
            )
            if number:
                grid_line[row]["text"] = number[3]
                grid_line[row]["lab"].setText(number[3])
                Stats.do_tip(grid_line[row]["lab"], number[5] + " " + number[4])
            else:
                grid_line[row]["text"] = stat
                grid_line[row]["lab"].setText(stat)

            if row == 1:
                # put an "x" close label onto the popup, invert bg/fg
                # the window can also be closed by clicking on any non-menu label
                # but this "x" is added incase the menu is entirely non-menu labels

                xlab = QLabel("x")
                xlab.setStyleSheet(
                    f"background:{self.win.aw.fgcolor};color:{self.win.aw.bgcolor};",
                )
                grid_line[row]["x"] = xlab
                self.grid.addWidget(grid_line[row]["x"], row - 1, 2)

            if submenu_to_run:
                lab = QLabel(">")
                grid_line[row]["arrow_object"] = lab
                lab.submenu = submenu_to_run
                grid_line[row]["lab"].submenu = submenu_to_run
                if row == 1:
                    self.grid.addWidget(grid_line[row]["arrow_object"], row - 1, 1)
                else:
                    self.grid.addWidget(
                        grid_line[row]["arrow_object"],
                        row - 1,
                        1,
                        1,
                        2,
                    )

            self.grid.addWidget(grid_line[row]["lab"], row - 1, 0)

            row += 1

    def mousePressEvent(self, event) -> None:
        widget = self.childAt(event.pos())
        submenu = "_destroy"
        if widget is not None and hasattr(widget, "submenu"):
            submenu = widget.submenu
        if submenu == "_destroy":
            self.destroy_pop()
            return
        if self.submenu_count < 1:  # only 1 popup allowed to be open at this level
            popup_factory(
                self.seat,
                self.stat_dict,
                self.win,
                self.config.popup_windows[submenu],
                self.hand_instance,
                self.config,
                self,
            )


class Multicol(Popup):
    # like a default, but will flow into columns of 16 items
    # use "blank" items if the default flowing affects readability

    def create(self) -> None:  # type: ignore[override]
        super().create()

        player_id = None
        for id in list(self.stat_dict.keys()):
            if self.seat == self.stat_dict[id]["seat"]:
                player_id = id
        if player_id is None:
            self.destroy_pop()
            return

        number_of_items = len(self.pop.pu_stats)
        if number_of_items < 1:
            self.destroy_pop()
            return

        number_of_cols = (number_of_items) // (16)
        if number_of_cols % 16:
            number_of_cols += 1

        number_per_col = (number_of_items) // (float(number_of_cols))

        # if number_per_col != round((number_of_items / float(number_of_cols)),0):
        #    number_per_col += 1
        # number_per_col = int(number_per_col)
        number_per_col = 16

        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.grid.setHorizontalSpacing(5)

        col_index, row_index = 0, 0
        text, tip_text = {}, {}
        for i in range(number_of_cols):
            text[i], tip_text[i] = "", ""

        for stat in self.pop.pu_stats:
            number = Stats.do_stat(
                self.stat_dict,
                player=int(player_id),
                stat=stat,
                hand_instance=self.hand_instance,
            )
            if number:
                text[col_index] += number[3] + "\n"
                tip_text[col_index] += number[5] + " " + number[4] + "\n"
            else:
                text[col_index] += stat + "\n"
                tip_text[col_index] += stat + "\n"

            row_index += 1
            if row_index >= number_per_col:
                col_index += 1
                row_index = 0

        if row_index > 0:
            for i in range(number_per_col - row_index):
                # pad final column with blank lines
                text[col_index] += "\n"

        for i in text:
            contentlab = QLabel(text[i][:-1])
            Stats.do_tip(contentlab, tip_text[i][:-1])
            self.grid.addWidget(contentlab, 0, int(i))


def resolve_popup_class(pu_class: str) -> type | None:
    """Find the class named ``pu_class`` across the popup modules, or None."""
    # sys.modules, not __import__(__name__): imported as "fpdb_3_legacy.Popup"
    # the latter hands back the top-level package, which holds no popup class,
    # so every classic popup would silently degrade to the default one.
    class_to_return = getattr(sys.modules[__name__], pu_class, None)

    # If class not found in Popup module, try ModernPopup module
    if class_to_return is None:
        try:
            import fpdb_3_legacy.ModernPopup as ModernPopup

            # Try direct attribute access
            class_to_return = getattr(ModernPopup, pu_class, None)
            if class_to_return is None:
                # Try from MODERN_POPUP_CLASSES dict
                if hasattr(ModernPopup, "MODERN_POPUP_CLASSES"):
                    class_to_return = ModernPopup.MODERN_POPUP_CLASSES.get(pu_class)
        except (ImportError, AttributeError) as e:
            log.debug(f"Could not import ModernPopup classes: {e}")

    # If still not found, try the range-chart popup module (PT4 Nash grids).
    if class_to_return is None:
        try:
            import fpdb_3_legacy.RangeChartPopup as RangeChartPopup

            class_to_return = getattr(RangeChartPopup, pu_class, None)
        except (ImportError, AttributeError) as e:
            log.debug(f"Could not import RangeChartPopup classes: {e}")

    # Or the block-popup module (PT4 popup groups: info popups / text-grid charts).
    if class_to_return is None:
        try:
            import fpdb_3_legacy.BlockPopup as BlockPopup

            class_to_return = getattr(BlockPopup, pu_class, None)
        except (ImportError, AttributeError) as e:
            log.debug(f"Could not import BlockPopup classes: {e}")

    return class_to_return


def popup_factory(
    seat=None,
    stat_dict=None,
    win=None,
    pop=None,
    hand_instance=None,
    config=None,
    parent_popup=None,
    anchor_widget=None,
):
    # a factory function to discover the base type of the popup
    # and to return a class instance of the correct popup
    class_to_return = resolve_popup_class(pop.pu_class)

    # Fallback to default popup if class still not found
    if class_to_return is None:
        log.warning(f"Popup class '{pop.pu_class}' not found, falling back to default")
        class_to_return = default

    return class_to_return(
        seat,
        stat_dict,
        win,
        pop,
        hand_instance,
        config,
        parent_popup,
        anchor_widget,
    )
