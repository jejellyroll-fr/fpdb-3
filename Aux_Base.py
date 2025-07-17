#    Copyright 2008-2012,  Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
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
"""Base classes for auxiliary HUD elements like Mucked cards."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from PyQt5.QtGui import QMouseEvent

#    Standard Library modules
from loggingFpdb import get_logger

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hud")


def clamp_to_screen(x: int, y: int, width: int = 200, height: int = 100) -> tuple[int, int]:
    """Clamp window position to screen boundaries."""
    app = QApplication.instance()
    if app is None:
        return max(0, x), max(0, y)

    screen = app.primaryScreen()
    if screen is None:
        return max(0, x), max(0, y)

    geometry = screen.geometry()
    max_x = geometry.width() - width
    max_y = geometry.height() - height

    clamped_x = max(0, min(x, max_x))
    clamped_y = max(0, min(y, max_y))

    return clamped_x, clamped_y


### Aux_Base.py
# Some base classes for Aux_Hud, Mucked, and other aux-handlers.
# These classes were previously in Mucked, and have been split away
# for clarity
###

# FPDB


# This holds all card images in a nice lookup table. One instance is
# populated on the first run of AuxWindow.get_card_images() and all
# subsequent uses will have the same instance available.
deck = None

# This allows for a performance gain. Loading and parsing 53 SVG cards
# takes some time. If that is done at the first access of
# AuxWindow.get_card_images(), it can add a delay of several seconds.
# A pre-populated deck on the other hand grants instant access.


class AuxWindow:
    """Base class for an auxiliary window in the HUD."""

    def __init__(self, hud: Any, params: dict, config: Any) -> None:
        """Initialize the AuxWindow.

        Args:
            hud: The main HUD object.
            params: A dictionary of parameters for this window.
            config: The main configuration object.
        """
        self.hud = hud
        self.params = params
        self.config = config

    #   Override these methods as needed
    def update_data(self, *args: Any) -> None:
        """Update the data for the window."""

    def update_gui(self, *args: Any) -> None:
        """Update the GUI of the window."""

    def create(self, *args: Any) -> None:
        """Create the window."""

    def save_layout(self, *args: Any) -> None:
        """Save the layout of the window."""

    def move_windows(self, *args: Any) -> None:
        """Move the window."""

    def destroy(self) -> None:
        """Destroy the window."""
        with contextlib.suppress(Exception):
            self.container.destroy()

    ############################################################################
    #    Some utility routines useful for Aux_Windows
    #
    # Returns the number of places where cards were shown. This can be N
    # players + common cards
    def count_seats_with_cards(self, cards: dict) -> int:
        """Return the number of seats with shown cards in the list.

        'cards' is a dictionary with EVERY INVOLVED SEAT included;
        in addition, the unknown/unshown cards are marked with
        zeroes, not None.
        """
        return sum(seat != "common" and cards_tuple[0] != 0 for seat, cards_tuple in list(cards.items()))

    def get_id_from_seat(self, seat: int) -> str | None:
        """Determine player id from seat number, given stat_dict.

        hh_seats is a list of the actual seat numbers used in the hand history.
        Some sites (e.g. iPoker) miss out some seat numbers if max is <10,
        e.g. iPoker 6-max uses seats 1,3,5,6,8,10 NOT 1,2,3,4,5,6.
        """
        seat = self.hud.layout.hh_seats[seat]
        return next(
            (player_id for player_id, player_data in list(self.hud.stat_dict.items()) if seat == player_data["seat"]),
            None,
        )


class SeatWindow(QWidget):
    """A window for a single seat at the table."""

    def __init__(self, aw: AuxWindow | None = None, seat: int | None = None) -> None:
        """Initialize the SeatWindow.

        Args:
            aw: The parent AuxWindow.
            seat: The seat number for this window.
        """
        super().__init__(
            None,
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint,
        )
        self.lastPos = None
        self.aw = aw
        self.seat = seat
        self.resize(10, 10)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events."""
        if event.button() == Qt.LeftButton:
            self.button_press_left(event)
        elif event.button() == Qt.MiddleButton:
            self.button_press_middle(event)
        elif event.button() == Qt.RightButton:
            self.button_press_right(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events."""
        if event.button() == Qt.LeftButton:
            self.button_release_left(event)
        elif event.button() == Qt.MiddleButton:
            self.button_release_middle(event)
        elif event.button() == Qt.RightButton:
            self.button_release_right(event)

    def button_press_left(self, event: QMouseEvent) -> None:
        """Handle left mouse button press."""
        self.lastPos = event.globalPos()

    def button_press_middle(self, event: QMouseEvent) -> None:
        """Handle middle mouse button press."""

    def button_press_right(self, event: QMouseEvent) -> None:
        """Handle right mouse button press."""

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events."""
        if self.lastPos is not None:
            self.move(self.pos() + event.globalPos() - self.lastPos)
            self.lastPos = event.globalPos()

    def button_release_left(self, _event: QMouseEvent) -> None:
        """Handle left mouse button release."""
        self.lastPos = None
        self.aw.configure_event_cb(self, self.seat)

    def button_release_middle(self, event: QMouseEvent) -> None:
        """Handle middle mouse button release."""

    def button_release_right(self, event: QMouseEvent) -> None:
        """Handle right mouse button release."""

    def create_contents(self, *args: Any) -> None:
        """Create the contents of the window."""

    def update_contents(self, *args: Any) -> None:
        """Update the contents of the window."""


class AuxSeats(AuxWindow):
    """A super class to display an aux_window or a stat block at each seat."""

    def __init__(self, hud: Any, config: Any, params: dict) -> None:
        """Initialize the AuxSeats.

        Args:
            hud: The main HUD object.
            config: The main configuration object.
            params: A dictionary of parameters for this window.
        """
        super().__init__(hud, params, config)
        self.positions = {}  # dict of window positions. normalised for favourite seat and offset
        # but _not_ offset to the absolute screen position
        self.displayed = False  # the seat windows are displayed
        self.uses_timer = False  # the Aux_seats object uses a timer to control hiding
        self.timer_on = False  # bool = Ture if the timeout for removing the cards is on

        self.aw_class_window = SeatWindow  # classname to be used by the aw_class_window

    #    placeholders that should be overridden--so we don't throw errors
    def create_contents(self) -> None:
        """Create the contents of the windows."""

    def create_common(self, x: int, y: int) -> None:
        """Create the common card window."""

    def update_contents(self) -> None:
        """Update the contents of the windows."""

    def resize_windows(self) -> None:
        """Resize all windows."""
        # Resize calculation has already happened in HUD_main&hud.py
        # refresh our internal map to reflect these changes
        for i in list(range(1, self.hud.max + 1)):
            self.positions[i] = self.hud.layout.location[self.adj[i]]
        self.positions["common"] = self.hud.layout.common
        # and then move everything to the new places
        self.move_windows()

    def move_windows(self) -> None:
        """Move all windows to their correct positions."""
        # Ensure table coordinates are valid (not negative or off-screen)
        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50

        for i in list(range(1, self.hud.max + 1)):
            pos_x = self.positions[i][0] + table_x
            pos_y = self.positions[i][1] + table_y
            clamped_x, clamped_y = clamp_to_screen(pos_x, pos_y)
            self.m_windows[i].move(clamped_x, clamped_y)

        common_x = self.hud.layout.common[0] + table_x
        common_y = self.hud.layout.common[1] + table_y
        clamped_common_x, clamped_common_y = clamp_to_screen(common_x, common_y)
        self.m_windows["common"].move(clamped_common_x, clamped_common_y)

    def create(self) -> None:
        """Create all seat windows."""
        self.adj = self.adj_seats()
        self.m_windows = {}  # windows to put the card/hud items in
        for i in [*list(range(1, self.hud.max + 1)), "common"]:
            if i == "common":
                #    The common window is different from the others. Note that it needs to
                #    get realized, shown, topified, etc. in create_common
                #    self.hud.layout.xxxxx is updated here after scaling, to ensure
                #    layout and positions are in sync
                (x, y) = self.hud.layout.common
                self.m_windows[i] = self.create_common(x, y)
                self.hud.layout.common = self.create_scale_position(x, y)
            else:
                (x, y) = self.hud.layout.location[self.adj[i]]
                self.m_windows[i] = self.aw_class_window(self, i)
                self.positions[i] = self.create_scale_position(x, y)
                table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
                table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
                pos_x = max(0, self.positions[i][0] + table_x)
                pos_y = max(0, self.positions[i][1] + table_y)
                self.m_windows[i].move(pos_x, pos_y)
                self.hud.layout.location[self.adj[i]] = self.positions[i]
                if "opacity" in self.params:
                    self.m_windows[i].setWindowOpacity(float(self.params["opacity"]))

            # main action below - fill the created window with content
            #    the create_contents method is supplied by the subclass
            #      for hud's this is probably Aux_Hud.stat_window
            self.create_contents(self.m_windows[i], i)

            self.m_windows[i].create()  # ensure there is a native window handle for topify
            self.hud.table.topify(self.m_windows[i])
            if not self.uses_timer:
                self.m_windows[i].show()

        self.hud.layout.height = self.hud.table.height
        self.hud.layout.width = self.hud.table.width

    def create_scale_position(self, x: int, y: int) -> tuple[int, int]:
        """Scale a position according to the current table size.

        For a given x/y, scale according to current height/width vs. reference
        height/width. This method is needed for create (because the table may not be
        the same size as the layout in config).

        Any subsequent resizing of this table will be handled through
        hud_main.idle_resize.
        """
        x_scale = 1.0 * self.hud.table.width / self.hud.layout.width
        y_scale = 1.0 * self.hud.table.height / self.hud.layout.height
        return int(x * x_scale), int(y * y_scale)

    def update_gui(self, _new_hand_id: Any) -> None:
        """Update the gui, LDO."""
        for i in list(self.m_windows.keys()):
            self.update_contents(self.m_windows[i], i)
        # reload latest block positions, in case another aux has changed them
        # these lines allow the propagation of block-moves across
        # the hud and mucked handlers for this table
        self.resize_windows()

    #   Methods likely to be of use for any SeatWindow implementation
    def destroy(self) -> None:
        """Destroy all of the seat windows."""
        with contextlib.suppress(AttributeError):
            for i in list(self.m_windows.keys()):
                self.m_windows[i].destroy()
                del self.m_windows[i]

    #   Methods likely to be useful for mucked card windows (or similar) only
    def hide(self) -> None:
        """Hide the seat windows."""
        for _i, w in list(self.m_windows.items()):
            if w is not None:
                w.hide()
        self.displayed = False

    def save_layout(self, *_args: Any) -> None:
        """Save new layout back to the aux element in the config file.

        This method is overridden in the specific aux because
        the HUD's controlling stat boxes set the seat positions and
        the mucked card aux's control the common location.
        This class method would only be valid for an aux which has full control
        over all seat and common locations.
        """
        log.error("AuxSeats.save_layout called - this shouldn't happen")
        log.error("save_layout method should be handled in the aux")

    def configure_event_cb(self, widget: SeatWindow, i: int | str) -> None:
        """Update the current location for each statblock.

        This method is needed to record moves for an individual block.
        Move/resize also end up in here due to it being a configure.
        This is not optimal, but isn't easy to work around. fixme.
        """
        if i:
            new_abs_position = widget.pos()  # absolute value of the new position
            # Ensure table coordinates are valid for calculation
            table_x = self.hud.table.x if self.hud.table.x is not None else 0
            table_y = self.hud.table.y if self.hud.table.y is not None else 0
            new_position = (
                new_abs_position.x() - table_x,
                new_abs_position.y() - table_y,
            )
            self.positions[i] = new_position  # write this back to our map
            if i != "common":
                self.hud.layout.location[self.adj[i]] = new_position  # update the hud-level dict,
                # so other aux can be told
            else:
                self.hud.layout.common = new_position

    def adj_seats(self) -> list[int]:
        """Determine how to adjust seating arrangements.

        If a "preferred seat" is set in the hud layout configuration.
        Need range here, not xrange -> need the actual list.
        """
        adj = list(range(self.hud.max + 1))  # default seat adjustments = no adjustment

        #   does the user have a fav_seat? if so, just get out now
        if self.hud.site_parameters["fav_seat"][self.hud.max] == 0:
            return adj

        # find the hero's actual seat

        actual_seat = None
        for key in self.hud.stat_dict:
            if self.hud.stat_dict[key]["screen_name"] == self.config.supported_sites[self.hud.site].screen_name:
                # Seat from stat_dict is the seat num recorded in the hand history and database
                # For tables <10-max, some sites omit some seat nums (e.g. iPoker 6-max uses 1,3,5,6,8,10)
                # The seat nums in the hh from the site are recorded in config file for each layout, and available
                # here as the self.layout.hh_seats list
                #    (e.g. for iPoker - [None,1,3,5,6,8,10];
                #      for most sites-  [None, 1,2,3,4,5,6]
                # we need to match 'seat' from hand history with the postion in the list, as the hud
                #  always numbers its stat_windows using consecutive numbers (e.g. 1-6)

                for i in range(1, self.hud.max + 1):
                    if self.hud.layout.hh_seats[i] == self.hud.stat_dict[key]["seat"]:
                        actual_seat = i
                        break

        if not actual_seat:  # this shouldn't happen because we don't create huds if the hero isn't seated.
            log.error("Error finding hero seat.")
            return adj

        for i in range(self.hud.max + 1):
            j = actual_seat + i
            if j > self.hud.max:
                j = j - self.hud.max
            adj[j] = self.hud.site_parameters["fav_seat"][self.hud.max] + i
            if adj[j] > self.hud.max:
                adj[j] = adj[j] - self.hud.max

        return adj
