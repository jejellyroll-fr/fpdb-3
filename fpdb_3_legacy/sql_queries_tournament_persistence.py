"""Tournament and tournament-player persistence queries."""

from __future__ import annotations


def tournament_persistence_queries(db_server: str = "") -> dict[str, str]:
    """Return tournament lookup, write, result, and repair queries."""
    query: dict[str, str] = {}
    rank = "`rank`" if db_server == "mysql" else "rank"
    query["getTourneyByTourneyNo"] = """SELECT t.*
                                    FROM Tourneys t
                                    INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                    WHERE tt.siteId=%s AND t.siteTourneyNo=%s
    """

    query["getTourneyInfo"] = """SELECT tt.*, t.*
                                    FROM Tourneys t
                                    INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                    INNER JOIN Sites s ON (tt.siteId = s.id)
                                    WHERE s.name=%s AND t.siteTourneyNo=%s
    """

    query["getSiteTourneyNos"] = """SELECT t.siteTourneyNo
                                    FROM Tourneys t
                                    INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                    INNER JOIN Sites s ON (tt.siteId = s.id)
                                    WHERE tt.siteId=%s
    """

    query["getTourneyPlayerInfo"] = """SELECT tp.*
                                    FROM Tourneys t
                                    INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                    INNER JOIN Sites s ON (tt.siteId = s.id)
                                    INNER JOIN TourneysPlayers tp ON (tp.tourneyId = t.id)
                                    INNER JOIN Players p ON (p.id = tp.playerId)
                                    WHERE s.name=%s AND t.siteTourneyNo=%s AND p.name=%s
    """

    query["insertTourney"] = """insert into Tourneys (
                                         tourneyTypeId, sessionId, siteTourneyNo, entries, prizepool,
                                         startTime, endTime, tourneyName, totalRebuyCount, totalAddOnCount,
                                         comment, commentTs, added, addedCurrency)
                                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    query["updateTourney"] = """UPDATE Tourneys
                                         SET entries = %s,
                                             prizepool = %s,
                                             startTime = %s,
                                             endTime = %s,
                                             tourneyName = %s,
                                             totalRebuyCount = %s,
                                             totalAddOnCount = %s,
                                             comment = %s,
                                             commentTs = %s,
                                             added = %s,
                                             addedCurrency = %s
                                    WHERE id=%s
    """

    query["updateTourneyStart"] = """UPDATE Tourneys
                                         SET startTime = %s
                                    WHERE id=%s
    """

    query["updateTourneyEnd"] = """UPDATE Tourneys
                                         SET endTime = %s
                                    WHERE id=%s
    """

    query["getTourneysPlayersByIds"] = """SELECT *
                                            FROM TourneysPlayers
                                            WHERE tourneyId=%s AND playerId=%s AND entryId=%s
    """

    query["getTourneysPlayersByTourney"] = """SELECT playerId, entryId
                                                   FROM TourneysPlayers
                                                   WHERE tourneyId=%s
    """

    query["updateTourneysPlayer"] = f"""UPDATE TourneysPlayers
                                             SET {rank} = %s,
                                                 winnings = %s,
                                                 winningsCurrency = %s,
                                                 rebuyCount = %s,
                                                 addOnCount = %s,
                                                 koCount = %s
                                             WHERE id=%s
    """

    query["updateTourneysPlayerBounties"] = """UPDATE TourneysPlayers
                                             SET koCount = case when koCount is null then %s else koCount+%s end
                                             WHERE id=%s
    """

    query["updateTourneysPlayerResults"] = f"""UPDATE TourneysPlayers
                                             SET {rank} = CASE WHEN %s IS NULL THEN {rank} ELSE %s END,
                                                 winnings = CASE WHEN %s IS NULL THEN winnings ELSE %s END,
                                                 winningsCurrency = CASE WHEN %s IS NULL THEN winningsCurrency ELSE %s END
                                             WHERE id=%s
    """

    query["insertTourneysPlayer"] = f"""insert into TourneysPlayers (
                                                tourneyId,
                                                playerId,
                                                entryId,
                                                {rank},
                                                winnings,
                                                winningsCurrency,
                                                rebuyCount,
                                                addOnCount,
                                                koCount
                                            )
                                            values (%s, %s, %s, %s, %s,
                                                    %s, %s, %s, %s)
    """

    query["selectHandsPlayersWithWrongTTypeId"] = """SELECT id
                                                          FROM HandsPlayers
                                                          WHERE tourneyTypeId <> %s AND (TourneysPlayersId+0=%s)
    """

    #            query['updateHandsPlayersForTTypeId2'] = """UPDATE HandsPlayers
    #                                                            SET tourneyTypeId= %s
    #                                                            WHERE (TourneysPlayersId+0=%s)
    #            """

    query["updateHandsPlayersForTTypeId"] = """UPDATE HandsPlayers
                                                     SET tourneyTypeId= %s
                                                     WHERE (id=%s)
    """

    query["handsPlayersTTypeId_joiner"] = " OR TourneysPlayersId+0="
    query["handsPlayersTTypeId_joiner_id"] = " OR id="
    return query
