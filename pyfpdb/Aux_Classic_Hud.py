#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    Copyright 2011-2012,  "Gimick" of the FPDB project  fpdb.sourceforge.net
#                     -  bbtgaf@googlemail.com
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

########################################################################

"""
Aux_Classic_Hud.py

FPDB classic hud, implemented using new-hud framework.

This module structure must be based upon simple HUD in the module Aux_Hud.

Aux_Hud is minimal frozen functionality and is not changed,so
HUD customisation is done in modules which extend/subclass/override aux_hud.

***HERE BE DRAGONS*** 
Please take extra care making changes to this code - there is 
multiple-level inheritence in much of this code, class heirarchies
are not immediately obvious, and there is very close linkage with most of 
the Hud modules.
"""

from L10n import set_locale_translation
import contextlib
#import L10n
#_ = L10n.get_translation()

# to do
#=======
# check that the parameters stored at AW level make sense for players
#  - when playing more than one site
# sort out the wierd focus issues in flop-mucked.

#    Standard Library modules
import logging
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("hud")

#    FreePokerTools modules
import Aux_Hud
import Stats

set_locale_translation()

class Classic_HUD(Aux_Hud.Simple_HUD):
    """
    There is one instance of this class per poker table.
    The stat_windows for each player are controlled from this class.
    """

    def __init__(self, hud, config, params):
        """
        Initializes an instance of the Classic_HUD class.

        :param hud: The hud object.
        :param config: The configuration object.
        :param params: The parameters object.
        """
        super(Classic_HUD, self).__init__(hud, config, params)

        # The following attributes ensure that the correct
        # classes are invoked by the calling modules (aux_hud+mucked)
        
        self.aw_class_window = Classic_Stat_Window  # Class for auxiliary stat windows
        self.aw_class_stat = Classic_stat  # Class for auxiliary stats
        self.aw_class_table_mw = Classic_table_mw  # Class for auxiliary table muck windows
        self.aw_class_label = Classic_label  # Class for auxiliary labels



class Classic_Stat_Window(Aux_Hud.Simple_Stat_Window):
    """
    Stat windows are the blocks shown continually, one for each player.
    """

    def update_contents(self, i):
        """
        Updates the contents of the stat window for a specific player.

        :param i: The seat index of the player.
        """
        super(Classic_Stat_Window, self).update_contents(i)
        
        if i == "common":
            return

        # Control kill/display of active/inactive player stat blocks
        if self.aw.get_id_from_seat(i) is None:
            # No player dealt in this seat for this hand
            # Hide the display
            self.hide()
        else:
            # Player dealt-in, force display of stat block
            # Need to call move() to re-establish window position
            self.move(
                self.aw.positions[i][0] + self.aw.hud.table.x,
                self.aw.positions[i][1] + self.aw.hud.table.y
            )
            self.setWindowOpacity(float(self.aw.params['opacity']))
            # Show item, just in case it was hidden by the user
            self.show()

            
    def button_press_middle(self, event):
        """
        This function is called when the middle button is pressed.
        It hides the current object.

        Args:
            event: The event object that triggered the function.
        """
        # Hide the current object
        self.hide()



class Classic_stat(Aux_Hud.Simple_stat):
    """
    A class to display each individual statistic on the Stat_Window.
    """

    def __init__(self, stat, seat, popup, game_stat_config, aw):
        """
        Initializes an instance of the Classic_stat class.

        :param stat: The statistic to display.
        :param seat: The seat index of the player.
        :param popup: A flag indicating whether the statistic has a popup.
        :param game_stat_config: The game statistic configuration.
        :param aw: The associated Aux_Window instance.
        """
        super(Classic_stat, self).__init__(stat, seat, popup, game_stat_config, aw)

        # game_stat_config is the instance of this stat in the supported games stat configuration
        # use this prefix to directly extract the attributes
        self.popup = game_stat_config.popup
        self.click = game_stat_config.click  # Not implemented yet
        self.tip = game_stat_config.tip  # Not implemented yet
        self.hudprefix = game_stat_config.hudprefix
        self.hudsuffix = game_stat_config.hudsuffix

        # Set the color attributes, fallback to default values if not provided
        try:
            self.stat_locolor = game_stat_config.stat_locolor
            self.stat_loth = game_stat_config.stat_loth
        except Exception:
            self.stat_locolor = self.stat_loth = ""
        try:
            self.stat_hicolor = game_stat_config.stat_hicolor
            self.stat_hith = game_stat_config.stat_hith
        except Exception:
            self.stat_hicolor = self.stat_hith = ""
        try:
            self.hudcolor = game_stat_config.hudcolor
        except Exception:
            self.hudcolor = aw.params['fgcolor']


    def update(self, player_id, stat_dict):
        """
        Update the player's stats with the given dictionary of stats.

        Args:
            player_id (int): The player's ID.
            stat_dict (dict): The dictionary of stats to update.

        Returns:
            bool: True if the stat was updated successfully, False otherwise.
        """
        # Call the superclass's update method
        super(Classic_stat, self).update(player_id, stat_dict)

        # If the stat was not created, exit the function
        if not self.number: 
            return False

        # Determine the foreground color of the HUD based on the stat's value
        fg=self.hudcolor
        if self.stat_loth != "":
            with contextlib.suppress(Exception):
                if float(self.number[1]) < float(self.stat_loth):
                    fg=self.stat_locolor
        if self.stat_hith != "":
            with contextlib.suppress(Exception):
                if float(self.number[1]) > float(self.stat_hith):
                    fg=self.stat_hicolor

        # Set the HUD color
        self.set_color(fg=fg,bg=None)

        # Set the text of the HUD to display the stat value
        statstring = f"{self.hudprefix}{str(self.number[1])}{self.hudsuffix}"
        self.lab.setText(statstring)

        # Set the tooltip text to display the player's name and some stat details
        tip = "%s\n%s\n%s, %s" % (stat_dict[player_id]['screen_name'], self.number[5], self.number[3], self.number[4])
        Stats.do_tip(self.lab, tip)



class Classic_label(Aux_Hud.Simple_label):
    """
    A class to represent a label in the Classic HUD.
    Inherits from Aux_Hud.Simple_label.
    """
    pass


class Classic_table_mw(Aux_Hud.Simple_table_mw):
    """
    A class normally controlling the table menu for that table.
    Normally a 1:1 relationship with the Classic_HUD class.
    This is invoked by the create_common method of the Classic/Simple_HUD class
    (although note that the positions of this block are controlled by shiftx/y
    and NOT by the common position in the layout).
    Movements of the menu block are handled through Classic_HUD/common methods.
    Inherits from Aux_Hud.Simple_table_mw.
    """
    pass

