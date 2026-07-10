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

"""Aux_Classic_Hud.py.

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

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QTextEdit, QVBoxLayout

#    FreePokerTools modules
from fpdb_3_legacy import Aux_Hud, Database, Stats
from fpdb_3_legacy.AutoNotes import format_generated_notes

#    Standard Library modules
from fpdb_3_legacy.loggingFpdb import get_logger

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hud_main")


class ClassicHud(Aux_Hud.SimpleHUD):
    """There is one instance of this class per poker table.

    The stat_windows for each player are controlled
    from this class.
    """

    def __init__(self, hud: Any, config: Any, params: Any) -> None:
        """Initializes the ClassicHud instance for a poker table.

        Sets up the class attributes to ensure the correct stat window, stat, table menu, and label classes are used.

        Args:
            hud: The HUD instance associated with the table.
            config: The configuration object for the HUD.
            params: Additional parameters for HUD customization.
        """
        super().__init__(hud, config, params)

        # the following attributes ensure that the correct
        # classes are invoked by the calling modules (aux_hud+mucked)

        self.aw_class_window = ClassicStatWindow
        self.aw_class_stat = ClassicStat
        self.aw_class_table_mw = ClassicTableMw
        self.aw_class_label = ClassicLabel


class ClassicStatWindow(Aux_Hud.SimpleStatWindow):
    """Stat windows are the blocks shown continually, 1 for each player."""

    @staticmethod
    def _nz(value: int | None, default: int = 0) -> int:
        """Returns the value if it is not None, otherwise returns the default.

        This utility function provides a fallback value when the input is None.

        Args:
            value: The value to check for None.
            default: The value to return if value is None.

        Returns:
            int: The value if not None, otherwise the default.
        """
        return default if value is None else value

    def update_contents(self, seat: int | str) -> None:
        """Updates the contents of the stat window for the given seat.

        This method refreshes the stat window display, hiding or repositioning it as needed based on the seat status.

        Args:
            seat: The seat identifier, which can be an integer or the string "common".
        """
        super().update_contents(seat)

        if seat == "common" or seat == "table":
            return

        if self.isHidden():
            return

        # seat inactive → hide window
        if self.aw.get_id_from_seat(seat) is None:
            self.hide()
            return

        # active seat → position and display
        self._position_and_show_block(seat)

    def _position_and_show_block(self, seat: int) -> None:
        """Show the stat window, repositioning only on a real geometry change.

        Windows are placed at create() and re-placed on resize/move; a plain
        per-hand refresh must not move them. We gate the move on the hud's
        geometry generation: the window remembers the generation it was last
        placed at and only re-moves when it differs, so nothing drifts between
        hands. Multiblock windows use their own canonical position (never the
        shared seat anchor); classic single-window seats use the seat anchor.

        Args:
            seat: The seat number for which to show the stat window.
        """
        gen = getattr(self.aw.hud, "geometry_generation", 0)
        if getattr(self, "_pos_gen", None) != gen:
            block_key = getattr(self, "block_key", None)
            if block_key is not None:
                canon = self.aw._canonical_for(block_key)
                pos_x, pos_y = self.aw._canonical_to_screen(canon)
                log.debug(
                    "MULTIBLOCK HUD - seat %s block %s: canonical %s -> screen (%d,%d)",
                    seat, block_key, canon, pos_x, pos_y,
                )
            else:
                table_x = self._nz(self.aw.hud.table.x)
                table_y = self._nz(self.aw.hud.table.y)
                pos_x = max(0, self.aw.positions[seat][0] + table_x)
                pos_y = max(0, self.aw.positions[seat][1] + table_y)
                log.info(
                    "CLASSIC HUD - Moving seat %d stat window to (%d,%d)",
                    seat, pos_x, pos_y,
                )
            self.move(pos_x, pos_y)
            self._pos_gen = gen

        self.setWindowOpacity(float(self.aw.params["opacity"]))
        self.show()  # in case the user has hidden it

    def button_press_middle(self, _event: Any) -> None:
        """Handles the middle mouse button press event.

        This method hides the stat window when the middle mouse button is pressed.

        Args:
            _event: The event object associated with the mouse button press.
        """
        self.hide()


class ClassicStat(Aux_Hud.SimpleStat):
    """A class to display each individual statistic on the Stat_Window."""

    def __init__(
        self,
        stat: str,
        seat: int,
        popup: Any,
        aw: Any,
        colors: dict | None = None,
    ) -> None:
        """Initializes a ClassicStat instance for displaying a statistic.

        Sets up the statistic's configuration, color, and click behavior based on the HUD and stat configuration.

        Args:
            stat: The name of the statistic to display.
            seat: The seat number associated with the statistic.
            popup: The popup configuration or identifier for the stat.
            aw: The auxiliary HUD object providing context and configuration.
            colors: Optional color parameters for the statistic.
        """
        super().__init__(stat, seat, popup, aw, colors=colors)
        # popup is the instance of this stat in the supported games stat configuration
        # use this prefix to directly extract the attributes

        self.aw = aw
        self.popup = popup  # popup is a string identifier
        self.click = ""  # Default click action
        self.incolor = "rgba(0, 0, 0, 0)"
        self.tip = ""  # not implemented yet
        self.hudprefix = ""
        self.hudsuffix = ""

        # Try to get configuration for this stat from the hud config
        stat_config = None
        try:
            # Access the stat configuration properly through supported_games_parameters
            if hasattr(aw.hud, "supported_games_parameters") and aw.hud.supported_games_parameters:
                stat_set = aw.hud.supported_games_parameters.get("game_stat_set")
                if stat_set and hasattr(stat_set, "stats"):
                    # Find the stat by name across all positions
                    for stat_obj in stat_set.stats.values():
                        if hasattr(stat_obj, "stat_name") and stat_obj.stat_name == stat:
                            stat_config = stat_obj
                            break

            if stat_config:
                self.stat_locolor = getattr(stat_config, "stat_locolor", "")
                self.stat_loth = getattr(stat_config, "stat_loth", "")
                self.stat_hicolor = getattr(stat_config, "stat_hicolor", "")
                self.stat_hith = getattr(stat_config, "stat_hith", "")
                self.stat_midcolor = getattr(stat_config, "stat_midcolor", "")
                self.hudcolor = getattr(stat_config, "hudcolor", aw.params["fgcolor"]) or aw.params["fgcolor"]
                self.hudprefix = getattr(stat_config, "hudprefix", "")
                self.hudsuffix = getattr(stat_config, "hudsuffix", "")
                self.click = getattr(stat_config, "click", "")
                self.tip = getattr(stat_config, "tip", "")
            else:
                # Fallback to defaults if config not found
                self.stat_locolor = ""
                self.stat_loth = ""
                self.stat_hicolor = ""
                self.stat_hith = ""
                self.stat_midcolor = ""
                self.hudcolor = aw.params["fgcolor"]

        except (AttributeError, KeyError):
            # Fallback to defaults if config not found
            self.stat_locolor = ""
            self.stat_loth = ""
            self.stat_hicolor = ""
            self.stat_hith = ""
            self.stat_midcolor = ""
            self.hudcolor = aw.params["fgcolor"]

        if self.click == "open_comment_dialog":
            self.lab.mouseDoubleClickEvent = self.open_comment_dialog

    def open_comment_dialog(self, _event: Any) -> None:
        """Opens a dialog for adding or editing a comment for a player.

        This method displays a multi-line input dialog to allow the user
        to add or update a comment for the selected player.

        Args:
            _event: The event object associated with the double-click action.
        """
        if self.stat not in ("playershort", "player_note"):
            return

        player_id = self.get_player_id()
        if player_id is None:
            return

        player_name = self.get_player_name(player_id)
        current_comment = self.get_current_comment(player_id)
        generated_notes = self.get_generated_notes_text(player_id)

        dialog = QDialog()
        dialog.setWindowTitle(f"Player notes: {player_name}")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(f"Manual note for {player_name}:"))
        manual_note = QTextEdit()
        manual_note.setPlainText(current_comment)
        manual_note.setMinimumSize(460, 160)
        layout.addWidget(manual_note)

        layout.addWidget(QLabel("Generated notes:"))
        auto_notes = QTextEdit()
        auto_notes.setReadOnly(True)
        auto_notes.setPlainText(generated_notes or "No generated notes.")
        auto_notes.setMinimumSize(460, 180)
        layout.addWidget(auto_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            self.save_comment(player_id, manual_note.toPlainText())

    def get_player_id(self) -> int | None:
        """Returns the player ID for the current seat.

        This method searches the stat dictionary for a player
        whose seat matches the label's seat and returns their player ID.

        Returns:
            int | None: The player ID if found, otherwise None.
        """
        return next(
            (player_id_ for player_id_, data in self.stat_dict.items() if data["seat"] == self.lab.aw_seat), None
        )

    def get_player_name(self, player_id: int) -> str:
        """Returns the player name for the given player ID.

        This method queries the database to retrieve the player's name based on their ID.

        Args:
            player_id: The unique identifier of the player.

        Returns:
            str: The player's name if found, otherwise "Unknown Player".
        """
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query["get_player_name"]
            db.cursor.execute(q, (player_id,))
            result = db.cursor.fetchone()
            return result[0] if result else "Unknown Player"
        except Exception:  # intentional broad catch: HUD comment DB lookup must not break UI.
            log.exception("Error fetching player name:")
            return "Unknown Player"
        finally:
            db.close_connection()

    def get_current_comment(self, player_id: int) -> str:
        """Retrieves the current comment for the specified player.

        This method queries the database to fetch the comment associated with the given player ID.

        Args:
            player_id: The unique identifier of the player.

        Returns:
            str: The player's comment if found, otherwise an empty string.
        """
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query["get_player_comment"]
            db.cursor.execute(q, (player_id,))
            result = db.cursor.fetchone()
            return result[0] if result else ""
        except Exception:  # intentional broad catch: HUD comment DB lookup must not break UI.
            log.exception("Error fetching comment:")
            return ""
        finally:
            db.close_connection()

    def get_generated_notes_text(self, player_id: int) -> str:
        """Return generated player notes formatted for display."""
        db = Database.Database(self.aw.hud.config)
        try:
            return format_generated_notes(db.getPlayerAutoNotes(player_id, limit=50))
        except Exception:
            log.exception("Error fetching generated notes:")
            return ""
        finally:
            db.close_connection()

    def save_comment(self, player_id: int, comment: str) -> None:
        """Saves a comment for the specified player in the database.

        This method updates the player's comment and displays a message box indicating success or failure.

        Args:
            player_id: The unique identifier of the player.
            comment: The comment text to be saved.
        """
        db = Database.Database(self.aw.hud.config)
        try:
            q = db.sql.query["update_player_comment"]
            db.cursor.execute(q, (comment, player_id))
            db.commit()
            QMessageBox.information(
                None,
                "Comment saved",
                "The comment has been successfully saved.",
            )
        except Exception as e:  # intentional broad catch: HUD comment DB write must not break UI.
            log.exception("Error saving comment:")
            QMessageBox.warning(
                None,
                "Error",
                f"An error occurred while saving the comment: {e}",
            )
        finally:
            db.close_connection()

    def has_comment(self, player_id: int) -> bool:
        """Checks if the specified player has a comment in the database.

        This method queries the database to determine if a comment exists for the given player ID.

        Args:
            player_id: The unique identifier of the player.

        Returns:
            bool: True if a comment exists for the player, otherwise False.
        """
        db = Database.Database(self.aw.hud.config)
        try:
            return db.playerHasNotes(player_id)
        except Exception:  # intentional broad catch: HUD comment DB lookup must not break UI.
            log.exception("Error checking comment:")
            return False
        finally:
            db.close_connection()

    def update(self, player_id: int, stat_dict: dict) -> bool | None:
        """Updates the display of the statistic for a given player.

        This method refreshes the statistic's value, color,
        and tooltip based on the player's data and stat configuration.

        Args:
            player_id: The unique identifier of the player.
            stat_dict: A dictionary containing statistics for all players.

        Returns:
            bool | None: Returns False if the stat was not created, otherwise None.
        """
        super().update(player_id, stat_dict)

        if not self.number:  # stat did not create, so exit now
            return False

        fg = self.hudcolor

        if self.stat_loth != "" and self.stat_hith != "":
            try:
                value_str = self.number[1]
                if value_str in ("NA", "-", ""):
                    fg = "white"  # default color for NA/no data
                else:
                    # Stat values can be money/percent formatted (e.g. "$-0.43",
                    # "$1.99", "45%"): strip everything but digits, sign and the
                    # decimal point before the numeric threshold comparison.
                    cleaned = "".join(ch for ch in value_str if ch.isdigit() or ch in ".-")
                    value = float(cleaned)
                    if value < float(self.stat_loth):
                        fg = self.stat_locolor
                    elif value < float(self.stat_hith):
                        fg = self.stat_midcolor
                    else:
                        fg = self.stat_hicolor
            except (ValueError, IndexError):
                log.exception("Error in color selection:")

        statstring = f"{self.hudprefix}{self.number[1]!s}{self.hudsuffix}"

        # Special handling for playerprofile virtual stat
        if self.stat == "playerprofile":
            try:
                from fpdb_3_legacy.PlayerProfiler import classify_player
                profile, icon, color = classify_player(stat_dict, player_id)
                fg = color
                statstring = f"{self.hudprefix}{icon}{self.hudsuffix}"
            except Exception:  # intentional broad catch
                log.exception("Error in playerprofile classic stat update:")

        # Special handling to append profile and color player names
        elif self.stat in ("playershort", "playername"):
            try:
                hud_params = getattr(self.hud, "hud_params", {})
                player_profiling = hud_params.get("player_profiling", "True") == "True"
                profile_in_name = hud_params.get("profile_in_name", "True") == "True"
                min_hands = int(hud_params.get("profile_min_hands", 10))
            except Exception:  # intentional broad catch
                player_profiling = True
                profile_in_name = True
                min_hands = 10

            if player_profiling and profile_in_name:
                try:
                    from fpdb_3_legacy.PlayerProfiler import classify_player
                    profile, icon, color = classify_player(stat_dict, player_id, min_hands)
                    if profile != "unknown":
                        fg = color
                        statstring = f"{self.hudprefix}{self.number[1]!s} {icon}{self.hudsuffix}"
                except Exception:  # intentional broad catch
                    log.exception("Error in playershort/playername classic stat update:")

        # Special handling for player_note stat - change color based on notes
        elif self.stat == "player_note":
            if self.has_comment(player_id):
                # Orange/yellow color when notes exist
                statstring = f'<span style="color: #FFA500; font-size: 16px;">{self.number[1]}</span>'
            else:
                # Gray color when no notes
                statstring = f'<span style="color: #808080; font-size: 16px;">{self.number[1]}</span>'

        self.set_color(fg=fg, bg=None)
        self.lab.setText(statstring)

        screen_name = stat_dict.get(player_id, {}).get("screen_name") or f"Player {player_id}"
        tip = f"{screen_name}\n{self.number[5]}\n{self.number[3]}, {self.number[4]}"
        try:
            from fpdb_3_legacy.PlayerProfiler import classify_player
            profile, icon, color = classify_player(stat_dict, player_id)
            if profile != "unknown":
                tip += f"\nProfile: {profile.upper()} {icon}"
        except Exception:  # intentional broad catch
            pass

        Stats.do_tip(self.lab, tip)
        return None


class ClassicLabel(Aux_Hud.SimpleLabel):
    """A simple label for the HUD."""


class ClassicTableMw(Aux_Hud.SimpleTableMW):
    """A class normally controlling the table menu for that table.

    Normally a 1:1 relationship with the ClassicHud class.

    This is invoked by the create_common method of the Classic/Simple_HUD class
    (although note that the positions of this block are controlled by shiftx/y
    and NOT by the common position in the layout)
    Movements of the menu block are handled through ClassicHud/common methods
    """
