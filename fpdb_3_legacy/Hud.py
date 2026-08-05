"""Hud.py.

Create and manage the hud overlays.
"""
#    Copyright 2008-2012  Ray E. Barker

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

from __future__ import annotations

import copy
from typing import Any

#    FreePokerTools modules
from fpdb_3_legacy import Database, Hand
from fpdb_3_legacy.hud_profiles import HudContext, HudPositionScope

#    Standard Library modules
from fpdb_3_legacy.loggingFpdb import get_logger

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hud")

# Package that holds the aux modules the config refers to by bare name.
LEGACY_PACKAGE = "fpdb_3_legacy"


def importName(module_name: str, name: str) -> Any:
    """Import a named object 'name' from module 'module_name'."""
    #    Recipe 16.3 in the Python Cookbook, 2nd ed.  Thanks!!!!

    # The config names aux modules without a package ("Aux_Classic_Hud"). A
    # source install resolves that from the legacy directory on sys.path, but a
    # packaged build only exposes the package, so fall back to the qualified
    # name rather than losing the HUD overlay.
    candidates = [module_name]
    if "." not in module_name:
        candidates.append(f"{LEGACY_PACKAGE}.{module_name}")

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            module = __import__(candidate, globals(), locals(), [name])
        except Exception as exc:  # intentional broad catch: HUD aux modules are runtime plugins.
            last_error = exc
            continue

        try:
            return getattr(module, name)
        except AttributeError:
            log.exception("Could not find attribute %s in module %s", name, candidate)
            return None

    log.error(
        "Could not load hud module %s (tried %s)",
        module_name,
        ", ".join(candidates),
        exc_info=last_error,
    )
    return None


class Hud:
    """A class to manage the HUD overlays."""

    def __init__(self, parent: Any, table: Any, max_players: int, poker_game: str, game_type: str, config: Any, context: HudContext | None = None) -> None:  # noqa: PLR0913, PLR0915
        """Initialize the HUD.

        This method is intended to be called from the stdin thread,
        so it must not touch the GUI.
        """
        self.parent = parent
        self.table = table
        self.config = config
        self.db_hud_connection: Database.Database | None = None
        self.poker_game = poker_game
        self.game_type = game_type  # (ring|tour)
        self.max = max_players
        self.type = game_type
        self.cards: dict[str, Any] | None = None
        # Table-scope stats (e.g. live_min_stack_bb), refreshed once per hand by
        # HUD_main._set_table_stats; read by table-scope stat widgets.
        self.table_stats: dict[str, Any] = {}
        # Bumped on every real table geometry change (resize/move). Block windows
        # remember the generation they were last placed at and only re-move when
        # it changes, so per-hand refreshes never reposition (see Aux_Hud).
        self.geometry_generation: int = 0
        self.site = table.site
        provided_context = context
        self.hud_context = provided_context or HudContext(
            site=self.site,
            game=poker_game,
            game_type=game_type,
            max_seats=max_players,
        )
        self.hud_params = dict.copy(
            parent.hud_params,
        )  # we must dict.copy a fresh hud_params dict
        # because each aux hud can control local hud param
        # settings.  Simply assigning the dictionary does not
        # create a local/discrete version of the dictionary,
        # so the different hud-windows get cross-contaminated
        self.aux_windows: list[Any] = []
        self.stat_dict: dict[Any, Any] = {}
        self.seat_players: dict[Any, Any] = {}
        self.hand_instance: Any = None
        self.is_loading = False
        self.loading_window: Any = None
        self.table_name = ""
        self.tablenumber: Any = None
        self.tablehudlabel: Any = None

        self.site_parameters = config.get_site_parameters(self.table.site)
        if provided_context is None:
            self.supported_games_parameters = config.get_supported_games_parameters(self.poker_game, self.game_type)
        else:
            self.supported_games_parameters = config.get_supported_games_parameters(
                self.poker_game,
                self.game_type,
                self.hud_context,
            )
        overrides = getattr(parent, "_table_stat_set_overrides", None)
        if self.supported_games_parameters is not None and isinstance(overrides, dict):
            override_name = parent.get_table_stat_set_override(
                self.table.key,
                self.poker_game,
                self.game_type,
            )
            override_stat_set = config.stat_sets.get(override_name) if override_name else None
            if override_stat_set is not None:
                self.supported_games_parameters = dict(self.supported_games_parameters)
                self.supported_games_parameters["game_stat_set"] = override_stat_set
                log.info("Applying table-local HUD profile %s to %s", override_name, self.table.key)
        self.layout_set = config.get_layout(self.table.site, self.game_type)

        # Just throw error and die if any serious config issues are discovered
        if self.supported_games_parameters is None:
            log.warning(
                "No <game_stat_set> found for %s games for type %s.\n",
                self.poker_game,
                self.game_type,
            )
            return

        if self.layout_set is None:
            log.warning(
                "No layout found for %s games for site %s.\n",
                self.game_type,
                self.table.site,
            )
            return

        if self.max not in self.layout_set.layout:
            log.warning(
                "No layout found for %d-max %s games for site %s.\n",
                self.max,
                self.game_type,
                self.table.site,
            )
            return
        self.layout = copy.deepcopy(
            self.layout_set.layout[self.max],
        )  # deepcopy required here, because self.layout is used
        self.position_scope = HudPositionScope.from_hud(self)
        log.debug(
            f"HUD layout created for {self.max}-max table. Positions: {[self.layout.location[i] for i in range(1, self.max + 1) if self.layout.location[i] is not None]}"
        )
        # to propagate block moves from hud to mucked display
        # (needed because there is only 1 layout for all aux)
        #
        # if we didn't deepcopy, self.layout would be shared
        # amongst all open huds - this is fine until one of the
        # huds does a resize, and then we have a total mess to
        # understand how a single block move on a resized screen
        # should be propagated to other tables of different sizes

        # if there are AUX windows configured, set them up
        if self.supported_games_parameters["aux"] != [""]:
            for aux_str in self.supported_games_parameters["aux"].split(","):
                aux = aux_str.strip()  # remove leading/trailing spaces
                aux_params = config.get_aux_parameters(aux)
                my_import = importName(aux_params["module"], aux_params["class"])
                if my_import is None:
                    continue
                # The main action happening below !!!
                # the module/class is instantiated and is fed the config
                # and aux_params.  Normally this is ultimately inherited
                # at Mucked.Aux_seats() for a hud aux
                #
                # The instatiated aux object is recorded in the
                # self.aux_windows list in this module
                #
                # Subsequent updates to the aux's are controlled by
                # hud_main.pyw
                #
                self.aux_windows.append(my_import(self, config, aux_params))

        self.creation_attrs = None

    def move_table_position(self) -> None:
        """Move the table position."""

    def kill(self) -> None:
        """Kill all stat_windows, popups and aux_windows in this HUD."""
        #    heap dead, burnt bodies, blood 'n guts, veins between my teeth
        #    kill all aux windows
        for aux in self.aux_windows:
            try:
                aux.kill()
            except Exception:  # intentional broad catch: aux window callback boundary.
                log.exception("Error killing aux window")
        self.aux_windows = []
        if self.loading_window is not None:
            try:
                self.loading_window.hide()
                self.loading_window.close()
                self.loading_window.deleteLater()
            except Exception:
                log.exception("Error killing HUD loading indicator")
            self.loading_window = None
        if self.db_hud_connection is not None:
            try:
                self.db_hud_connection.close_connection()
            except Exception:
                log.exception("Error closing the legacy HUD database connection")
            self.db_hud_connection = None

    def resize_windows(self) -> None:
        """Resize the windows based on the table size."""
        # resize self.layout object; this will then be picked-up
        # by all attached aux's when called by hud_main.idle_update

        # Freeze each reference field if not already set. They are set
        # independently (not all-or-nothing) because Aux_Hud._ensure_reference
        # may have frozen ref_layout_width/height first from the config layout;
        # gating the whole block on ref_layout_width then skipped setting
        # ref_layout_locations/common and crashed here.
        if not getattr(self, "ref_layout_width", None):
            self.ref_layout_width = self.layout.width or 792
        if not getattr(self, "ref_layout_height", None):
            self.ref_layout_height = self.layout.height or 546
        if not getattr(self, "ref_layout_locations", None):
            self.ref_layout_locations = copy.deepcopy(self.layout.location)
        if not getattr(self, "ref_layout_common", None):
            self.ref_layout_common = self.layout.common

        x_scale = 1.0 * self.table.width / self.ref_layout_width
        y_scale = 1.0 * self.table.height / self.ref_layout_height

        log.info(
            "HUD RESIZE - Table: %dx%d, Reference: %dx%d, Scale: %.2fx%.2f",
            self.table.width,
            self.table.height,
            self.ref_layout_width,
            self.ref_layout_height,
            x_scale,
            y_scale,
        )

        for i in list(range(1, self.max + 1)):
            if self.ref_layout_locations[i]:
                old_pos = self.layout.location[i]
                self.layout.location[i] = (
                    int(self.ref_layout_locations[i][0] * x_scale),
                    int(self.ref_layout_locations[i][1] * y_scale),
                )
                log.debug(
                    "Seat %d layout scaled: (%d,%d) -> (%d,%d)",
                    i,
                    old_pos[0],
                    old_pos[1],
                    self.layout.location[i][0],
                    self.layout.location[i][1],
                )

        if self.ref_layout_common:
            old_common = self.layout.common
            self.layout.common = (
                int(self.ref_layout_common[0] * x_scale),
                int(self.ref_layout_common[1] * y_scale),
            )
            log.info(
                "Common layout scaled: (%d,%d) -> (%d,%d)",
                old_common[0],
                old_common[1],
                self.layout.common[0],
                self.layout.common[1],
            )

        self.layout.width = self.table.width
        self.layout.height = self.table.height

        # Call resize_windows on all aux windows
        for aux in self.aux_windows:
            try:
                aux.resize_windows()
            except Exception:  # intentional broad catch: aux window callback boundary.
                log.exception("Error resizing aux window")

    def reposition_windows(self) -> None:
        """Reposition the windows."""
        for aux in self.aux_windows:
            try:
                aux.reposition_windows()
            except Exception:  # intentional broad catch: aux window callback boundary.
                log.exception("Error repositioning aux window")

    def save_layout(self) -> None:
        """Ask each aux to save its layout back to the config object."""
        for aux in self.aux_windows:
            try:
                aux.save_layout(self.layout)
            except Exception:  # intentional broad catch: aux window callback boundary.
                log.exception("Error saving layout for aux window")
        #    write the layouts back to the HUD_config
        self.config.save()

    def create(
        self,
        hand: int | str,
        config: Any,
        stat_dict: dict[Any, Any],
        *,
        prepared: bool = False,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
        """Update this hud, to the stats and players as of "hand".

        hand is the hand id of the most recent hand played at this table.
        """
        self.stat_dict = stat_dict  # stat_dict from HUD_main.read_stdin is mapped here
        if prepared:
            self.cards = cards or {}
            self.hand_instance = hand_instance
        # the db_connection created in HUD_Main is NOT available to the
        #  hud.py and aux handlers, so create a fresh connection in this class
        # if the db connection is made in __init__, then the sqlite db threading will fail
        #  so the db connection is made here instead.
        elif self.db_hud_connection is None:
            try:
                self.db_hud_connection = Database.Database(self.config)
            except Exception:  # intentional broad catch: HUD DB drivers vary by backend.
                log.exception("Unable to initialize HUD database connection")
                self.db_hud_connection = None
        if not prepared:
            self.cards = self.get_cards(hand)
        if not prepared and self.db_hud_connection is not None:
            try:
                self.hand_instance = Hand.hand_factory(hand, config, self.db_hud_connection)
                self.db_hud_connection.connection.rollback()
            except Exception:  # intentional broad catch: hand factory spans parser and DB code.
                log.exception("Unable to load hand instance for HUD")
                self.hand_instance = None

        log.info("Creating hud from hand %d", hand)

    def update(
        self,
        hand: int | str,
        config: Any,
        *,
        prepared: bool = False,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
        """Re-load a hand instance and refresh the aux windows for ``hand``."""
        if prepared:
            self.hand_instance = hand_instance
            self.cards = cards or {}
        # re-load a hand instance (factory will load correct type for this hand)
        elif self.db_hud_connection is not None:
            self.hand_instance = Hand.hand_factory(hand, config, self.db_hud_connection)
            log.info("hud update after hand_factory")
            self.db_hud_connection.connection.rollback()

        # Get updated cards
        if not prepared:
            self.cards = self.get_cards(hand)

        # Refresh every aux window with the new hand so the displayed stats
        # update. This is the only place they are refreshed for a new hand, so
        # one failing window must not cost the others theirs.
        for aux in self.aux_windows:
            try:
                aux.update_gui(hand)
            except Exception:  # intentional broad catch: aux window callback boundary.
                log.exception("Error updating aux window %s for hand %s", type(aux).__name__, hand)

    def get_cards(self, hand: int | str) -> dict[str, Any]:
        """Get the cards for a given hand."""
        if self.db_hud_connection is None:
            return {}

        try:
            cards = self.db_hud_connection.get_cards(hand)
            if self.poker_game in ["holdem", "omahahi", "omahahilo"]:
                comm_cards = self.db_hud_connection.get_common_cards(hand)
                cards["common"] = comm_cards["common"]
            return cards
        except Exception:  # intentional broad catch: HUD card lookup spans DB backends.
            log.exception("Error getting cards for hand %d", hand)
            return {}
