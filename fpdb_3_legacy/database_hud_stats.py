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
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")


class DatabaseHudStatsMixin:
    """Reads the aggregates the HUD displays.

    Mixed into Database, which supplies the connection, the query catalogue and
    the configuration named below.
    """

    # Provided by Database.
    sql: Any
    config: Any
    connection: Any
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

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def get_site_id(self, site: Any) -> Any: ...

        def get_gameinfo_from_hid(self, hand_id: Any) -> Any: ...

        def get_hero_player_ids(self, site_name: Any = None, profile: Any = None) -> Any: ...

        def getAofProfileStats(self, player_ids: Any, category: str) -> Any: ...

        def _rollback_after_failed_read(self) -> None: ...

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

    def init_hud_stat_vars(self, hud_days, h_hud_days) -> None:
        """Initialise variables used by Hud to fetch stats:
        self.hand_1day_ago     handId of latest hand played more than a day ago
        self.date_ndays_ago    date n days ago
        self.h_date_ndays_ago  date n days ago for hero (different n).
        """
        self.hand_1day_ago = 1
        c = self.get_cursor()
        c.execute(self.sql.query["get_hand_1day_ago"])
        row = c.fetchone()
        if row and row[0]:
            self.hand_1day_ago = int(row[0])

        tz = datetime.utcnow() - datetime.today()
        tz_offset = (tz.seconds) // (3600)
        tz_day_start_offset = self.day_start + tz_offset

        d = timedelta(days=hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

        d = timedelta(days=h_hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.h_date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

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
            hud_params = {
                "stat_range": "A",
                "agg_bb_mult": 1000,
                "seats_style": "A",
                "seats_cust_nums_low": 1,
                "seats_cust_nums_high": 10,
                "h_stat_range": "S",
                "h_agg_bb_mult": 1000,
                "h_seats_style": "A",
                "h_seats_cust_nums_low": 1,
                "h_seats_cust_nums_high": 10,
            }
        stat_range = hud_params["stat_range"]
        agg_bb_mult = hud_params["agg_bb_mult"]
        seats_style = hud_params["seats_style"]
        seats_cust_nums_low = hud_params["seats_cust_nums_low"]
        seats_cust_nums_high = hud_params["seats_cust_nums_high"]
        h_stat_range = hud_params["h_stat_range"]
        h_agg_bb_mult = hud_params["h_agg_bb_mult"]
        h_seats_style = hud_params["h_seats_style"]
        h_seats_cust_nums_low = hud_params["h_seats_cust_nums_low"]
        h_seats_cust_nums_high = hud_params["h_seats_cust_nums_high"]

        stat_dict: dict[Any, Any] = {}

        if seats_style == "A":
            seats_min, seats_max = 0, 10
        elif seats_style == "C":
            seats_min, seats_max = seats_cust_nums_low, seats_cust_nums_high
        elif seats_style == "E":
            seats_min, seats_max = num_seats, num_seats
        else:
            seats_min, seats_max = 0, 10
            log.warning(f"bad seats_style value: {seats_style}")

        if h_seats_style == "A":
            h_seats_min, h_seats_max = 0, 10
        elif h_seats_style == "C":
            h_seats_min, h_seats_max = h_seats_cust_nums_low, h_seats_cust_nums_high
        elif h_seats_style == "E":
            h_seats_min, h_seats_max = num_seats, num_seats
        else:
            h_seats_min, h_seats_max = 0, 10
            log.warning(f"bad h_seats_style value: {h_seats_style}")

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

        if stat_range == "T":
            stylekey = self.date_ndays_ago
        elif stat_range == "A":
            stylekey = "0000000"  # all stylekey values should be higher than this
        elif stat_range == "S":
            stylekey = "zzzzzzz"  # all stylekey values should be lower than this
        else:
            stylekey = "0000000"
            log.info(f"stat_range: {stat_range}")

        if h_stat_range == "T":
            h_stylekey = self.h_date_ndays_ago
        elif h_stat_range == "A":
            h_stylekey = "0000000"  # all stylekey values should be higher than this
        elif h_stat_range == "S":
            h_stylekey = "zzzzzzz"  # all stylekey values should be lower than this
        else:
            h_stylekey = "00000000"
            log.info(f"h_stat_range: {h_stat_range}")

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
