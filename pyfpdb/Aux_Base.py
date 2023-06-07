#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aux_Base.py

Some base classes for Aux_Hud, Mucked, and other aux-handlers.
These classes were previously in Mucked, and have been split away
for clarity
"""

import contextlib
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

########################################################################

#import L10n
#_ = L10n.get_translation()
#    to do

#    Standard Library modules
import logging
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("hud")

from PyQt5.QtCore import Qt, QObject
from PyQt5.QtWidgets import QWidget

#   FPDB
import Card


# This holds all card images in a nice lookup table. One instance is
# populated on the first run of Aux_Window.get_card_images() and all
# subsequent uses will have the same instance available.
deck = None

# This allows for a performance gain. Loading and parsing 53 SVG cards
# takes some time. If that is done at the first access of
# Aux_Window.get_card_images(), it can add a delay of several seconds.
# A pre-populated deck on the other hand grants instant access.


class Aux_Window(object):
    def __init__(self, hud, params, config):
        """
        Initializes an instance of the Aux_Window class.

        :param hud: The HUD object.
        :param params: The parameters.
        :param config: The configuration object.
        """
        self.hud = hud
        self.params = params
        self.config = config

    def update_data(self, *args):
        """
        Update data method. Override this method as needed.
        """
        pass

    def update_gui(self, *args):
        """
        Update GUI method. Override this method as needed.
        """
        pass

    def create(self, *args):
        """
        Create method. Override this method as needed.
        """
        pass

    def save_layout(self, *args):
        """
        Save layout method. Override this method as needed.
        """
        pass

    def move_windows(self, *args):
        """
        Move windows method. Override this method as needed.
        """
        pass

    def destroy(self):
        """
        Destroy method. Destroys the container.
        """
        with contextlib.suppress(Exception):
            self.container.destroy()

############################################################################
#    Some utility routines useful for Aux_Windows
#
    # Returns the number of places where cards were shown. This can be N
    # players + common cards
    # XXX XXX: AAAAAGGGGGGHHHHHHHHHHHHHH!
    # XXX XXX: 'cards' is a dictionary with EVERY INVOLVED SEAT included;
    # XXX XXX: in addition, the unknown/unshown cards are marked with
    # zeroes, not None
    def count_seats_with_cards(self, cards):
        """Returns the number of seats with shown cards in the list.

        Args:
            cards (dict): A dictionary containing the cards for each seat.

        Returns:
            int: The number of seats with shown cards.
        """
        return sum(
            # Check if the seat is not 'common' and if the first element of the cards_tuple is not 0
            seat != 'common' and cards_tuple[0] != 0
            # Iterate over the items in the cards dictionary as a list of (seat, cards_tuple) tuples
            for seat, cards_tuple in list(cards.items())
    )


    def get_id_from_seat(self, seat):
        """Returns the player id for a given seat number.

        Args:
        seat (int): The seat number of the player.

        Returns:
        int or None: The id of the player, or None if not found.
        """

        # The seat number may not match the actual seat number used in the hand history.
        # This is because some sites skip seat numbers if max is <10, e.g. iPoker 6-max uses seats 1,3,5,6,8,10 NOT 1,2,3,4,5,6
        actual_seat = self.hud.layout.hh_seats[seat]

        # Find the player id associated with the given seat number
        id = next(
            (
                id
                for id, dict in list(self.hud.stat_dict.items())
                if actual_seat == dict['seat']
            ),
            None,
        )

        return id

        
class Seat_Window(QWidget):
    def __init__(self, aw=None, seat=None):
        """
        Initializes an instance of the Seat_Window class.

        :param aw: The Aux_Window object.
        :param seat: The seat object.
        """
        super(Seat_Window, self).__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint)
        self.lastPos = None  # Last position of the window
        self.aw = aw  # The Aux_Window object
        self.seat = seat  # The seat object
        self.resize(10, 10)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)

    def mousePressEvent(self, event):
        """
        Handles left, middle, and right button presses.

        :param event: The mouse event object.
        """
        if event.button() == Qt.LeftButton:
            # Handle left button press
            self.button_press_left(event)
        elif event.button() == Qt.MiddleButton:
            # Handle middle button press
            self.button_press_middle(event)
        elif event.button() == Qt.RightButton:
            # Handle right button press
            self.button_press_right(event)


    def mouseReleaseEvent(self, event):
        """
        Handle the mouse release event.

        Args:
            event (QMouseEvent): The mouse event object.
        """
        if event.button() == Qt.LeftButton:
            # Handle left button release
            self.button_release_left(event)
        elif event.button() == Qt.MiddleButton:
            # Handle middle button release
            self.button_release_middle(event)
        elif event.button() == Qt.RightButton:
            # Handle right button release
            self.button_release_right(event)


    def button_press_left(self, event):
        """
        This function is called when the left button is pressed.
        It sets the last position to the current global position.

        Args:
            event: A QMouseEvent object representing the button press event.
        """
        self.lastPos = event.globalPos()


    def button_press_middle(self, event):
        """
        Handle a button press in the middle of the widget.

        Subclasses should override this method to define custom behavior.
        """
        pass



    def button_press_right(self, event):
        """
        Handle a button press event for the right button.
        Subclasses should override this method to define custom behavior.
        :param event: the event object representing the button press
        """
        pass # subclass will define this


    def mouseMoveEvent(self, event):
        """Handles mouse move events."""
        if self.lastPos is not None:
            # Calculate the new position of the window
            new_pos = self.pos() + event.globalPos() - self.lastPos
            self.move(new_pos)
            self.lastPos = event.globalPos()


    def button_release_left(self, event):
        """
        Callback method for when the left mouse button is released.

        Args:
            event: The event object representing the button release event.
        """
        self.lastPos = None
        self.aw.configure_event_cb(self, self.seat) # Call the configure_event_cb method of the aw object with self and self.seat as arguments.


    def button_release_middle(self, event):
        """
        This method is called when the middle mouse button is released.

        Args:
            event: The event object representing the mouse button release event.
        """
        pass  # Subclass will define this


    def button_release_right(self, event):
        """
        Handle right button release event.

        Args:
            event: The event object passed by the GUI.

        Returns:
            None.
        """
        pass #subclass will define this

    
    def create_contents(self, *args):
        """
        Creates contents for this object.

        Args:
            *args: Variable length argument list.

        Returns:
            None
        """
        pass  # TODO: Implement function


    def update_contents(self, *args):
        """
        Update the contents of the object with the given arguments.

        Args:
            *args: Variable-length argument list.

        Returns:
            None
        """
        pass# TODO: Implement function

    
class Aux_Seats(Aux_Window):
    """
    A superclass to display an aux_window or a stat block at each seat.
    """

    def __init__(self, hud, config, params):
        """
        Initializes an instance of the Aux_Seats class.

        :param hud: The hud object.
        :param config: The configuration object.
        :param params: The parameters object.
        """
        super(Aux_Seats, self).__init__(hud, params, config)
        self.positions = {}  # Dictionary of window positions, normalized for favorite seat and offset
                             # but _not_ offset to the absolute screen position
        self.displayed = False  # Indicates if the seat windows are displayed
        self.uses_timer = False  # Indicates if the Aux_Seats object uses a timer to control hiding
        self.timer_on = False  # Indicates if the timeout for removing the cards is on

        self.aw_class_window = Seat_Window  # Class name to be used by the aw_class_window

    def create_contents(self):
        """
        Placeholder method that should be overridden. Creates the contents of the aux seats.
        """
        pass

    def create_common(self, x, y):
        """
        Placeholder method that should be overridden. Creates common elements of the aux seats.

        :param x: The x position.
        :param y: The y position.
        """
        pass

    def update_contents(self):
        """
        Placeholder method that should be overridden. Updates the contents of the aux seats.
        """
        pass

    
    def resize_windows(self):
        """Calculate window resizing and move windows to the new positions"""

        # Resize calculation has already happened in HUD_main&hud.py

        # Refresh our internal map to reflect these changes
        for i in (list(range(1, self.hud.max + 1))):
            self.positions[i] = self.hud.layout.location[self.adj[i]]
        self.positions["common"] = self.hud.layout.common

        # Move everything to the new places
        self.move_windows()


    def move_windows(self):
        """Move the windows to their designated positions."""
        for i in (list(range(1, self.hud.max + 1))): # loop through windows
            self.m_windows[i].move(self.positions[i][0] + self.hud.table.x, # move window
                                self.positions[i][1] + self.hud.table.y)
        self.m_windows["common"].move(self.hud.layout.common[0] + self.hud.table.x, # move the common window
                                    self.hud.layout.common[1] + self.hud.table.y)

    def create(self):
        """Create the HUD windows and fill them with content."""
        self.adj = self.adj_seats()
        self.m_windows = {}  # windows to put the card/hud items in

        # Create windows for each location in the HUD
        for i in (list(range(1, self.hud.max + 1)) + ['common']):
            if i == 'common':
                # The common window is different from the others. Note that it needs to
                # get realized, shown, topified, etc. in create_common
                # self.hud.layout.xxxxx is updated here after scaling, to ensure
                # layout and positions are in sync
                (x, y) = self.hud.layout.common
                self.m_windows[i] = self.create_common(x, y)
                self.hud.layout.common = self.create_scale_position(x, y)
            else:
                (x, y) = self.hud.layout.location[self.adj[i]]
                self.m_windows[i] = self.aw_class_window(self, i)
                self.positions[i] = self.create_scale_position(x, y)
                self.m_windows[i].move(self.positions[i][0] + self.hud.table.x, self.positions[i][1] + self.hud.table.y)
                self.hud.layout.location[self.adj[i]] = self.positions[i]
                if 'opacity' in self.params:
                    self.m_windows[i].setWindowOpacity(float(self.params['opacity']))

            # Fill the created window with content
            self.create_contents(self.m_windows[i], i)

            # Ensure there is a native window handle for topify
            self.m_windows[i].create()

            # Topify the window and show it
            self.hud.table.topify(self.m_windows[i])
            if not self.uses_timer:
                self.m_windows[i].show()

        # Set the height and width of the HUD layout to match the table
        self.hud.layout.height = self.hud.table.height
        self.hud.layout.width = self.hud.table.width

        

    def create_scale_position(self, x, y):
        """
        For a given x/y, scale according to current height/wid vs. reference
        height/width. This method is needed for create (because the table may not be 
        the same size as the layout in config).

        Any subsequent resizing of this table will be handled through
        hud_main.idle_resize.

        Args:
            x (int): The x-coordinate to scale.
            y (int): The y-coordinate to scale.

        Returns:
            Tuple[int, int]: The scaled x and y coordinates as a tuple of integers.
        """
        x_scale = (1.0 * self.hud.table.width / self.hud.layout.width)
        y_scale = (1.0 * self.hud.table.height / self.hud.layout.height)
        return (int(x * x_scale), int(y * y_scale))

        
    def update_gui(self, new_hand_id):
        """Update the graphical user interface for the new hand ID.

        This function updates the contents of all the windows in the GUI for the new hand ID.
        It also reloads the latest block positions and resizes the windows to allow the 
        propagation of block-moves across the HUD and mucked handlers for this table.

        Args:
            new_hand_id (int): The ID of the new hand.
        """
        # Update the contents of all the windows
        for i in list(self.m_windows.keys()):
            self.update_contents(self.m_windows[i], i)

        # Reload the latest block positions in case another auxiliary has changed them
        # These lines allow the propagation of block-moves across
        # the HUD and mucked handlers for this table
        self.resize_windows()


#   Methods likely to be of use for any Seat_Window implementation
    def destroy(self):
        """Destroy all of the seat windows."""
        with contextlib.suppress(AttributeError):
            # Loop through the keys of the dictionary of windows
            for i in list(self.m_windows.keys()):
                # Destroy the window
                self.m_windows[i].destroy()
                # Remove the window from the dictionary
                del(self.m_windows[i])


#   Methods likely to be useful for mucked card windows (or similar) only
    def hide(self):
        """Hide the seat windows."""
        for (i, w) in list(self.m_windows.items()):
            if w is not None: w.hide()
        self.displayed = False


    def save_layout(self, *args):
        """
        Saves the new layout back to the aux element in the config file.

        This method is overridden in the specific aux because the HUD's controlling stat boxes set the seat positions and
        the mucked card aux's control the common location. This class method would only be valid for an aux which has full
        control over all seat and common locations.
        """
        # Log an error message if this method is called, as it should be handled in the aux.
        log.error("Aux_Seats.save_layout called - this shouldn't happen")
        log.error("save_layout method should be handled in the aux")



    def configure_event_cb(self, widget, i):
        """
        Update the current location for each statblock.
        This method is needed to record moves for an individual block.
        Move/resize also end up in here due to it being a configure.
        This is not optimal, but isn't easy to work around. fixme.

        Args:
            widget: The widget whose position needs to be updated.
            i: The index of the widget in the positions dictionary.

        Returns:
            None.
        """
        if i: 
            # Calculate the new absolute position of the widget
            new_abs_position = widget.pos()

            # Calculate the new position relative to the table
            new_position = (
                new_abs_position.x() - self.hud.table.x,
                new_abs_position.y() - self.hud.table.y
            )

            # Update the positions dictionary with the new position
            self.positions[i] = new_position

            if i != "common":
                # If it's not the common block, update the location in the hud-level dict
                self.hud.layout.location[self.adj[i]] = new_position
            else:
                # If it's the common block, update the common position in the hud-level dict
                self.hud.layout.common = new_position


    def adj_seats(self):
        """
        Determines how to adjust seating arrangements, if a "preferred seat" is set in the hud layout configuration.
        Need range here, not xrange -> need the actual list.

        Returns:
            list: List of adjusted seat numbers.
        """

        adj = list(range(self.hud.max + 1))  # Create list of seat numbers.

        # Does the user have a fav_seat? If so, just return the original list.
        if self.hud.site_parameters["fav_seat"][self.hud.max] == 0:
            return adj

        # Find the hero's actual seat.
        actual_seat = None
        for key in self.hud.stat_dict:
            if self.hud.stat_dict[key]['screen_name'] == self.config.supported_sites[self.hud.site].screen_name:
                # Seat from stat_dict is the seat num recorded in the hand history and database
                # For tables <10-max, some sites omit some seat nums (e.g. iPoker 6-max uses 1,3,5,6,8,10)
                # The seat nums in the hh from the site are recorded in config file for each layout, and available
                # here as the self.layout.hh_seats list
                # (e.g. for iPoker - [None,1,3,5,6,8,10];
                # for most sites- [None, 1,2,3,4,5,6]
                # We need to match 'seat' from hand history with the postion in the list, as the hud
                # always numbers its stat_windows using consecutive numbers (e.g. 1-6).
                for i in range(1, self.hud.max + 1):
                    if self.hud.layout.hh_seats[i] == self.hud.stat_dict[key]['seat']:
                        actual_seat = i
                        break

                if not actual_seat:  # This shouldn't happen because we don't create huds if the hero isn't seated.
                    log.error(("Error finding hero seat."))
                    return adj

                for i in range(self.hud.max + 1):
                    j = actual_seat + i
                    if j > self.hud.max:
                        j = j - self.hud.max
                    adj[j] = self.hud.site_parameters["fav_seat"][self.hud.max] + i
                    if adj[j] > self.hud.max:
                        adj[j] = adj[j] - self.hud.max

                return adj
