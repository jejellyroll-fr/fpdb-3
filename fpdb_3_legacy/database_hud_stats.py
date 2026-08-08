"""HUD statistics reads for the fpdb database.

Split out of Database.py: these methods answer the question the HUD asks on
every hand -- what are the aggregated statistics of the players at this table --
by reading HudCache and the hand tables, and they own the time windows and the
hero identity that scope those reads.

They read; the writing side lives in database_caches. Borrowings from the host
are declared below.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from time import time
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.autonotes_aof import AOF_CATEGORIES
from fpdb_3_legacy.db_reconnect import reconnect_on_connection_loss
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

# How long the 24-hour boundary hand id is reused before being re-read. It is a
# sliding boundary, so any value here is a compromise; five minutes of drift on
# a 24-hour window is invisible, and it turns one query per table per hand into
# one query per five minutes.
HAND_1DAY_AGO_TTL = 300.0

# What a caller gets when it asks for statistics without saying how. Kept here
# so the per-hand and batched paths cannot disagree about it.
_DEFAULT_HUD_PARAMS = {
    "stat_range": "A",
    "agg_bb_mult": 1000,
    "seats_style": "A",
    "seats_cust_nums_low": 1,
    "seats_cust_nums_high": 10,
    "h_stat_range": "A",
    "h_agg_bb_mult": 1000,
    "h_seats_style": "A",
    "h_seats_cust_nums_low": 1,
    "h_seats_cust_nums_high": 10,
}


class DatabaseHudStatsMixin:
    """Reads the aggregates the HUD displays.

    Mixed into Database, which supplies the connection, the query catalogue and
    the configuration named below.
    """

    # Provided by Database.
    sql: Any
    config: Any
    connection: Any
    backend: int
    db_server: str
    day_start: float
    hero: dict[Any, Any]
    hero_ids: dict[Any, Any]
    hero_hudstart_def: str
    date_ndays_ago: str
    h_date_ndays_ago: str
    hand_1day_ago: int

    # Set by _inject_hud_chipev_columns, below.
    _hud_chipev_clause: str

    # Provided by Database; reset by its resetCache.
    _hand_1day_ago_read_at: float

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def get_site_id(self, site: Any) -> Any: ...

        def get_gameinfo_from_hid(self, hand_id: Any) -> Any: ...

        def get_hero_player_ids(self, site_name: Any = None, profile: Any = None) -> Any: ...

        def getAofProfileStats(self, player_ids: Any, category: str) -> Any: ...

        def _rollback_after_failed_read(self) -> None: ...

        def recover_connection(self) -> bool: ...

    def get_seat_players(self, hand_id: str) -> dict[int, dict[str, object]]:
        """Return seatNo -> {player_id, screen_name} dict for a hand.

        player_id is a native int to match the keys of the stat_dict built by
        get_stats_from_hand; get_id_from_seat() feeds it straight into
        stat_dict[player_id] lookups.
        """
        players = {}
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = (
                "SELECT hp.seatNo, hp.playerId, p.name "
                "FROM HandsPlayers hp "
                "INNER JOIN Players p ON hp.playerId = p.id "
                "WHERE hp.handId = %s"
            ).replace("%s", ph)
            c = self.connection.cursor()
            c.execute(q, (hand_id,))
            for row in c.fetchall():
                players[int(row[0])] = {"player_id": int(row[1]), "screen_name": row[2]}
        except Exception:
            log.exception("get_seat_players failed for hand %s", hand_id)
            self._rollback_after_failed_read()
        return players

    def get_table_min_stack_bb(self, hand_id: str) -> float | None:
        """Smallest end-of-hand stack at the table, in big blinds (PT4 live stat).

        From the given (most recently imported) hand, take each seated player's
        end-of-hand stack (startCash - committed + winnings), drop eliminated
        players (stack <= 0), and divide the minimum by the big blind. Returns
        None when it cannot be computed.

        Note: the big blind comes from Gametypes, so for multi-level tournaments
        this is the gametype's blind, not necessarily the current level's.
        """
        try:
            ph = self.sql.query.get("placeholder", "%s")
            c = self.get_cursor()
            c.execute(
                (
                    "SELECT gt.bigBlind FROM Hands h INNER JOIN Gametypes gt ON h.gametypeId = gt.id WHERE h.id = %s"
                ).replace("%s", ph),
                (hand_id,),
            )
            row = c.fetchone()
            if not row or not row[0]:
                return None
            big_blind = float(row[0])
            if big_blind <= 0:
                return None
            c.execute(
                (
                    "SELECT startCash, committed, winnings FROM HandsPlayers WHERE handId = %s AND sitout = FALSE"
                ).replace("%s", ph),
                (hand_id,),
            )
            stacks = []
            for start_cash, committed, winnings in c.fetchall():
                end_cash = float(start_cash) - float(committed) + float(winnings)
                if end_cash > 0:
                    stacks.append(end_cash)
            if not stacks:
                return None
            return min(stacks) / big_blind
        except Exception:
            log.exception("get_table_min_stack_bb failed for hand %s", hand_id)
            self._rollback_after_failed_read()
            return None

    def _inject_hud_chipev_columns(self, sql_text):
        """Replace the <chipev_columns> placeholder in the HUD aggregation query.

        Substitutes bucket-encoded ChipEV-by-position SUM(CASE...) columns from
        the declarative stat registry so descriptor stats become stat_dict keys.
        The compiled clause is cached (the HUD calls this once per hand) and the
        substitution is best-effort: on any error the placeholder is removed and
        the base query runs unchanged.
        """
        if "<chipev_columns>" not in sql_text:
            return sql_text
        if not hasattr(self, "_hud_chipev_clause"):
            try:
                from fpdb_3_legacy.stat_adapters import HudAdapter
                from fpdb_3_legacy.stat_registry import get_registry

                descriptors = [d for d in get_registry().series_for_scope("tour") if d.dimension]
                self._hud_chipev_clause = HudAdapter().select_clause(descriptors)
            except Exception:
                log.exception("failed to build HUD ChipEV columns; disabling")
                self._hud_chipev_clause = ""
        return sql_text.replace("<chipev_columns>", self._hud_chipev_clause)

    def _refresh_hand_1day_ago(self) -> None:
        """Re-read the 24-hour boundary hand id, at most once per TTL.

        It is a sliding boundary on a 24-hour window, so it is always a little
        stale by construction and a few minutes more changes nothing about
        which hands count as "this session". The HUD asks for it once per open
        table per hand dealt, which measurably made it one of the three largest
        sources of round trips (tools/measure_hud_round_trips.py) -- for a
        value that moves once a day.
        """
        now = time()
        if self._hand_1day_ago_read_at and now - self._hand_1day_ago_read_at < HAND_1DAY_AGO_TTL:
            return

        self.hand_1day_ago = 1
        c = self.get_cursor()
        c.execute(self.sql.query["get_hand_1day_ago"])
        row = c.fetchone()
        if row and row[0]:
            self.hand_1day_ago = int(row[0])
        self._hand_1day_ago_read_at = now

    def init_hud_stat_vars(self, hud_days, h_hud_days) -> None:
        """Initialise variables used by Hud to fetch stats:
        self.hand_1day_ago     handId of latest hand played more than a day ago
        self.date_ndays_ago    date n days ago
        self.h_date_ndays_ago  date n days ago for hero (different n).
        """
        self._refresh_hand_1day_ago()

        tz = datetime.utcnow() - datetime.today()
        tz_offset = (tz.seconds) // (3600)
        tz_day_start_offset = self.day_start + tz_offset

        d = timedelta(days=hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

        d = timedelta(days=h_hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.h_date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

    @staticmethod
    def _seat_bounds(style, cust_low, cust_high, num_seats) -> tuple[int, int]:
        """The seat range a stat window covers, from its configured style.

        'A' means every seat count, 'C' a configured range, 'E' exactly this
        table's. Anything else is a configuration error and is treated as 'A',
        because showing stats over all seat counts is a great deal less wrong
        than showing none.
        """
        if style == "A":
            return 0, 10
        if style == "C":
            return cust_low, cust_high
        if style == "E":
            return num_seats, num_seats
        log.warning("bad seats_style value: %s", style)
        return 0, 10

    def _style_key(self, stat_range, *, hero: bool) -> str:
        """The styleKey floor for a stat range.

        styleKey is 'd' followed by yyyymmdd, so a floor below every real key
        ('0000000') means all of history and one above every real key
        ('zzzzzzz') means none of it -- the session range reads its numbers
        from a different query entirely.
        """
        if stat_range == "T":
            return self.h_date_ndays_ago if hero else self.date_ndays_ago
        if stat_range == "A":
            return "0000000"
        if stat_range == "S":
            return "zzzzzzz"
        log.info("unknown stat_range %r, reading all of history", stat_range)
        return "0000000"

    @reconnect_on_connection_loss
    def get_stats_from_hand(
        self,
        hand,
        game_type=None,  # "ring" or "tour"; currently inferred from hand metadata
        hud_params=None,
        hero_id=-1,
        num_seats=6,
        poker_game: str | None = None,
        **kwargs,
    ):
        if game_type is None and "type" in kwargs:
            game_type = kwargs.pop("type")
        if kwargs:
            log.warning("Ignoring unknown get_stats_from_hand arguments: %s", ", ".join(sorted(kwargs)))

        if hud_params is None:
            hud_params = dict(_DEFAULT_HUD_PARAMS, h_stat_range="S")
        stat_range = hud_params["stat_range"]
        agg_bb_mult = hud_params["agg_bb_mult"]
        h_stat_range = hud_params["h_stat_range"]
        h_agg_bb_mult = hud_params["h_agg_bb_mult"]

        stat_dict: dict[Any, Any] = {}

        # Shared with the batched path (get_stats_from_hands): two ways of
        # deriving these would mean two answers for the same table.
        seats_min, seats_max = self._seat_bounds(
            hud_params["seats_style"],
            hud_params["seats_cust_nums_low"],
            hud_params["seats_cust_nums_high"],
            num_seats,
        )
        h_seats_min, h_seats_max = self._seat_bounds(
            hud_params["h_seats_style"],
            hud_params["h_seats_cust_nums_low"],
            hud_params["h_seats_cust_nums_high"],
            num_seats,
        )

        if stat_range == "S" or h_stat_range == "S":
            self.get_stats_from_hand_session(
                hand,
                stat_dict,
                hero_id,
                stat_range,
                seats_min,
                seats_max,
                h_stat_range,
                h_seats_min,
                h_seats_max,
            )

            if stat_range == "S" and h_stat_range == "S":
                self._merge_aof_profile_stats(stat_dict, poker_game)
                return stat_dict

        stylekey = self._style_key(stat_range, hero=False)
        h_stylekey = self._style_key(h_stat_range, hero=True)

        # lookup gametypeId from hand
        handinfo = self.get_gameinfo_from_hid(hand)
        if handinfo is None:
            log.warning(f"No game info found for hand ID {hand}")
            return stat_dict  # Return an empty stat_dict if no game info is found

        gametypeId = handinfo["gametypeId"]

        query = "get_stats_from_hand_aggregated"
        subs = (
            hand,
            hero_id,
            stylekey,
            agg_bb_mult,
            agg_bb_mult,
            gametypeId,
            seats_min,
            seats_max,  # hero params
            hero_id,
            h_stylekey,
            h_agg_bb_mult,
            h_agg_bb_mult,
            gametypeId,
            h_seats_min,
            h_seats_max,
        )  # villain params

        stime = time()
        c = self.connection.cursor()

        # Inject declarative ChipEV-by-position columns (stat_registry.py) into
        # the HUD aggregation. These are bucket-encoded SUM(CASE...) columns that
        # become stat_dict keys, so descriptor stats render live in the HUD.
        sql_text = self._inject_hud_chipev_columns(self.sql.query[query])

        # Now get the stats
        c.execute(sql_text, subs)
        ptime = time() - stime
        log.info(
            f"HudCache query get_stats_from_hand_aggregated took {ptime:.3f} seconds",
        )
        colnames = [desc[0] for desc in c.description]
        for row in c.fetchall():
            # Keep player ids as native DB integers: do_stat() coerces the player
            # to int and every stat function indexes stat_dict[int]. Coercing keys
            # to str here silently makes all stat lookups miss. String ids only
            # appear at the JSON persistence boundary (see merge_stats).
            playerid = row[0]
            is_hero = False
            if hero_id is not None:
                try:
                    is_hero = int(playerid) == int(hero_id)
                except (ValueError, TypeError):
                    is_hero = str(playerid) == str(hero_id)
            if (is_hero and h_stat_range != "S") or (not is_hero and stat_range != "S"):
                t_dict = {}
                for name, val in zip(colnames, row, strict=False):
                    t_dict[name.lower()] = val
                stat_dict[t_dict["player_id"]] = t_dict

        self._merge_aof_profile_stats(stat_dict, poker_game or handinfo["category"])
        return stat_dict

    def _live_player_rewrites(self, placeholder: str, player_count: int):
        """The edits that key the HUD aggregate on players instead of a hand.

        Fast-Fold tables know who is sitting there from the client log long
        before any hand history for that table exists, so there is no hand to
        join through. Rewriting the one source query keeps the column list --
        and therefore every stat function downstream -- identical to the normal
        path; a second copy of a 300-line aggregate would drift, and the HUD
        would report different numbers depending on which path served it.
        """
        ids = ", ".join([placeholder] * player_count)
        return (
            # The seat column reads HandsPlayers through the hand being asked
            # about. There is no such hand here and the caller assigns seats from
            # the log, so the whole expression goes -- along with the last
            # references to both Hands and HandsPlayers.
            (
                "max(case when hc.gametypeId = h.gametypeId\n"
                "                            then hp.seatNo\n"
                "                            else -1\n"
                "                       end)                            AS seat,",
                "-1                                         AS seat,",
            ),
            (
                "FROM Hands h\n                 INNER JOIN HandsPlayers hp ON (hp.handId = h.id)\n"
                "                 INNER JOIN HudCache hc     ON (hc.playerId = hp.playerId)",
                "FROM HudCache hc",
            ),
            (f"WHERE h.id = {placeholder}", f"WHERE hc.playerId IN ({ids})"),
            ("hp.playerId != ", "hc.playerId != "),
            ("hp.playerId = ", "hc.playerId = "),
        )

    @reconnect_on_connection_loss
    def get_stats_for_players(
        self,
        player_ids,
        gametype_id,
        hud_params=None,
        hero_id=-1,
        num_seats=6,
        poker_game: str | None = None,
    ):
        """HUD stats for a set of players, with no hand to hang them on.

        Same aggregate and same columns as :meth:`get_stats_from_hand`, so the
        result drops straight into a HUD's ``stat_dict``. ``gametype_id`` says
        which stakes to consider comparable and normally comes from a hand
        already imported for the table.
        """
        if not player_ids:
            return {}

        if hud_params is None:
            hud_params = dict(_DEFAULT_HUD_PARAMS)
        # Session stats are read from a different query, one that needs hands on
        # this table. These players have none yet, so read all of history rather
        # than returning a stat line of blanks.
        stat_range = "A" if hud_params["stat_range"] == "S" else hud_params["stat_range"]
        h_stat_range = "A" if hud_params["h_stat_range"] == "S" else hud_params["h_stat_range"]

        seats_min, seats_max = self._seat_bounds(
            hud_params["seats_style"],
            hud_params["seats_cust_nums_low"],
            hud_params["seats_cust_nums_high"],
            num_seats,
        )
        h_seats_min, h_seats_max = self._seat_bounds(
            hud_params["h_seats_style"],
            hud_params["h_seats_cust_nums_low"],
            hud_params["h_seats_cust_nums_high"],
            num_seats,
        )

        ids = [int(pid) for pid in player_ids]
        placeholder = self.sql.query.get("placeholder", "%s")
        sql_text = self._inject_hud_chipev_columns(self.sql.query["get_stats_from_hand_aggregated"])
        for original, replacement in self._live_player_rewrites(placeholder, len(ids)):
            if original not in sql_text:
                log.warning(
                    "Cannot key the HUD aggregate on players: %r is no longer in the query; "
                    "no live Fast-Fold stats this update.",
                    original,
                )
                return {}
            sql_text = sql_text.replace(original, replacement, 1)

        subs = (
            *ids,
            hero_id,
            self._style_key(stat_range, hero=False),
            hud_params["agg_bb_mult"],
            hud_params["agg_bb_mult"],
            gametype_id,
            seats_min,
            seats_max,
            hero_id,
            self._style_key(h_stat_range, hero=True),
            hud_params["h_agg_bb_mult"],
            hud_params["h_agg_bb_mult"],
            gametype_id,
            h_seats_min,
            h_seats_max,
        )

        stat_dict: dict[Any, Any] = {}
        c = self.connection.cursor()
        c.execute(sql_text, subs)
        colnames = [desc[0] for desc in c.description]
        for row in c.fetchall():
            t_dict = {name.lower(): val for name, val in zip(colnames, row, strict=False)}
            stat_dict[t_dict["player_id"]] = t_dict

        self._merge_aof_profile_stats(stat_dict, poker_game)
        return stat_dict

    def _batch_rewrites(self, placeholder: str):
        """The edits that turn the per-hand aggregate into a per-batch one.

        Expressed as substitutions on the single source query rather than as a
        second copy of it: the aggregate is 300 lines of stat columns, and two
        copies would drift, which would show up as the HUD reporting different
        numbers depending on which path happened to serve a table.

        The bind placeholder has to be passed in: the catalogue is rewritten
        per backend on load (``finalize_query_placeholders``), so the query
        says ``= ?`` under SQLite and ``= %s`` under PostgreSQL.
        """
        return (
            # Appended at the end of the select list rather than the start, so
            # the query still opens with the text the round-trip profiler
            # matches it against and its report can still name it.
            ("FROM Hands h", ", h.id AS batch_hand_id FROM Hands h"),
            (f"WHERE h.id = {placeholder}", "WHERE h.id IN (<hand_ids>)"),
            ("GROUP BY hc.PlayerId, p.name", "GROUP BY h.id, hc.PlayerId, p.name"),
            ("ORDER BY hc.PlayerId, p.name", "ORDER BY h.id, hc.PlayerId, p.name"),
        )

    def _batched_aggregated_sql(self, sql_text: str, hand_count: int) -> str | None:
        """Rewrite the aggregate to answer for several hands in one round trip.

        Returns None if the query has changed shape such that any of the
        rewrites no longer applies -- the caller then falls back to asking per
        hand, which is slower but cannot be subtly wrong.
        """
        placeholder = self.sql.query.get("placeholder", "%s")
        for original, replacement in self._batch_rewrites(placeholder):
            if original not in sql_text:
                log.warning(
                    "Cannot batch the HUD aggregate: %r is no longer in the query; asking per hand instead.",
                    original,
                )
                return None
            sql_text = sql_text.replace(original, replacement, 1)

        return sql_text.replace("<hand_ids>", ", ".join([placeholder] * hand_count))

    @reconnect_on_connection_loss
    def get_stats_from_hands(
        self,
        hands,
        game_type=None,
        hud_params=None,
        hero_id=-1,
        num_seats=6,
        poker_game: str | None = None,
    ) -> dict[Any, dict[Any, Any]]:
        """Return ``{hand_id: stat_dict}`` for several hands at once.

        Every open table refreshes its statistics on every hand dealt at any
        table, so this path runs once per table per hand -- one round trip each,
        which over a VPN is the single largest cost the HUD imposes. The hands
        given must share their HUD parameters; they are split internally by
        gametype, which is the one parameter that varies per hand rather than
        per table.

        Falls back to asking per hand for the session stat range, which reads a
        different query per hand and has nothing to batch.
        """
        hands = list(dict.fromkeys(hands))
        if not hands:
            return {}

        params = hud_params if hud_params is not None else _DEFAULT_HUD_PARAMS
        if params["stat_range"] == "S" or params["h_stat_range"] == "S":
            return self._stats_per_hand(hands, game_type, params, hero_id, num_seats, poker_game)

        by_gametype: dict[Any, list[Any]] = {}
        categories: dict[Any, Any] = {}
        for hand in hands:
            handinfo = self.get_gameinfo_from_hid(hand)
            if handinfo is None:
                log.warning("No game info found for hand ID %s", hand)
                continue
            by_gametype.setdefault(handinfo["gametypeId"], []).append(hand)
            categories[hand] = handinfo["category"]

        results: dict[Any, dict[Any, Any]] = {}
        for gametype_id, group in by_gametype.items():
            batched = self._run_batched_aggregate(group, gametype_id, params, hero_id, num_seats)
            if batched is None:
                results.update(self._stats_per_hand(group, game_type, params, hero_id, num_seats, poker_game))
                continue
            for hand in group:
                stat_dict = batched.get(hand, {})
                self._merge_aof_profile_stats(stat_dict, poker_game or categories.get(hand))
                results[hand] = stat_dict
        return results

    def _stats_per_hand(self, hands, game_type, hud_params, hero_id, num_seats, poker_game):
        """The unbatched path, kept as the answer of record."""
        return {
            hand: self.get_stats_from_hand(
                hand,
                game_type,
                hud_params,
                hero_id,
                num_seats,
                poker_game=poker_game,
            )
            for hand in hands
        }

    def _run_batched_aggregate(self, hands, gametype_id, hud_params, hero_id, num_seats):
        """One aggregate covering ``hands``, or None if it could not be built."""
        seats_min, seats_max = self._seat_bounds(
            hud_params["seats_style"],
            hud_params["seats_cust_nums_low"],
            hud_params["seats_cust_nums_high"],
            num_seats,
        )
        h_seats_min, h_seats_max = self._seat_bounds(
            hud_params["h_seats_style"],
            hud_params["h_seats_cust_nums_low"],
            hud_params["h_seats_cust_nums_high"],
            num_seats,
        )
        stylekey = self._style_key(hud_params["stat_range"], hero=False)
        h_stylekey = self._style_key(hud_params["h_stat_range"], hero=True)

        sql_text = self._inject_hud_chipev_columns(self.sql.query["get_stats_from_hand_aggregated"])
        batched = self._batched_aggregated_sql(sql_text, len(hands))
        if batched is None:
            return None

        subs = (
            *hands,
            hero_id,
            stylekey,
            hud_params["agg_bb_mult"],
            hud_params["agg_bb_mult"],
            gametype_id,
            seats_min,
            seats_max,  # villain params
            hero_id,
            h_stylekey,
            hud_params["h_agg_bb_mult"],
            hud_params["h_agg_bb_mult"],
            gametype_id,
            h_seats_min,
            h_seats_max,  # hero params
        )

        stime = time()
        c = self.connection.cursor()
        c.execute(batched, subs)
        log.info(
            "HudCache batched aggregate covered %d hand(s) in %.3f seconds",
            len(hands),
            time() - stime,
        )
        colnames = [desc[0].lower() for desc in c.description]
        # ZMQ supplies hand ids as strings while every SQL backend returns the
        # selected Hands.id as an integer. Preserve the caller's key type in the
        # public result while using a canonical representation to match rows.
        hand_key_by_id = {str(hand): hand for hand in hands}
        results: dict[Any, dict[Any, Any]] = {hand: {} for hand in hands}
        for row in c.fetchall():
            t_dict = dict(zip(colnames, row, strict=False))
            # Not a statistic: it only says which table's row this is, and
            # leaving it in stat_dict would offer it to the stat renderer.
            returned_hand = t_dict.pop("batch_hand_id")
            hand = hand_key_by_id.get(str(returned_hand), returned_hand)
            if not self._row_is_wanted(t_dict["player_id"], hero_id, hud_params):
                continue
            results.setdefault(hand, {})[t_dict["player_id"]] = t_dict
        return results

    @staticmethod
    def _row_is_wanted(playerid, hero_id, hud_params) -> bool:
        """Apply the same hero/villain stat-range filter the per-hand path does."""
        is_hero = False
        if hero_id is not None:
            try:
                is_hero = int(playerid) == int(hero_id)
            except (ValueError, TypeError):
                is_hero = str(playerid) == str(hero_id)
        if is_hero:
            return hud_params["h_stat_range"] != "S"
        return hud_params["stat_range"] != "S"

    def _merge_aof_profile_stats(
        self,
        stat_dict: dict[Any, Any],
        category: str | None,
    ) -> None:
        """Add one grouped objective-profile read to an AoF table's stats.

        Splash is included in the same query via a pre-aggregated subquery.
        """
        normalized = str(category or "").lower()
        if normalized not in AOF_CATEGORIES or not stat_dict:
            return
        try:
            grouped = self.getAofProfileStats(stat_dict, normalized)
        except Exception:
            log.exception("AoF profile aggregation failed for %s players", len(stat_dict))
            self._rollback_after_failed_read()
            return
        for player_id, aggregates in grouped.items():
            if player_id in stat_dict:
                stat_dict[player_id].update(aggregates)

    def get_stats_from_hand_session(
        self,
        hand,
        stat_dict,
        hero_id,
        stat_range,
        seats_min,
        seats_max,
        h_stat_range,
        h_seats_min,
        h_seats_max,
    ) -> None:
        """Get stats for just this session (currently defined as any play in the last 24 hours - to
        be improved at some point ...)
        h_stat_range and stat_range params indicate whether to get stats for hero and/or others
        - only fetch heroes stats if h_stat_range == 'S',
        and only fetch others stats if stat_range == 'S'
        seats_min/max params give seats limits, only include stats if between these values.
        """
        query = self.sql.query["get_stats_from_hand_session"]
        query = query.replace("<signed>", "signed ") if self.db_server == "mysql" else query.replace("<signed>", "")

        subs = (
            self.hand_1day_ago,
            hand,
            hero_id,
            seats_min,
            seats_max,
            hero_id,
            h_seats_min,
            h_seats_max,
        )
        c = self.get_cursor()

        # now get the stats
        # print "sess_stats: subs =", subs, "subs[0] =", subs[0]
        c.execute(query, subs)
        colnames = [desc[0] for desc in c.description]
        row = c.fetchone()
        if colnames[0].lower() == "player_id":
            # Loop through stats adding them to appropriate stat_dict:
            while row:
                # Native int keys, matching do_stat()/stat functions. See the
                # aggregated loop above for why str coercion breaks stat lookups.
                playerid = row[0]
                is_hero = False
                if hero_id is not None:
                    try:
                        is_hero = int(playerid) == int(hero_id)
                    except (ValueError, TypeError):
                        is_hero = str(playerid) == str(hero_id)
                if (is_hero and h_stat_range == "S") or (not is_hero and stat_range == "S"):
                    for name, val in zip(colnames, row, strict=False):
                        if playerid not in stat_dict:
                            stat_dict[playerid] = {}
                            stat_dict[playerid][name.lower()] = val
                        elif name.lower() not in stat_dict[playerid]:
                            stat_dict[playerid][name.lower()] = val
                        elif name.lower() not in (
                            "hand_id",
                            "player_id",
                            "seat",
                            "screen_name",
                            "seats",
                        ):
                            stat_dict[playerid][name.lower()] += val
                row = c.fetchone()
        else:
            log.error(f"query {query} result does not have player_id as first column")

    def get_hero_hudcache_start(self):
        """Fetches earliest stylekey from hudcache for one of hero's player ids."""
        try:
            # derive list of program owner's player ids
            self.hero = {}  # name of program owner indexed by site id
            self.hero_ids = {
                "dummy": -53,
                "dummy2": -52,
            }  # playerid of owner indexed by site id
            # make sure at least two values in list
            # so that tuple generation creates doesn't use
            # () or (1,) style
            for site in self.config.get_supported_sites():
                result = self.get_site_id(site)
                if result:
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    for idx, p_id in enumerate(self.get_hero_player_ids(site)):
                        self.hero_ids[f"{site_id}_{idx}"] = int(p_id)

            q = self.sql.query["get_hero_hudcache_start"].replace(
                "<playerid_list>",
                str(tuple(self.hero_ids.values())),
            )
            c = self.get_cursor()
            c.execute(q)
            tmp = c.fetchone()
            if tmp == (None,):
                return self.hero_hudstart_def
            return "20" + tmp[0][1:3] + "-" + tmp[0][3:5] + "-" + tmp[0][5:7]
        except Exception:  # intentional broad catch: hero hudcache start query/parse best-effort, log only
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            log.exception(f"Error rebuilding hudcache: {sys.exc_info()[1]!s}\n{err}")

    # end def get_hero_hudcache_start
