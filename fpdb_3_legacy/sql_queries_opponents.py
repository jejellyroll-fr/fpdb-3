"""Head-to-head opponent report queries."""

from __future__ import annotations


def opponent_report_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific opponent aggregation query."""
    query: dict[str, str] = {}
    ####################################
    # Opponents Report (head-to-head vs hero)
    # Aggregates, per opponent, the hands played at the same table as the hero.
    # Percentages, danger and exploit heuristics are computed in Python from
    # the raw sums returned here. All aliases are lowercase so they work
    # uniformly across backends.
    ####################################
    if db_server == "mysql":
        query["opponentsReport"] = """
                 select  opp.playerId                                                  AS opp_id
                        ,p.name                                                        AS pname
                        ,count(1)                                                      AS hds
                        ,sum(hphero.totalProfit/(gt.bigBlind+0.0))                     AS hero_net_bb
                        ,sum(opp.totalProfit/(gt.bigBlind+0.0))                        AS opp_net_bb
                        ,sum(cast(opp.street0VPIChance as signed))                     AS vpip_opp
                        ,sum(cast(opp.street0VPI as signed))                           AS vpip
                        ,sum(cast(opp.street0AggrChance as signed))                    AS pfr_opp
                        ,sum(cast(opp.street0Aggr as signed))                          AS pfr
                        ,sum(cast(opp.street0_3Bchance as signed))                     AS tb_opp
                        ,sum(cast(opp.street0_3Bdone as signed))                       AS tb
                        ,sum(cast(opp.street0_FoldTo3Bchance as signed))               AS f3b_opp
                        ,sum(cast(opp.street0_FoldTo3Bdone as signed))                 AS f3b
                        ,sum(cast(opp.street1Seen as signed))                          AS saw_f
                        ,sum(cast(opp.sawShowdown as signed))                          AS sd
                        ,sum(cast(opp.street1CBChance as signed))                      AS cb_opp
                        ,sum(cast(opp.street1CBDone as signed))                        AS cb
                        ,sum(cast(opp.foldToStreet1CBChance as signed))                AS f_cb_opp
                        ,sum(cast(opp.foldToStreet1CBDone as signed))                  AS f_cb
                        ,sum(cast(opp.street2CBChance as signed))                      AS cb2_opp
                        ,sum(cast(opp.street2CBDone as signed))                        AS cb2
                        ,sum(cast(opp.foldToStreet2CBChance as signed))                AS f_cb2_opp
                        ,sum(cast(opp.foldToStreet2CBDone as signed))                  AS f_cb2
                        ,sum(cast(opp.street3CBChance as signed))                      AS cb3_opp
                        ,sum(cast(opp.street3CBDone as signed))                        AS cb3
                        ,sum(cast(opp.foldBbToStealChance as signed))                  AS bbsteal_opp
                        ,sum(cast(opp.foldedBbToSteal as signed))                      AS bbsteal_fold
                        ,sum(cast(opp.street3Aggr as signed))                          AS river_aggr
                        ,sum(cast(opp.street3Seen as signed))                          AS river_seen
                        ,sum(cast(opp.wonAtSD as signed))                              AS wmsd
                        ,sum(cast(opp.street1Aggr as signed)+cast(opp.street2Aggr as signed)+cast(opp.street3Aggr as signed))   AS postflop_aggr
                        ,sum(cast(opp.street1Seen as signed)+cast(opp.street2Seen as signed)+cast(opp.street3Seen as signed))   AS postflop_seen
                        ,max(h.startTime)                                              AS last_seen
                  from HandsPlayers hphero
                       inner join Hands h             on (h.id = hphero.handId)
                       inner join Gametypes gt        on (gt.id = h.gametypeId)
                       inner join Sites s             on (s.id = gt.siteId)
                       inner join HandsPlayers opp    on (opp.handId = hphero.handId and opp.playerId not in <player_test>)
                       inner join Players p           on (p.id = opp.playerId)
                  where hphero.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  <gtbigBlind_test>
                  and   date_format(h.startTime, '%Y-%m-%d %T') <datestest>
                  group by opp.playerId, p.name
                  having count(1) >= <minhands>
                  order by hds desc
                  limit <maxopponents>
                  """
    elif db_server == "postgresql":
        query["opponentsReport"] = """
                 select  opp.playerId                                                  AS opp_id
                        ,p.name                                                        AS pname
                        ,count(1)                                                      AS hds
                        ,sum(hphero.totalProfit/(gt.bigBlind+0.0))                     AS hero_net_bb
                        ,sum(opp.totalProfit/(gt.bigBlind+0.0))                        AS opp_net_bb
                        ,sum(cast(opp.street0VPIChance as integer))                    AS vpip_opp
                        ,sum(cast(opp.street0VPI as integer))                          AS vpip
                        ,sum(cast(opp.street0AggrChance as integer))                   AS pfr_opp
                        ,sum(cast(opp.street0Aggr as integer))                         AS pfr
                        ,sum(cast(opp.street0_3Bchance as integer))                    AS tb_opp
                        ,sum(cast(opp.street0_3Bdone as integer))                      AS tb
                        ,sum(cast(opp.street0_FoldTo3Bchance as integer))              AS f3b_opp
                        ,sum(cast(opp.street0_FoldTo3Bdone as integer))                AS f3b
                        ,sum(cast(opp.street1Seen as integer))                         AS saw_f
                        ,sum(cast(opp.sawShowdown as integer))                         AS sd
                        ,sum(cast(opp.street1CBChance as integer))                     AS cb_opp
                        ,sum(cast(opp.street1CBDone as integer))                       AS cb
                        ,sum(cast(opp.foldToStreet1CBChance as integer))               AS f_cb_opp
                        ,sum(cast(opp.foldToStreet1CBDone as integer))                 AS f_cb
                        ,sum(cast(opp.street2CBChance as integer))                     AS cb2_opp
                        ,sum(cast(opp.street2CBDone as integer))                       AS cb2
                        ,sum(cast(opp.foldToStreet2CBChance as integer))               AS f_cb2_opp
                        ,sum(cast(opp.foldToStreet2CBDone as integer))                 AS f_cb2
                        ,sum(cast(opp.street3CBChance as integer))                     AS cb3_opp
                        ,sum(cast(opp.street3CBDone as integer))                       AS cb3
                        ,sum(cast(opp.foldBbToStealChance as integer))                 AS bbsteal_opp
                        ,sum(cast(opp.foldedBbToSteal as integer))                     AS bbsteal_fold
                        ,sum(cast(opp.street3Aggr as integer))                         AS river_aggr
                        ,sum(cast(opp.street3Seen as integer))                         AS river_seen
                        ,sum(cast(opp.wonAtSD as integer))                             AS wmsd
                        ,sum(cast(opp.street1Aggr as integer)+cast(opp.street2Aggr as integer)+cast(opp.street3Aggr as integer))   AS postflop_aggr
                        ,sum(cast(opp.street1Seen as integer)+cast(opp.street2Seen as integer)+cast(opp.street3Seen as integer))   AS postflop_seen
                        ,max(h.startTime)                                              AS last_seen
                  from HandsPlayers hphero
                       inner join Hands h             on (h.id = hphero.handId)
                       inner join Gametypes gt        on (gt.id = h.gametypeId)
                       inner join Sites s             on (s.id = gt.siteId)
                       inner join HandsPlayers opp    on (opp.handId = hphero.handId and opp.playerId not in <player_test>)
                       inner join Players p           on (p.id = opp.playerId)
                  where hphero.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  <gtbigBlind_test>
                  and   to_char(h.startTime, 'YYYY-MM-DD HH24:MI:SS') <datestest>
                  group by opp.playerId, p.name
                  having count(1) >= <minhands>
                  order by hds desc
                  limit <maxopponents>
                  """
    elif db_server == "sqlite":
        query["opponentsReport"] = """
                 select  opp.playerId                                                  AS opp_id
                        ,p.name                                                        AS pname
                        ,count(1)                                                      AS hds
                        ,sum(hphero.totalProfit/(gt.bigBlind+0.0))                     AS hero_net_bb
                        ,sum(opp.totalProfit/(gt.bigBlind+0.0))                        AS opp_net_bb
                        ,sum(opp.street0VPIChance)                                     AS vpip_opp
                        ,sum(opp.street0VPI)                                           AS vpip
                        ,sum(opp.street0AggrChance)                                    AS pfr_opp
                        ,sum(opp.street0Aggr)                                          AS pfr
                        ,sum(opp.street0_3Bchance)                                     AS tb_opp
                        ,sum(opp.street0_3Bdone)                                       AS tb
                        ,sum(opp.street0_FoldTo3Bchance)                               AS f3b_opp
                        ,sum(opp.street0_FoldTo3Bdone)                                 AS f3b
                        ,sum(opp.street1Seen)                                          AS saw_f
                        ,sum(opp.sawShowdown)                                          AS sd
                        ,sum(opp.street1CBChance)                                      AS cb_opp
                        ,sum(opp.street1CBDone)                                        AS cb
                        ,sum(opp.foldToStreet1CBChance)                                AS f_cb_opp
                        ,sum(opp.foldToStreet1CBDone)                                  AS f_cb
                        ,sum(opp.street2CBChance)                                      AS cb2_opp
                        ,sum(opp.street2CBDone)                                        AS cb2
                        ,sum(opp.foldToStreet2CBChance)                                AS f_cb2_opp
                        ,sum(opp.foldToStreet2CBDone)                                  AS f_cb2
                        ,sum(opp.street3CBChance)                                      AS cb3_opp
                        ,sum(opp.street3CBDone)                                        AS cb3
                        ,sum(opp.foldBbToStealChance)                                  AS bbsteal_opp
                        ,sum(opp.foldedBbToSteal)                                      AS bbsteal_fold
                        ,sum(opp.street3Aggr)                                          AS river_aggr
                        ,sum(opp.street3Seen)                                          AS river_seen
                        ,sum(opp.wonAtSD)                                              AS wmsd
                        ,sum(opp.street1Aggr+opp.street2Aggr+opp.street3Aggr)          AS postflop_aggr
                        ,sum(opp.street1Seen+opp.street2Seen+opp.street3Seen)          AS postflop_seen
                        ,max(h.startTime)                                              AS last_seen
                  from HandsPlayers hphero
                       inner join Hands h             on (h.id = hphero.handId)
                       inner join Gametypes gt        on (gt.id = h.gametypeId)
                       inner join Sites s             on (s.id = gt.siteId)
                       inner join HandsPlayers opp    on (opp.handId = hphero.handId and opp.playerId not in <player_test>)
                       inner join Players p           on (p.id = opp.playerId)
                  where hphero.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  <gtbigBlind_test>
                  and   datetime(h.startTime) <datestest>
                  group by opp.playerId, p.name
                  having count(1) >= <minhands>
                  order by hds desc
                  limit <maxopponents>
                  """

    return query

