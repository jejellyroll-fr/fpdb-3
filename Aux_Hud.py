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
log = get_logger("hud")


class SimpleHUD(Aux_Base.AuxSeats):
    """A simple HUD class based on the Aux_Window interface."""

    def __init__(self, hud: Any, config: Any, aux_params: Any) -> None:
        """Initialise the HUD."""
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

    def create_contents(self, container: Any, i: int) -> None:
        """Create the contents of the container."""
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.create_contents(i)

    def update_contents(self, container: Any, i: int) -> None:
        """Update the contents of the container."""
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.update_contents(i)

    def create_common(self, _x: int = 0, _y: int = 0) -> Any:
        """Create the common menu window."""
        # invokes the simple_table_mw class (or similar)
        self.table_mw = self.aw_class_table_mw(self.hud, aw=self)
        return self.table_mw

    def move_windows(self) -> None:
        """Move the windows."""
        super().move_windows()
        #
        # tell our mw that an update is needed (normally on table move)
        # custom code here, because we don't use the ['common'] element
        # to control menu position
        self.table_mw.move_windows()

    def save_layout(self) -> None:
        """Save new layout back to the aux element in the config file."""
        new_locs = {self.adj[int(i)]: ((pos[0]), (pos[1])) for i, pos in list(self.positions.items()) if i != "common"}
        self.config.save_layout_set(
            self.hud.layout_set,
            self.hud.max,
            new_locs,
            self.hud.table.width,
            self.hud.table.height,
        )


class SimpleStatWindow(Aux_Base.SeatWindow):
    """Simple window class for stat windows."""

    def __init__(self, aw: Any | None = None, seat: Any | None = None) -> None:
        """Initialise the stat window."""
        super().__init__(aw, seat)
        self.popup_count = 0
        self.setWindowTitle("HUD - stats")

    def button_release_right(self, event: Any) -> None:  # show pop up
        """Show the popup menu."""
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
        """Create the contents of the stat window."""
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
        """Update the contents of the stat window."""
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
        """Initialise the stat."""
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
        """Update the stat value."""
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
        """Set the color of the stat."""
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
        """Initialise the main window."""
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
        """Handle button clicks in the FPDB main menu event box."""
        if not self.menu_is_popped:
            self.menu_is_popped = True
            SimpleTablePopupMenu(self)

    def move_windows(self) -> None:
        """Move the windows."""
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
        """Initialise the popup menu."""
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
        self.setWindowTitle(self.parentwin.menu_label + " - HUD configuration")
        self._setup_ui()
        self.show()
        self.raise_()

    def _setup_ui(self) -> None:
        """Set up the UI for the popup menu."""
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
        """Create the main control buttons and combo box."""
        vbox = QVBoxLayout()
        vbox.addWidget(self.build_button("Restart This HUD", "kill"))
        vbox.addWidget(self.build_button("Save HUD Layout", "save"))
        vbox.addWidget(self.build_button("Stop this HUD", "blacklist"))
        vbox.addWidget(self.build_button("Close", "close"))
        vbox.addWidget(QLabel(""))
        vbox.addWidget(self.build_combo_and_set_active("new_max_seats", cb_max_dict))
        return vbox

    def _create_player_stats_box(
        self,
        multiplier_dict: dict,
        seats_style_dict: dict,
        stat_range_dict: dict,
    ) -> QVBoxLayout:
        """Create the player stats configuration box."""
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
        """Create the opponent stats configuration box."""
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
        """Create the dictionary for the stat range combo box."""
        return {
            0: ("Since: All Time", "A"),
            1: ("Since: Session", "S"),
            2: ("Since: n Days" + " - - >", "T"),
        }

    def _create_seats_style_dict(self) -> dict:
        """Create the dictionary for the seats style combo box."""
        return {
            0: ("Number of Seats: Any Number", "A"),
            1: ("Number of Seats: Custom", "C"),
            2: ("Number of Seats: Exact", "E"),
        }

    def _create_multiplier_dict(self) -> dict:
        """Create the dictionary for the multiplier combo box."""
        return {
            0: ("For This Blind Level Only", 1),
            1: ("  0.5 to 2 * Current Blinds", 2),
            2: ("  0.33 to 3 * Current Blinds", 3),
            3: ("  0.1 to 10 * Current Blinds", 10),
            4: ("All Levels", 10000),
        }

    def _create_max_seats_dict(self) -> dict:
        """Create the dictionary for the max seats combo box."""
        cb_max_dict = {0: ("Force layout...", None)}
        for pos, i in enumerate(
            sorted(self.parentwin.hud.layout_set.layout),
            start=1,
        ):
            cb_max_dict[pos] = (f"{i}-max", i)
        return cb_max_dict

    def delete_event(self) -> None:
        """Delete the event."""
        self.parentwin.menu_is_popped = False
        self.destroy()

    def callback(self, _check_state: Any, data: str | None = None) -> None:
        """Handle callbacks from the menu."""
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
        """Build a button."""
        button = QPushButton(labeltext)
        button.clicked.connect(partial(self.callback, data=cbkeyword))
        return button

    def build_spinner(self, field: str, low: int, high: int) -> QSpinBox:
        """Build a spinner."""
        spin_box = QSpinBox()
        spin_box.setRange(low, high)
        spin_box.setValue(self.parentwin.hud.hud_params[field])
        spin_box.valueChanged.connect(partial(self.change_spin_field_value, field=field))
        return spin_box

    def build_combo_and_set_active(self, field: str, combo_dict: dict) -> QComboBox:
        """Build a combo box and set the active item."""
        widget = QComboBox()
        for pos in combo_dict:
            widget.addItem(combo_dict[pos][0])
            if combo_dict[pos][1] == self.parentwin.hud.hud_params[field]:
                widget.setCurrentIndex(pos)
        widget.currentIndexChanged[int].connect(
            partial(self.change_combo_field_value, field=field, combo_dict=combo_dict),
        )
        return widget

    def change_combo_field_value(self, sel: int, field: str, combo_dict: dict) -> None:
        """Change the value of a combo box field."""
        self.parentwin.hud.hud_params[field] = combo_dict[sel][1]
        self.set_spinners_active()

    def change_spin_field_value(self, value: int, field: str) -> None:
        """Change the value of a spin box field."""
        self.parentwin.hud.hud_params[field] = value

    def set_spinners_active(self) -> None:
        """Set the spinners active or inactive based on the combo box selection."""
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
