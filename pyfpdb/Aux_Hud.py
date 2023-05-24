#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aux_Hud.py

Simple HUD display for FreePokerTools/fpdb HUD.
"""

#import L10n
#_ = L10n.get_translation()
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

########################################################################

#    to do

#    Standard Library modules
import logging
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("hud")
from functools import partial

from PyQt5.QtGui import QCursor, QFont
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout,
                             QLabel, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)

#    FreePokerTools modules
import Aux_Base
import Stats
import Popup


class Simple_HUD(Aux_Base.Aux_Seats):
    """
    A simple HUD class based on the Aux_Window interface.
    Inherits from Aux_Base.Aux_Seats.
    """

    def __init__(self, hud, config, aux_params):
        """
        Initializes an instance of the Simple_HUD class.

        :param hud: The HUD object.
        :param config: The configuration object.
        :param aux_params: Auxiliary parameters.
        """
        # Save everything you need to know about the hud as attrs.
        # That way a subclass doesn't have to grab them.
        # Also, the subclass can override any of these attributes
        super(Simple_HUD, self).__init__(hud, config, aux_params)
        self.poker_game = self.hud.poker_game
        self.site_params = self.hud.site_parameters
        self.aux_params = aux_params
        self.game_params = self.hud.supported_games_parameters["game_stat_set"]
        self.max = self.hud.max
        self.nrows = self.game_params.rows
        self.ncols = self.game_params.cols
        self.xpad = self.game_params.xpad
        self.ypad = self.game_params.ypad
        self.xshift = self.site_params['hud_menu_xshift']
        self.yshift = self.site_params['hud_menu_yshift']
        self.fgcolor = self.aux_params["fgcolor"]
        self.bgcolor = self.aux_params["bgcolor"]
        self.opacity = self.aux_params["opacity"]
        self.font = QFont(self.aux_params["font"], int(self.aux_params["font_size"]))

        # Store these class definitions for use elsewhere.
        # This is needed to guarantee that the classes in _this_ module
        # are called, and that some other overriding class is not used.
        self.aw_class_window = Simple_Stat_Window
        self.aw_class_stat = Simple_stat
        self.aw_class_table_mw = Simple_table_mw
        self.aw_class_label = Simple_label

        # Layout is handled by superclass!
        # Retrieve the contents of the stats, popup, and tips elements
        # for future use. Do this here so that subclasses don't have to bother.
        self.stats = [[None] * self.ncols for _ in range(self.nrows)]
        self.popups = [[None] * self.ncols for _ in range(self.nrows)]
        self.tips = [[None] * self.ncols for _ in range(self.nrows)]

        for stat in self.game_params.stats:
            self.stats[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] \
                    = self.game_params.stats[stat].stat_name
            self.popups[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] \
                    = self.game_params.stats[stat].popup
            self.tips[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] \
                    = self.game_params.stats[stat].tip

                                        
    def create_contents(self, container, i):
        """
        Create contents in the given container at the specified index.

        Args:
            container (Container): The container to create contents in.
            i (int): The index to create contents at.

        Returns:
            None
        """
        # Calls the create_contents method on the object stored in self.aw_class_window
        container.create_contents(i)


    def update_contents(self, container, i):
        """
        Updates the contents of the given container.

        Args:
            container (Container): The container to update.
            i (int): The index of the container to update.

        Returns:
            None
        """
        # This is a call to whatever is in self.aw_class_window but it isn't obvious
        container.update_contents(i)


    def create_common(self, x, y):
        """
        Creates a common table using the simple_table_mw class.

        Args:
            self (obj): reference to the current object
            x (int): x position of the table
            y (int): y position of the table

        Returns:
            obj: an instance of the simple_table_mw class
        """
        # invokes the simple_table_mw class (or similar)
        self.table_mw = self.aw_class_table_mw(self.hud, aw=self)
        return self.table_mw

        
    def move_windows(self):
        """
        Move the windows of the Simple_HUD object.

        This method calls its parent class' `move_windows` method, and then moves the windows of the table_mw object.
        """
        super(Simple_HUD, self).move_windows()

        # Tell our mw that an update is needed (normally on table move)
        # Custom code here, because we don't use the ['common'] element
        # to control menu position
        self.table_mw.move_windows()


    def save_layout(self, *args):
        """Save new layout back to the aux element in the config file."""

        # Create a dictionary where the keys are integer values
        # corresponding to the indexes of self.adj, and the values
        # are tuples representing the x and y positions of each
        # element in the layout.
        new_locs = {
            self.adj[int(i)]: ((pos[0]), (pos[1]))
            for i, pos in list(self.positions.items())
            if i != 'common'
        }

        # Call the save_layout_set method of the config object to
        # save the new layout. Pass in the layout set, max, new_locs,
        # and the width and height of the table.
        self.config.save_layout_set(self.hud.layout_set, self.hud.max,
                    new_locs ,self.hud.table.width, self.hud.table.height)


        
class Simple_Stat_Window(Aux_Base.Seat_Window):
    """
    Simple window class for stat windows.
    Inherits from Aux_Base.Seat_Window.
    """

    def __init__(self, aw=None, seat=None):
        """
        Initializes an instance of the Simple_Stat_Window class.

        :param aw: The auxiliary window object.
        :param seat: The seat associated with the window.
        """
        super(Simple_Stat_Window, self).__init__(aw, seat)
        self.popup_count = 0

        
    def button_release_right(self, event):
        """
        Show pop up when right button is released on a widget with valid stat_dict and aw_popup.

        Args:
            event: QMouseEvent, contains information about the mouse event that triggered this function.
        """
        widget = self.childAt(event.pos())  # Get the widget at the position of the mouse event.

        if widget.stat_dict and self.popup_count == 0 and widget.aw_popup:  # Only show popup if widget has a valid stat_dict, there is no other active popup, and the widget has an aw_popup property.
            pu = Popup.popup_factory(
                seat=widget.aw_seat,
                stat_dict=widget.stat_dict,
                win=self,
                pop=self.aw.config.popup_windows[widget.aw_popup],
                hand_instance=self.aw.hud.hand_instance,
                config=self.aw.config)
            # Set the style sheet for the popup.
            pu.setStyleSheet("QWidget{background:%s;color:%s;}QToolTip{}" % (self.aw.bgcolor, self.aw.fgcolor))

                    
    def create_contents(self, i):
        """
        Creates the widget contents.

        Args:
            i (int): The widget index.

        Returns:
            None
        """
        # Set widget style sheet
        self.setStyleSheet("QWidget{background:%s;color:%s;}QToolTip{}" % (self.aw.bgcolor, self.aw.fgcolor))

        # Create grid layout for the widget
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(4)
        self.grid.setVerticalSpacing(1)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.grid)

        # Create list to hold widget objects
        self.stat_box = [[None]*self.aw.ncols for i in range(self.aw.nrows)]

        # Loop through the rows and columns to create the widget objects
        for r in range(self.aw.nrows):
            for c in range(self.aw.ncols):
                # Create the widget object
                self.stat_box[r][c] = self.aw.aw_class_stat(
                    self.aw.stats[r][c],  # Stats for the widget
                    seat=self.seat,  # Seat position for the widget
                    popup=self.aw.popups[r][c],  # Popup for the widget
                    game_stat_config=self.aw.hud.supported_games_parameters["game_stat_set"].stats[(r,c)],  # Game stats for the widget
                    aw=self.aw  # Parent object
                )
                # Add the widget to the grid layout
                self.grid.addWidget(self.stat_box[r][c].widget, r, c)
                # Set the font for the widget
                self.stat_box[r][c].widget.setFont(self.aw.font)


    def update_contents(self, i):
        """
        Updates the contents of the stat boxes for a given player.

        Args:
            i (str): The seat of the player to update.

        Returns:
            None
        """
        # Do not update common stat box
        if i == "common":
            return

        # Get player id from the seat
        player_id = self.aw.get_id_from_seat(i)

        # Return if player id is invalid
        if player_id is None:
            return

        # Update the stat box for each cell
        for r in range(self.aw.nrows):
            for c in range(self.aw.ncols):
                self.stat_box[r][c].update(player_id, self.aw.hud.stat_dict)


class Simple_stat(object):
    """
    A simple class for displaying a single stat.
    """

    def __init__(self, stat, seat, popup, game_stat_config=None, aw=None):
        """
        Initializes an instance of the Simple_stat class.

        :param stat: The stat to display.
        :param seat: The seat associated with the stat.
        :param popup: The popup value for the stat.
        :param game_stat_config: The game stat configuration.
        :param aw: The auxiliary window object.
        """
        self.stat = stat
        self.lab = aw.aw_class_label("xxx")  # xxx is used as an initial value because longer labels don't shrink
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.aw_seat = aw.hud.layout.hh_seats[seat]
        self.lab.aw_popup = popup
        self.lab.stat_dict = None
        self.widget = self.lab
        self.stat_dict = None
        self.hud = aw.hud


    def update(self, player_id, stat_dict):
        """
        Updates the Simple_stat object with new stats for a player.

        Args:
            player_id (int): The ID of the player to update stats for.
            stat_dict (dict): A dictionary containing the updated stats for the player.
        """
        # Set the Simple_stat object's stat_dict attribute to the updated stats.
        self.stat_dict = stat_dict

        # Set the Simple_stat object's lab's stat_dict attribute to the updated stats.
        self.lab.stat_dict = stat_dict

        # Use Stats.do_stat() to calculate the updated stat value for the player.
        self.number = Stats.do_stat(stat_dict, player_id, self.stat, self.hud.hand_instance)

        # If the updated stat value is not 0, update the Simple_stat object's lab with the new value.
        if self.number:
            self.lab.setText(str(self.number[1]))


    def set_color(self, fg=None, bg=None):
        """
        Sets the foreground and/or background color of a QLabel object.

        Args:
        - fg (str): The foreground color to set. If None, foreground color is not changed.
        - bg (str): The background color to set. If None, background color is not changed.

        Returns:
        - None
        """
        # Construct the style sheet string
        ss = "QLabel{"
        if fg:
            ss += f"color: {fg};"
        if bg:
            ss += f"background: {bg};"

        # Apply the style sheet to the QLabel object
        self.lab.setStyleSheet(ss + "}")

class Simple_label(QLabel):
    """
    A simple QLabel subclass for displaying labels in the Simple_HUD.
    """
    pass


class Simple_table_mw(Aux_Base.Seat_Window):
    """
    Create a default table HUD menu label.

    This class recreates the table main window from the default HUD in the old Hud.py.
    It includes the menu options from that HUD.

    Note: It might be better to implement this with a different AW (Aux_Window).
    """

    def __init__(self, hud, aw=None):
        """
        Initializes an instance of Simple_table_mw. 

        Args:
        - hud: The hud object.
        - aw: The aw object, defaults to None.

        Returns:
        None.
        """
        super(Simple_table_mw, self).__init__(aw)
        self.hud = hud
        self.aw = aw
        self.menu_is_popped = False

        # self.connect("configure_event", self.configure_event_cb, "auxmenu") - base class will deal with this

        try:
            self.menu_label = hud.hud_params['label']
        except Exception:
            self.menu_label = "fpdb menu"

        lab = QLabel(self.menu_label)
        lab.setStyleSheet(f"background: {self.aw.bgcolor}; color: {self.aw.fgcolor};")

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(lab)

        self.move(self.hud.table.x + self.aw.xshift, self.hud.table.y + self.aw.yshift)


    def button_press_right(self, event):
        """Handle button clicks in the FPDB main menu event box."""
        # If menu is not already open, open it
        if not self.menu_is_popped:
            self.menu_is_popped = True
            # Create and display menu
            Simple_table_popup_menu(self)

    
    def move_windows(self, *args):
        """Moves the windows to an offset position from the table origin.

        Args:
            *args: Variable length argument list.
        """
        # Force menu to the offset position from table origin (do not use common setting)
        self.move(self.hud.table.x + self.aw.xshift, self.hud.table.y + self.aw.yshift)



class Simple_table_popup_menu(QWidget):
    """
    Create a popup menu for the table HUD.

    This class represents a popup menu for the table HUD, containing various options and configurations.

    Args:
        parentwin: The parent window of the popup menu.

    Attributes:
        parentwin (QWidget): The parent window of the popup menu.

    """

    def __init__(self, parentwin):
        """
        Initializes the Simple_table_popup_menu class.

        Args:
            parentwin: The parent widget of the popup menu.
        """
        super(Simple_table_popup_menu, self).__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.parentwin = parentwin
        self.move(self.parentwin.hud.table.x + self.parentwin.aw.xshift,
                  self.parentwin.hud.table.y + self.parentwin.aw.yshift)
        self.setWindowTitle(self.parentwin.menu_label)

        # Combobox - stat range
        stat_range_combo_dict = {
            0: ("Since: All Time", "A"),
            1: ("Since: Session", "S"),
            2: ("Since: n Days - ->", "T"),
        }

        # Combobox - seats style
        seats_style_combo_dict = {
            0: ("Number of Seats: Any Number", "A"),
            1: ("Number of Seats: Custom", "C"),
            2: ("Number of Seats: Exact", "E"),
        }

        # Combobox - multiplier
        multiplier_combo_dict = {
            0: ("For This Blind Level Only", 1),
            1: ("0.5 to 2 * Current Blinds", 2),
            2: ("0.33 to 3 * Current Blinds", 3),
            3: ("0.1 to 10 * Current Blinds", 10),
            4: ("All Levels", 10000),
        }

        # ComboBox - set max seats
        cb_max_dict = {0: ("Force layout...", None)}
        for pos, i in enumerate(sorted(self.parentwin.hud.layout_set.layout), start=1):
            cb_max_dict[pos] = ("%d-max" % i, i)

        grid = QGridLayout()
        self.setLayout(grid)
        vbox1 = QVBoxLayout()
        vbox2 = QVBoxLayout()
        vbox3 = QVBoxLayout()

        vbox1.addWidget(self.build_button("Restart This HUD", "kill"))
        vbox1.addWidget(self.build_button("Save HUD Layout", "save"))
        vbox1.addWidget(self.build_button("Stop this HUD", "blacklist"))
        vbox1.addWidget(self.build_button("Close", "close"))
        vbox1.addWidget(QLabel(""))
        vbox1.addWidget(self.build_combo_and_set_active("new_max_seats", cb_max_dict))

        vbox2.addWidget(QLabel("Show Player Stats for"))
        vbox2.addWidget(self.build_combo_and_set_active("h_agg_bb_mult", multiplier_combo_dict))
        vbox2.addWidget(self.build_combo_and_set_active("h_seats_style", seats_style_combo_dict))
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Custom"))
        self.h_nums_low_spinner = self.build_spinner("h_seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.h_nums_low_spinner)
        hbox.addWidget(QLabel("To"))
        self.h_nums_high_spinner = self.build_spinner("h_seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.h_nums_high_spinner)
        vbox2.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(self.build_combo_and_set_active("h_stat_range", stat_range_combo_dict))
        self.h_hud_days_spinner = self.build_spinner("h_hud_days", 1, 9999)
        hbox.addWidget(self.h_hud_days_spinner)
        vbox2.addLayout(hbox)

        vbox3.addWidget(QLabel("Show Opponent Stats for"))
        vbox3.addWidget(self.build_combo_and_set_active("agg_bb_mult", multiplier_combo_dict))
        vbox3.addWidget(self.build_combo_and_set_active("seats_style", seats_style_combo_dict))
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Custom"))
        self.nums_low_spinner = self.build_spinner("seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.nums_low_spinner)
        hbox.addWidget(QLabel("To"))
        self.nums_high_spinner = self.build_spinner("seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.nums_high_spinner)
        vbox3.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(self.build_combo_and_set_active("stat_range", stat_range_combo_dict))
        self.hud_days_spinner = self.build_spinner("hud_days", 1, 9999)
        hbox.addWidget(self.hud_days_spinner)
        vbox3.addLayout(hbox)

        self.set_spinners_active()

        grid.addLayout(vbox1, 0, 0)
        grid.addLayout(vbox2, 0, 1)
        grid.addLayout(vbox3, 0, 2)

        self.show()
        self.raise_()


    def delete_event(self):
        """
        Method to delete an event

        Sets menu_is_popped to False and destroys the event
        """
        self.parentwin.menu_is_popped = False
        self.destroy()

        
    def callback(self, checkState, data=None):
        """Callback function called when a checkbox is clicked."""
        if data == "kill":
            # Kill the selected HUD
            self.parentwin.hud.parent.kill_hud("kill", self.parentwin.hud.table.key)
        elif data == "blacklist":
            # Blacklist the selected HUD
            self.parentwin.hud.parent.blacklist_hud("kill", self.parentwin.hud.table.key)
        elif data == "save":
            # Save the current layout for all installed AWs
            self.parentwin.hud.save_layout()
        # Close the current window
        self.delete_event()


    def build_button(self, labeltext, cbkeyword):
        """Builds a QPushButton object with the given label and callback keyword.

        Args:
            labeltext (str): The text to display on the button.
            cbkeyword (str): The keyword to use when calling the callback function.

        Returns:
            QPushButton: The constructed button object.
        """
        # Create a new QPushButton object with the given label text.
        button = QPushButton(labeltext)

        # Connect the button's clicked signal to the callback function, with the
        # given keyword argument.
        button.clicked.connect(partial(self.callback, data=cbkeyword))

        # Return the constructed button object.
        return button


    def build_spinner(self, field, low, high):
        """Builds a spin box widget with specified range and initial value.

        Args:
            field (str): The name of the field to be associated with the spin box.
            low (int): The lowest value that can be selected in the spin box.
            high (int): The highest value that can be selected in the spin box.

        Returns:
            A QSpinBox object with specified range and initial value.
        """
        # Create a QSpinBox object
        spinBox = QSpinBox()

        # Set the range of the spin box
        spinBox.setRange(low, high)

        # Set the initial value of the spin box to the value of the specified field
        spinBox.setValue(self.parentwin.hud.hud_params[field])

        # Connect the valueChanged signal of the spin box to a method that updates the specified field
        spinBox.valueChanged.connect(partial(self.change_spin_field_value, field=field))

        # Return the spin box object
        return spinBox


    def build_combo_and_set_active(self, field, combo_dict):
        """
        Builds a QComboBox widget and sets the active item based on the field and combo_dict parameters.

        Args:
            field (str): The name of the field.
            combo_dict (dict): A dictionary containing the items to be added to the QComboBox.

        Returns:
            widget (QComboBox): The QComboBox widget.
        """
        # Create a new QComboBox widget.
        widget = QComboBox()

        # Loop through the positions in the combo_dict.
        for pos in combo_dict:
            # Add the item at the current position to the widget.
            widget.addItem(combo_dict[pos][0])

            # If the item's value matches the value of the field, set the current index to the current position.
            if combo_dict[pos][1] == self.parentwin.hud.hud_params[field]:
                widget.setCurrentIndex(pos)

        # Connect the currentIndexChanged signal of the widget to the change_combo_field_value slot.
        widget.currentIndexChanged[int].connect(partial(self.change_combo_field_value, field=field, combo_dict=combo_dict))

        return widget

                
    def change_combo_field_value(self, sel, field, combo_dict):
        """
        Changes the value of a field in the HUD parameters dictionary based on
        the selected item in a combo box.

        Args:
            sel (int): Index of the selected item in the combo box.
            field (str): Name of the field to be changed.
            combo_dict (dict): A dictionary containing the items in the combo box and their corresponding values.

        Returns:
            None
        """
        # Update the value of the field in the HUD parameters dictionary based on the selected item in the combo box
        self.parentwin.hud.hud_params[field] = combo_dict[sel][1]

        # Activate spinners to reflect the new value of the field
        self.set_spinners_active()

                
    def change_spin_field_value(self, value, field):
        """
        Sets the value for a given field in the HUD parameters dictionary.

        Args:
            value: The value to set for the field.
            field: The name of the field to set.

        Returns:
            None
        """
        # Set the value for the given field in the parameters dictionary.
        self.parentwin.hud.hud_params[field] = value


    def set_spinners_active(self):
        """
        Enables or disables certain spinners based on the value of various hud_params.

        If h_stat_range is "T", enables h_hud_days_spinner; otherwise, disables it.
        If stat_range is "T", enables hud_days_spinner; otherwise, disables it.
        If h_seats_style is "C", enables h_nums_low_spinner and h_nums_high_spinner;
        otherwise, disables them.
        If seats_style is "C", enables nums_low_spinner and nums_high_spinner; otherwise,
        disables them.
        """
        if self.parentwin.hud.hud_params['h_stat_range'] == "T":
            self.h_hud_days_spinner.setEnabled(True)
        else:
            self.h_hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params['stat_range'] == "T":
            self.hud_days_spinner.setEnabled(True)
        else:
            self.hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params['h_seats_style'] == "C":
            self.h_nums_low_spinner.setEnabled(True)
            self.h_nums_high_spinner.setEnabled(True)
        else:
            self.h_nums_low_spinner.setEnabled(False)
            self.h_nums_high_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params['seats_style'] == "C":
            self.nums_low_spinner.setEnabled(True)
            self.nums_high_spinner.setEnabled(True)
        else:
            self.nums_low_spinner.setEnabled(False)
            self.nums_high_spinner.setEnabled(False)

