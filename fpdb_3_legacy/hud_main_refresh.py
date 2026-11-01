"""Refreshing the stats of HUDs other than the one whose hand just arrived."""

import contextlib

from fpdb_3_legacy import Hud, db_profile
from fpdb_3_legacy.hud_main_base import HudMainBase, log
from fpdb_3_legacy.table_info import TableInfo


class HudMainRefreshMixin(HudMainBase):
    """Keep the other tables' HUDs and seat positions current."""

    def _seat_players(self, hand_id: str) -> dict:
        """Seat players for a hand, read from the database once."""
        key = ("seats", hand_id)
        cached = self._hand_players.get(key)
        if cached is None:
            cached = self.db_connection.get_seat_players(hand_id)
            self._hand_players[key] = cached
        return cached

    def _hand_positions(self, hand_id: str) -> dict:
        """Each player's position in a hand, read from the database once."""
        key = ("positions", hand_id)
        cached = self._hand_players.get(key)
        if cached is None:
            cached = self.db_connection.get_hand_positions(hand_id)
            self._hand_players[key] = cached
        return cached

    @db_profile.scoped("secondary_refresh")
    def _refresh_secondary_hud(
        self,
        hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
        stat_dict: dict | None = None,
    ) -> None:
        """Update a HUD whose own table has not dealt a new hand.

        ``stat_dict`` is the statistics this table's caller already fetched, in
        one query covering every table being refreshed; passing None makes this
        fetch its own, which is the fallback when the tables cannot share a
        query (see _refresh_other_huds).

        Only the aggregated statistics can have moved: the seats, the cards and
        the table stats all describe this table's own last hand, which is the
        hand being reused here, so re-reading them would return what the HUD
        already holds. Skipping them matters because this runs once per open
        table per hand dealt at any table -- the cost of the full update would
        grow with the square of the number of tables, on the path that has to
        finish before the player acts.

        The positions are re-read because the statistics dictionary is built
        afresh and they live inside it.

        The repaint deliberately does not go through update_HUD. That path
        calls Hud.update, which rebuilds the hand from the database through
        hand_factory, re-reads the cards, and refreshes the aux windows a
        second time -- all of it describing the same unchanged hand. The aux
        windows read hud.stat_dict when they redraw, so handing them the new
        one and asking them to redraw is the whole job.
        """
        hud = self.hud_dict[temp_key]
        if stat_dict is None:
            self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
            stat_dict = self.db_connection.get_stats_from_hand(
                hand_id,
                game_type,
                hud.hud_params,
                self.hero_ids[site_id],
                num_seats,
                poker_game=hud.poker_game,
            )
        self._merge_positions(stat_dict, hand_id)
        hud.stat_dict = stat_dict
        for aux in hud.aux_windows:
            try:
                aux.refresh_stats(hand_id)
            except Exception:
                log.exception("Error redrawing aux window of table %s", temp_key)
        log.debug("secondary hud redrawn for table %s using hand %s", temp_key, hand_id)

    def _tables_to_refresh(self, updated_tables: set[str]) -> list[tuple]:
        """The tables owed a statistics refresh, with what each one needs."""
        pending = []
        for table_name in list(self.hud_dict):
            if table_name in updated_tables:
                continue

            if self._hud_is_fast_fold(self.hud_dict[table_name], table_name):
                # This refresh replaces stat_dict with the players of the last
                # hand imported for the table. On a Fast-Fold table those left
                # long ago, and the seats still point at the live players -- so
                # every block would look up a player id the statistics no longer
                # hold, and show a nameless column of NA. Its statistics come
                # from the live path instead.
                log.debug("Skipping global HUD refresh for Fast-Fold table %s", table_name)
                continue

            last_hand_id = self._last_processed_hands.get(table_name)
            if last_hand_id is None:
                log.debug("Skipping global HUD refresh for %s: no last hand", table_name)
                continue

            table_info = self._get_table_info(last_hand_id)
            if table_info is None:
                log.warning(
                    "Skipping global HUD refresh for table %s: no table info for hand %s",
                    table_name,
                    last_hand_id,
                )
                continue

            info = TableInfo.coerce(table_info)
            pending.append((table_name, last_hand_id, info.game_type, info.site_id, info.num_seats))
        return pending

    def _batch_secondary_stats(self, pending: list[tuple]) -> dict:
        """Fetch every refreshing table's statistics in as few queries as possible.

        Tables can share a query only when every parameter of that query
        matches, so they are grouped by the whole set: the stat-window
        configuration, the hero, the seat count and the game. Multi-tabling one
        site at one stake -- which is what makes this path expensive in the
        first place -- collapses to a single group, and so to a single round
        trip in place of one per table.

        Best-effort by design: a group that fails leaves its tables without a
        precomputed answer, and each falls back to fetching its own.
        """
        # The hero is only known once a hand has been processed. Before that
        # there is nothing to group by, and each table falls back to fetching
        # its own -- which is what this path did before it batched at all.
        hero_ids = getattr(self, "hero_ids", None)
        if not hero_ids:
            return {}

        groups: dict[str, tuple] = {}
        for table_name, last_hand_id, game_type, site_id, num_seats in pending:
            hud = self.hud_dict.get(table_name)
            if hud is None:
                continue
            hero_id = hero_ids.get(site_id)
            if hero_id is None:
                continue
            # repr rather than a tuple of the items: hud_params comes from
            # user-edited configuration, and one unhashable value in it would
            # otherwise take down the refresh round rather than merely stop it
            # batching.
            key = repr((sorted(hud.hud_params.items(), key=str), hero_id, num_seats, hud.poker_game, game_type))
            if key not in groups:
                groups[key] = (hud.hud_params, hero_id, num_seats, hud.poker_game, game_type, [])
            groups[key][5].append(last_hand_id)

        stats_by_hand: dict = {}
        for hud_params, hero_id, num_seats, poker_game, game_type, hand_ids in groups.values():
            try:
                self.db_connection.init_hud_stat_vars(hud_params["hud_days"], hud_params["h_hud_days"])
                stats_by_hand.update(
                    self.db_connection.get_stats_from_hands(
                        hand_ids,
                        game_type,
                        hud_params,
                        hero_id,
                        num_seats,
                        poker_game=poker_game,
                    ),
                )
            except Exception as exc:
                if self.note_db_error(exc):
                    return stats_by_hand
                # PostgreSQL leaves the transaction aborted after a statement
                # error. Clear it before the caller falls back to per-table
                # queries, otherwise the first fallback necessarily fails with
                # InFailedSqlTransaction and that table remains stale.
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()
                log.exception("Batched statistics failed for %d table(s); each will ask for its own", len(hand_ids))
        return stats_by_hand

    def _refresh_other_huds(self, updated_tables: set[str]) -> None:
        """Refresh every active HUD except the tables this batch already updated.

        HUD statistics are aggregated globally, but each HUD must keep using
        its own latest hand for seats, cards, positions, and game context.
        Reusing that table's last processed hand makes all open HUDs observe
        the latest HudCache state without mixing table-local data.

        A secondary HUD is best-effort: one stale or failing table must not
        prevent the remaining tables from refreshing.
        """
        pending = self._tables_to_refresh(updated_tables)
        if not pending:
            return
        stats_by_hand = self._batch_secondary_stats(pending)

        for table_name, last_hand_id, game_type, site_id, num_seats in pending:
            if not self._db_available:
                # Opened by an earlier table in this same loop.
                log.debug("Stopping the HUD refresh round: database unavailable")
                return
            try:
                self._refresh_secondary_hud(
                    last_hand_id,
                    table_name,
                    game_type,
                    site_id,
                    num_seats,
                    stat_dict=stats_by_hand.get(last_hand_id),
                )
            except Exception as exc:
                if self.note_db_error(exc):
                    return
                log.exception(
                    "Global HUD refresh failed for table %s using hand %s",
                    table_name,
                    last_hand_id,
                )
                # PostgreSQL rejects every later query after one statement
                # fails until the transaction is explicitly rolled back.
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()

    def _set_table_stats(self, hud: Hud.Hud, hand_id: str) -> None:
        """Compute table-scope stats once per hand and cache them on the hud.

        Keeps the per-label HUD update off the database: the table stat widgets
        read hud.table_stats instead of querying on the UI thread.
        """
        try:
            hud.table_stats = {
                "live_min_stack_bb": self.db_connection.get_table_min_stack_bb(hand_id),
            }
        except Exception:
            log.exception("could not compute table stats for hand %s", hand_id)
            hud.table_stats = {}

    def _merge_positions(self, stat_dict: dict, hand_id: str) -> None:
        """Attach each player's current-hand position to stat_dict.

        Enables position-conditional HUD panels (e.g. show the SB panel only for
        the player in the small blind this hand). Best-effort: failures are
        logged and leave stat_dict unchanged.
        """
        try:
            positions = self._hand_positions(hand_id)
        except Exception:
            log.exception("could not load positions for hand %s", hand_id)
            return
        for pid, pos in positions.items():
            if pid in stat_dict:
                stat_dict[pid]["position"] = pos
        self._advance_live_positions(stat_dict, hand_id)

    def _advance_live_positions(self, stat_dict: dict, hand_id: str) -> None:
        """Estimate each player's CURRENT-hand position for positional panels.

        An import-driven HUD only knows the *last imported* hand's position, but
        the table has already moved to the next hand, so a positional panel would
        be one hand stale (a BB villain still showing the SB panel). Advance the
        button one seat from the last hand and store the result as live_position;
        block_visible prefers it over the imported position.

        Best-effort: it assumes the same seated players next hand (true between
        Spin&Go hands until someone busts), and leaves live_position unset when
        the button can't be found so the caller falls back to the imported one.
        """
        try:
            seat_players = self._seat_players(hand_id)
        except Exception:
            return
        if len(seat_players) < 2:
            return
        seats = sorted(seat_players)
        n = len(seats)
        btn_codes = {"0", "BTN", "BU", "D", "BUTTON"}
        btn_seat = None
        for seat in seats:
            pid = seat_players[seat].get("player_id")
            pos = stat_dict.get(pid, {}).get("position")
            if pos is not None and str(pos).strip().upper() in btn_codes:
                btn_seat = seat
                break
        if btn_seat is None:
            return
        # Button moves one occupied seat clockwise; SB/BB follow, then seats
        # after the BB. Codes use DerivedStats' convention (0=BTN, S, B, 1..).
        new_btn = (seats.index(btn_seat) + 1) % n
        codes = ["0", "S", "B"] + [str(i) for i in range(1, n)]
        for k in range(n):
            seat = seats[(new_btn + k) % n]
            pid = seat_players[seat].get("player_id")
            if pid in stat_dict:
                stat_dict[pid]["live_position"] = codes[k]
