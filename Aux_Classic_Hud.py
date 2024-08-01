#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    Copyright 2011-2012,  "Gimick" of the FPDB project  fpdb.sourceforge.net
#                     -  bbtgaf@googlemail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.

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


import contextlib
# import L10n
# _ = L10n.get_translation()

# to do
# =======
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
from PyQt5.QtWidgets import QInputDialog, QMessageBox
import SQL
import Database
import Configuration
import os

class Classic_HUD(Aux_Hud.Simple_HUD):
    """
        There is one instance of this class per poker table
        the stat_windows for each player are controlled
        from this class.
    """

    def __init__(self, hud, config, params):
        super(Classic_HUD, self).__init__(hud, config, params)

        # the following attributes ensure that the correct
        # classes are invoked by the calling modules (aux_hud+mucked)

        self.aw_class_window = Classic_Stat_Window
        self.aw_class_stat = Classic_stat
        self.aw_class_table_mw = Classic_table_mw
        self.aw_class_label = Classic_label


class Classic_Stat_Window(Aux_Hud.Simple_Stat_Window):
    """Stat windows are the blocks shown continually, 1 for each player."""

    def update_contents(self, i):
        super(Classic_Stat_Window, self).update_contents(i)
        if i == "common":
            return

        # control kill/display of active/inactive player stat blocks
        if self.aw.get_id_from_seat(i) is None:
            # no player dealt in this seat for this hand
            # hide the display
            self.hide()
        else:
            # player dealt-in, force display of stat block
            # need to call move() to re-establish window position
            self.move(self.aw.positions[i][0]+self.aw.hud.table.x,
                        self.aw.positions[i][1]+self.aw.hud.table.y)
            self.setWindowOpacity(float(self.aw.params['opacity']))
            # show item, just in case it was hidden by the user
            self.show()

    def button_press_middle(self, event):
        self.hide()


class Classic_stat(Aux_Hud.Simple_stat):
    """A class to display each individual statistic on the Stat_Window"""

    def __init__(self, stat, seat, popup, game_stat_config, aw):

        super(Classic_stat, self).__init__(stat, seat, popup, game_stat_config, aw)
        # game_stat_config is the instance of this stat in the supported games stat configuration
        # use this prefix to directly extract the attributes

        # debug
        # print(f"Initializing Classic_stat for {stat}")
        # print(f"stat_locolor: {game_stat_config.stat_locolor}")
        # print(f"stat_loth: {game_stat_config.stat_loth}")
        # print(f"stat_midcolor: {game_stat_config.stat_midcolor}")
        # print(f"stat_hicolor: {game_stat_config.stat_hicolor}")
        # print(f"stat_hith: {game_stat_config.stat_hith}")

        self.aw = aw
        self.popup = game_stat_config.popup
        self.click = game_stat_config.click
        self.incolor = "rgba(0, 0, 0, 0)"
        if self.click == "open_comment_dialog":
            self.lab.mouseDoubleClickEvent = self.open_comment_dialog
        #print(f"value of self.click in the constructor : {self.click}")  # debug
        self.tip = game_stat_config.tip     # not implemented yet
        self.hudprefix = game_stat_config.hudprefix
        self.hudsuffix = game_stat_config.hudsuffix

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
            self.stat_midcolor = game_stat_config.stat_midcolor
        except Exception:
            self.stat_midcolor = ""
        try:
            self.hudcolor = game_stat_config.hudcolor
        except Exception:
            self.hudcolor = aw.params['fgcolor']


    def open_comment_dialog(self, event):
        if self.stat != "playershort":
            return
        
        player_id = self.get_player_id()
        if player_id is None:
            return

        player_name = self.get_player_name(player_id)
        current_comment = self.get_current_comment(player_id)
        
        new_comment, ok = QInputDialog.getMultiLineText(
            None, 
            f"Add comment to player: {player_name}",
            f"Add your comment for {player_name}:",
            current_comment
        )
        if ok:
            self.save_comment(player_id, new_comment)

    def get_player_id(self):
        for id, data in self.stat_dict.items():
            if data['seat'] == self.lab.aw_seat:
                return id
        return None

    def get_player_name(self, player_id):
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query['get_player_name']
            db.cursor.execute(q, (player_id,))
            result = db.cursor.fetchone()
            return result[0] if result else "Unknown Player"
        except Exception as e:
            print(f"Error fetching player name: {e}")
            return "Unknown Player"
        finally:
            db.close_connection()

    def get_current_comment(self, player_id):
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query['get_player_comment']
            db.cursor.execute(q, (player_id,))
            result = db.cursor.fetchone()
            return result[0] if result else ""
        except Exception as e:
            print(f"Error fetching comment: {e}")
            return ""
        finally:
            db.close_connection()

    def save_comment(self, player_id, comment):
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query['update_player_comment']
            db.cursor.execute(q, (comment, player_id))
            db.commit()
            QMessageBox.information(None, "Comment saved", "The comment has been successfully saved.")
        except Exception as e:
            print(f"Error saving comment: {e}")
            QMessageBox.warning(None, "Error", f"An error occurred while saving the comment: {e}")
        finally:
            db.close_connection()

    def has_comment(self, player_id):
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query['get_player_comment']
            db.cursor.execute(q, (player_id,))
            result = db.cursor.fetchone()
            return bool(result and result[0])
        except Exception as e:
            print(f"Error checking comment: {e}")
            return False
        finally:
            db.close_connection()


    def update(self, player_id, stat_dict):
        super(Classic_stat, self).update(player_id, stat_dict)

        if not self.number:  # stat did not create, so exit now
            return False

        fg = self.hudcolor
        #print(f"Updating stat for {self.stat}: value={self.number[1]}, loth={self.stat_loth}, hith={self.stat_hith}")
        
        if self.stat_loth != "" and self.stat_hith != "":
            try:
                value_str = self.number[1]
                if value_str == "NA":
                    fg = self.incolor   # default color for NA
                else:
                    value = float(value_str)
                    if value < float(self.stat_loth):
                        fg = self.stat_locolor
                        #print(f"Using locolor: {fg}")
                    elif value < float(self.stat_hith):
                        fg = self.stat_midcolor
                        #print(f"Using midcolor: {fg}")
                    else:
                        fg = self.stat_hicolor
                        #print(f"Using hicolor: {fg}")
            except Exception as e:
                print(f"Error in color selection: {e}")

        
        statstring = f"{self.hudprefix}{str(self.number[1])}{self.hudsuffix}"

        # Check if the player has a comment and adjust color or add symbol if it's playershort
        if self.stat == "playershort" and self.has_comment(player_id):
            #fg = "#FF0000"  # Red color for players with comments
            icon_path = os.path.join(Configuration.GRAPHICS_PATH, 'pencil.png')  # Chemin vers l'image de l'icône
            icon_img = f'<img src="{icon_path}" width="24" height="24">'  # Ajuster la taille de l'icône
            statstring = f"{icon_img} {self.hudprefix}{str(self.number[1])}{self.hudsuffix} "  # Add star symbol

        self.set_color(fg=fg, bg=None)
        self.lab.setText(statstring)

        tip = f"{stat_dict[player_id]['screen_name']}\n{self.number[5]}\n{self.number[3]}, {self.number[4]}"
        Stats.do_tip(self.lab, tip)


class Classic_label(Aux_Hud.Simple_label):
    pass


class Classic_table_mw(Aux_Hud.Simple_table_mw):
    """
    A class normally controlling the table menu for that table
    Normally a 1:1 relationship with the Classic_HUD class
    
    This is invoked by the create_common method of the Classic/Simple_HUD class
    (although note that the positions of this block are controlled by shiftx/y
    and NOT by the common position in the layout)
    Movements of the menu block are handled through Classic_HUD/common methods
    """
    pass
