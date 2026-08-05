"""Queries for displaying the details of one poker hand."""

from __future__ import annotations


def hand_detail_queries() -> dict[str, str]:
    """Return backend-neutral player, table, seat, and card queries."""
    query: dict[str, str] = {}
    query["get_players_from_hand"] = """
            SELECT HandsPlayers.playerId, seatNo, name
            FROM  HandsPlayers INNER JOIN Players ON (HandsPlayers.playerId = Players.id)
            WHERE handId = %s
        """
    #                    WHERE handId = %s AND Players.id LIKE %s

    query["get_winners_from_hand"] = """
            SELECT name, winnings
            FROM HandsPlayers, Players
            WHERE winnings > 0
                AND Players.id = HandsPlayers.playerId
                AND handId = %s;
        """

    query["get_table_name"] = """
            SELECT h.tableName, gt.maxSeats, gt.category, gt.type, gt.fast, s.id, s.name
                 , count(1) as numseats, gt.limitType
            FROM Hands h, Gametypes gt, Sites s, HandsPlayers hp
            WHERE h.id = %s
                AND   gt.id = h.gametypeId
                AND   s.id = gt.siteID
                AND   hp.handId = h.id
            GROUP BY h.tableName, gt.maxSeats, gt.category, gt.type, gt.fast, s.id, s.name, gt.limitType
        """

    query["get_actual_seat"] = """
            select seatNo
            from HandsPlayers
            where HandsPlayers.handId = %s
            and   HandsPlayers.playerId  = (select Players.id from Players
                                            where Players.name = %s)
        """

    query["get_cards"] = """
/*
    changed to activate mucked card display in draw games
    in draw games, card6->card20 contain 3 sets of 5 cards at each draw

    CASE code searches from the highest card number (latest draw) and when
    it finds a non-zero card, it returns that set of data
*/
        SELECT
            seatNo AS seat_number,
            CASE Gametypes.base
                when 'draw' then COALESCE(NULLIF(card16,0), NULLIF(card11,0), NULLIF(card6,0), card1)
                else card1
            end card1,
            CASE Gametypes.base
                when 'draw' then COALESCE(NULLIF(card17,0), NULLIF(card12,0), NULLIF(card7,0), card2)
                else card2
            end card2,
            CASE Gametypes.base
                when 'draw' then COALESCE(NULLIF(card18,0), NULLIF(card13,0), NULLIF(card8,0), card3)
                else card3
            end card3,
            CASE Gametypes.base
                when 'draw' then COALESCE(NULLIF(card19,0), NULLIF(card14,0), NULLIF(card9,0), card4)
                else card4
            end card4,
            CASE Gametypes.base
                when 'draw' then COALESCE(NULLIF(card20,0), NULLIF(card15,0), NULLIF(card10,0), card5)
                else card5
            end card5,
            CASE Gametypes.base
                when 'draw' then 0
                else card6
            end card6,
            CASE Gametypes.base
                when 'draw' then 0
                else card7
            end card7

            FROM HandsPlayers, Hands, Gametypes
            WHERE handID = %s
             AND HandsPlayers.handId=Hands.id
             AND Hands.gametypeId = Gametypes.id
            ORDER BY seatNo
        """

    query["get_common_cards"] = """
            select
            boardcard1,
            boardcard2,
            boardcard3,
            boardcard4,
            boardcard5
            from Hands
            where Id = %s
        """

    return query
