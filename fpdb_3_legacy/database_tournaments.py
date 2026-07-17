"""Tournament persistence for the fpdb database.

Split out of Database.py: these methods own the TourneyTypes, Tourneys and
TourneysPlayers tables -- the format of a tournament, each running of it, and
each player's entry, results and bounties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")


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

    if TYPE_CHECKING:

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
            or (field == "koBounty" and value1)
        )
    def createOrUpdateTourneyType(self, obj):
        ttid, _ttid, updateDb = None, None, False
        obj.limitType = obj.gametype["limitType"]
        cursor = self.get_cursor()
        q = self.sql.query["getTourneyTypeIdByTourneyNo"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        cursor.execute(q, (obj.tourNo, obj.siteId))
        result = cursor.fetchone()

        if result is not None:
            columnNames = [desc[0].lower() for desc in cursor.description]
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
            resultDict = dict(list(zip(columnNames, result, strict=False)))
            ttid = resultDict["id"]
            for ev in expectedValues:
                objField, dbField = ev
                objVal, dbVal = getattr(obj, objField), resultDict[dbField]
                if (
                    self.defaultTourneyTypeValue(objVal, dbVal, objField) and dbVal
                ):  # DB has this value but object doesnt, so update object
                    setattr(obj, objField, dbVal)
                elif (
                    self.defaultTourneyTypeValue(dbVal, objVal, objField) and objVal
                ):  # object has this value but DB doesnt, so update DB
                    updateDb = True
                    oldttid = ttid
        if not result or updateDb:
            if obj.gametype["mix"] != "none":
                category, limitType = obj.gametype["mix"], "mx"
            elif result is not None and resultDict["limittype"] == "mx":
                category, limitType = resultDict["category"], "mx"
            else:
                category, limitType = (
                    obj.gametype["category"],
                    obj.gametype["limitType"],
                )
            row = (
                obj.siteId,
                obj.buyinCurrency,
                obj.buyin,
                obj.fee,
                category,
                limitType,
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
                cursor.execute(
                    self.sql.query["insertTourneyType"].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    ),
                    row,
                )
                ttid = self.get_last_insert_id(cursor)
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
        result = None
        c = self.get_cursor()
        q = self.sql.query["getTourneyByTourneyNo"]
        q = q.replace("%s", self.sql.query["placeholder"])
        t = hand.startTime.replace(tzinfo=None)
        c.execute(q, (hand.siteId, hand.tourNo))

        tmp = c.fetchone()
        if tmp is None:
            c.execute(
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
            result = self.get_last_insert_id(c)
        else:
            result = tmp[0]
            columnNames = [desc[0] for desc in c.description]
            resultDict = dict(list(zip(columnNames, tmp, strict=False)))
            if self.backend == self.PGSQL:
                startTime, endTime = resultDict["starttime"], resultDict["endtime"]
                tourneyName = resultDict.get("tourneyname")
            else:
                startTime, endTime = resultDict["startTime"], resultDict["endTime"]
                tourneyName = resultDict.get("tourneyName")

            if not tourneyName and hand.tourneyName:
                q_update = """UPDATE Tourneys SET tourneyName = %s WHERE id = %s"""
                q_update = q_update.replace("%s", self.sql.query["placeholder"])
                c.execute(q_update, (hand.tourneyName, result))

            if startTime is None or t < startTime:
                q = self.sql.query["updateTourneyStart"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                )
                c.execute(q, (t, result))
            elif endTime is None or t > endTime:
                q = self.sql.query["updateTourneyEnd"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                )
                c.execute(q, (t, result))
        return result
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

            tourneyId = resultDict["id"]
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
                    tourneyId,
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
            cursor.execute(
                self.sql.query["insertTourney"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                row,
            )
            tourneyId = self.get_last_insert_id(cursor)
        return tourneyId
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

        for player in hand.players:
            playerId = hand.playerIds[player[1]]
            result[player[1]] = self.tpcache[(playerId, hand.tourneyId, hand.entryId)]

        return result
    def insertTourneysPlayers(self, playerId, tourneyId, entryId):
        result = None
        c = self.get_cursor()
        q = self.sql.query["getTourneysPlayersByIds"]
        q = q.replace("%s", self.sql.query["placeholder"])

        c.execute(q, (tourneyId, playerId, entryId))

        tmp = c.fetchone()
        if tmp is None:  # new player
            c.execute(
                self.sql.query["insertTourneysPlayer"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                (tourneyId, playerId, entryId, None, None, None, None, None, None),
            )
            # Get last id might be faster here.
            # c.execute ("SELECT id FROM Players WHERE name=%s", (name,))
            result = self.get_last_insert_id(c)
        else:
            result = tmp[0]
        return result
    def updateTourneyPlayerBounties(self, hand) -> None:
        updateDb = False
        cursor = self.get_cursor()
        bounty_query = self.sql.query["updateTourneysPlayerBounties"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        result_query = self.sql.query["updateTourneysPlayerResults"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        for player, tourneysPlayersId in list(hand.tourneysPlayersIds.items()):
            if player in hand.koCounts:
                cursor.execute(
                    bounty_query,
                    (hand.koCounts[player], hand.koCounts[player], tourneysPlayersId),
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
        tourneysPlayersIds, tplayers, inserts = {}, [], []
        cursor = self.get_cursor()
        cursor.execute(
            self.sql.query["getTourneysPlayersByTourney"].replace(
                "%s",
                self.sql.query["placeholder"],
            ),
            (summary.tourneyId,),
        )
        result = cursor.fetchall()
        if result:
            tplayers += list(result)
        for player, entries in list(summary.players.items()):
            playerId = summary.playerIds[player]
            for entryIdx in range(len(entries)):
                entryId = entries[entryIdx]
                if (playerId, entryId) in tplayers:
                    cursor.execute(
                        self.sql.query["getTourneysPlayersByIds"].replace(
                            "%s",
                            self.sql.query["placeholder"],
                        ),
                        (summary.tourneyId, playerId, entryId),
                    )
                    columnNames = [desc[0] for desc in cursor.description]
                    result = cursor.fetchone()
                    if self.backend == self.PGSQL:
                        expectedValues = (
                            ("rank", "rank"),
                            ("winnings", "winnings"),
                            ("winningsCurrency", "winningscurrency"),
                            ("rebuyCount", "rebuycount"),
                            ("addOnCount", "addoncount"),
                            ("koCount", "kocount"),
                        )
                    else:
                        expectedValues = (
                            ("rank", "rank"),
                            ("winnings", "winnings"),
                            ("winningsCurrency", "winningsCurrency"),
                            ("rebuyCount", "rebuyCount"),
                            ("addOnCount", "addOnCount"),
                            ("koCount", "koCount"),
                        )
                    updateDb = False
                    resultDict = dict(list(zip(columnNames, result, strict=False)))
                    tourneysPlayersIds[(player, entryId)] = result[0]
                    for ev in expectedValues:
                        summaryAttribute = ev[0]
                        if ev[0] != "winnings" and ev[0] != "winningsCurrency":
                            summaryAttribute += "s"
                        summaryDict = getattr(summary, summaryAttribute)
                        if (
                            summaryDict[player][entryIdx] is None and resultDict[ev[1]] is not None
                        ):  # DB has this value but object doesnt, so update object
                            summaryDict[player][entryIdx] = resultDict[ev[1]]
                            setattr(summary, summaryAttribute, summaryDict)
                        elif (
                            summaryDict[player][entryIdx] is not None and not resultDict[ev[1]]
                        ):  # object has this value but DB doesnt, so update DB
                            updateDb = True
                    if updateDb:
                        q = self.sql.query["updateTourneysPlayer"].replace(
                            "%s",
                            self.sql.query["placeholder"],
                        )
                        inputs = (
                            summary.ranks[player][entryIdx],
                            summary.winnings[player][entryIdx],
                            summary.winningsCurrency[player][entryIdx],
                            summary.rebuyCounts[player][entryIdx],
                            summary.addOnCounts[player][entryIdx],
                            summary.koCounts[player][entryIdx],
                            tourneysPlayersIds[(player, entryId)],
                        )
                        # print q
                        # pp = pprint.PrettyPrinter(indent=4)
                        # pp.pprint(inputs)
                        cursor.execute(q, inputs)
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
                        ),
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
