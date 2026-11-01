"""Read queries on hands, tables, sites and tourneys.

Split out of Database.py (#452); mixed into Database.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.db_reconnect import reconnect_on_connection_loss
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.table_info import TableInfo

log = get_logger("database")


class DatabaseQueriesMixin:
    """Answer the read queries the GUI, the HUD and the importer ask."""

    # Provided by Database.
    _gameinfo_cache: Any
    config: Any
    connection: Any
    cursor: Any
    sql: Any

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        get_cursor: Callable[..., Any]

    def get_sites(self) -> None:
        self.cursor.execute("SELECT name,id FROM Sites")
        db_sites = dict(self.cursor.fetchall())
        configured_sites = getattr(self.config, "site_ids", {})
        sites = {**configured_sites, **db_sites}
        self.config.set_site_ids(sorted(sites.items(), key=lambda item: (item[1], item[0])))

    @reconnect_on_connection_loss
    def get_table_name(self, hand_id: Any) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        return c.fetchone()

    @reconnect_on_connection_loss
    def get_table_info(self, hand_id: Any) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        row = c.fetchone()
        if row is None:
            # Hand not yet committed to the DB (race between the HUD reading the
            # hand id from stdin and the importer writing the row). Let the caller
            # skip and retry on a later notification instead of crashing.
            log.debug("No table info found yet for hand %s", hand_id)
            return None
        # The query selects the eight historical columns first, so the row
        # maps onto TableInfo's leading fields; anything added to the SELECT
        # is read by name here rather than shifting a caller's index.
        limit_type = row[8] if len(row) > 8 else "all"
        table_info = list(row[:8])
        if row[3] == "ring":  # cash game
            return TableInfo.coerce([*table_info, None, None, None, limit_type])
        # tournament
        table_parts = re.split(" ", row[0], maxsplit=1)
        if len(table_parts) == 2:
            tour_no, tab_no = table_parts
        else:
            # Native/HTTP captures can know that a hand is a tournament before
            # the lobby metadata arrives.  In that case the physical table id
            # is also the best stable tournament key; keep the HUD operational
            # instead of raising while parsing the legacy "<tour> <table>"
            # storage convention.
            tour_no = tab_no = str(row[0])
            log.warning(
                "Tournament hand %s has unqualified tableName %r; using it for both tour and table ids",
                hand_id,
                row[0],
            )
        table_info.append(tour_no)
        table_info.append(tab_no)

        # Query tournament name
        tourney_name = None
        try:
            ph = self.sql.query.get("placeholder", "%s")
            # Only the backend's placeholder is formatted in; the value is bound.
            q = f"SELECT tourneyName FROM Tourneys WHERE siteTourneyNo = {ph}"  # nosec B608  # nosemgrep
            c.execute(q, (int(tour_no),))
            trow = c.fetchone()
            if trow:
                tourney_name = trow[0]
        except Exception:
            log.exception("Error querying tourneyName for siteTourneyNo=%s", tour_no)
            self._rollback_after_failed_read()

        table_info.append(tourney_name)
        return TableInfo.coerce([*table_info, limit_type])

    def get_last_hand(self) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_last_hand"])
        row = c.fetchone()
        return row[0]

    def get_xml(self, hand_id: Any) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_xml"], (hand_id))
        row = c.fetchone()
        return row[0]

    def get_recent_hands(self, last_hand: Any) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_recent_hands"], {"last_hand": last_hand})
        return c.fetchall()

    def get_gameinfo_from_hid(self, hand_id: Any) -> Any:
        """Return the gametype of a hand, as Hand.hand_factory wants it.

        Cached: a hand's game is settled when the hand is written and never
        changes afterwards, while the HUD asks for it once per open table per
        hand dealt -- measurably the joint second-largest source of round trips
        (see tools/measure_hud_round_trips.py), which over a VPN is pure
        latency for an answer that cannot have moved.
        """
        cached = self._gameinfo_cache.get(hand_id)
        if cached is not None:
            return cached

        # returns a gameinfo (gametype) dictionary suitable for passing
        # to Hand.hand_factory
        c = self.connection.cursor()
        q = self.sql.query["get_gameinfo_from_hid"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (hand_id,))
        row = c.fetchone()

        if row is None:
            # Not cached: the hand may simply not be committed yet, and caching
            # the miss would keep answering "no such hand" after it arrives.
            log.warning(f"No game info found for hand ID {hand_id}")
            return None

        gameinfo = {
            "sitename": row[0],
            "category": row[1],
            "base": row[2],
            "type": row[3],
            "limitType": row[4],
            "hilo": row[5],
            "sb": row[6],
            "bb": row[7],
            "sbet": row[8],
            "bbet": row[9],
            "currency": row[10],
            "gametypeId": row[11],
            "split": row[12],
        }
        self._gameinfo_cache[hand_id] = gameinfo
        return gameinfo

    def get_last_gametype_id_for_table(self, site_name: Any, table_name: Any) -> Any:
        """Return the gametypeId this table last dealt, or None.

        A Fast-Fold HUD built from the client log has no hand of its own to
        take a gametypeId from -- the log names the table seconds to minutes
        before the hand history arrives. Without one the statistics query is
        skipped entirely and the first hand of every table shows empty blocks.
        The pool's own last imported hand settles it, and a pool does not
        change what it deals.

        Takes the site's name rather than its id because the id is itself
        learned from an imported hand, which is the thing missing here.
        """
        if not site_name or not table_name:
            return None
        cursor = self.connection.cursor()
        query = self.sql.query["get_last_gametype_for_table"]
        query = query.replace("%s", self.sql.query["placeholder"])
        cursor.execute(query, (site_name, table_name))
        row = cursor.fetchone()
        return None if row is None else row[0]

    #   Query 'get_hand_info' does not exist, so it seems
    #    def get_hand_info(self, new_hand_id):
    #        c = self.connection.cursor()
    #        c.execute(self.sql.query['get_hand_info'], new_hand_id)
    #        return c.fetchall()

    def getHandCount(self) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["getHandCount"])
        return c.fetchone()[0]

    # end def getHandCount

    def getTourneyCount(self) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getTourneyTypeCount(self) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyTypeCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getSiteTourneyNos(self, site: Any) -> Any:
        c = self.connection.cursor()
        q = self.sql.query["getSiteId"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (site,))
        siteid = c.fetchone()[0]
        q = self.sql.query["getSiteTourneyNos"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (siteid,))
        alist = []
        for row in c.fetchall():
            alist.append(row)
        return alist

    def get_actual_seat(self, hand_id: Any, name: Any) -> Any:
        c = self.connection.cursor()
        c.execute(self.sql.query["get_actual_seat"], (hand_id, name))
        row = c.fetchone()
        return row[0]

    @reconnect_on_connection_loss
    def get_cards(self, hand: Any) -> Any:
        """Get and return the cards for each player in the hand."""
        cards = {}  # dict of cards, the key is the seat number,
        # the value is a tuple of the players cards
        # example: {1: (0, 0, 20, 21, 22, 0 , 0)}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_cards"], [hand])
        for row in c.fetchall():
            cards[row[0]] = row[1:]
        return cards

    def _rollback_after_failed_read(self) -> None:
        """Clear an aborted transaction left by a best-effort HUD read.

        Under PostgreSQL a single failed statement blocks every later query on
        the connection until an explicit ROLLBACK, so a swallowed read error
        would otherwise resurface as InFailedSqlTransaction in unrelated code.
        """
        try:
            self.connection.rollback()
        except Exception:
            log.debug("rollback after failed read did not succeed")

    def get_hand_positions(self, hand: Any) -> Any:
        """Return {playerId: position} for a hand, for position-conditional HUD panels.

        Position values are as stored by DerivedStats in HandsPlayers.position:
        0 = button, 'S' = small blind, 'B' = big blind, 1.. = seats after the BB.
        """
        positions = {}
        try:
            ph = self.sql.query.get("placeholder", "%s")
            # Only the backend's placeholder is formatted in; the value is bound.
            q = "SELECT playerId, position FROM HandsPlayers WHERE handId = %s".replace("%s", ph)  # nosec B608  # nosemgrep
            c = self.connection.cursor()
            c.execute(q, (hand,))
            for row in c.fetchall():
                # int keys, so `pid in stat_dict` in _merge_positions matches.
                positions[row[0]] = row[1]
        except Exception:
            log.exception("get_hand_positions failed for hand %s", hand)
            self._rollback_after_failed_read()
        return positions

    @reconnect_on_connection_loss
    def get_common_cards(self, hand: Any) -> Any:
        """Get and return the community cards for the specified hand."""
        cards = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_common_cards"], [hand])
        #        row = c.fetchone()
        cards["common"] = c.fetchone()
        return cards

    def get_action_from_hand(self, hand_no: Any) -> Any:
        action: list[list[Any]] = [[], [], [], [], []]
        c = self.connection.cursor()
        c.execute(self.sql.query["get_action_from_hand"], (hand_no,))
        for row in c.fetchall():
            street = row[0]
            act = row[1:]
            action[street].append(act)
        return action

    def get_winners_from_hand(self, hand: Any) -> Any:
        """Returns a hash of winners:amount won, given a hand number."""
        winners = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_winners_from_hand"], (hand,))
        for row in c.fetchall():
            winners[row[0]] = row[1]
        return winners

    def get_site_id(self, site: Any) -> Any:
        c = self.get_cursor()
        c.execute(self.sql.query["getSiteId"], (site,))
        return c.fetchall()

    def get_site_hand_no(self, hand_id: Any) -> str | None:
        """The site's own hand id for a database hand id.

        Lets a stored hand be matched against a source that speaks the site's
        ids, such as the Winamax client log.
        """
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_site_hand_no"], (hand_id,))
            row = c.fetchone()
            return str(row[0]) if row and row[0] is not None else None
        except Exception:
            log.exception("get_site_hand_no failed for hand %s", hand_id)
            self._rollback_after_failed_read()
            return None

    def get_player_id_by_name(self, player_name: str) -> int | None:
        """Retrieve database player ID by player screen name."""
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_player_id_by_name"], (player_name,))
            row = c.fetchone()
            return int(row[0]) if row else None
        except Exception:
            log.exception("get_player_id_by_name failed for player %s", player_name)
            self._rollback_after_failed_read()
            return None

    def get_hands_showdown(self, hand_id: Any) -> dict:
        """Return {player_name: (combo, cards)} for a hand, or {} if none/absent.

        Tolerates databases created before the HandsShowdown table existed.
        """
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_showdown"], (hand_id,))
            for name, combo, cards in c.fetchall():
                result[name] = (combo, cards)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no showdown info.
            return {}
        return result

    def get_hands_cashout(self, hand_id: Any) -> dict:
        """Return {player_name: (amount, fee)} for a hand, or {} if none/absent."""
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_cashout"], (hand_id,))
            for name, amount, fee in c.fetchall():
                result[name] = (amount, fee)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no cashout info.
            return {}
        return result

    def get_hands_splash(self, hand_id: Any) -> dict:
        """Return {player_name: cents} of splash collected, or {} if none/absent."""
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_splash"], (hand_id,))
            for name, amount in c.fetchall():
                result[name] = amount
        except Exception:  # noqa: BLE001 - column absent on a database predating the splash work.
            self._rollback_after_failed_read()
            return {}
        return result

    def get_id(self, file: Any) -> Any:
        q = self.sql.query["get_id"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, (file,))
        id = c.fetchone()
        if not id:
            return 0
        return id[0]

    def fetchallDict(self, cursor: Any, desc: Any) -> Any:
        data = cursor.fetchall()
        if not data:
            return []
        results: list[dict[Any, Any]] = [{} for _ in data]
        for i in range(len(data)):
            for n in range(len(desc)):
                results[i][desc[n]] = data[i][n]
        return results
