"""Detailed tournament-player report queries."""

from __future__ import annotations


def tournament_player_detailed_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific detailed tournament-player query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["tourneyPlayerDetailedStats"] = """
                  select s.name                                                                 AS siteName
                        ,tt.currency                                                            AS currency
                        ,(CASE
                            WHEN tt.currency = 'play' THEN tt.buyIn
                            ELSE tt.buyIn/100.0
                          END)                                                                  AS buyIn
                        ,tt.fee/100.0                                                           AS fee
                        ,tt.category                                                            AS category
                        ,tt.limitType                                                           AS limitType
                        ,tt.speed                                                                AS speed
                        ,tt.maxSeats                                                            AS maxSeats
							,tt.knockout                                                            AS knockout
							,tt.reEntry                                                             AS reEntry
                        ,p.name                                                                 AS playerName
                        ,t.tourneyTypeId                                                        AS tourneyTypeId
                        ,MAX(tp.playerId)                                                       AS playerId
                        ,COUNT(1)                                                               AS tourneyCount
                        ,SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END)                           AS unknownRank
                        ,(CAST(SUM(CASE WHEN winnings > 0 THEN 1 ELSE 0 END) AS SIGNED)/CAST(COUNT(1) AS SIGNED))*100                 AS itm
                        ,SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END)                              AS _1st
                        ,SUM(CASE WHEN rank = 2 THEN 1 ELSE 0 END)                              AS _2nd
                        ,SUM(CASE WHEN rank = 3 THEN 1 ELSE 0 END)                              AS _3rd
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0))/100.0              AS won
                        ,SUM(CASE
                               WHEN tt.currency = 'play' THEN tt.buyIn
                               ELSE (tt.buyIn+tt.fee)/100.0
                             END)                                                               AS spent
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-tt.buyIn-tt.fee)/100.0	 								AS net
                        ,(CAST(SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0) - tt.buyin - tt.fee) AS SIGNED)/
                            CAST(SUM(tt.buyin+tt.fee) AS SIGNED))* 100.0                                                                    AS roi
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-(tt.buyin+tt.fee))/100.0/(COUNT(1)-SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END)) AS profitPerTourney
                  from TourneysPlayers tp
                       inner join Tourneys t        on  (t.id = tp.tourneyId)
                       inner join TourneyTypes tt   on  (tt.Id = t.tourneyTypeId)
                       inner join Sites s           on  (s.Id = tt.siteId)
                       inner join Players p         on  (p.Id = tp.playerId)
                  where tp.playerId in <nametest> <sitetest>
                  AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                                    OR t.startTime is NULL)
                  group by tourneyTypeId, playerName
                  order by tourneyTypeId
                          ,playerName
                          ,siteName"""
    elif db_server == "postgresql":
        # sc: itm and profitPerTourney changed to "ELSE 0" to avoid divide by zero error as temp fix
        # proper fix should use coalesce() or case ... when ... to work in all circumstances
        query["tourneyPlayerDetailedStats"] = """
                  select s.name                                                                 AS "siteName"
                        ,tt.currency                                                            AS "currency"
                        ,(CASE
                            WHEN tt.currency = 'play' THEN tt.buyIn
                            ELSE tt.buyIn/100.0
                          END)                                                                  AS "buyIn"
                        ,tt.fee/100.0                                                           AS "fee"
                        ,tt.category                                                            AS "category"
                        ,tt.limitType                                                           AS "limitType"
                        ,tt.speed                                                                AS "speed"
                        ,tt.maxSeats                                                            AS "maxSeats"
							,tt.knockout                                                            AS "knockout"
							,tt.reEntry                                                             AS "reEntry"
                        ,p.name                                                                 AS "playerName"
                        ,t.tourneyTypeId                                                        AS "tourneyTypeId"
                        ,MAX(tp.playerId)                                                       AS "playerId"
                        ,COUNT(1)                                                               AS "tourneyCount"
                        ,SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END)                           AS "unknownRank"
                        ,(CAST(SUM(CASE WHEN winnings > 0 THEN 1 ELSE 0 END) AS BIGINT)/CAST(COUNT(1) AS BIGINT))*100                 AS itm
                        ,SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END)                              AS "_1st"
                        ,SUM(CASE WHEN rank = 2 THEN 1 ELSE 0 END)                              AS "_2nd"
                        ,SUM(CASE WHEN rank = 3 THEN 1 ELSE 0 END)                              AS "_3rd"
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0))/100.0              AS "won"
                        ,SUM(CASE
                               WHEN tt.currency = 'play' THEN tt.buyIn
                               ELSE (tt.buyIn+tt.fee)/100.0
                             END)                                                               AS "spent"
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-tt.buyIn-tt.fee)/100.0	 								AS "net"
                        ,(CAST(SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0) - tt.buyin - tt.fee) AS BIGINT)/
                            CAST(SUM(tt.buyin+tt.fee) AS BIGINT))* 100.0                                                                    AS "roi"
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-(tt.buyin+tt.fee))/100.0
                         /(COUNT(1)-SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 0 END))               AS "profitPerTourney"
                  from TourneysPlayers tp
                       inner join Tourneys t        on  (t.id = tp.tourneyId)
                       inner join TourneyTypes tt   on  (tt.Id = t.tourneyTypeId)
                       inner join Sites s           on  (s.Id = tt.siteId)
                       inner join Players p         on  (p.Id = tp.playerId)
                  where tp.playerId in <nametest> <sitetest>
                  AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                                    OR t.startTime is NULL)
                  group by t.tourneyTypeId, s.name, p.name, tt.currency, tt.buyin, tt.fee
                         , tt.category, tt.limitType, tt.speed, tt.maxSeats, tt.knockout, tt.reEntry
                  order by t.tourneyTypeId
                          ,p.name
                          ,s.name"""
    elif db_server == "sqlite":
        query["tourneyPlayerDetailedStats"] = """
                  select s.name                                                                 AS siteName
                        ,tt.currency                                                            AS currency
                        ,(CASE
                            WHEN tt.currency = 'play' THEN tt.buyIn
                            ELSE tt.buyIn/100.0
                          END)                                                                  AS buyIn
                        ,tt.fee/100.0                                                           AS fee
                        ,tt.category                                                            AS category
                        ,tt.limitType                                                           AS limitType
                        ,tt.speed                                                                AS speed
                        ,tt.maxSeats                                                            AS maxSeats
							,tt.knockout                                                            AS knockout
							,tt.reEntry                                                             AS reEntry
                        ,p.name                                                                 AS playerName
                        ,t.tourneyTypeId                                                        AS tourneyTypeId
                        ,MAX(tp.playerId)                                                       AS playerId
                        ,COUNT(1)                                                               AS tourneyCount
                        ,SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END)                           AS unknownRank
                        ,(CAST(SUM(CASE WHEN winnings > 0 THEN 1 ELSE 0 END) AS REAL)/CAST(COUNT(1) AS REAL))*100                 AS itm
                        ,SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END)                              AS _1st
                        ,SUM(CASE WHEN rank = 2 THEN 1 ELSE 0 END)                              AS _2nd
                        ,SUM(CASE WHEN rank = 3 THEN 1 ELSE 0 END)                              AS _3rd
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0))/100.0              AS won
                        ,SUM(CASE
                               WHEN tt.currency = 'play' THEN tt.buyIn
                               ELSE (tt.buyIn+tt.fee)/100.0
                             END)                                                               AS spent
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-tt.buyIn-tt.fee)/100.0	 								AS net
                        ,(CAST(SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0) - tt.buyin - tt.fee) AS REAL)/
                            CAST(SUM(tt.buyin+tt.fee) AS REAL))* 100.0                                                                    AS roi
                        ,SUM(tp.winnings+COALESCE(tp.koCount*tt.koBounty,0)-(tt.buyin+tt.fee))/100.0/(COUNT(1)-SUM(CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END)) AS profitPerTourney
                  from TourneysPlayers tp
                       inner join Tourneys t        on  (t.id = tp.tourneyId)
                       inner join TourneyTypes tt   on  (tt.Id = t.tourneyTypeId)
                       inner join Sites s           on  (s.Id = tt.siteId)
                       inner join Players p         on  (p.Id = tp.playerId)
                  where tp.playerId in <nametest> <sitetest>
                  AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                                    OR t.startTime is NULL)
                  group by tourneyTypeId, playerName
                  order by tourneyTypeId
                          ,playerName
                          ,siteName"""

    return query

