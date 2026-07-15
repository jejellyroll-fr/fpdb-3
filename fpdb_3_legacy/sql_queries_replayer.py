"""Hand-range and replayer detail queries."""

from __future__ import annotations


def replayer_queries() -> dict[str, str]:
    """Return hand range, board, player, and action queries."""
    query: dict[str, str] = {}
    ####################################
    # Querry to get all hands in a date range
    ####################################
    query["handsInRange"] = """
        select h.id
            from Hands h
            join HandsPlayers hp on h.id = hp.handId
            join Gametypes gt on gt.id = h.gametypeId
        where h.startTime <datetest>
            and hp.playerId in <player_test>
            <game_test>
            <limit_test>
            <position_test>"""

    ####################################
    # Querry to get all hands in a date range for cash games session
    ####################################
    query["handsInRangeSession"] = """
        select h.id
            from Hands h

        where h.startTime <datetest>
           """

    ####################################
    # Querry to get all hands in a date range for cash games session variation filter
    ####################################
    query["handsInRangeSessionFilter"] = """
        select h.id
        from Hands h
        join Gametypes gt on h.gametypeId = gt.id
        join HandsPlayers hp on h.id = hp.handId  -- utilisation de HandsPlayers
        where h.startTime <datetest>
        <game_test>
        <limit_test>
        <player_test>
        <position_test>
    """

    query["getPlayerId"] = """
        SELECT id
        FROM Players
        WHERE siteId = %s
        AND name = %s
    """

    ####################################
    # Query to get a single hand for the replayer
    ####################################
    query["singleHand"] = """
             SELECT h.*
                FROM Hands h
                WHERE id = %s"""

    ####################################
    # Query to get run it twice boards for the replayer
    ####################################
    query["singleHandBoards"] = """
             SELECT b.*
                FROM Boards b
                WHERE handId = %s"""

    ####################################
    # Query to get a single player hand for the replayer
    ####################################
    query["playerHand"] = """
        SELECT
                    hp.seatno,
                    round(hp.winnings / 100.0,2) as winnings,
                    p.name,
                    round(hp.startCash / 100.0,2) as chips,
                    hp.card1,hp.card2,hp.card3,hp.card4,hp.card5,
                    hp.card6,hp.card7,hp.card8,hp.card9,hp.card10,
                    hp.card11,hp.card12,hp.card13,hp.card14,hp.card15,
                    hp.card16,hp.card17,hp.card18,hp.card19,hp.card20,
                    hp.position,
                    round(hp.startBounty / 100.0,2) as bounty,
                    hp.sitout,
                    hp.isCashOut
                FROM
                    HandsPlayers as hp,
                    Players as p
                WHERE
                    hp.handId = %s
                    and p.id = hp.playerId
                ORDER BY
                    hp.seatno
            """

    ####################################
    # Query for the actions of a hand
    ####################################
    query["handActions"] = """
        SELECT
                  ha.actionNo,
                  p.name,
                  ha.street,
                  ha.actionId,
                  ha.allIn,
                  round(ha.amount / 100.0,2) as bet,
                  ha.numDiscarded,
                  ha.cardsDiscarded
            FROM
                  HandsActions as ha,
                  Players as p,
                  Hands as h
            WHERE
                      h.id = %s
                  AND ha.handId = h.id
                  AND ha.playerId = p.id
            ORDER BY
                  ha.id ASC
            """

    ####################################
    # Queries to rebuild/modify hudcache
    ####################################

    return query

