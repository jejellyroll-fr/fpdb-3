"""Building, updating and reconfiguring a table's HUD, and its loading indicator.

One of the mixins HudMain (HUD_main.pyw) is built from. What it calls on the
other mixins is declared, for the type checker, on HudMainBase in hud_main_base.
"""

import contextlib
import os
import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from fpdb_3_legacy import Aux_Base, Configuration, Hud, db_profile
from fpdb_3_legacy.hud_diagnostics import session_id
from fpdb_3_legacy.hud_main_base import HUDCreationArgs, HudMainBase, log
from fpdb_3_legacy.hud_profiles import HudContext, HudPositionScope
from fpdb_3_legacy.hud_window_registry import ClaimOutcome
from fpdb_3_legacy.loggingFpdb import hud_trace
from fpdb_3_legacy.SmartHudManager import RestartReason
from fpdb_3_legacy.table_info import TableInfo


class HudMainHudsMixin(HudMainBase):
    """Create, update and reconfigure the HUD of a table."""

    def set_table_stat_set_override(
        self,
        table: str,
        poker_game: str,
        game_type: str,
        stat_set: str,
    ) -> None:
        """Remember a table-local HUD profile for this capture session."""
        if stat_set not in self.config.stat_sets:
            raise KeyError(f"unknown stat set: {stat_set}")
        self._table_stat_set_overrides[table] = (poker_game, game_type, stat_set)
        log.info("Table-local HUD profile: table=%s profile=%s", table, stat_set)

    def get_table_stat_set_override(self, table: str, poker_game: str, game_type: str) -> str | None:
        """Return a compatible table-local profile override, if one exists."""
        override = self._table_stat_set_overrides.get(table)
        if override is None:
            return None
        override_game, override_type, stat_set = override
        if (override_game, override_type) != (poker_game, game_type):
            return None
        return stat_set

    def clear_table_stat_set_override(self, table: str) -> None:
        """Forget the local profile when the underlying table is gone."""
        self._table_stat_set_overrides.pop(table, None)

    def _read_config_fingerprint(self) -> tuple[float, int] | None:
        """Cheap change detector for HUD_config.xml, polled with the tables."""
        try:
            stat = os.stat(self.config.file)
        except OSError:
            return None
        return (stat.st_mtime, stat.st_size)

    def refresh_profiles_from_config(self) -> int:
        """Re-apply the profile rules to open tables after a config change.

        HUD Preferences runs in the fpdb process and this one is a subprocess,
        so nothing can call in when Apply is pressed: the configuration file is
        the signal. Rebuilding a HUD destroys and recreates its windows, which
        the player sees, so only tables whose effective profile actually
        changed are touched -- saving an unrelated preference rebuilds nothing.

        Returns the number of tables rebuilt.
        """
        fingerprint = self._read_config_fingerprint()
        if fingerprint is None or fingerprint == self._config_fingerprint:
            return 0
        self._config_fingerprint = fingerprint
        if self.config.reload() is False:
            log.warning("HUD_config.xml changed but could not be reloaded; keeping the profiles in use")
            return 0

        rebuilt = 0
        for temp_key, hud in list(self.hud_dict.items()):
            if self._reapply_profile(temp_key, hud):
                rebuilt += 1
        if rebuilt:
            log.info("Config change applied: %d table(s) rebuilt with a new HUD profile", rebuilt)
        return rebuilt

    def _reapply_profile(self, temp_key: str, hud: Hud.Hud) -> bool:
        """Rebuild one table if the rules now select a different profile."""
        context = getattr(hud, "hud_context", None)
        if context is None:
            return False
        table_key = getattr(getattr(hud, "table", None), "key", None)
        if table_key is not None and self.get_table_stat_set_override(table_key, hud.poker_game, hud.game_type):
            # The table menu is an explicit, session-only choice by the player.
            return False

        params = self.config.get_supported_games_parameters(hud.poker_game, hud.game_type, context)
        new_stat_set = params.get("game_stat_set") if isinstance(params, dict) else None
        if new_stat_set is None:
            return False
        current = (hud.supported_games_parameters or {}).get("game_stat_set")
        if getattr(new_stat_set, "name", None) == getattr(current, "name", None):
            return False

        try:
            self._rebuild_hud_with_stat_set(hud, new_stat_set)
        except Exception:  # intentional broad catch: a failed rebuild must leave no orphan windows
            log.exception("Rebuilding %s for profile %s failed; restarting it", temp_key, new_stat_set.name)
            self.kill_hud(None, temp_key)
        return True

    @staticmethod
    def _rebuild_hud_with_stat_set(hud: Hud.Hud, stat_set: Any) -> None:
        """Swap a HUD onto another profile, the way the table menu does.

        The scope is recomputed with the profile because saved positions are
        filed under it: a table that changes profile has to read the positions
        belonging to the new one, not keep pointing at the old one's.
        """
        hud.supported_games_parameters = dict(hud.supported_games_parameters)
        hud.supported_games_parameters["game_stat_set"] = stat_set
        hud.position_scope = HudPositionScope.from_hud(hud)
        for aux in list(getattr(hud, "aux_windows", [])):
            if not hasattr(aux, "refresh_stats_layout"):
                continue  # Mucked and friends carry no stat-set layout
            aux.game_params = stat_set
            aux.destroy()
            aux.refresh_stats_layout()
            aux.create()
            if getattr(hud, "stat_dict", None):
                aux.update_gui(None)
        log.info("Table %s rebuilt with HUD profile %s", getattr(hud, "table_name", "?"), stat_set.name)

    def create_HUD(self, args: HUDCreationArgs) -> None:
        """Create a new HUD for a table.

        Refuses outright to put a second renderer on a window that already has
        one, and destroys the previous generation when a window's HUD key
        changes. Both cases are what a player sees as doubled overlays, and
        both are decided here rather than at each of the callers that can
        reach this method.
        """
        log.debug("Creating HUD for table %s and hand %s", args.temp_key, args.new_hand_id)
        window_id = getattr(args.table, "number", None)
        claim = self._window_registry.claim(window_id, args.temp_key)
        if claim.outcome is ClaimOutcome.DUPLICATE:
            log.warning(
                "HUD create refused: window %s already renders table %r at generation %s "
                "(session=%s pid=%s hand=%s)",
                window_id,
                args.temp_key,
                claim.generation,
                session_id(),
                os.getpid(),
                args.new_hand_id,
            )
            return
        if claim.outcome is ClaimOutcome.SUPERSEDED and claim.superseded is not None:
            log.warning(
                "HUD create supersedes table %r on window %s (generation %s -> %s); "
                "destroying the previous renderer first",
                claim.superseded.temp_key,
                window_id,
                claim.superseded.generation,
                claim.generation,
            )
            self._destroy_superseded_hud(claim.superseded.temp_key)

        self._hud_generation = claim.generation
        # What this key held before the attempt. A build that fails must leave
        # it exactly there: the same key can already have a live HUD on an
        # earlier window of the same table, and that HUD is none of this
        # attempt's business.
        previous_hud = self.hud_dict.get(args.temp_key)
        try:
            self._build_claimed_hud(args, window_id)
        except Exception:
            # The window is claimed before the HUD is built, so a build that
            # raises leaves the claim behind -- and every later hand for this
            # table is then refused as a duplicate, which makes one failure
            # permanent and silent. Hand back the window *this attempt*
            # claimed, and let the error travel on to its usual handler.
            self._window_registry.release_registration(claim.registration)
            if previous_hud is None:
                self.hud_dict.pop(args.temp_key, None)
            else:
                self.hud_dict[args.temp_key] = previous_hud
            log.warning(
                "HUD create failed for table %r on window %s; released the window so the next hand can retry",
                args.temp_key,
                window_id,
            )
            raise

    def _build_claimed_hud(self, args: HUDCreationArgs, window_id: Any) -> None:
        """Build the HUD for a window this caller has already claimed.

        Separate from ``create_HUD`` only so that the claim can be undone as a
        whole when any part of the build fails.
        """
        self.hud_dict[args.temp_key] = Hud.Hud(
            self,
            args.table,
            args.max_seats,
            args.poker_game,
            args.game_type,
            self.config,
            args.context,
        )
        self.hud_dict[args.temp_key].table_name = args.temp_key
        self.hud_dict[args.temp_key].stat_dict = args.stat_dict
        self.hud_dict[args.temp_key].cards = args.cards
        self.hud_dict[args.temp_key].max = args.max_seats
        self.hud_dict[args.temp_key]._fpdb_generation = self._hud_generation
        # Before idle_create, because the aux windows read this in adj_seats()
        # when they are built. Setting it afterwards -- which is where every
        # caller used to set it -- left the seat rotation applied twice.
        if self._creation_is_fast_fold(args):
            self.hud_dict[args.temp_key].is_fast_fold = True

        args.table.hud = self.hud_dict[args.temp_key]

        self.hud_dict[args.temp_key].hud_params["new_max_seats"] = None  # trigger for seat layout change

        if not args.loading:
            for aw in self.hud_dict[args.temp_key].aux_windows:
                aw.update_data(args.new_hand_id, self.db_connection)

        self.idle_create(args)
        self._publish_analytics(self.hud_dict[args.temp_key], args.new_hand_id)
        created = self.hud_dict[args.temp_key]
        log.info(
            "HUD created: session=%s pid=%s generation=%s table=%r window_id=%s hand=%s "
            "profile=%r aux=%s overlays=%s",
            session_id(),
            os.getpid(),
            self._hud_generation,
            args.temp_key,
            window_id,
            args.new_hand_id,
            getattr(getattr(created, "stat_set", None), "name", None),
            self._describe_aux_windows(created),
            self._describe_overlay_win_ids(created),
        )
        log.debug("HUD for table %s created successfully.", args.temp_key)

    def _creation_is_fast_fold(self, args: HUDCreationArgs) -> bool:
        """Whether the HUD being created is for a Fast-Fold table.

        Decided from what the caller already knows rather than from the HUD
        object, because this has to be answered before the HUD's aux windows
        exist. ``context.speed`` is set by ``_create_new_hud`` for every path;
        the table set is the fallback for a direct ``create_HUD`` call.
        """
        if getattr(args.context, "speed", None) == "fast":
            return True
        return args.temp_key in getattr(self, "_fast_fold_tables", set())

    def _destroy_superseded_hud(self, temp_key: str) -> None:
        """Tear down a HUD whose window has been claimed by another key.

        Goes through the ordinary kill path so the label, the aux windows and
        the pending Fast-Fold state all go with it; leaving any of them behind
        is exactly the residual overlay this guard exists to prevent.
        """
        if temp_key not in self.hud_dict:
            self._window_registry.release(temp_key)
            return
        self.clear_table_stat_set_override(temp_key)
        self.idle_kill(temp_key)

    @staticmethod
    def _describe_aux_windows(hud: Hud.Hud) -> str:
        """Name the aux window classes attached to a HUD, with their count."""
        aux_windows = list(getattr(hud, "aux_windows", []) or [])
        names = ",".join(sorted({type(aux).__name__ for aux in aux_windows})) or "none"
        return f"{len(aux_windows)}[{names}]"

    @staticmethod
    def _describe_overlay_win_ids(hud: Hud.Hud) -> str:
        """List the native window ids of a HUD's own overlay windows.

        This is what tells a second renderer from a redrawn one: two sets of
        blocks over one table carry two disjoint sets of native ids, while one
        set painted twice keeps the ids it already had. ``m_windows`` holds the
        per-seat blocks, ``container`` the single-window aux types.
        """
        ids: list[str] = []
        for aux in list(getattr(hud, "aux_windows", []) or []):
            name = type(aux).__name__
            widgets = list((getattr(aux, "m_windows", None) or {}).values())
            container = getattr(aux, "container", None)
            if container is not None:
                widgets.append(container)
            for widget in widgets:
                win_id = getattr(widget, "winId", None)
                if not callable(win_id):
                    continue
                with contextlib.suppress(Exception):
                    ids.append(f"{name}:{int(win_id())}")
        return ",".join(ids) or "none"

    def update_HUD(
        self,
        new_hand_id: str,
        table_name: str,
        config: Configuration.Config,
        *,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
        """Update an existing HUD."""
        log.debug("Updating HUD for table %s and hand %s", table_name, new_hand_id)
        if cards is None and hand_instance is None:
            self.idle_update(new_hand_id, table_name, config)
        else:
            self.idle_update(
                new_hand_id,
                table_name,
                config,
                cards=cards,
                hand_instance=hand_instance,
            )

    def _initialize_hero_data(self) -> None:
        """Initialize hero data from the configuration."""
        self.hero = {}
        self.hero_ids = {}
        enabled_sites = self.config.get_supported_sites()
        if not enabled_sites:
            log.error("No enabled sites found")
            self.db_connection.connection.rollback()
            self.destroy()
            return

        for site in enabled_sites:
            if result := self.db_connection.get_site_id(site):
                site_id = result[0][0]
                self.hero[site_id] = self.config.supported_sites[site].screen_name
                player_id = self.db_connection.get_player_id(self.config, site, self.hero[site_id])
                self.hero_ids[site_id] = -1 if player_id is None else player_id

            for db_site in self._get_db_site_aliases(site):
                if db_site == site:
                    continue
                if result := self.db_connection.get_site_id(db_site):
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    player_id = self.db_connection.get_player_id(self.config, db_site, self.hero[site_id])
                    self.hero_ids[site_id] = -1 if player_id is None else player_id

    def _get_db_site_aliases(self, config_site: str) -> tuple[str, ...]:
        """Return database site names covered by one HUD config site."""
        if config_site == "PokerStars":
            return (
                "PokerStars",
                "PokerStars.COM",
                "PokerStars.FR",
                "PokerStars.IT",
                "PokerStars.ES",
                "PokerStars.PT",
                "PokerStars.EU",
                "PokerStars.DE",
            )
        return (config_site,)

    def _resolve_hud_config_site(self, db_site_name: str, enabled_sites: list[str]) -> str:
        """Map regional DB site names to the HUD config site used for layout/detection."""
        if db_site_name in enabled_sites:
            return db_site_name
        if db_site_name.startswith("PokerStars.") and "PokerStars" in enabled_sites:
            return "PokerStars"
        return db_site_name

    def _resolve_hud_poker_game(self, poker_game: str) -> str:
        """Map parser game categories to a HUD-supported game profile."""
        aliases = {
            "fusion": "holdem",
        }
        return aliases.get(poker_game, poker_game)

    def _get_table_info(self, hand_id: str) -> tuple | None:
        """Get table information from cache or database."""
        if hand_id in self.cache:
            log.debug("Using cached data for hand %s", hand_id)
            return self.cache[hand_id]

        log.debug("Data not found in cache for hand_id: %s", hand_id)
        try:
            table_info = self.db_connection.get_table_info(hand_id)
        except Exception as exc:
            if self.note_db_error(exc):
                # Swallowing this one would make every hand of the outage look
                # like a hand that is merely not committed yet, which is how the
                # HUD used to die silently and stay dead.
                return None
            log.exception("Database error while processing hand %s", hand_id)
            try:
                self.db_connection.connection.rollback()
            except Exception:
                log.debug("Rollback failed after table-info lookup error", exc_info=True)
            return None
        else:
            # Don't cache a missing result: the hand may simply not be committed
            # to the DB yet, and caching None would skip it forever on retries.
            if table_info is not None:
                self.cache[hand_id] = table_info
            return table_info

    def _handle_hud_reconfiguration(self, temp_key: str, poker_game: str) -> tuple[str, int | None]:
        """Handle HUD reconfiguration for max seats and game type changes."""
        if temp_key not in self.hud_dict:
            return poker_game, None

        hud_poker_game = self._resolve_hud_poker_game(poker_game)
        hud = self.hud_dict[temp_key]
        current_state = {
            "poker_game": getattr(hud, "poker_game", ""),
            "max_seats": getattr(hud, "max", 0),
        }

        # Check for max seats change
        with contextlib.suppress(Exception):
            newmax = hud.hud_params.get("new_max_seats")
            if newmax and hud.max != newmax:
                new_state = current_state.copy()
                new_state["max_seats"] = newmax

                should_restart, reason = self.smart_hud_manager.should_restart_hud(
                    temp_key,
                    RestartReason.MAX_SEATS_CHANGE,
                    current_state,
                    new_state,
                )

                if should_restart:
                    log.info(f"Smart restart for max seats change: {reason}")
                    self.smart_hud_manager.record_restart(temp_key, f"Max seats: {reason}")
                    self.kill_hud(None, temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
                    hud.hud_params["new_max_seats"] = None
                    return poker_game, int(newmax)
                log.info(f"Skipping restart for max seats change: {reason}")

        # Check for game type change
        if hud.poker_game != hud_poker_game:
            new_state = current_state.copy()
            new_state["poker_game"] = hud_poker_game

            should_restart, reason = self.smart_hud_manager.should_restart_hud(
                temp_key,
                RestartReason.GAME_TYPE_CHANGE,
                current_state,
                new_state,
            )

            if should_restart:
                log.info(f"Smart restart for game type change: {reason}")
                self.smart_hud_manager.record_restart(temp_key, f"Game type: {reason}")
                with contextlib.suppress(Exception):
                    self.kill_hud(None, temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
            else:
                log.info(f"Skipping restart for game type change: {reason}")

        return hud_poker_game, None

    def _publish_analytics(self, hud: Any, hand_id: Any) -> None:
        """Hand a finished batch's analytics values to the table's HUD (#335).

        The values were computed on the worker, so this only stores them on each
        aux window's session; the seat labels read them on their next refresh.
        ``aux_windows`` is read defensively because a HUD that is still being
        built has none yet, and a profile with no analytics cell has no values
        to store at all.
        """
        prepared = self._prepared_hands.get(str(hand_id))
        values = getattr(prepared, "analytics_values", None)
        if not values:
            return
        for aw in getattr(hud, "aux_windows", None) or ():
            publish = getattr(aw, "publish_analytics", None)
            if publish is None:
                continue
            try:
                publish(values)
            except Exception:  # intentional broad catch: one window must not cost the others theirs
                log.exception("Could not publish analytics values to %s", type(aw).__name__)

    @db_profile.scoped("update_hud")
    def _update_existing_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
    ) -> bool:
        """Update an existing HUD with new hand data."""
        log.debug("update hud for hand %s", new_hand_id)
        hud = self.hud_dict[temp_key]
        was_loading = bool(getattr(hud, "is_loading", False))
        self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
        stat_dict = self.db_connection.get_stats_from_hand(
            new_hand_id,
            game_type,
            hud.hud_params,
            self.hero_ids[site_id],
            num_seats,
            poker_game=hud.poker_game,
        )
        log.debug("got stats for hand %s", new_hand_id)

        if was_loading and not any(
            values.get("screen_name") == self.hero.get(site_id) for values in stat_dict.values()
        ):
            if not self._hud_is_fast_fold(hud, temp_key):
                log.warning(
                    "Removing loading HUD for hand %s table=%s: hero %r is not seated",
                    new_hand_id,
                    temp_key,
                    self.hero.get(site_id),
                )
                self.kill_hud(None, temp_key)
                return False

        if was_loading:
            cached_stats = self.stats_persistence.load_hud_stats(temp_key)
            if cached_stats:
                merged = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
                stat_dict = merged.get("stat_dict", stat_dict)

        # On a Fast-Fold table the hand being imported finished seconds ago and
        # the hero has already been moved on. Its players are history, so the
        # live path owns this overlay outright -- including when it holds
        # nobody. Falling back to the imported hand when the live map is empty
        # is what put a finished table's players back on screen seconds after
        # the overlay had been cleared, and left them there once the hero sat
        # out and no further hand came to clear them again.
        if self._hud_is_fast_fold(hud, temp_key):
            stat_dict = getattr(hud, "stat_dict", None) or {}
            seat_players = getattr(hud, "fast_fold_seat_players", None) or {}
        else:
            self._merge_positions(stat_dict, new_hand_id)
            seat_players = self._seat_players(new_hand_id)

        try:
            hud.stat_dict = stat_dict
        except KeyError:
            log.exception("hud_dict[%s] was not found", temp_key)
            return False

        hud.seat_players = seat_players
        self._set_table_stats(hud, new_hand_id)
        self._publish_analytics(hud, new_hand_id)
        hud.cards = self.get_cards(new_hand_id, hud.poker_game)
        for aw in hud.aux_windows:
            aw.update_data(new_hand_id, self.db_connection)
        prepared = self._prepared_hands.get(str(new_hand_id))
        self.update_HUD(
            new_hand_id,
            temp_key,
            self.config,
            cards=hud.cards,
            hand_instance=prepared.hand_instance if prepared is not None else None,
        )
        hud.is_loading = False
        log.debug("hud updated for table %s and hand %s", temp_key, new_hand_id)
        return True

    @db_profile.scoped("create_hud")
    def _create_new_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        table_info: tuple,
        site_id: int,
        num_seats: int,
        hud_site_name: str | None = None,
        *,
        loading: bool = False,
        stats: dict | None = None,
        resolved_window: Any | None = None,
    ) -> None:
        """Create a new HUD for a table.

        ``loading`` builds the placeholder shown while a table's first hand is
        still being read: it has no aux windows, so it cannot display anything
        until a later hand replaces it.

        ``stats`` supplies the statistics directly instead of reading them from
        the database, which is what lets a table be created from the client log
        with no hand behind it -- a full HUD, aux windows and all, on a thread
        that has no database connection.

        ``resolved_window`` is a macOS Fast-Fold window already found at hand
        start. Passing it through prevents OSXTables from performing a second
        window scan that can disagree with the first one while TCC is changing.
        """
        if not resolved_window and self._resolve_fast_fold_key(temp_key) != temp_key:
            log.info("Skipping legacy HUD creation for %r: live FastFold HUD is already active", temp_key)
            return

        info = TableInfo.coerce(table_info)
        table_name = info.table_name
        max_seats = info.max_seats
        poker_game = info.poker_game
        game_type = info.game_type
        tour_number = info.tour_number
        tab_number = info.tab_number
        tourney_name = info.tourney_name
        hud_site_name = hud_site_name or info.site_name
        hud_poker_game = self._resolve_hud_poker_game(poker_game)
        if self.config.get_supported_games_parameters(hud_poker_game, game_type) is None:
            log.error(
                "HUD creation skipped for hand %s table=%s: no HUD profile for poker_game=%s (mapped from %s) game_type=%s",
                new_hand_id,
                table_name,
                hud_poker_game,
                poker_game,
                game_type,
            )
            return

        log.debug("create new hud for hand %s", new_hand_id)
        # Everything below that reads the database is skipped both for the
        # placeholder and when the caller brought its own statistics.
        from_database = stats is None and not loading
        if stats is not None:
            stat_dict = stats
        elif loading:
            stat_dict = {}
        else:
            self.db_connection.init_hud_stat_vars(self.hud_params["hud_days"], self.hud_params["h_hud_days"])
            stat_dict = self.db_connection.get_stats_from_hand(
                new_hand_id,
                game_type,
                self.hud_params,
                self.hero_ids[site_id],
                num_seats,
                poker_game=hud_poker_game,
            )
            log.debug("got stats for hand %s", new_hand_id)

        # Try to load cached stats to preserve data across restarts
        cached_stats = self.stats_persistence.load_hud_stats(temp_key) if from_database else None
        if cached_stats:
            log.info(f"Found cached HUD stats for table {temp_key}, merging with current data")
            merged_data = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
            stat_dict = merged_data.get("stat_dict", stat_dict)
            log.debug("Merged cached stats with fresh database stats")

        if from_database:
            self._merge_positions(stat_dict, new_hand_id)
        if from_database and not any(stat_dict[key]["screen_name"] == self.hero[site_id] for key in stat_dict):
            log.warning(
                "HUD not created for hand %s table=%s: hero %r (site_id=%s) not among players %s",
                new_hand_id,
                table_name,
                self.hero.get(site_id),
                site_id,
                sorted(stat_dict[key]["screen_name"] for key in stat_dict),
            )
            return

        prepared = self._prepared_hands.get(str(new_hand_id))
        cards = prepared.cards if prepared is not None else self.get_cards(new_hand_id, poker_game)
        table_kwargs = {
            "table_name": table_name,
            "tournament": tour_number,
            "table_number": tab_number,
            "tourney_name": tourney_name,
        }
        if resolved_window is not None:
            table_kwargs["resolved_window"] = resolved_window
        tablewindow = self.Tables.Table(self.config, hud_site_name, **table_kwargs)

        if tablewindow.number is None:
            if game_type == "tour":
                table_name = f"{tour_number} {tab_number}"
            self._log_table_not_found(temp_key, table_name, info.site_name, hud_site_name, tablewindow)
            return
        if tablewindow.number in self.blacklist:
            log.warning(
                "HUD skipped for hand %s table=%s: window %s is blacklisted",
                new_hand_id,
                table_name,
                tablewindow.number,
            )
            return

        # Record the matched window for diagnostics without treating normal
        # table discovery as a warning.
        self._tables_attached.add(temp_key)
        # Baseline for _handle_tour_table_switch, taken from the title this HUD
        # was built on rather than from the first poll up to 800 ms later: a
        # Twister window handed to the next match in between would otherwise
        # become the baseline, and the stale HUD would sit there unnoticed.
        tablewindow.seed_title_table_no()
        log.info(
            "HUD attach: table=%r site=%s hwnd=%s title=%r geometry=(%s,%s %sx%s)",
            temp_key,
            hud_site_name,
            tablewindow.number,
            getattr(tablewindow, "title", ""),
            tablewindow.x,
            tablewindow.y,
            tablewindow.width,
            tablewindow.height,
        )

        tablewindow.key = temp_key
        tablewindow.max = max_seats
        tablewindow.site = hud_site_name

        # Register table state with smart HUD manager
        self.smart_hud_manager.update_table_state(
            temp_key,
            hud_poker_game,
            game_type,
            max_seats,
            hud_site_name,
            table_name,
        )

        if hasattr(tablewindow, "number"):
            args = HUDCreationArgs(
                new_hand_id=new_hand_id,
                table=tablewindow,
                temp_key=temp_key,
                max_seats=max_seats,
                poker_game=hud_poker_game,
                game_type=game_type,
                stat_dict=stat_dict,
                cards=cards,
                context=HudContext(
                    site=hud_site_name,
                    game=hud_poker_game,
                    game_type=game_type,
                    limit_type=info.limit_type,
                    max_seats=max_seats,
                    players=info.num_seats,
                    speed="fast" if info.fast else "normal",
                ),
                hand_instance=prepared.hand_instance if prepared is not None else None,
                loading=loading,
            )
            self.create_HUD(args)
            if args.temp_key in self.hud_dict:
                self.hud_dict[args.temp_key].is_loading = loading
                if not loading:
                    self.hud_dict[args.temp_key].seat_players = self._seat_players(new_hand_id)
                    self._set_table_stats(self.hud_dict[args.temp_key], new_hand_id)
        else:
            log.error('Table "%s" no longer exists', table_name)

    def get_cards(self, new_hand_id: str, poker_game: str) -> dict[str, Any]:
        """Get card data for a given hand."""
        cards = self.db_connection.get_cards(new_hand_id)
        if poker_game in ["holdem", "omahahi", "omahahilo"]:
            comm_cards = self.db_connection.get_common_cards(new_hand_id)
            cards["common"] = comm_cards["common"]
        return cards

    @staticmethod
    def _create_loading_indicator(hud: Hud.Hud) -> None:
        """Show one cheap table overlay while the complete snapshot is loading."""
        label: QLabel | None = None
        try:
            flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            label = QLabel("Loading HUD…", None, flags)
            label.setObjectName("hud-loading-indicator")
            label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            label.setStyleSheet(
                "QLabel { color: white; background: rgba(20, 20, 20, 210); "
                "border: 1px solid #777; border-radius: 4px; padding: 6px 10px; }",
            )
            label.adjustSize()
            hud.loading_window = label
            HudMainHudsMixin._position_loading_indicator(hud)
            label.create()
            hud.table.topify(label)
            label.show()
        except Exception:
            if label is not None:
                label.close()
                label.deleteLater()
            hud.loading_window = None
            log.exception("Could not create loading indicator for table %s", hud.table_name)

    @staticmethod
    def _position_loading_indicator(hud: Hud.Hud) -> None:
        """Keep the provisional indicator centered on the current table geometry."""
        label = hud.loading_window
        if label is None:
            return
        table_x = hud.table.x if hud.table.x is not None else 0
        table_y = hud.table.y if hud.table.y is not None else 0
        table_width = hud.table.width if hud.table.width is not None else label.width()
        table_height = hud.table.height if hud.table.height is not None else label.height()
        x = table_x + max(0, (table_width - label.width()) // 2)
        y = table_y + max(0, (table_height - label.height()) // 2)
        x, y = Aux_Base.clamp_to_screen(x, y)
        label.move(x, y)

    def idle_update(
        self,
        new_hand_id: str,
        table_name: str,
        config: Configuration.Config,
        *,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
        """Show a new hand on one table.

        Hud.update owns the new-hand cycle: it rebuilds the hand, re-reads the
        cards, and refreshes every aux window, keeping one failing window from
        stopping the rest. This used to refresh them a second time afterwards,
        which drew each of them twice -- and for the mucked-cards windows that
        is not merely wasted work, since theirs appends a row to the list and
        re-shows the cards, so every hand was replayed to the player.
        """
        try:
            log.debug("idle_update entered for %s %s", table_name, new_hand_id)
            hud = self.hud_dict[table_name]
            if str(new_hand_id) in self._prepared_hands:
                hud.update(
                    new_hand_id,
                    config,
                    prepared=True,
                    cards=cards,
                    hand_instance=hand_instance,
                )
            else:
                hud.update(new_hand_id, config)
            hud_trace(
                "idle_update OK: table=%s hand=%s aux_windows=%d",
                table_name,
                new_hand_id,
                len(hud.aux_windows),
            )
        except Exception:
            log.exception("Error updating HUD for hand %s (table=%s).", new_hand_id, table_name)
