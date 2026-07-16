"""Game and tournament type persistence queries."""

from __future__ import annotations


def game_type_queries(db_server: str) -> dict[str, str]:
    """Return game/tournament type lookup and persistence queries.

    ``limitType`` is deliberately part of both game lookups.  It is a required
    dimension of ``Gametypes`` and distinguishes variants that otherwise share
    the same site, category, stakes and table size.
    """
    query: dict[str, str] = {}
    query["getGametypeFL"] = """SELECT id
                                       FROM Gametypes
                                       WHERE siteId=%s
                                       AND   type=%s
                                       AND   category=%s
                                       AND   limitType=%s
                                       AND   smallBet=%s
                                       AND   bigBet=%s
                                       AND   maxSeats=%s
                                       AND   ante=%s
    """

    query["getGametypeNL"] = """SELECT id
                                       FROM Gametypes
                                       WHERE siteId=%s
                                       AND   type=%s
                                       AND   category=%s
                                       AND   limitType=%s
                                       AND   currency=%s
                                       AND   mix=%s
                                       AND   smallBlind=%s
                                       AND   bigBlind=%s
                                       AND   maxSeats=%s
                                       AND   ante=%s
                                       AND   buyinType=%s
                                       AND   fast=%s
                                       AND   newToGame=%s
                                       AND   homeGame=%s
                                       AND   split=%s
    """

    query[
        "insertGameTypes"
    ] = """insert into Gametypes (siteId, currency, type, base, category, limitType, hiLo, mix,
                                           smallBlind, bigBlind, smallBet, bigBet, maxSeats, ante, buyinType, fast, newToGame, homeGame, split)
                                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    query["isAlreadyInDB"] = """SELECT H.id FROM Hands H
                                     INNER JOIN Gametypes G ON (H.gametypeId = G.id)
                                     WHERE siteHandNo=%s AND G.siteId=%s<heroSeat>
    """

    query["getTourneyTypeIdByTourneyNo"] = """SELECT tt.id,
                                                          tt.siteId,
                                                          tt.currency,
                                                          tt.buyin,
                                                          tt.fee,
                                                          tt.category,
                                                          tt.limitType,
                                                          tt.maxSeats,
                                                          tt.sng,
                                                          tt.knockout,
                                                          tt.koBounty,
                                                          tt.progressive,
                                                          tt.rebuy,
                                                          tt.rebuyCost,
                                                          tt.addOn,
                                                          tt.addOnCost,
                                                          tt.speed,
                                                          tt.shootout,
                                                          tt.matrix,
                                                          tt.fast,
                                                          tt.stack,
                                                          tt.step,
                                                          tt.stepNo,
                                                          tt.chance,
                                                          tt.chanceCount,
                                                          tt.multiEntry,
                                                          tt.reEntry,
                                                          tt.homeGame,
                                                          tt.newToGame,
                                                          tt.split,
                                                          tt.fifty50,
                                                          tt.time,
                                                          tt.timeAmt,
                                                          tt.satellite,
                                                          tt.doubleOrNothing,
                                                          tt.cashOut,
                                                          tt.onDemand,
                                                          tt.flighted,
                                                          tt.guarantee,
                                                          tt.guaranteeAmt,
                                                          tt.lottery,
                                                          tt.multiplier
                                                FROM TourneyTypes tt
                                                INNER JOIN Tourneys t ON (t.tourneyTypeId = tt.id)
                                                WHERE t.siteTourneyNo=%s AND tt.siteId=%s
    """

    query["getTourneyTypeId"] = """SELECT  id
                                        FROM TourneyTypes
                                        WHERE siteId=%s
                                        AND currency=%s
                                        AND buyin=%s
                                        AND fee=%s
                                        AND category=%s
                                        AND limitType=%s
                                        AND maxSeats=%s
                                        AND sng=%s
                                        AND knockout=%s
                                        AND koBounty=%s
                                        AND progressive=%s
                                        AND rebuy=%s
                                        AND rebuyCost=%s
                                        AND addOn=%s
                                        AND addOnCost=%s
                                        AND speed=%s
                                        AND shootout=%s
                                        AND matrix=%s
                                        AND fast=%s
                                        AND stack=%s
                                        AND step=%s
                                        AND stepNo=%s
                                        AND chance=%s
                                        AND chanceCount=%s
                                        AND multiEntry=%s
                                        AND reEntry=%s
                                        AND homeGame=%s
                                        AND newToGame=%s
                                        AND split=%s
                                        AND fifty50=%s
                                        AND time=%s
                                        AND timeAmt=%s
                                        AND satellite=%s
                                        AND doubleOrNothing=%s
                                        AND cashOut=%s
                                        AND onDemand=%s
                                        AND flighted=%s
                                        AND guarantee=%s
                                        AND guaranteeAmt=%s
                                        AND lottery=%s
                                        AND multiplier=%s
    """

    query["insertTourneyType"] = """insert into TourneyTypes (
                                               siteId, currency, buyin, fee, category, limitType, maxSeats, sng, knockout, koBounty, progressive,
                                               rebuy, rebuyCost, addOn, addOnCost, speed, shootout, matrix, fast,
                                               stack, step, stepNo, chance, chanceCount, multiEntry, reEntry, homeGame, newToGame, split,
                                               fifty50, time, timeAmt, satellite, doubleOrNothing, cashOut, onDemand, flighted, guarantee, guaranteeAmt,
                                               lottery, multiplier
                                               )
                                          values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    if db_server == "sqlite":
        query["updateTourneyTypeId"] = """UPDATE Tourneys
                                            SET tourneyTypeId = %s
                                            WHERE tourneyTypeId in (SELECT id FROM TourneyTypes WHERE siteId=%s)
                                            AND siteTourneyNo=%s
        """
    elif db_server == "postgresql":
        query["updateTourneyTypeId"] = """UPDATE Tourneys t
                                            SET tourneyTypeId = %s
                                            FROM TourneyTypes tt
                                            WHERE t.tourneyTypeId = tt.id
                                            AND tt.siteId=%s
                                            AND t.siteTourneyNo=%s
        """
    else:
        query[
            "updateTourneyTypeId"
        ] = """UPDATE Tourneys t INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                            SET tourneyTypeId = %s
                                            WHERE tt.siteId=%s AND t.siteTourneyNo=%s
        """

    query["selectTourneyWithTypeId"] = """SELECT id
                                            FROM Tourneys
                                            WHERE tourneyTypeId = %s
    """

    query["deleteTourneyTypeId"] = """DELETE FROM TourneyTypes WHERE id = %s
    """
    return query
