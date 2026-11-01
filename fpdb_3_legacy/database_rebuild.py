"""Rebuilding the stats caches, the week/month periods and the sessions from the hands.

Split out of Database.py (#452); mixed into Database.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytz

from fpdb_3_legacy import hud_day, session_rebuild
from fpdb_3_legacy.cache_rebuild import rebuild_stat_columns
from fpdb_3_legacy.database_caches import CACHE_KEYS, HUDCACHE_EXTRA_KEYS, SESSION_CACHE_KEYS
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.sql_queries_cache_rebuild import HAND_TIME_RANGE

log = get_logger("database")


class DatabaseRebuildMixin:
    """Rebuild the caches from the hands they summarise."""

    # Provided by Database.
    MYSQL_INNODB: Any
    PGSQL: Any
    SQLITE: Any
    backend: Any
    build_full_hudcache: Any
    cacheSessions: Any
    callHud: Any
    config: Any
    day_start: Any
    hero: Any
    hero_hudstart_def: Any
    hero_ids: Any
    sql: Any
    tbulk: Any
    ttnew: Any
    ttold: Any
    villain_hudstart_def: Any
    wmnew: Any
    wmold: Any

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        commit: Callable[..., None]
        fetchallDict: Callable[..., Any]
        get_cursor: Callable[..., Any]
        get_hero_player_ids: Callable[..., Any]
        get_site_id: Callable[..., Any]
        insertOrUpdate: Callable[..., Any]

    @staticmethod
    def _apply_tourney_clauses(query: Any, type: Any) -> Any:
        """Fill the three tourney placeholders, or blank them for ring games."""
        if type == "tour":
            query = query.replace("<tourney_insert_clause>", ",tourneyTypeId")
            query = query.replace("<tourney_select_clause>", ",t.tourneyTypeId")
            query = query.replace("<tourney_group_clause>", ",t.tourneyTypeId")
        else:
            query = query.replace("<tourney_insert_clause>", "")
            query = query.replace("<tourney_select_clause>", "")
            query = query.replace("<tourney_group_clause>", "")
        return query

    def _statscache_hudcache(self, query: Any, type: Any) -> Any:
        """Fill the rebuild template for HudCache, whose key carries the position."""
        insert = """HudCache
            (gametypeId
            ,playerId
            ,seats
            ,position
            <tourney_insert_clause>
            ,styleKey"""

        select = """h.gametypeId
                  ,hp.playerId
                  ,h.seats as seat_num
                  <hc_position>
                  <tourney_select_clause>
                  <styleKey>"""

        group = """h.gametypeId
                    ,hp.playerId
                    ,seat_num
                    ,hc_position
                    <tourney_group_clause>
                    <styleKeyGroup>"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<sessions_join_clause>", "")

        if self.build_full_hudcache:
            query = query.replace(
                "<hc_position>",
                """,case when hp.position = 'B' then 'B'
                        when hp.position = 'S' then 'S'
                        when hp.position = '0' then 'D'
                        when hp.position = '1' then 'C'
                        when hp.position = '2' then 'M'
                        when hp.position = '3' then 'M'
                        when hp.position = '4' then 'M'
                        when hp.position = '5' then 'E'
                        when hp.position = '6' then 'E'
                        when hp.position = '7' then 'E'
                        when hp.position = '8' then 'E'
                        when hp.position = '9' then 'E'
                        else 'E'
                   end                                            as hc_position""",
            )
            day = self.hud_day_sql(self._hud_day_minutes())
            query = query.replace("<styleKey>", "," + day)
            query = query.replace("<styleKeyGroup>", "," + day)
        else:
            query = query.replace(
                "<hc_position>",
                """,case when hp.position = 'B' then 'B'
                        when hp.position = 'S' then 'S'
                        when hp.position = '0' then 'D'
                        when hp.position = '1' then 'C'
                        when hp.position = '2' then 'M'
                        when hp.position = '3' then 'M'
                        when hp.position = '4' then 'M'
                        when hp.position = '5' then 'E'
                        when hp.position = '6' then 'E'
                        when hp.position = '7' then 'E'
                        when hp.position = '8' then 'E'
                        when hp.position = '9' then 'E'
                        else 'E'
                   end                                            as hc_position""",
            )
            query = query.replace("<styleKey>", ",'A000000' as styleKey")
            query = query.replace("<styleKeyGroup>", ",styleKey")

        query = self._apply_tourney_clauses(query, type)

        query = query.replace("<hero_where>", "")
        query = query.replace("<hero_join>", "")
        return query

    def _statscache_cardscache(self, query: Any, type: Any) -> Any:
        """Fill the rebuild template for CardsCache, keyed by starting hand."""
        insert = """CardsCache
            (weekId
            ,monthId
            ,gametypeId
            <tourney_insert_clause>
            ,playerId
            ,startCards"""

        select = """s.weekId
                  ,s.monthId
                  ,h.gametypeId
                  <tourney_select_clause>
                  ,hp.playerId
                  ,hp.startCards"""

        group = """s.weekId
                    ,s.monthId
                    ,h.gametypeId
                    <tourney_group_clause>
                    ,hp.playerId
                    ,hp.startCards"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<hero_join>", "")
        query = query.replace(
            "<sessions_join_clause>",
            """INNER JOIN Sessions s ON (s.id = h.sessionId)
            INNER JOIN Players p ON (hp.playerId = p.id)""",
        )
        query = query.replace("<hero_where>", "")

        query = self._apply_tourney_clauses(query, type)
        return query

    def _statscache_positionscache(self, query: Any, type: Any) -> Any:
        """Fill the rebuild template for PositionsCache, keyed by seat and position."""
        insert = """PositionsCache
            (weekId
            ,monthId
            ,gametypeId
            <tourney_insert_clause>
            ,playerId
            ,seats
            ,maxPosition
            ,position"""

        select = """s.weekId
                  ,s.monthId
                  ,h.gametypeId
                  <tourney_select_clause>
                  ,hp.playerId
                  ,h.seats
                  ,h.maxPosition
                  ,hp.position"""

        group = """s.weekId
                    ,s.monthId
                    ,h.gametypeId
                    <tourney_group_clause>
                    ,hp.playerId
                    ,h.seats
                    ,h.maxPosition
                    ,hp.position"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<hero_join>", "")
        query = query.replace(
            "<sessions_join_clause>",
            """INNER JOIN Sessions s ON (s.id = h.sessionId)
            INNER JOIN Players p ON (hp.playerId = p.id)""",
        )
        query = query.replace("<hero_where>", "")

        query = self._apply_tourney_clauses(query, type)
        return query

    def hud_day_sql(self, minutes: str) -> str:
        """The styleKey of a hand as storeHudCache takes it: ``dYYMMDD`` of its UTC
        start time moved by ``minutes``, the offset in force at that time (#600)."""
        if self.backend == self.PGSQL:
            return "'d' || to_char(h.startTime + " + minutes + " * INTERVAL '1 minute', 'YYMMDD')"
        if self.backend == self.MYSQL_INNODB:
            return "date_format(h.startTime + INTERVAL " + minutes + " MINUTE, 'd%y%m%d')"
        return "'d' || substr(strftime('%Y%m%d', h.startTime, " + minutes + " || ' minutes'), 3, 7)"

    def _hud_day_minutes(self) -> str:
        """SQL for the minutes from a hand's UTC start to its HudCache day, over the stored hands."""
        first = last = None
        if getattr(self, "connection", None) is not None:
            cursor = self.get_cursor()
            cursor.execute(HAND_TIME_RANGE)
            first, last = (hud_day.parse_time(value) for value in cursor.fetchone())
        return hud_day.minutes_sql(first, last, self.day_start)

    def replace_statscache(self, type: str, table: str, query: str) -> str:
        if table == "HudCache":
            query = self._statscache_hudcache(query, type)
        elif table == "CardsCache":
            query = self._statscache_cardscache(query, type)
        elif table == "PositionsCache":
            query = self._statscache_positionscache(query, type)
        # The same keys the import writes into each table (#591): HudCache
        # carries the HUD-only counters on top of the shared statistics.
        if "<stat_insert_columns>" not in query:
            return query
        keys = [*CACHE_KEYS, *HUDCACHE_EXTRA_KEYS] if table == "HudCache" else SESSION_CACHE_KEYS
        server = {self.MYSQL_INNODB: "mysql", self.PGSQL: "postgresql", self.SQLITE: "sqlite"}[self.backend]
        insert_columns, select_columns = rebuild_stat_columns(server, keys)
        return query.replace("<stat_insert_columns>", insert_columns).replace("<stat_select_columns>", select_columns)

    def _rebuild_prepare_heroes(self, h_start: Any, v_start: Any) -> Any:
        """Resolve the owner's player ids and the two rebuild start dates."""
        # stime = time()
        # derive list of program owner's player ids
        self.hero = {}  # name of program owner indexed by site id
        self.hero_ids: Any = {
            "dummy": -53,
            "dummy2": -52,
        }  # playerid of owner indexed by site id
        # make sure at least two values in list
        # so that tuple generation creates doesn't use
        # () or (1,) style
        if not h_start and not v_start:
            self.hero_ids = None
        else:
            for site in self.config.get_supported_sites():
                result = self.get_site_id(site)
                if result:
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    for idx, p_id in enumerate(self.get_hero_player_ids(site)):
                        self.hero_ids[f"{site_id}_{idx}"] = int(p_id)

            if not h_start:
                h_start = self.hero_hudstart_def
            if not v_start:
                v_start = self.villain_hudstart_def
        return h_start, v_start

    def rebuild_sql(self, game_type: str, table: str, where: str) -> str:
        """The INSERT ... SELECT that refills one half ("ring" or "tour") of a statistics cache."""
        query = self.sql.query["rebuildCache"].replace("%s", self.sql.query["placeholder"])
        tourney_join = "INNER JOIN Tourneys t ON (t.id = h.tourneyId)" if game_type == "tour" else ""
        query = query.replace("<tourney_join_clause>", tourney_join).replace("<where_clause>", where)
        return self.replace_statscache(game_type, table, query)

    def _rebuild_ring_cache(self, table: Any, h_start: Any, v_start: Any, wmid: Any, commit: bool = True) -> None:
        """Rebuild the cash half of a statistics cache."""
        if self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'ring' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
            else:
                where = "WHERE g.type = 'ring'<hero_where>"
        else:
            where = (
                "where (((    hp.playerId not in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + v_start
                + "')"
                + "   or (    hp.playerId in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + h_start
                + "'))"
                + "   AND hp.tourneysPlayersId IS NULL)"
            )
        self.get_cursor().execute(self.rebuild_sql("ring", table, where))
        if commit:
            self.commit()
        # print ("Rebuild cache(cash) took %.1f seconds") % (time() - stime,)

    def _rebuild_tourney_cache(self, table: Any, h_start: Any, v_start: Any, ttid: Any, wmid: Any, commit: bool = True) -> None:
        """Rebuild the tournament half of a statistics cache."""
        if ttid:
            where = f"WHERE t.tourneyTypeId = {ttid}<hero_where>"
        elif self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'tour' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
            else:
                where = "WHERE g.type = 'tour'<hero_where>"
        else:
            where = (
                "where (((    hp.playerId not in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + v_start
                + "')"
                + "   or (    hp.playerId in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + h_start
                + "'))"
                + "   AND hp.tourneysPlayersId >= 0)"
            )
        self.get_cursor().execute(self.rebuild_sql("tour", table, where))
        if commit:
            self.commit()
        # print ("Rebuild hudcache took %.1f seconds") % (time() - stime,)

    def rebuild_cache(
        self,
        h_start: Any=None,
        v_start: Any=None,
        table: str="HudCache",
        ttid: Any=None,
        wmid: Any=None,
        commit: bool = True,
    ) -> None:
        """Clears hudcache and rebuilds from the individual handsplayers records.

        With ``commit=False`` nothing is committed: the clear and both inserts
        stay in the caller's transaction, which a maintenance tool commits or
        rolls back together with its own changes.
        """
        h_start, v_start = self._rebuild_prepare_heroes(h_start, v_start)

        if not ttid and not wmid:
            self.get_cursor().execute(self.sql.query[f"clear{table}"])
            if commit:
                self.commit()

        if not ttid:
            self._rebuild_ring_cache(table, h_start, v_start, wmid, commit)

        self._rebuild_tourney_cache(table, h_start, v_start, ttid, wmid, commit)

    # end def rebuild_cache

    def update_timezone(self, tz_name: Any) -> None:
        select_W = self.sql.query["select_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        select_M = self.sql.query["select_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_W = self.sql.query["insert_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_M = self.sql.query["insert_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        update_WM_S = self.sql.query["update_WM_S"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        c = self.get_cursor()
        c.execute("SELECT id, sessionStart, weekId wid, monthId mid FROM Sessions")
        sessions = self.fetchallDict(c, ["id", "sessionStart", "wid", "mid"])
        for s in sessions:
            utc_start = pytz.utc.localize(s["sessionStart"])
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime("%z")
            offset = timedelta(
                hours=int(loc_tz[:-2]),
                minutes=int(loc_tz[0] + loc_tz[-2:]),
            )
            local = s["sessionStart"] + offset
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day)
            weekStart = weekdate - timedelta(days=weekdate.weekday())
            wid = self.insertOrUpdate("weeks", c, (weekStart,), select_W, insert_W)
            mid = self.insertOrUpdate("months", c, (monthStart,), select_M, insert_M)
            if wid != s["wid"] or mid != s["mid"]:
                row = [wid, mid, s["id"]]
                c.execute(update_WM_S, row)
                self.wmold.add((s["wid"], s["mid"]))
                self.wmnew.add((wid, mid))
        self.commit()
        self.cleanUpWeeksMonths()

    def updateTourneysSessions(self) -> None:
        if self.tbulk:
            q_update_sessions = self.sql.query["updateTourneysSessions"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            c = self.get_cursor()
            for t, sid in list(self.tbulk.items()):
                c.execute(q_update_sessions, (sid, t))
                self.commit()

    def _clear_period_caches(self, cursor: Any, wid: Any, mid: Any) -> None:
        """Drop the CardsCache and PositionsCache rows of one week/month pair."""
        for t in ("CardsCache", "PositionsCache"):
            statement = f"clear{t}WeeksMonths"
            clear = self.sql.query[statement].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor.execute(clear, (wid, mid))
        self.commit()

    def _delete_orphan_periods(self, cursor: Any, ids: Any, select_query: Any, delete_query: Any) -> None:
        """Remove week or month rows no session points at any more."""
        for period_id in ids:
            cursor.execute(select_query, (period_id,))
            if not cursor.fetchone():
                cursor.execute(delete_query, (period_id,))
                self.commit()

    def _rebuild_period_caches(self, cursor: Any) -> None:
        """Rebuild the per-period caches for every pair the cleanup touched."""
        wmids = set()
        for t in ("CardsCache", "PositionsCache"):
            statement = f"fetchNew{t}WeeksMonths"
            fetch = self.sql.query[statement].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor.execute(fetch)
            for wid, mid in cursor.fetchall():
                wmids.add((wid, mid))
        for wmid in wmids:
            for t in ("CardsCache", "PositionsCache"):
                self.rebuild_cache(None, None, t, None, wmid)

    def cleanUpWeeksMonths(self) -> None:
        if not (self.cacheSessions and self.wmold):
            return
        selectWeekId = self.sql.query["selectSessionWithWeekId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        selectMonthId = self.sql.query["selectSessionWithMonthId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        deleteWeekId = self.sql.query["deleteWeekId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        deleteMonthId = self.sql.query["deleteMonthId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        cursor = self.get_cursor()
        weeks, months = set(), set()
        for wid, mid in self.wmold:
            self._clear_period_caches(cursor, wid, mid)
            weeks.add(wid)
            months.add(mid)

        self._delete_orphan_periods(cursor, weeks, selectWeekId, deleteWeekId)
        self._delete_orphan_periods(cursor, months, selectMonthId, deleteMonthId)

        for wid, mid in self.wmnew:
            self._clear_period_caches(cursor, wid, mid)

        self._rebuild_period_caches(cursor)
        self.commit()

    def rebuild_caches(self) -> None:
        if self.callHud:
            self.rebuild_cache(None, None, "HudCache")
        if self.cacheSessions:
            self.rebuild_session_caches()

    def rebuild_hand_caches(self, commit: bool = True) -> tuple[str, ...]:
        """Rebuild every cache derived from the hands, as a repair that moved or deleted hands needs.

        The session tables when sessions are cached, or were when the database
        was imported: their rows would otherwise keep counting what the repair
        changed. Returns the tables rebuilt.
        """
        self.rebuild_cache(None, None, "HudCache", commit=False)
        tables: tuple[str, ...]
        if self.cacheSessions or session_rebuild.has_sessions(self):
            self.rebuild_session_caches(commit=False)
            tables = ("HudCache", "Sessions", "SessionsCache", "TourneysCache", "CardsCache", "PositionsCache")
        else:
            for table in ("CardsCache", "PositionsCache"):
                self.rebuild_cache(None, None, table, commit=False)
            tables = ("HudCache", "CardsCache", "PositionsCache")
        if commit:
            self.commit()
        return tables

    def rebuild_sessions(self, commit: bool = True, batch: int = session_rebuild.BATCH) -> None:
        """Regenerate Sessions, SessionsCache, TourneysCache and the session ids from the hands (#598)."""
        session_rebuild.rebuild_sessions(self, commit=commit, batch=batch)

    def rebuild_session_caches(self, commit: bool = True) -> None:
        """Rebuild the sessions, then the two caches that read their week and month through them."""
        self.rebuild_sessions(commit=False)
        for table in ("CardsCache", "PositionsCache"):
            self.rebuild_cache(None, None, table, commit=False)
        session_rebuild.delete_orphan_periods(self)
        if commit:
            self.commit()

    def resetClean(self) -> None:
        self.ttold = set()
        self.ttnew = set()
        self.wmold = set()
        self.wmnew = set()

    def cleanRequired(self) -> bool:
        return bool(self.ttold or self.wmold)

    # end def createOrUpdateTourney

    # end def getTourneyPlayerInfo
