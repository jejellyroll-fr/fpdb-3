#    Copyright 2008-2012,  Ray E. Barker
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

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent

#    Standard Library modules
from fpdb_3_legacy.loggingFpdb import get_logger, hud_trace

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hud_main")


def _drag_trace(msg: str, *args: object) -> None:
    """Emit a drag diagnostic on the FPDB_HUD_TRACE channel (no-op otherwise)."""
    hud_trace(msg, *args)


# True while a HUD window is being dragged. HUD_main.check_tables polls this to
# suspend its 800ms geometry scan + window re-raise (topify), which on macOS
# re-orders the dragged window mid-drag and makes the drag stutter.
_drag_active = False


def is_drag_active() -> bool:
    """Whether a HUD window is currently being dragged."""
    return _drag_active


def set_drag_active(active: bool) -> None:
    """Mark drag start/stop (set from SeatWindow press/release)."""
    global _drag_active
    _drag_active = active


def _nearest_screen(app: Any, x: int, y: int) -> Any:
    """Return the screen whose geometry is closest to the point (x, y).

    Used as a fallback when a point falls outside every screen, so a window can
    still be clamped back onto a visible monitor instead of staying off-screen.
    """
    screens = app.screens()
    if not screens:
        return None

    def distance(screen: Any) -> int:
        g = screen.geometry()
        # Distance from the point to the screen rectangle (0 if inside).
        dx = max(g.left() - x, 0, x - g.right())
        dy = max(g.top() - y, 0, y - g.bottom())
        return dx * dx + dy * dy

    return min(screens, key=distance)


def clamp_to_screen(x: int, y: int, width: int = 200, height: int = 100) -> tuple[int, int]:
    """Clamp a window position to fit within the visible screen area.

    Ensures that the given coordinates and window size do not extend beyond the boundaries of the screen.

    Args:
        x: The x-coordinate of the window.
        y: The y-coordinate of the window.
        width: The width of the window (default is 200).
        height: The height of the window (default is 100).

    Returns:
        tuple[int, int]: The clamped (x, y) coordinates within the screen bounds.
    """
    from fpdb_3_legacy.loggingFpdb import get_logger

    log = get_logger("hud")

    app = QApplication.instance()
    if app is None:
        log.warning("No QApplication instance for screen clamping")
        return max(0, x), max(0, y)

    # Try to find the screen containing the point
    screen = app.screenAt(QPoint(x, y))
    if screen is None:
        # Point is off every screen. Don't leave the window stranded off-screen:
        # fall back to the geometrically nearest screen and clamp onto it. This
        # keeps multi-monitor setups working (a point on a secondary screen is
        # returned by screenAt above) while pulling truly off-screen windows back.
        screen = _nearest_screen(app, x, y)
        if screen is None:
            log.warning("No screen available for clamping point (%d,%d)", x, y)
            return max(0, x), max(0, y)
        log.warning(
            "Point (%d,%d) not on any screen, clamping to nearest screen: %s",
            x,
            y,
            screen.name(),
        )
    else:
        log.debug("Point (%d,%d) found on screen: %s", x, y, screen.name())

    geometry = screen.geometry()
    log.info(
        "Screen geometry: X=%d, Y=%d, Width=%d, Height=%d",
        geometry.x(),
        geometry.y(),
        geometry.width(),
        geometry.height(),
    )

    # Clamp to the actual screen boundaries (including offset for extended screens)
    min_x = geometry.x()
    max_x = geometry.x() + geometry.width() - width
    min_y = geometry.y()
    max_y = geometry.y() + geometry.height() - height

    clamped_x = max(min_x, min(x, max_x))
    clamped_y = max(min_y, min(y, max_y))

    if clamped_x != x or clamped_y != y:
        log.info(
            "CLAMPING: Original (%d,%d) -> Clamped (%d,%d) [Screen bounds: %d-%d, %d-%d]",
            x,
            y,
            clamped_x,
            clamped_y,
            min_x,
            max_x,
            min_y,
            max_y,
        )

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
        self.container: Any | None = None

    #   Override these methods as needed
    def update_data(self, *args: Any) -> None:
        """Update the data for the auxiliary window.

        This method is a placeholder for updating the window's data.
        """

    def refresh_stats(self, hand_id: Any) -> None:
        """Redraw from the statistics already on the hud, without a new hand.

        Called when another table dealt a hand: the aggregated statistics have
        moved but this table's own hand has not. Only a statistics HUD has
        anything to redo, so this does nothing by default -- an aux window that
        reacts to a *new* hand must not act here. The mucked-cards windows are
        why the contract is explicit rather than reusing update_gui: theirs
        appends a row and re-shows the cards, so a statistics refresh would
        replay a hand the player already saw.
        """

    def update_gui(self, *args: Any) -> None:
        """Update the graphical user interface for the auxiliary window.

        This method is a placeholder for updating the window's GUI elements.
        """

    def create(self, *args: Any) -> None:
        """Create the auxiliary window.

        This method is a placeholder for creating the window and its resources.
        """

    def save_layout(self, *args: Any) -> None:
        """Save the layout of the auxiliary window.

        This method is a placeholder for saving the current layout configuration.
        """

    def move_windows(self, *args: Any) -> None:
        """Move all auxiliary windows to their correct positions.

        This method is a placeholder for moving windows and should be overridden in subclasses.
        """

    def destroy(self) -> None:
        """Destroy the window and release its resources.

        Attempts to destroy the window container, suppressing any exceptions that may occur.
        """
        if self.container is not None:
            with contextlib.suppress(Exception):
                self.container.destroy()

    def kill(self) -> None:
        """Kill this auxiliary window.

        HUD_main historically calls ``kill`` on aux handlers, while the base
        class exposed ``destroy``. Keep both names so profile/stat-set switches
        can reliably tear down old windows.
        """
        self.destroy()

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

    def get_id_from_seat(self, seat: int) -> int | str | None:
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

    def __init__(self, aw: Any = None, seat: int | str | None = None) -> None:
        """Initialize the SeatWindow.

        Args:
            aw: The parent AuxWindow.
            seat: The seat number for this window.
        """
        # NB: WindowDoesNotAcceptFocus is intentionally NOT set here. It blocks the
        # native window move (startSystemMove), which is the only smooth way to
        # drag a frameless stay-on-top window on macOS. WA_ShowWithoutActivating
        # (below) keeps the HUD from stealing focus when it is shown.
        super().__init__(
            None,
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.lastPos: QPoint | None = None
        # True while the OS is handling the drag via startSystemMove(); used to
        # skip the manual move() fallback so the window is not moved twice.
        self._system_move_active = False
        self.aw = aw
        self.seat = seat
        self.resize(10, 10)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events for the seat window.

        Responds to left, middle, and right mouse button presses by calling the corresponding handler methods.

        Args:
            event: The mouse event containing button and position information.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.button_press_left(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.button_press_middle(event)
        elif event.button() == Qt.MouseButton.RightButton:
            self.button_press_right(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events for the seat window.

        Calls the appropriate handler method based on which mouse button was released.

        Args:
            event: The mouse event containing button and position information.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.button_release_left(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.button_release_middle(event)
        elif event.button() == Qt.MouseButton.RightButton:
            self.button_release_right(event)

    def button_press_left(self, event: QMouseEvent) -> None:
        """Start dragging the window.

        Records the cursor's global position and grabs the mouse. The grab is the
        key part: these HUD windows are frameless and WindowDoesNotAcceptFocus, so
        (a) macOS startSystemMove() is a no-op for them, and (b) without a grab the
        window stops receiving move events the moment it slides out from under the
        cursor. grabMouse() keeps every move/release event coming to this widget
        until the button is released, which makes the manual drag reliable on all
        platforms.

        Qt6: globalPosition() returns a QPointF with correct high-DPI/Retina
        coordinates, rounded to a QPoint.
        """
        self.lastPos = event.globalPosition().toPoint()
        self._press_origin = self.pos()
        set_drag_active(True)
        # Prefer the native window move (smooth on macOS). Fall back to a manual
        # grabMouse drag only where the platform can't start a system move.
        self._system_move_active = False
        handle = self.windowHandle()
        if handle is not None and handle.startSystemMove():
            self._system_move_active = True
        else:
            self.grabMouse()
        _drag_trace("drag-start seat=%s native=%s pos=%s", getattr(self, "seat", "?"),
                    self._system_move_active, (self.lastPos.x(), self.lastPos.y()))

    def button_press_middle(self, event: QMouseEvent) -> None:
        """Handle middle mouse button press.

        This method is a placeholder for handling middle mouse button press events.

        Args:
            event: The mouse event containing button and position information.
        """

    def button_press_right(self, event: QMouseEvent) -> None:
        """Handle right mouse button press.

        This method is a placeholder for handling right mouse button press events.

        Args:
            event: The mouse event containing button and position information.
        """

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events for the seat window.

        Moves the window according to the mouse movement if a drag is in progress.

        Args:
            event: The mouse event containing button and position information.
        """
        # When the OS is driving a native move, do nothing here (moving again
        # would fight it). Otherwise move manually by the cursor delta; the
        # button_press_left grab keeps events flowing even off-window.
        if self._system_move_active:
            return
        if self.lastPos is not None:
            global_pos = event.globalPosition().toPoint()
            self.move(self.pos() + global_pos - self.lastPos)
            self.lastPos = global_pos

    def button_release_left(self, _event: QMouseEvent) -> None:
        """Handle left mouse button release.

        Resets the last mouse position and triggers the configuration event callback.

        Args:
            _event: The mouse event containing button and position information.
        """
        # Only the manual drag holds a mouse grab; the native move does not.
        if self.lastPos is not None and not self._system_move_active:
            self.releaseMouse()
        self.lastPos = None
        was_native = self._system_move_active
        self._system_move_active = False
        set_drag_active(False)
        # Persist only on a real move. A plain click (press+release, no drag)
        # must not overwrite the stored position with the current spot, which is
        # what used to fill the position store with stale offsets.
        moved = self.pos() != getattr(self, "_press_origin", self.pos())
        final = (self.pos().x(), self.pos().y())
        _drag_trace("drag-end seat=%s block=%s native=%s moved=%s final=%s", getattr(self, "seat", "?"),
                    getattr(self, "block_key", None), was_native, moved, final)
        if moved and self.aw is not None and self.seat is not None:
            self.aw.configure_event_cb(self, self.seat)

    def button_release_middle(self, event: QMouseEvent) -> None:
        """Handle middle mouse button release.

        This method is a placeholder for handling middle mouse button release events.

        Args:
            event: The mouse event containing button and position information.
        """

    def button_release_right(self, event: QMouseEvent) -> None:
        """Handle right mouse button release.

        This method is a placeholder for handling right mouse button release events.

        Args:
            event: The mouse event containing button and position information.
        """

    def create_contents(self, *args: Any) -> None:
        """Create the contents of the seat window.

        This method is a placeholder for populating the window with its contents.
        """

    def update_contents(self, *args: Any) -> None:
        """Update the contents of the seat window.

        This method is a placeholder for updating the window's contents.
        """


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
        self.positions: dict[Any, tuple[int, int]] = {}
        # but _not_ offset to the absolute screen position
        self.displayed = False  # the seat windows are displayed
        self.uses_timer = False  # the Aux_seats object uses a timer to control hiding
        self.timer_on = False  # bool = True if the timeout for removing the cards is on

        self.aw_class_window = SeatWindow  # classname to be used by the aw_class_window

    #    placeholders that should be overridden--so we don't throw errors
    def create_contents(self, *_args: Any) -> None:
        """Create the contents for each seat window.

        This method is a placeholder and should be overridden to populate each seat window with its contents.
        """

    def create_common(self, x: int, y: int) -> Any:
        """Create the common window at the specified position.

        This method is a placeholder and should be overridden to create the common window at the given coordinates.

        Args:
            x: The x-coordinate for the common window.
            y: The y-coordinate for the common window.
        """

    def update_contents(self, *_args: Any) -> None:
        """Update the contents for each seat window.

        This method is a placeholder and should be overridden to update the contents of each seat window.
        """

    def resize_windows(self) -> None:
        """Resize and reposition all HUD windows.

        Updates the internal map of window positions based on the latest table and layout dimensions,
        then moves all windows accordingly.
        """
        log.debug("RESIZING HUD WINDOWS - Table dimensions: %dx%d", self.hud.table.width, self.hud.table.height)
        # Resize calculation has already happened in HUD_main&hud.py
        # refresh our internal map to reflect these changes
        for i in list(range(1, self.hud.max + 1)):
            old_pos = self.positions.get(i, (0, 0))
            self.positions[i] = self.hud.layout.location[self.adj[i]]
            log.debug(
                "Seat %d position updated: (%d,%d) -> (%d,%d)",
                i,
                old_pos[0],
                old_pos[1],
                self.positions[i][0],
                self.positions[i][1],
            )
        old_common = self.positions.get("common", (0, 0))
        self.positions["common"] = self.hud.layout.common
        log.debug(
            "Common position updated: (%d,%d) -> (%d,%d)",
            old_common[0],
            old_common[1],
            self.positions["common"][0],
            self.positions["common"][1],
        )
        # and then move everything to the new places
        self.move_windows()

    def move_windows(self) -> None:
        """Move all seat and common windows to their correct positions.

        Calculates the absolute positions for each window based on the table's current coordinates and layout,
        clamps them to the screen, and moves the windows accordingly.
        """
        # Ensure table coordinates are valid (not negative or off-screen)
        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50

        log.debug(
            "MOVING HUD WINDOWS - Table position: X=%d, Y=%d (from table.x=%s, table.y=%s)",
            table_x,
            table_y,
            self.hud.table.x,
            self.hud.table.y,
        )

        for i in list(range(1, self.hud.max + 1)):
            pos_x = self.positions[i][0] + table_x
            pos_y = self.positions[i][1] + table_y
            clamped_x, clamped_y = clamp_to_screen(pos_x, pos_y)
            log.debug(
                "Moving seat %d window: Layout pos (%d,%d) + Table pos (%d,%d) = Final pos (%d,%d) -> Clamped (%d,%d)",
                i,
                self.positions[i][0],
                self.positions[i][1],
                table_x,
                table_y,
                pos_x,
                pos_y,
                clamped_x,
                clamped_y,
            )
            self.m_windows[i].move(clamped_x, clamped_y)

        common_x = self.hud.layout.common[0] + table_x
        common_y = self.hud.layout.common[1] + table_y
        clamped_common_x, clamped_common_y = clamp_to_screen(common_x, common_y)
        log.debug(
            "Moving common window: Layout pos (%d,%d) + Table pos (%d,%d) = Final pos (%d,%d) -> Clamped (%d,%d)",
            self.hud.layout.common[0],
            self.hud.layout.common[1],
            table_x,
            table_y,
            common_x,
            common_y,
            clamped_common_x,
            clamped_common_y,
        )
        self.m_windows["common"].move(clamped_common_x, clamped_common_y)

    def create(self) -> None:
        """Create and initialize all seat and common windows for the HUD.

        Sets up the window objects for each seat and the common area,
        positions them according to the current layout and table size, and displays them as needed.
        """
        log.debug("=== AUX_BASE CREATE() METHOD CALLED ===")
        self.adj = self.adj_seats()
        self.m_windows: dict[Any, Any] = {}
        window_keys: list[int | str] = [*range(1, self.hud.max + 1), "common"]
        for i in window_keys:
            if i == "common":
                #    The common window is different from the others. Note that it needs to
                #    get realized, shown, topified, etc. in create_common
                #    self.hud.layout.xxxxx is updated here after scaling, to ensure
                #    layout and positions are in sync
                (x, y) = self.hud.layout.common
                self.m_windows[i] = self.create_common(x, y)
                self.hud.layout.common = self.create_scale_position(x, y)
            else:
                if not isinstance(i, int):
                    log.warning("Ignoring unexpected HUD window key during creation: %r", i)
                    continue
                (x, y) = self.hud.layout.location[self.adj[i]]
                log.debug("Seat %s: Loading position from layout: (%s, %s)", i, x, y)
                self.m_windows[i] = self.aw_class_window(self, i)
                self.positions[i] = self.create_scale_position(x, y)
                table_x = self.hud.table.x if self.hud.table.x is not None else 0
                table_y = self.hud.table.y if self.hud.table.y is not None else 0
                pos_x = max(0, self.positions[i][0] + table_x)
                pos_y = max(0, self.positions[i][1] + table_y)
                clamped_x, clamped_y = clamp_to_screen(pos_x, pos_y)
                log.debug(
                    "=== AUX_BASE POSITIONING === Seat %s: table(%s, %s) + relative(%s, %s) = final(%s, %s) -> Clamped(%s, %s)",
                    i,
                    table_x,
                    table_y,
                    self.positions[i][0],
                    self.positions[i][1],
                    pos_x,
                    pos_y,
                    clamped_x,
                    clamped_y,
                )
                self.m_windows[i].move(clamped_x, clamped_y)
                # Verify position after move
                actual_pos = self.m_windows[i].pos()
                log.debug(
                    "=== POSITION AFTER MOVE === Seat %s: requested(%s, %s) -> actual(%s, %s)",
                    i,
                    pos_x,
                    pos_y,
                    actual_pos.x(),
                    actual_pos.y(),
                )
                self.hud.layout.location[self.adj[i]] = self.positions[i]
                if "opacity" in self.params:
                    self.m_windows[i].setWindowOpacity(float(self.params["opacity"]))

            # main action below - fill the created window with content
            #    the create_contents method is supplied by the subclass
            #      for hud's this is probably Aux_Hud.stat_window
            self.create_contents(self.m_windows[i], i)

            self.m_windows[i].create()  # ensure there is a native window handle for topify
            log.debug(
                "=== AUX_BASE CALLING TOPIFY === window[%d]=%s, table=%s",
                i,
                self.m_windows[i],
                self.hud.table.title if hasattr(self.hud.table, "title") else "NO_TITLE",
            )
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
        lw, lh = self.hud.layout.width, self.hud.layout.height

        if lw == 0 or lh == 0:
            msg = "Layout width/height cannot be zero when scaling positions"
            raise ValueError(msg)

        x_scale = self.hud.table.width / lw
        y_scale = self.hud.table.height / lh

        scaled_x = int(x * x_scale)
        scaled_y = int(y * y_scale)

        log.debug(
            "=== SCALING DEBUG === Original(%d,%d) Layout(%dx%d) Table(%dx%d) Scale(%.2f,%.2f) Result(%d,%d)",
            x,
            y,
            lw,
            lh,
            self.hud.table.width,
            self.hud.table.height,
            x_scale,
            y_scale,
            scaled_x,
            scaled_y,
        )

        return scaled_x, scaled_y

    def update_gui(self, _new_hand_id: Any) -> None:
        """Update the graphical user interface for all seat windows.

        Calls the update_contents method for each seat window and
        resizes windows to reflect any changes in block positions.
        """
        for i in list(self.m_windows.keys()):
            self.update_contents(self.m_windows[i], i)
        # reload latest block positions, in case another aux has changed them
        # these lines allow the propagation of block-moves across
        # the hud and mucked handlers for this table
        self.resize_windows()

    #   Methods likely to be of use for any SeatWindow implementation
    def destroy(self) -> None:
        """Destroy all seat and common windows for the HUD.

        Iterates through all managed windows, destroys each one, and removes it from the internal dictionary.
        """
        with contextlib.suppress(AttributeError):
            for i, window in list(self.m_windows.items()):
                if window is not None:
                    with contextlib.suppress(Exception):
                        window.hide()
                    with contextlib.suppress(Exception):
                        window.close()
                    with contextlib.suppress(Exception):
                        window.destroy()
                    with contextlib.suppress(Exception):
                        window.deleteLater()
                del self.m_windows[i]
        self.displayed = False
        self.timer_on = False

    def kill(self) -> None:
        """Kill all managed seat/common windows."""
        self.destroy()

    #   Methods likely to be useful for mucked card windows (or similar) only
    def hide(self) -> None:
        """Hide all seat and common windows for the HUD.

        Iterates through all managed windows and hides each one, updating the displayed state.
        """
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
        log.warning("AuxSeats.save_layout called - save_layout method should be handled in the aux")

    def configure_event_cb(self, widget: SeatWindow, i: Any) -> None:
        """Update the current location for each statblock.

        This method is needed to record moves for an individual block.
        Move/resize also end up in here due to it being a configure.
        This is not optimal, but isn't easy to work around. fixme.
        """
        if i:
            new_abs_position = widget.pos()  # absolute value of the new position
            # Use the exact same table reference as move_windows() so the saved
            # relative position round-trips back to where the user dropped it.
            # (A mismatch here shifted the block off the table on redisplay.)
            table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
            table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
            new_position = (
                new_abs_position.x() - table_x,
                new_abs_position.y() - table_y,
            )
            log.debug(
                "Seat %s: Position updated - abs(%s, %s) - table(%s, %s) = relative(%s, %s)",
                i,
                new_abs_position.x(),
                new_abs_position.y(),
                table_x,
                table_y,
                new_position[0],
                new_position[1],
            )
            self.positions[i] = new_position  # write this back to our map
            slot: int | str
            if isinstance(i, int):
                slot = self.adj[i]
                self.hud.layout.location[slot] = new_position  # update the hud-level dict,
                # so other aux can be told
            elif i == "common":
                slot = "common"
                self.hud.layout.common = new_position
            else:
                log.warning("Ignoring unexpected HUD seat identifier while saving position: %r", i)
                return
            # Hud.resize_windows() rebuilds layout.location from the frozen
            # reference positions, so a drag that only touched layout.location
            # was undone by the next table move/resize.
            table_w = getattr(self.hud.table, "width", 0) or 0
            table_h = getattr(self.hud.table, "height", 0) or 0
            self._update_reference_position(self.hud, slot, new_position, table_w, table_h)
            self._propagate_to_open_huds(slot, new_position)
            scoped_override = self._persist_position_override(slot, new_position)
            # configure_event_cb only fires on a genuine drag-release (see
            # SeatWindow.button_release_left, gated on moved==True), so this
            # writes the config at most once per drag. Block-window HUDs already
            # auto-persist to the positions store; this makes the classic
            # one-window-per-seat HUD persist too, instead of keeping drags in
            # memory only until the "Save HUD Layout" menu is used.
            if not scoped_override:
                self._propagate_to_shared_layout(slot, new_position)
                self._persist_layout_after_drag()

    def _persist_position_override(self, seat: Any, position: tuple[int, int]) -> bool:
        """Persist a scoped user override when the concrete HUD supports it."""
        return False

    def _persist_layout_after_drag(self) -> None:
        """Write the just-dragged layout to HUD_config.xml immediately.

        Reuses the exact path the "Save HUD Layout" menu uses (each aux writes
        its positions into the config DOM, then the file is flushed), so the
        round-trip and the hist_seat ring are preserved. Failures are swallowed:
        a config-save hiccup must never break the drag or the HUD.
        """
        hud = getattr(self, "hud", None)
        save_layout = getattr(hud, "save_layout", None)
        if not callable(save_layout):
            return
        try:
            save_layout()
            log.info("HUD layout auto-saved after drag (%s-max, site=%s)", getattr(hud, "max", "?"), getattr(hud, "site", "?"))
        except Exception:
            log.exception("Auto-save of HUD layout after drag failed; use the Save HUD Layout menu")

    def _propagate_to_shared_layout(self, seat: Any, position: tuple[int, int]) -> None:
        """Mirror a dragged position onto the site's shared layout set.

        A HUD deep-copies its layout when it is created, so a drag that only
        updates this HUD's copy is lost on the next table: a table opened later
        with the same layout would fall back to the un-dragged positions. Writing
        through to the shared layout_set makes those new tables inherit the drag
        (permanent persistence still happens via the "Save Layout" menu).
        """
        layout_set = getattr(self.hud, "layout_set", None)
        shared = getattr(layout_set, "layout", {}).get(self.hud.max) if layout_set is not None else None
        if shared is None:
            return
        # ``position`` is in the current table's pixel space, but the shared layout
        # keeps its own reference width/height and create_scale_position() re-scales
        # from those when the next HUD is built. Convert back into the shared
        # layout's space so the drop point round-trips instead of being scaled a
        # second time by stale dimensions.
        ref = self._to_shared_layout_space(position, shared)
        with contextlib.suppress(Exception):
            if seat == "common":
                shared.common = ref
            else:
                shared.location[seat] = ref

    def _update_reference_position(
        self,
        hud: Any,
        seat: Any,
        position: tuple[int, int],
        table_w: int,
        table_h: int,
    ) -> None:
        """Store ``position`` in ``hud``'s frozen reference space.

        Hud.resize_windows() rebuilds layout.location from ref_layout_locations
        scaled by table/ref, so a dragged position that is not mirrored here is
        silently reverted the next time the table moves or is resized.
        """
        ref_w = getattr(hud, "ref_layout_width", 0) or 0
        ref_h = getattr(hud, "ref_layout_height", 0) or 0
        if not (ref_w and ref_h and table_w and table_h):
            return  # reference not frozen yet: nothing to keep in sync
        ref = (int(position[0] * ref_w / table_w), int(position[1] * ref_h / table_h))

        if seat == "common":
            if getattr(hud, "ref_layout_common", None) is not None:
                hud.ref_layout_common = ref
            return
        ref_locations = getattr(hud, "ref_layout_locations", None)
        if ref_locations and isinstance(seat, int) and 0 <= seat < len(ref_locations):
            ref_locations[seat] = ref

    def _propagate_to_open_huds(self, seat: Any, position: tuple[int, int]) -> None:
        """Apply a drag to the other tables already showing this layout.

        Every HUD deep-copies its layout when it is created, so writing through
        to the shared layout_set only reaches tables opened *later*. Tables
        already on screen keep their own copy and used to ignore the drag until
        they were restarted -- exactly the multi-tabling case where adjusting one
        table is expected to line the others up too.

        Positions are stored per layout slot (hero-anchored), which means the
        same slot is the same place on every table even when the hero sits in a
        different seat, so the value transfers directly; only a table-size
        difference needs scaling.

        Two tables count as the same arrangement only when their whole
        ``HudPositionScope`` matches -- room, game, cash/tournament, seats,
        profile and layout. Pairing on the layout set alone made CoinPoker's
        PLO4 and AoF PLO4 tables, which share one layout, drag each other
        around. A HUD with no scope propagates to nothing: without an identity
        it cannot claim to be the same arrangement as anything else.
        """
        parent = getattr(self.hud, "parent", None)
        hud_dict = getattr(parent, "hud_dict", None)
        if not hud_dict:
            return

        source_scope = getattr(self.hud, "position_scope", None)
        if source_scope is None:
            log.debug("Drag not mirrored: table %r has no position scope", getattr(self.hud, "table_name", "?"))
            return

        src_w = getattr(self.hud.table, "width", 0) or 0
        src_h = getattr(self.hud.table, "height", 0) or 0

        for other in list(hud_dict.values()):
            if other is self.hud:
                continue
            # Seat count is part of the scope, so it needs no separate test.
            if getattr(other, "position_scope", None) != source_scope:
                continue
            try:
                self._apply_position_to_hud(other, seat, position, src_w, src_h)
            except Exception:  # intentional broad catch: never break the drag
                log.exception("Could not apply the drag to table %r", getattr(other, "table_name", "?"))

    def _apply_position_to_hud(
        self,
        other: Any,
        seat: Any,
        position: tuple[int, int],
        src_w: int,
        src_h: int,
    ) -> None:
        """Place ``seat`` at ``position`` on ``other`` and re-lay its windows."""
        dst_w = getattr(other.table, "width", 0) or src_w
        dst_h = getattr(other.table, "height", 0) or src_h
        if src_w and src_h and dst_w and dst_h and (src_w, src_h) != (dst_w, dst_h):
            dst = (int(position[0] * dst_w / src_w), int(position[1] * dst_h / src_h))
        else:
            dst = position

        if seat == "common":
            other.layout.common = dst
        else:
            other.layout.location[seat] = dst
        self._update_reference_position(other, seat, dst, dst_w, dst_h)

        # Re-place through the aux (not Hud.resize_windows, which would rebuild
        # layout.location from the reference and undo what we just set).
        for aux in getattr(other, "aux_windows", []):
            with contextlib.suppress(Exception):
                aux.resize_windows()
        log.info(
            "HUD drag mirrored to table %r: slot %s -> %s",
            getattr(other, "table_name", "?"),
            seat,
            dst,
        )

    def _to_shared_layout_space(self, position: tuple[int, int], shared: Any) -> tuple[int, int]:
        table_w = getattr(self.hud.table, "width", 0) or 0
        table_h = getattr(self.hud.table, "height", 0) or 0
        shared_w = getattr(shared, "width", 0) or 0
        shared_h = getattr(shared, "height", 0) or 0
        if not (table_w and table_h and shared_w and shared_h):
            return position  # dimensions unknown: store as-is
        return (int(position[0] * shared_w / table_w), int(position[1] * shared_h / table_h))

    def _config_ring(self) -> list[Any]:
        """The site-configured available-seat ring (visual slot -> physical seat).

        Snapshotted the first time it is read, before any per-hand synthesis
        overwrites ``layout.hh_seats``, so later hands always rebuild from the
        original config rather than from a previous synthesis.
        """
        layout = self.hud.layout
        ring = getattr(layout, "config_hh_seats", None)
        if ring is None:
            ring = list(layout.hh_seats)
            layout.config_hh_seats = ring
        return ring

    def _occupied_seats(self) -> list[int]:
        """Physical seat numbers actually in play this hand, sorted ascending."""
        seats = set()
        for data in self.hud.stat_dict.values():
            seat = data.get("seat")
            # `if seat` would read seat 0 as an empty chair and drop that player
            # from the layout entirely, leaving them with no stat panel while
            # everyone else got one. Only a genuinely absent seat is skipped.
            if seat is not None:
                seats.add(int(seat))
        return sorted(seats)

    def _effective_hh_seats(self) -> list[Any]:
        """Map visual slot (1..max) -> physical HH seat, robust to sparse numbering.

        Prefer the site-configured ring when it already covers every occupied
        seat -- iPoker 6/9-max (1,3,5,6,8,10) and every standard site (1..N).
        Otherwise synthesise a ring from the occupied seats sorted ascending, so
        table sizes that have no hist_seat table in the config (iPoker Twister
        2/3-max, 5-max, ...) still assign players to slots instead of erroring
        out and dropping the whole HUD onto the wrong seats.
        """
        max_seats = self.hud.max
        ring = self._config_ring()
        occupied = self._occupied_seats()
        covered = {ring[i] for i in range(1, max_seats + 1) if i < len(ring) and ring[i] is not None}
        if occupied and set(occupied) <= covered:
            return list(ring)

        synth: list[Any] = [None] * (max_seats + 1)
        for idx, seat in enumerate(occupied[:max_seats], start=1):
            synth[idx] = seat
        if occupied:
            log.info(
                "HUD seat mapping: configured ring %s does not cover occupied seats %s; synthesised %s",
                ring,
                occupied,
                synth,
            )
        return synth

    def _bottom_center_slot(self) -> int:
        """Layout slot rendered at the bottom-centre (max y, nearest to centre-x).

        This is the anchor every poker client rotates the hero to, computed from
        the layout geometry rather than a hand-maintained per-size integer.
        """
        layout = self.hud.layout
        center_x = (getattr(layout, "width", 0) or 0) / 2
        best = self.hud.max
        best_key: tuple[int, float] | None = None
        for i in range(1, self.hud.max + 1):
            loc = layout.location[i] if i < len(layout.location) else None
            if loc is None:
                continue
            key = (loc[1], -abs(loc[0] - center_x))
            if best_key is None or key > best_key:
                best_key, best = key, i
        return best

    def _anchor_slot(self) -> int:
        """Layout slot the hero's block is pinned to.

        An explicit non-zero ``fav_seat`` for this table size wins (user
        override); otherwise the hero is anchored to the bottom-centre slot.
        Note the behaviour change from the legacy default: ``fav_seat=0`` used to
        mean "no rotation" (hero left wherever its raw seat mapped, so the hero
        was only at the bottom by coincidence). It now means "auto = bottom-
        centre", matching how the client renders the hero.
        """
        try:
            fav = self.hud.site_parameters["fav_seat"][self.hud.max]
        except (KeyError, TypeError):
            fav = 0
        return fav if fav else self._bottom_center_slot()

    def adj_seats(self) -> list[int]:
        """Map visual seats to layout positions with the hero anchored bottom-centre.

        The hero is always rotated to the anchor slot (bottom-centre by default),
        and the other seats follow clockwise, preserving their order around the
        table -- matching how clients render the hero at the bottom. This no
        longer depends on a per-size ``fav_seat`` integer being set, nor on a
        complete ``hist_seat`` table, both of which were routinely missing for
        iPoker table sizes and left the HUD unrotated or mis-seated.
        """
        max_seats = self.hud.max
        adj = list(range(max_seats + 1))  # identity default

        # Refresh visual-slot -> physical-seat so player lookups
        # (get_id_from_seat) and this position rotation agree, even when the
        # site numbers seats sparsely on a larger grid.
        hh_seats = self._effective_hh_seats()
        self.hud.layout.hh_seats = hh_seats

        anchor = self._anchor_slot()
        if not anchor:
            return adj

        # Find the hero's visual slot: the slot whose physical seat is the hero's.
        actual_seat = None
        for data in self.hud.stat_dict.values():
            if self.config.is_hero_name(self.hud.site, data["screen_name"]):
                hero_phys = data.get("seat")
                for i in range(1, max_seats + 1):
                    if i < len(hh_seats) and hh_seats[i] == hero_phys:
                        actual_seat = i
                        break
                break

        if not actual_seat:  # shouldn't happen: HUDs aren't created when the hero isn't seated.
            log.error(
                "HUD seat mapping: hero seat not found (hh_seats=%s, occupied=%s)",
                hh_seats,
                self._occupied_seats(),
            )
            return adj

        for i in range(max_seats):
            j = actual_seat + i
            if j > max_seats:
                j -= max_seats
            adj[j] = anchor + i
            if adj[j] > max_seats:
                adj[j] -= max_seats

        return adj
