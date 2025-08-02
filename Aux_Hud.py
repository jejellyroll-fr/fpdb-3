#    Copyright 2011-2012,  Ray E. Barker
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
"""A simple HUD display for FreePokerTools/fpdb HUD."""

########################################################################

#    Standard Library modules
from functools import partial
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

#    FreePokerTools modules
import Aux_Base
import Configuration
import Popup
import Stats
from loggingFpdb import get_logger

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("aux_hud")


class SimpleHUD(Aux_Base.AuxSeats):
    """A simple HUD class based on the Aux_Window interface."""

    def __init__(self, hud: Any, config: Any, aux_params: Any) -> None:
        """Initializes the SimpleHUD instance for a poker table.

        This constructor sets up the HUD's configuration, layout, and stat window classes for the table.
        It prepares the stat, popup, and tip arrays based on the current game parameters.

        Args:
            hud: The HUD instance associated with the table.
            config: The configuration object for the HUD.
            aux_params: Additional parameters for HUD customization.
        """
        #    Save everything you need to know about the hud as attrs.
        #    That way a subclass doesn't have to grab them.
        #    Also, the subclass can override any of these attributes
        super().__init__(hud, config, aux_params)
        self.poker_game = self.hud.poker_game
        self.site_params = self.hud.site_parameters
        self.aux_params = aux_params
        self.game_params = self.hud.supported_games_parameters["game_stat_set"]
        self.max = self.hud.max
        self.nrows = self.game_params.rows
        self.ncols = self.game_params.cols
        self.xpad = self.game_params.xpad
        self.ypad = self.game_params.ypad
        self.xshift = self.site_params["hud_menu_xshift"]
        self.yshift = self.site_params["hud_menu_yshift"]
        self.fgcolor = self.aux_params["fgcolor"]
        self.bgcolor = self.aux_params["bgcolor"]
        self.opacity = self.aux_params["opacity"]
        self.font = QFont(self.aux_params["font"], int(self.aux_params["font_size"]))

        # store these class definitions for use elsewhere
        # this is needed to guarantee that the classes in _this_ module
        # are called, and that some other overriding class is not used.

        self.aw_class_window = SimpleStatWindow
        self.aw_class_stat = SimpleStat
        self.aw_class_table_mw = SimpleTableMW
        self.aw_class_label = SimpleLabel

        #    layout is handled by superclass!
        #    retrieve the contents of the stats. popup and tips elements
        #    for future use do this here so that subclasses don't have to bother

        self.stats = [[None] * self.ncols for _ in range(self.nrows)]
        self.popups = [[None] * self.ncols for _ in range(self.nrows)]
        self.tips = [[None] * self.ncols for _ in range(self.nrows)]

        for stat in self.game_params.stats:
            self.stats[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].stat_name
            )
            self.popups[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].popup
            )
            self.tips[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].tip
            )

    def refresh_stats_layout(self) -> None:
        """Refreshes the stats layout arrays based on the current game parameters.

        This method updates the layout parameters and repopulates the stats, popups, and tips arrays
        to reflect any changes in the stat set configuration.
        """
        # Update layout parameters from new game_params
        self.nrows = self.game_params.rows
        self.ncols = self.game_params.cols
        self.xpad = self.game_params.xpad
        self.ypad = self.game_params.ypad

        # Reinitialize the stats arrays
        self.stats = [[None] * self.ncols for _ in range(self.nrows)]
        self.popups = [[None] * self.ncols for _ in range(self.nrows)]
        self.tips = [[None] * self.ncols for _ in range(self.nrows)]

        # Repopulate with new stat set configuration
        for stat in self.game_params.stats:
            self.stats[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].stat_name
            )
            self.popups[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].popup
            )
            self.tips[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].tip
            )

    def create_contents(self, container: Any, i: int) -> None:
        """Create the contents of the specified container.

        This method delegates the creation of contents to the container's create_contents method.

        Args:
            container: The container object whose contents are to be created.
            i: The index or identifier for the contents to be created.
        """
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.create_contents(i)

    def update_contents(self, container: Any, i: int) -> None:
        """Update the contents of the specified container.

        This method delegates the update of contents to the container's update_contents method.

        Args:
            container: The container object whose contents are to be updated.
            i: The index or identifier for the contents to be updated.
        """
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.update_contents(i)

    def create_common(self, _x: int = 0, _y: int = 0) -> Any:
        """Create the common table menu window for the HUD.

        This method instantiates and returns the main table menu window for the HUD.

        Args:
            _x: The x-coordinate for positioning (unused).
            _y: The y-coordinate for positioning (unused).

        Returns:
            Any: The created table menu window instance.
        """
        # invokes the simple_table_mw class (or similar)
        self.table_mw = self.aw_class_table_mw(self.hud, aw=self)
        return self.table_mw

    def move_windows(self) -> None:
        """Move all HUD windows to their appropriate positions.

        This method moves both the stat windows and the main table menu window to their updated locations.
        """
        super().move_windows()
        #
        # tell our mw that an update is needed (normally on table move)
        # custom code here, because we don't use the ['common'] element
        # to control menu position
        self.table_mw.move_windows()

    def save_layout(self) -> None:
        """Save the current HUD layout configuration.

        This method saves the positions of all HUD elements for the current table layout to the configuration.
        """
        new_locs = {self.adj[int(i)]: ((pos[0]), (pos[1])) for i, pos in list(self.positions.items()) if i != "common"}
        log.info("Saving layout for %s-max table: %s", self.hud.max, new_locs)
        self.config.save_layout_set(
            self.hud.layout_set,
            self.hud.max,
            new_locs,
            self.hud.table.width,
            self.hud.table.height,
        )
        log.info("Layout saved successfully")


class SimpleStatWindow(Aux_Base.SeatWindow):
    """Simple window class for stat windows."""

    def __init__(self, aw: Any | None = None, seat: Any | None = None) -> None:
        """Initializes the SimpleStatWindow for a specific seat.

        This constructor sets up the stat window, initializes the popup count, and sets the window title.

        Args:
            aw: The auxiliary HUD object providing context and configuration.
            seat: The seat number associated with this stat window.
        """
        super().__init__(aw, seat)
        self.popup_count = 0
        self.setWindowTitle("HUD - stats")

    def button_release_right(self, event: Any) -> None:  # show pop up
        """Show a popup window with detailed statistics when the right mouse button is released.

        This method displays a popup with additional stat information for the widget under the cursor,
        provided the widget contains stats and no other popup is currently active.

        Args:
            event: The mouse event triggering the popup.
        """
        widget = self.childAt(event.pos())

        if widget.stat_dict and self.popup_count == 0 and widget.aw_popup:
            # do not popup on empty blocks or if one is already active
            pu = Popup.popup_factory(
                seat=widget.aw_seat,
                stat_dict=widget.stat_dict,
                win=self,
                pop=self.aw.config.popup_windows[widget.aw_popup],
                hand_instance=self.aw.hud.hand_instance,
                config=self.aw.config,
            )
            pu.setStyleSheet(
                f"QWidget{{background:{self.aw.bgcolor};color:{self.aw.fgcolor};}}QToolTip{{}}",
            )

    def create_contents(self, _i: int) -> None:
        """Create and lay out the stat widgets for the stat window.

        This method initializes the grid layout and populates it with stat widgets for each row and column.
        """
        self.setStyleSheet(
            f"QWidget{{background:{self.aw.bgcolor};color:{self.aw.fgcolor};}}QToolTip{{}}",
        )
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(4)
        self.grid.setVerticalSpacing(1)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.grid)
        self.stat_box = [[None] * self.aw.ncols for _ in range(self.aw.nrows)]

        for r in range(self.aw.nrows):
            for c in range(self.aw.ncols):
                self.stat_box[r][c] = self.aw.aw_class_stat(
                    self.aw.stats[r][c],
                    seat=self.seat,
                    popup=self.aw.popups[r][c],
                    aw=self.aw,
                )
                self.grid.addWidget(self.stat_box[r][c].widget, r, c)
                self.stat_box[r][c].widget.setFont(self.aw.font)

    def update_contents(self, i: int) -> None:
        """Update the stat widgets for the specified seat.

        This method refreshes all stat widgets in the window for the given seat, using the latest player data.

        Args:
            i: The seat identifier to update.
        """
        if i == "common":
            return
        player_id = self.aw.get_id_from_seat(i)
        if player_id is None:
            return
        for r in range(self.aw.nrows):
            for c in range(self.aw.ncols):
                self.stat_box[r][c].update(player_id, self.aw.hud.stat_dict)


class SimpleStat:
    """A simple class for displaying a single stat."""

    def __init__(self, stat: str, seat: int, popup: str, aw: Any) -> None:
        """Initializes a SimpleStat instance for displaying a single statistic.

        This constructor sets up the label, associates it with the correct seat and popup,
        and stores relevant HUD context.

        Args:
            stat: The name of the statistic to display.
            seat: The seat number associated with the statistic.
            popup: The popup configuration or identifier for the stat.
            aw: The auxiliary HUD object providing context and configuration.
        """
        self.stat = stat
        self.lab = aw.aw_class_label(
            "---",
        )  # --- is used as initial value because longer labels don't shrink
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.aw_seat = aw.hud.layout.hh_seats[seat]
        self.lab.aw_popup = popup
        self.lab.stat_dict = None
        self.widget = self.lab
        self.stat_dict = None
        self.hud = aw.hud
        self.aux_params = aw.aux_params

    def update(self, player_id: str, stat_dict: dict) -> None:
        """Update the statistic display for a given player.

        This method recalculates the statistic value and updates the label text for the specified player.

        Args:
            player_id: The unique identifier of the player.
            stat_dict: A dictionary containing statistics for all players.
        """
        self.stat_dict = stat_dict  # So the Simple_stat obj always has a fresh stat_dict
        self.lab.stat_dict = stat_dict
        self.number = Stats.do_stat(
            stat_dict,
            player_id,
            self.stat,
            self.hud.hand_instance,
        )
        if self.number:
            self.lab.setText(str(self.number[1]))

    def set_color(self, fg: str | None = None, bg: str | None = None) -> None:
        """Set the foreground and background color of the stat label.

        This method updates the label's stylesheet to apply the specified font, foreground, and background colors.

        Args:
            fg: The foreground (text) color to apply.
            bg: The background color to apply.
        """
        ss = f"QLabel{{font-family: {self.aux_params['font']};font-size: {self.aux_params['font_size']}pt;"
        if fg:
            ss += f"color: {fg};"
        if bg:
            ss += f"background: {bg};"
        self.lab.setStyleSheet(ss + "}")


class SimpleLabel(QLabel):
    """A simple label class."""


class SimpleTableMW(Aux_Base.SeatWindow):
    """Create a default table hud menu label."""

    #    This is a recreation of the table main window from the default HUD
    #    in the old Hud.py. This has the menu options from that hud.

    #    BTW: It might be better to do this with a different AW.

    def __init__(self, hud: Any, aw: Any | None = None) -> None:
        """Initializes the SimpleTableMW, the main table HUD menu window.

        This constructor sets up the menu label, icon, layout, and positions the menu window relative to the table.

        Args:
            hud: The HUD instance associated with the table.
            aw: The auxiliary HUD object providing context and configuration.
        """
        super().__init__(aw)
        self.hud = hud
        self.aw = aw
        self.menu_is_popped = False

        # self.connect("configure_event", self.configure_event_cb, "auxmenu") base class will deal with this

        try:
            self.menu_label = hud.hud_params["label"]
        except KeyError:
            self.menu_label = "fpdb menu"

        lab = QLabel(self.menu_label)
        logo = Path(Configuration.GRAPHICS_PATH) / "tribal.jpg"
        pixmap = QPixmap(str(logo))
        pixmap = pixmap.scaled(45, 45)
        lab.setPixmap(pixmap)
        lab.setStyleSheet(f"background: {self.aw.bgcolor}; color: {self.aw.fgcolor};")

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(lab)

        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
        pos_x = table_x + self.aw.xshift
        pos_y = table_y + self.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y, 100, 100)
        self.move(clamped_x, clamped_y)

    def button_press_right(self, _event: Any) -> None:
        """Show the table popup menu when the right mouse button is pressed.

        This method displays the table popup menu if it is not already open.

        Args:
            _event: The mouse event triggering the popup menu.
        """
        if not self.menu_is_popped:
            self.menu_is_popped = True
            SimpleTablePopupMenu(self)

    def move_windows(self) -> None:
        """Move the table menu window to its correct position relative to the table.

        This method repositions the menu window based on the table's current coordinates and configured offsets.
        """
        # force menu to the offset position from table origin (do not use common setting)
        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
        pos_x = table_x + self.aw.xshift
        pos_y = table_y + self.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y)
        self.move(clamped_x, clamped_y)


class SimpleTablePopupMenu(QWidget):
    """A simple table popup menu."""

    def __init__(self, parentwin: Any) -> None:
        """Initializes the SimpleTablePopupMenu for HUD configuration.

        This constructor sets up the popup menu window, positions it relative to the table, and initializes the UI.

        Args:
            parentwin: The parent window instance that owns this popup menu.
        """
        super().__init__(
            None,
            Qt.Window | Qt.FramelessWindowHint,
        )
        self.parentwin = parentwin
        table_x = max(0, self.parentwin.hud.table.x) if self.parentwin.hud.table.x is not None else 50
        table_y = max(0, self.parentwin.hud.table.y) if self.parentwin.hud.table.y is not None else 50
        pos_x = table_x + self.parentwin.aw.xshift
        pos_y = table_y + self.parentwin.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y, 400, 300)  # Larger window size
        self.move(clamped_x, clamped_y)
        self.setWindowTitle(f"{self.parentwin.menu_label} - HUD configuration")
        self._setup_ui()
        self.show()
        self.raise_()

    def _setup_ui(self) -> None:
        """Set up the user interface for the table popup menu.

        This method initializes the combo box dictionaries, creates the main controls and stats configuration boxes,
        and arranges them in the popup menu layout.
        """
        # Dictionaries for combo boxes
        stat_range_combo_dict = self._create_stat_range_dict()
        seats_style_combo_dict = self._create_seats_style_dict()
        multiplier_combo_dict = self._create_multiplier_dict()
        cb_max_dict = self._create_max_seats_dict()

        # Layouts
        grid = QGridLayout()
        self.setLayout(grid)
        vbox1 = self._create_main_controls(cb_max_dict)
        vbox2 = self._create_player_stats_box(
            multiplier_combo_dict,
            seats_style_combo_dict,
            stat_range_combo_dict,
        )
        vbox3 = self._create_opponent_stats_box(
            multiplier_combo_dict,
            seats_style_combo_dict,
            stat_range_combo_dict,
        )

        self.set_spinners_active()

        grid.addLayout(vbox1, 0, 0)
        grid.addLayout(vbox2, 0, 1)
        grid.addLayout(vbox3, 0, 2)
        grid.addWidget(QLabel(f"Stat set: {self.parentwin.aw.game_params.name}"), 1, 0)

    def _create_main_controls(self, cb_max_dict: dict) -> QVBoxLayout:
        """Create the main control buttons and selectors for the popup menu.

        This method adds buttons for HUD control actions and, if available, a stat set selector and max seats combo box.

        Args:
            cb_max_dict: The dictionary for the max seats combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all main controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(self.build_button("Restart This HUD", "kill"))
        vbox.addWidget(self.build_button("Save HUD Layout", "save"))
        vbox.addWidget(self.build_button("Stop this HUD", "blacklist"))
        vbox.addWidget(self.build_button("Close", "close"))
        vbox.addWidget(QLabel(""))

        # Add stat set selector
        stat_sets_dict = self._create_stat_sets_dict()
        if len(stat_sets_dict) > 1:  # Only show if there are multiple stat sets
            vbox.addWidget(QLabel("Stat Set (HUD):"))
            self.stat_set_combo = self.build_stat_set_combo(stat_sets_dict)
            vbox.addWidget(self.stat_set_combo)
            vbox.addWidget(QLabel(""))

        vbox.addWidget(self.build_combo_and_set_active("new_max_seats", cb_max_dict))
        return vbox

    def _create_player_stats_box(
        self,
        multiplier_dict: dict,
        seats_style_dict: dict,
        stat_range_dict: dict,
    ) -> QVBoxLayout:
        """Create the player stats configuration box for the popup menu.

        This method builds and arranges the controls for configuring player stats display,
        including combo boxes and spinners.

        Args:
            multiplier_dict: The dictionary for the multiplier combo box.
            seats_style_dict: The dictionary for the seats style combo box.
            stat_range_dict: The dictionary for the stat range combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all player stats controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Show Player Stats for"))
        vbox.addWidget(
            self.build_combo_and_set_active("h_agg_bb_mult", multiplier_dict),
        )
        vbox.addWidget(
            self.build_combo_and_set_active("h_seats_style", seats_style_dict),
        )
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Custom"))
        self.h_nums_low_spinner = self.build_spinner("h_seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.h_nums_low_spinner)
        hbox.addWidget(QLabel("To"))
        self.h_nums_high_spinner = self.build_spinner("h_seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.h_nums_high_spinner)
        vbox.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(
            self.build_combo_and_set_active("h_stat_range", stat_range_dict),
        )
        self.h_hud_days_spinner = self.build_spinner("h_hud_days", 1, 9999)
        hbox.addWidget(self.h_hud_days_spinner)
        vbox.addLayout(hbox)
        return vbox

    def _create_opponent_stats_box(
        self,
        multiplier_dict: dict,
        seats_style_dict: dict,
        stat_range_dict: dict,
    ) -> QVBoxLayout:
        """Create the opponent stats configuration box for the popup menu.

        This method builds and arranges the controls for configuring opponent stats display,
        including combo boxes and spinners.

        Args:
            multiplier_dict: The dictionary for the multiplier combo box.
            seats_style_dict: The dictionary for the seats style combo box.
            stat_range_dict: The dictionary for the stat range combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all opponent stats controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Show Opponent Stats for"))
        vbox.addWidget(self.build_combo_and_set_active("agg_bb_mult", multiplier_dict))
        vbox.addWidget(
            self.build_combo_and_set_active("seats_style", seats_style_dict),
        )
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Custom"))
        self.nums_low_spinner = self.build_spinner("seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.nums_low_spinner)
        hbox.addWidget(QLabel("To"))
        self.nums_high_spinner = self.build_spinner("seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.nums_high_spinner)
        vbox.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(self.build_combo_and_set_active("stat_range", stat_range_dict))
        self.hud_days_spinner = self.build_spinner("hud_days", 1, 9999)
        hbox.addWidget(self.hud_days_spinner)
        vbox.addLayout(hbox)
        return vbox

    def _create_stat_range_dict(self) -> dict:
        """Create the dictionary for the stat range combo box.

        This method returns a dictionary mapping stat range options to their display labels and codes.

        Returns:
            dict: The dictionary for the stat range combo box.
        """
        return {
            0: ("Since: All Time", "A"),
            1: ("Since: Session", "S"),
            2: ("Since: n Days" + " - - >", "T"),
        }

    def _create_seats_style_dict(self) -> dict:
        """Create the dictionary for the seats style combo box.

        This method returns a dictionary mapping seat style options to their display labels and codes.

        Returns:
            dict: The dictionary for the seats style combo box.
        """
        return {
            0: ("Number of Seats: Any Number", "A"),
            1: ("Number of Seats: Custom", "C"),
            2: ("Number of Seats: Exact", "E"),
        }

    def _create_multiplier_dict(self) -> dict:
        """Create the dictionary for the multiplier combo box.

        This method returns a dictionary mapping multiplier options to their display labels and values.

        Returns:
            dict: The dictionary for the multiplier combo box.
        """
        return {
            0: ("For This Blind Level Only", 1),
            1: ("  0.5 to 2 * Current Blinds", 2),
            2: ("  0.33 to 3 * Current Blinds", 3),
            3: ("  0.1 to 10 * Current Blinds", 10),
            4: ("All Levels", 10000),
        }

    def _create_max_seats_dict(self) -> dict:
        """Create the dictionary for the max seats combo box.

        This method returns a dictionary mapping available table layouts to their display labels and values.

        Returns:
            dict: The dictionary for the max seats combo box.
        """
        cb_max_dict = {0: ("Force layout...", None)}
        for pos, i in enumerate(
            sorted(self.parentwin.hud.layout_set.layout),
            start=1,
        ):
            cb_max_dict[pos] = (f"{i}-max", i)
        return cb_max_dict

    def _create_stat_sets_dict(self) -> dict:
        """Create the dictionary for the stat set combo box.

        This method returns a dictionary mapping available stat sets to their display labels and values.

        Returns:
            dict: The dictionary for the stat set combo box.
        """
        stat_sets = self.parentwin.hud.config.get_stat_sets()
        return {i: (stat_set_name, stat_set_name) for i, stat_set_name in enumerate(stat_sets)}

    def delete_event(self) -> None:
        """Handle the event to close and destroy the popup menu.

        This method resets the menu state in the parent window and destroys the popup menu instance.
        """
        self.parentwin.menu_is_popped = False
        self.destroy()

    def callback(self, _check_state: Any, data: str | None = None) -> None:
        """Handle button callbacks for popup menu actions.

        This method processes actions such as killing the HUD, blacklisting, saving the layout, and closing the popup.

        Args:
            _check_state: The state of the triggering event (unused).
            data: The action keyword indicating which operation to perform.
        """
        if data == "kill":
            self.parentwin.hud.parent.kill_hud("kill", self.parentwin.hud.table.key)
        if data == "blacklist":
            self.parentwin.hud.parent.blacklist_hud(
                "kill",
                self.parentwin.hud.table.key,
            )
        if data == "save":
            # This calls the save_layout method of the Hud object. The Hud object
            # then calls the save_layout method in each installed AW.
            self.parentwin.hud.save_layout()
        self.delete_event()

    def build_button(self, labeltext: str, cbkeyword: str) -> QPushButton:
        """Build a QPushButton with a connected callback for the popup menu.

        This method creates a button with the specified label and connects it
        to the callback using the provided keyword.

        Args:
            labeltext: The text to display on the button.
            cbkeyword: The keyword to pass to the callback when the button is clicked.

        Returns:
            QPushButton: The created button instance.
        """
        button = QPushButton(labeltext)
        button.clicked.connect(partial(self.callback, data=cbkeyword))
        return button

    def build_spinner(self, field: str, low: int, high: int) -> QSpinBox:
        """Build a QSpinBox for numeric input in the popup menu.

        This method creates a spin box with the specified range and initial value,
        and connects it to update the HUD parameter.

        Args:
            field: The HUD parameter field to bind to the spin box.
            low: The minimum value for the spin box.
            high: The maximum value for the spin box.

        Returns:
            QSpinBox: The created spin box instance.
        """
        spin_box = QSpinBox()
        spin_box.setRange(low, high)
        spin_box.setValue(self.parentwin.hud.hud_params[field])
        spin_box.valueChanged.connect(partial(self.change_spin_field_value, field=field))
        return spin_box

    def build_combo_and_set_active(self, field: str, combo_dict: dict) -> QComboBox:
        """Build a QComboBox for selection in the popup menu and set the active value.

        This method creates a combo box with the specified options, sets the current value based on the HUD parameter,
        and connects it to update the parameter when changed.

        Args:
            field: The HUD parameter field to bind to the combo box.
            combo_dict: The dictionary of options for the combo box.

        Returns:
            QComboBox: The created combo box instance.
        """
        widget = QComboBox()
        for pos in combo_dict:
            widget.addItem(combo_dict[pos][0])
            if combo_dict[pos][1] == self.parentwin.hud.hud_params[field]:
                widget.setCurrentIndex(pos)
        widget.currentIndexChanged[int].connect(
            partial(self.change_combo_field_value, field=field, combo_dict=combo_dict),
        )
        return widget

    def build_stat_set_combo(self, stat_sets_dict: dict) -> QComboBox:
        """Build a QComboBox for selecting the stat set in the popup menu.

        This method creates a combo box with available stat sets, sets the current value,
        and connects it to update the stat set.

        Args:
            stat_sets_dict: The dictionary of available stat sets.

        Returns:
            QComboBox: The created combo box instance for stat set selection.
        """
        combo = QComboBox()
        for pos in stat_sets_dict:
            combo.addItem(stat_sets_dict[pos][0])
            # Get current stat set name
            current_stat_set = self._get_current_stat_set()
            if stat_sets_dict[pos][1] == current_stat_set:
                combo.setCurrentIndex(pos)
        combo.currentIndexChanged[int].connect(
            partial(self.change_stat_set, stat_sets_dict=stat_sets_dict),
        )
        return combo

    def _get_current_stat_set(self) -> str:
        """Get the name of the currently active stat set.

        This method retrieves the stat set name from the current game parameters.

        Returns:
            str: The name of the current stat set.
        """
        # The stat set is available in the game parameters
        return self.parentwin.aw.game_params.name

    def change_stat_set(self, sel: int, stat_sets_dict: dict) -> None:
        """Change the active stat set for the HUD and refresh the display.

        This method updates the configuration to use the selected stat set, saves the configuration,
        closes the popup menu, and attempts to refresh the HUD with the new stat set. If refreshing fails,
        the HUD is restarted to apply the new stat set.

        Args:
            sel: The index of the selected stat set in the combo box.
            stat_sets_dict: The dictionary of available stat sets.
        """
        new_stat_set = stat_sets_dict[sel][1]

        # Update the configuration to use the new stat set
        self._update_stat_set_in_config(new_stat_set)

        # Save the configuration
        self.parentwin.hud.config.save()

        # Close the popup menu
        self.delete_event()

        # Instead of killing the HUD, try to refresh it with the new stat set
        try:
            # Update the game params to use the new stat set
            self.parentwin.aw.game_params = self.parentwin.hud.config.get_supported_games_parameters(
                self.parentwin.hud.poker_game,
                self.parentwin.hud.game_type,
            )["game_stat_set"]

            # Refresh the HUD display with new stat set
            if hasattr(self.parentwin.hud, "stat_dict"):
                # Need to refresh the stats layout and popups with new stat set
                self.parentwin.aw.refresh_stats_layout()

                # Recreate contents of all existing windows with new stat set
                for seat in self.parentwin.aw.stat_windows:
                    if self.parentwin.aw.stat_windows[seat] is not None:
                        self.parentwin.aw.stat_windows[seat].create_contents(seat)

                # Update with current data
                self.parentwin.aw.update(self.parentwin.hud.stat_dict)
                log.info("HUD refreshed with new stat set: %s", new_stat_set)
        except (AttributeError, KeyError, TypeError) as e:
            # If refresh fails, restart the HUD to apply the new stat set
            # This is intentional for the switch feature, not an unwanted restart
            log.info("Refreshing HUD failed, restarting to apply stat set '%s': %s", new_stat_set, e)
            self.parentwin.hud.parent.kill_hud("kill", self.parentwin.hud.table.key)

    def _update_stat_set_in_config(self, new_stat_set: str) -> None:
        """Update the stat set in the configuration and XML for the current game.

        This method updates the stat set for the current poker game and game type in both the in-memory configuration
        and the XML configuration file.

        Args:
            new_stat_set: The name of the new stat set to apply.
        """
        # Update the game_stat_set configuration
        poker_game = self.parentwin.hud.poker_game
        if poker_game in self.parentwin.hud.config.supported_games:
            game_config = self.parentwin.hud.config.supported_games[poker_game]

            # game_stat_set is a dictionary indexed by game_type
            game_type = self.parentwin.hud.game_type
            if game_type in game_config.game_stat_set:
                game_config.game_stat_set[game_type].stat_set = new_stat_set

            # Also update the XML directly
            self._update_xml_stat_set(poker_game, game_type, new_stat_set)

    def _update_xml_stat_set(self, poker_game: str, game_type: str, new_stat_set: str) -> None:
        """Update the stat set attribute in the XML configuration for a specific game and game type.

        This method locates the relevant game and game_stat_set nodes in the XML document and updates
        the stat_set attribute to the new value.

        Args:
            poker_game: The name of the poker game to update.
            game_type: The type of the game to update.
            new_stat_set: The new stat set name to assign in the XML.
        """
        # Find the game node in the XML document
        game_nodes = self.parentwin.hud.config.doc.getElementsByTagName("game")
        for game_node in game_nodes:
            if game_node.getAttribute("game_name") == poker_game:
                # Find the game_stat_set node for this game type
                game_stat_set_nodes = game_node.getElementsByTagName("game_stat_set")
                for gss_node in game_stat_set_nodes:
                    if gss_node.getAttribute("game_type") == game_type:
                        # Update the stat_set attribute
                        gss_node.setAttribute("stat_set", new_stat_set)
                        break
                break

    def change_combo_field_value(self, sel: int, field: str, combo_dict: dict) -> None:
        """Update the HUD parameter value based on the selected combo box option.

        This method sets the specified HUD parameter to the value associated with the selected combo box item
        and updates the enabled state of related spinners.

        Args:
            sel: The index of the selected item in the combo box.
            field: The HUD parameter field to update.
            combo_dict: The dictionary of options for the combo box.
        """
        self.parentwin.hud.hud_params[field] = combo_dict[sel][1]
        self.set_spinners_active()

    def change_spin_field_value(self, value: int, field: str) -> None:
        """Update the HUD parameter value based on the spin box input.

        This method sets the specified HUD parameter to the value provided by the spin box.

        Args:
            value: The new value selected in the spin box.
            field: The HUD parameter field to update.
        """
        self.parentwin.hud.hud_params[field] = value

    def set_spinners_active(self) -> None:
        """Enable or disable spinner controls based on current HUD parameter selections.

        This method updates the enabled state of various spinner widgets in the popup menu
        according to the current values of the HUD's parameter fields.
        """
        if self.parentwin.hud.hud_params["h_stat_range"] == "T":
            self.h_hud_days_spinner.setEnabled(True)
        else:
            self.h_hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["stat_range"] == "T":
            self.hud_days_spinner.setEnabled(True)
        else:
            self.hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["h_seats_style"] == "C":
            self.h_nums_low_spinner.setEnabled(True)
            self.h_nums_high_spinner.setEnabled(True)
        else:
            self.h_nums_low_spinner.setEnabled(False)
            self.h_nums_high_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["seats_style"] == "C":
            self.nums_low_spinner.setEnabled(True)
            self.nums_high_spinner.setEnabled(True)
        else:
            self.nums_low_spinner.setEnabled(False)
            self.nums_high_spinner.setEnabled(False)
