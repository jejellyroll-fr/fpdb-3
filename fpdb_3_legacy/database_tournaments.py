"""Tournament persistence for the fpdb database.

Split out of Database.py: these methods own the TourneyTypes, Tourneys and
TourneysPlayers tables -- the format of a tournament, each running of it, and
each player's entry, results and bounties.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")


@dataclass
class _KnownTourney:
    """A Tourneys row as this import knows it, with the times it has not written yet."""

    id: Any
    start: Any
    end: Any
    name: Any
    start_changed: bool = False
    end_changed: bool = False


@dataclass
class _FileTourneyLookups:
    """What a file's hands would otherwise read again each: its tourney type and tourney rows."""

    types: dict[Any, tuple[Any, list[str]]] = field(default_factory=dict)
    tourneys: dict[Any, _KnownTourney] = field(default_factory=dict)


class DatabaseTournamentsMixin:
    """Reads and writes the tournament tables.

    Mixed into Database, which provides the connection, the query catalogue and
    the id caches named below.
    """

    # Provided by Database.
    sql: Any
    backend: Any
    PGSQL: int
    connection: Any
    callHud: bool
    cacheSessions: bool
    printdata: bool
    tpcache: Any
    ttold: set[Any]
    ttnew: set[Any]
    _tourney_lookups: _FileTourneyLookups | None = None

    if TYPE_CHECKING:
        insert_returning_id: Callable[..., Any]
        insert_many_returning_ids: Callable[..., list[Any]]

        def get_cursor(self, connect: bool = False) -> Any: ...

        def commit(self, force: bool = False) -> None: ...

        def executemany(self, c: Any, q: Any, values: Any) -> None: ...

        def get_last_insert_id(self, cursor: Any = None) -> Any: ...

        def rebuild_cache(
            self,
            h_start: Any = None,
            v_start: Any = None,
            table: str = "HudCache",
            ttid: Any = None,
            wmid: Any = None,
        ) -> None: ...

    def getTourneyInfo(self, siteName, tourneyNo):
        c = self.get_cursor()
        q = self.sql.query["getTourneyInfo"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        c.execute(q, (siteName, tourneyNo))
        columnNames = c.description

        names = []
        for column in columnNames:
            names.append(column[0])

        data = c.fetchone()
        return (names, data)
    def getTourneyTypesIds(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyTypesIds"])
        return c.fetchall()
    def getSqlTourneyTypeIDs(self, hand):
        # if(self.ttcache == None):
        #    self.ttcache = LambdaDict(lambda  key:self.insertTourneyType(key[0], key[1], key[2]))

        # tourneydata =   (hand.siteId, hand.buyinCurrency, hand.buyin, hand.fee, hand.gametype['category'],
        #                 hand.gametype['limitType'], hand.maxseats, hand.isSng, hand.isKO, hand.koBounty, hand.isProgressive,
        #                 hand.isRebuy, hand.rebuyCost, hand.isAddOn, hand.addOnCost, hand.speed, hand.isShootout, hand.isMatrix)

        return self.createOrUpdateTourneyType(
            hand,
        )  # self.ttcache[(hand.tourNo, hand.siteId, tourneydata)]
    def defaultTourneyTypeValue(self, value1, value2, field) -> bool:
        return bool(
            not value1
            or (field == "maxseats" and value1 > value2)
            or (field == "limitType" and value2 == "mx")
            or (field, value1) == ("buyinCurrency", "NA")
            or (field, value1) == ("stack", "Regular")
            or (field, value1) == ("speed", "Normal")
            # A hand only knows a lottery tournament is one; its multiplier
            # comes from the prize pool in the summary. Left as 1, the hands'
            # value would keep the summary's from ever reaching the type.
            or (field == "tourneyMultiplier" and value1 == 1)
            or (field == "koBounty" and value1)
        )
    @contextmanager
    def tourney_lookups_for_file(self) -> Iterator[None]:
        """Read a file's tournament rows once, for the hands prepared inside the block (#705).

        A file holds one tournament, or few: each hand read the same type and
        tourney rows and moved the end time one hand further. Inside the block
        they are read once and the times are written once, on the way out, with
        the values they would have reached one hand at a time.
        """
        self._tourney_lookups = _FileTourneyLookups()
        try:
            yield
            cursor = self.get_cursor()
            for known in self._tourney_lookups.tourneys.values():
                self._write_tourney_times(cursor, known)
        finally:
            self._tourney_lookups = None

    def _tourney_type_row(self, cursor, tour_no, site_id) -> tuple[Any, list[str]]:
        """The tourney's type row and lower-case column names, or (None, []) if it has none yet."""
        lookups = self._tourney_lookups
        known = lookups.types.get((tour_no, site_id)) if lookups is not None else None
        if known is not None:
            return known
        q = self.sql.query["getTourneyTypeIdByTourneyNo"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        cursor.execute(q, (tour_no, site_id))
        row = cursor.fetchone()
        if row is None:
            return None, []
        found = (row, [desc[0].lower() for desc in cursor.description])
        if lookups is not None:
            lookups.types[(tour_no, site_id)] = found
        return found

    def createOrUpdateTourneyType(self, obj):
        ttid, _ttid, updateDb = None, None, False
        obj.limitType = obj.gametype["limitType"]
        cursor = self.get_cursor()
        result, column_names = self._tourney_type_row(cursor, obj.tourNo, obj.siteId)

        if result is not None:
            expectedValues = (
                ("buyin", "buyin"),
                ("fee", "fee"),
                ("buyinCurrency", "currency"),
                ("limitType", "limittype"),
                ("isSng", "sng"),
                ("maxseats", "maxseats"),
                ("isKO", "knockout"),
                ("koBounty", "kobounty"),
                ("isProgressive", "progressive"),
                ("isRebuy", "rebuy"),
                ("rebuyCost", "rebuycost"),
                ("isAddOn", "addon"),
                ("addOnCost", "addoncost"),
                ("speed", "speed"),
                ("isShootout", "shootout"),
                ("isMatrix", "matrix"),
                ("isFast", "fast"),
                ("stack", "stack"),
                ("isStep", "step"),
                ("stepNo", "stepno"),
                ("isChance", "chance"),
                ("chanceCount", "chancecount"),
                ("isMultiEntry", "multientry"),
                ("isReEntry", "reentry"),
                ("isHomeGame", "homegame"),
                ("isNewToGame", "newtogame"),
                ("isSplit", "split"),
                ("isFifty50", "fifty50"),
                ("isTime", "time"),
                ("timeAmt", "timeamt"),
                ("isSatellite", "satellite"),
                ("isDoubleOrNothing", "doubleornothing"),
                ("isCashOut", "cashout"),
                ("isOnDemand", "ondemand"),
                ("isFlighted", "flighted"),
                ("isGuarantee", "guarantee"),
                ("guaranteeAmt", "guaranteeamt"),
                ("isLottery", "lottery"),
                ("tourneyMultiplier", "multiplier"),
            )
            result_dict = dict(list(zip(column_names, result, strict=False)))
            ttid = result_dict["id"]
            for ev in expectedValues:
                objField, dbField = ev
                obj_val, db_val = getattr(obj, objField), result_dict[dbField]
                if (
                    self.defaultTourneyTypeValue(obj_val, db_val, objField) and db_val
                ):  # DB has this value but object doesnt, so update object
                    setattr(obj, objField, db_val)
                elif (
                    self.defaultTourneyTypeValue(db_val, obj_val, objField) and obj_val
                ):  # object has this value but DB doesnt, so update DB
                    updateDb = True
                    oldttid = ttid
        if not result or updateDb:
            if self._tourney_lookups is not None:
                self._tourney_lookups.types.pop((obj.tourNo, obj.siteId), None)
            if obj.gametype["mix"] != "none":
                category, limit_type = obj.gametype["mix"], "mx"
            elif result is not None and result_dict["limittype"] == "mx":
                category, limit_type = result_dict["category"], "mx"
            else:
                category, limit_type = (
                    obj.gametype["category"],
                    obj.gametype["limitType"],
                )
            row = (
                obj.siteId,
                obj.buyinCurrency,
                obj.buyin,
                obj.fee,
                category,
                limit_type,
                obj.maxseats,
                obj.isSng,
                obj.isKO,
                obj.koBounty,
                obj.isProgressive,
                obj.isRebuy,
                obj.rebuyCost,
                obj.isAddOn,
                obj.addOnCost,
                obj.speed,
                obj.isShootout,
                obj.isMatrix,
                obj.isFast,
                obj.stack,
                obj.isStep,
                obj.stepNo,
                obj.isChance,
                obj.chanceCount,
                obj.isMultiEntry,
                obj.isReEntry,
                obj.isHomeGame,
                obj.isNewToGame,
                obj.isSplit,
                obj.isFifty50,
                obj.isTime,
                obj.timeAmt,
                obj.isSatellite,
                obj.isDoubleOrNothing,
                obj.isCashOut,
                obj.isOnDemand,
                obj.isFlighted,
                obj.isGuarantee,
                obj.guaranteeAmt,
                getattr(obj, "isLottery", False),
                getattr(obj, "tourneyMultiplier", 1),
            )
            cursor.execute(
                self.sql.query["getTourneyTypeId"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                row,
            )
            tmp = cursor.fetchone()
            try:
                ttid = tmp[0]
            except TypeError:  # this means we need to create a new entry
                if self.printdata:
                    log.debug("######## Tourneys ##########")
                    import pprint

                    pp = pprint.PrettyPrinter(indent=4)
                    pp.pprint(row)
                    log.debug("###### End Tourneys ########")
                ttid = self.insert_returning_id(
                    cursor,
                    self.sql.query["insertTourneyType"].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    ),
                    row,
                )
            if updateDb:
                # print 'DEBUG createOrUpdateTourneyType:', 'old', oldttid, 'new', ttid, row
                q = self.sql.query["updateTourneyTypeId"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                )
                cursor.execute(q, (ttid, obj.siteId, obj.tourNo))
                self.ttold.add(oldttid)
                self.ttnew.add(ttid)
        return ttid
    def cleanUpTourneyTypes(self) -> None:
        if self.ttold:
            tables: tuple[str, ...] | set[str]
            if self.callHud and self.cacheSessions:
                tables = ("HudCache", "CardsCache", "PositionsCache")
            elif self.callHud:
                tables = ("HudCache",)
            elif self.cacheSessions:
                tables = ("CardsCache", "PositionsCache")
            else:
                tables = set()
            select = self.sql.query["selectTourneyWithTypeId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            delete = self.sql.query["deleteTourneyTypeId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor = self.get_cursor()
            for ttid in self.ttold:
                for t in tables:
                    statement = f"clear{t}TourneyType"
                    clear = self.sql.query[statement].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    )
                    cursor.execute(clear, (ttid,))
                self.commit()
                cursor.execute(select, (ttid,))
                result = cursor.fetchone()
                if not result:
                    cursor.execute(delete, (ttid,))
                    self.commit()
            for ttid in self.ttnew:
                for t in tables:
                    statement = f"clear{t}TourneyType"
                    clear = self.sql.query[statement].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    )
                    cursor.execute(clear, (ttid,))
                self.commit()
            for t in tables:
                statement = f"fetchNew{t}TourneyTypeIds"
                fetch = self.sql.query[statement].replace(
                    "%s",
                    self.sql.query["placeholder"],
                )
                cursor.execute(fetch)
                for id in cursor.fetchall():
                    self.rebuild_cache(None, None, t, id[0])
    def getSqlTourneyIDs(self, hand):
        c = self.get_cursor()
        t = hand.startTime.replace(tzinfo=None)
        lookups = self._tourney_lookups
        key = (hand.siteId, hand.tourNo)
        known = lookups.tourneys.get(key) if lookups is not None else None
        if known is None:
            q = self.sql.query["getTourneyByTourneyNo"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c.execute(q, key)
            tmp = c.fetchone()
            if tmp is None:
                result = self.insert_returning_id(
                    c,
                    self.sql.query["insertTourney"].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    ),
                    (
                        hand.tourneyTypeId,
                        None,
                        hand.tourNo,
                        None,
                        None,
                        t,
                        t,
                        hand.tourneyName,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                )
                if lookups is not None:
                    lookups.tourneys[key] = _KnownTourney(result, t, t, hand.tourneyName)
                return result
            columnNames = [desc[0] for desc in c.description]
            resultDict = dict(list(zip(columnNames, tmp, strict=False)))
            if self.backend == self.PGSQL:
                startTime, endTime = resultDict["starttime"], resultDict["endtime"]
                tourneyName = resultDict.get("tourneyname")
            else:
                startTime, endTime = resultDict["startTime"], resultDict["endTime"]
                tourneyName = resultDict.get("tourneyName")
            known = _KnownTourney(tmp[0], startTime, endTime, tourneyName)
            if lookups is not None:
                lookups.tourneys[key] = known

        if not known.name and hand.tourneyName:
            q_update = """UPDATE Tourneys SET tourneyName = %s WHERE id = %s"""
            q_update = q_update.replace("%s", self.sql.query["placeholder"])
            c.execute(q_update, (hand.tourneyName, known.id))
            known.name = hand.tourneyName

        if known.start is None or t < known.start:
            known.start, known.start_changed = t, True
        elif known.end is None or t > known.end:
            known.end, known.end_changed = t, True
        if lookups is None:
            self._write_tourney_times(c, known)
        return known.id

    def _write_tourney_times(self, cursor, known: _KnownTourney) -> None:
        if known.start_changed:
            q = self.sql.query["updateTourneyStart"].replace("%s", self.sql.query["placeholder"])
            cursor.execute(q, (known.start, known.id))
            known.start_changed = False
        if known.end_changed:
            q = self.sql.query["updateTourneyEnd"].replace("%s", self.sql.query["placeholder"])
            cursor.execute(q, (known.end, known.id))
            known.end_changed = False

    def createOrUpdateTourney(self, summary):
        cursor = self.get_cursor()
        q = self.sql.query["getTourneyByTourneyNo"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        cursor.execute(q, (summary.siteId, summary.tourNo))

        columnNames = [desc[0] for desc in cursor.description]
        result = cursor.fetchone()

        row: tuple[Any, ...]
        if result is not None:
            if self.backend == self.PGSQL:
                expectedValues = (
                    ("comment", "comment"),
                    ("tourneyName", "tourneyname"),
                    ("totalRebuyCount", "totalrebuycount"),
                    ("totalAddOnCount", "totaladdoncount"),
                    ("prizepool", "prizepool"),
                    ("startTime", "starttime"),
                    ("entries", "entries"),
                    ("commentTs", "commentts"),
                    ("endTime", "endtime"),
                    ("added", "added"),
                    ("addedCurrency", "addedcurrency"),
                )
            else:
                expectedValues = (
                    ("comment", "comment"),
                    ("tourneyName", "tourneyName"),
                    ("totalRebuyCount", "totalRebuyCount"),
                    ("totalAddOnCount", "totalAddOnCount"),
                    ("prizepool", "prizepool"),
                    ("startTime", "startTime"),
                    ("entries", "entries"),
                    ("commentTs", "commentTs"),
                    ("endTime", "endTime"),
                    ("added", "added"),
                    ("addedCurrency", "addedCurrency"),
                )
            updateDb = False
            resultDict = dict(list(zip(columnNames, result, strict=False)))

            tourney_id = resultDict["id"]
            for ev in expectedValues:
                if (
                    getattr(summary, ev[0]) is None and resultDict[ev[1]] is not None
                ):  # DB has this value but object doesnt, so update object
                    setattr(summary, ev[0], resultDict[ev[1]])
                elif (
                    getattr(summary, ev[0]) is not None and not resultDict[ev[1]]
                ):  # object has this value but DB doesnt, so update DB
                    updateDb = True
                # elif ev=="startTime":
                #    if (resultDict[ev] < summary.startTime):
                #        summary.startTime=resultDict[ev]
            if updateDb:
                q = self.sql.query["updateTourney"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                )
                startTime, endTime = None, None
                if summary.startTime is not None:
                    startTime = summary.startTime.replace(tzinfo=None)
                if summary.endTime is not None:
                    endTime = summary.endTime.replace(tzinfo=None)
                row = (
                    summary.entries,
                    summary.prizepool,
                    startTime,
                    endTime,
                    summary.tourneyName,
                    summary.totalRebuyCount,
                    summary.totalAddOnCount,
                    summary.comment,
                    summary.commentTs,
                    summary.added,
                    summary.addedCurrency,
                    tourney_id,
                )
                cursor.execute(q, row)
        else:
            startTime, endTime = None, None
            if summary.startTime is not None:
                startTime = summary.startTime.replace(tzinfo=None)
            if summary.endTime is not None:
                endTime = summary.endTime.replace(tzinfo=None)
            row = (
                summary.tourneyTypeId,
                None,
                summary.tourNo,
                summary.entries,
                summary.prizepool,
                startTime,
                endTime,
                summary.tourneyName,
                summary.totalRebuyCount,
                summary.totalAddOnCount,
                summary.comment,
                summary.commentTs,
                summary.added,
                summary.addedCurrency,
            )
            if self.printdata:
                log.debug("######## Tourneys ##########")
                import pprint

                pp = pprint.PrettyPrinter(indent=4)
                pp.pprint(row)
                log.debug("###### End Tourneys ########")
            tourney_id = self.insert_returning_id(
                cursor,
                self.sql.query["insertTourney"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                row,
            )
        return tourney_id
    def getTourneyPlayerInfo(self, siteName, tourneyNo, playerName):
        c = self.get_cursor()
        c.execute(
            self.sql.query["getTourneyPlayerInfo"],
            (siteName, tourneyNo, playerName),
        )
        columnNames = c.description

        names = []
        for column in columnNames:
            names.append(column[0])

        data = c.fetchone()
        return (names, data)
    def getSqlTourneysPlayersIDs(self, hand):
        result = {}
        if self.tpcache is None:
            self.tpcache = LambdaDict(
                lambda key: self.insertTourneysPlayers(key[0], key[1], key[2]),
            )

        if self.backend == self.PGSQL:
            self._load_tourneys_players(hand)
        for player in hand.players:
            playerId = hand.playerIds[player[1]]
            result[player[1]] = self.tpcache[(playerId, hand.tourneyId, hand.entryId)]

        return result
    def _load_tourneys_players(self, hand) -> None:
        """Fill tpcache with the hand's entries it lacks, in two round trips however many there are (#705)."""
        missing = list(
            dict.fromkeys(
                hand.playerIds[player[1]]
                for player in hand.players
                if (hand.playerIds[player[1]], hand.tourneyId, hand.entryId) not in self.tpcache
            ),
        )
        if not missing:
            return
        c = self.get_cursor()
        c.execute(self.sql.query["tourneysPlayersIdsByPlayers"], (hand.tourneyId, hand.entryId, missing))
        stored = dict(c.fetchall())
        for player_id, entry in stored.items():
            self.tpcache[(player_id, hand.tourneyId, hand.entryId)] = entry
        new_players = [player_id for player_id in missing if player_id not in stored]
        if new_players:
            ids = self.insert_many_returning_ids(
                c,
                self.sql.query["insertTourneysPlayer"],
                [
                    (hand.tourneyId, player_id, hand.entryId, None, None, None, None, None, None, None)
                    for player_id in new_players
                ],
            )
            for player_id, entry in zip(new_players, ids, strict=True):
                self.tpcache[(player_id, hand.tourneyId, hand.entryId)] = entry

    def insertTourneysPlayers(self, playerId, tourneyId, entryId):
        result = None
        c = self.get_cursor()
        q = self.sql.query["getTourneysPlayersByIds"]
        q = q.replace("%s", self.sql.query["placeholder"])

        c.execute(q, (tourneyId, playerId, entryId))

        tmp = c.fetchone()
        if tmp is None:  # new player
            result = self.insert_returning_id(
                c,
                self.sql.query["insertTourneysPlayer"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                (tourneyId, playerId, entryId, None, None, None, None, None, None, None),
            )
        else:
            result = tmp[0]
        return result
    def updateTourneyPlayerResult(
        self,
        site_name: str,
        tourney_no: str,
        player_name: str,
        rank: int,
        winnings=None,
        winnings_currency: str | None = None,
    ) -> bool:
        """Record where a player finished a tournament. True if a row was found.

        Kept apart from updateTourneyPlayerBounties, which rides on a hand: the
        room announces the finishing places once the tournament has closed, so
        there is no hand left to carry them.

        The update coalesces, so a prize that is not money -- a seat in another
        tournament, say -- leaves the winnings column as it was rather than
        being written down as zero.
        """
        names, row = self.getTourneyPlayerInfo(site_name, tourney_no, player_name)
        if row is None:
            log.debug("No %s entry for %s in tournament %s", site_name, player_name, tourney_no)
            return False
        query = self.sql.query["updateTourneysPlayerResults"].replace("%s", self.sql.query["placeholder"])
        self.get_cursor().execute(query, (rank, winnings, winnings_currency, row[names.index("id")]))
        return True

    def _settle_bounty_money(self, cursor, tourney_id, player_id) -> None:
        """Count a summary's bounty total once: the player's other entries get none of their own (#447).

        The total is tournament-wide and sits on the entry that finished; the hand import keeps
        adding koCount to entry 1, which the reports would otherwise turn into bounty money again.
        """
        ph = self.sql.query["placeholder"]
        cursor.execute(self.sql.query["countTourneyPlayerKoWinnings"].replace("%s", ph), (tourney_id, player_id))
        if cursor.fetchone()[0]:
            cursor.execute(self.sql.query["settleTourneyPlayerKoWinnings"].replace("%s", ph), (tourney_id, player_id))

    def updateTourneyPlayerBounties(self, hand) -> None:
        updateDb = False
        cursor = self.get_cursor()
        bounty_query = self.sql.query["updateTourneysPlayerBounties"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        ko_winnings_query = self.sql.query["updateTourneysPlayerKoWinnings"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        result_query = self.sql.query["updateTourneysPlayerResults"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        # koCounts is a knockout count; the money a hand states goes to
        # koWinnings, which the profit queries read first (COALESCE ahead of
        # koCount * koBounty). getattr: older callers build hand stand-ins
        # without the attribute.
        hand_ko_winnings = getattr(hand, "koWinnings", {})
        for player, tourneysPlayersId in list(hand.tourneysPlayersIds.items()):
            if player in hand.koCounts:
                cursor.execute(
                    bounty_query,
                    (hand.koCounts[player], hand.koCounts[player], tourneysPlayersId),
                )
                if hand.tourneyId is not None and player in hand.playerIds:
                    self._settle_bounty_money(cursor, hand.tourneyId, hand.playerIds[player])
                updateDb = True
            if player in hand_ko_winnings:
                cursor.execute(
                    ko_winnings_query,
                    (hand_ko_winnings[player], hand_ko_winnings[player], tourneysPlayersId),
                )
                updateDb = True
            if player in getattr(hand, "tourneyRanks", {}):
                winnings = getattr(hand, "tourneyWinnings", {}).get(player)
                winnings_currency = getattr(hand, "tourneyWinningsCurrency", {}).get(player)
                rank = hand.tourneyRanks[player]
                cursor.execute(
                    result_query,
                    (
                        rank,
                        winnings,
                        winnings_currency,
                        tourneysPlayersId,
                    ),
                )
                updateDb = True
        if updateDb:
            self.commit()
    def createOrUpdateTourneysPlayers(self, summary) -> None:
        tourneys_players_ids, inserts, updates = {}, [], []
        cursor = self.get_cursor()
        cursor.execute(
            self.sql.query["getTourneysPlayersByTourney"].replace(
                "%s",
                self.sql.query["placeholder"],
            ),
            (summary.tourneyId,),
        )
        column_names = [desc[0] for desc in cursor.description]
        lower_names = [name.lower() for name in column_names]
        player_column, entry_column = lower_names.index("playerid"), lower_names.index("entryid")
        # One read for the whole tournament: a large field would pay one per entrant (#705).
        stored = {(row[player_column], row[entry_column]): row for row in cursor.fetchall()}
        for player, entries in list(summary.players.items()):
            playerId = summary.playerIds[player]
            for entryIdx in range(len(entries)):
                entryId = entries[entryIdx]
                if (playerId, entryId) in stored:
                    result = stored[(playerId, entryId)]
                    if self.backend == self.PGSQL:
                        expectedValues = (
                            ("rank", "rank"),
                            ("winnings", "winnings"),
                            ("winningsCurrency", "winningscurrency"),
                            ("rebuyCount", "rebuycount"),
                            ("addOnCount", "addoncount"),
                            ("koCount", "kocount"),
                            ("koWinnings", "kowinnings"),
                        )
                    else:
                        expectedValues = (
                            ("rank", "rank"),
                            ("winnings", "winnings"),
                            ("winningsCurrency", "winningsCurrency"),
                            ("rebuyCount", "rebuyCount"),
                            ("addOnCount", "addOnCount"),
                            ("koCount", "koCount"),
                            ("koWinnings", "koWinnings"),
                        )
                    updateDb = False
                    result_dict = dict(list(zip(column_names, result, strict=False)))
                    tourneys_players_ids[(player, entryId)] = result[0]
                    for ev in expectedValues:
                        summaryAttribute = ev[0]
                        if ev[0] not in ("winnings", "winningsCurrency", "koWinnings"):
                            summaryAttribute += "s"
                        summaryDict = getattr(summary, summaryAttribute)
                        if (
                            summaryDict[player][entryIdx] is None and result_dict[ev[1]] is not None
                        ):  # DB has this value but object doesnt, so update object
                            summaryDict[player][entryIdx] = result_dict[ev[1]]
                            setattr(summary, summaryAttribute, summaryDict)
                        elif (
                            summaryDict[player][entryIdx] is not None and not result_dict[ev[1]]
                        ):  # object has this value but DB doesnt, so update DB
                            updateDb = True
                    if updateDb:
                        updates.append((
                            summary.ranks[player][entryIdx],
                            summary.winnings[player][entryIdx],
                            summary.winningsCurrency[player][entryIdx],
                            summary.rebuyCounts[player][entryIdx],
                            summary.addOnCounts[player][entryIdx],
                            summary.koCounts[player][entryIdx],
                            summary.koWinnings[player][entryIdx],
                            tourneys_players_ids[(player, entryId)],
                        ))
                else:
                    inserts.append(
                        (
                            summary.tourneyId,
                            playerId,
                            entryId,
                            summary.ranks[player][entryIdx],
                            summary.winnings[player][entryIdx],
                            summary.winningsCurrency[player][entryIdx],
                            summary.rebuyCounts[player][entryIdx],
                            summary.addOnCounts[player][entryIdx],
                            summary.koCounts[player][entryIdx],
                            summary.koWinnings[player][entryIdx],
                        ),
                    )
        if updates:
            cursor.executemany(
                self.sql.query["updateTourneysPlayer"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                updates,
            )
        if inserts:
            self.executemany(
                cursor,
                self.sql.query["insertTourneysPlayer"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                inserts,
            )
        for player, totals in getattr(summary, "koWinnings", {}).items():
            if any(total is not None for total in totals):
                self._settle_bounty_money(cursor, summary.tourneyId, summary.playerIds[player])
