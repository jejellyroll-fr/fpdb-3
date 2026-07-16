"""Detailed cash-player report queries."""

from __future__ import annotations


def player_detailed_report_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific detailed cash-player query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["playerDetailedStats"] = """
                 select  <hgametypeId>                                                          AS hgametypeid
                        ,<playerName>                                                           AS pname
                        ,gt.base
                        ,gt.category
                        ,upper(gt.limitType)                                                    AS limittype
                        ,s.name
                        ,min(gt.bigBlind)                                                       AS minbigblind
                        ,max(gt.bigBlind)                                                       AS maxbigblind
                        ,gt.ante                                                                AS ante
                        ,gt.currency                                                            AS currency
                        /*,<hcgametypeId>                                                         AS gtid*/
                        ,<position>                                                             AS plposition
                        ,gt.fast                                                                AS fast
                        ,count(1)                                                               AS n
                        ,case when sum(cast(hp.street0VPIChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0VPI as SIGNED))/sum(cast(hp.street0VPIChance as SIGNED))
                         end                                                                    AS vpip
                        ,case when sum(cast(hp.street0AggrChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0Aggr as SIGNED))/sum(cast(hp.street0AggrChance as SIGNED))
                         end                                                                    AS pfr
                        ,case when sum(cast(hp.street0CalledRaiseChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0CalledRaiseDone as SIGNED))/sum(cast(hp.street0CalledRaiseChance as SIGNED))
                         end                                                                    AS car0
                        ,case when sum(cast(hp.street0_3Bchance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_3Bdone as SIGNED))/sum(cast(hp.street0_3Bchance as SIGNED))
                         end                                                                    AS pf3
                        ,case when sum(cast(hp.street1_3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_3BDone as SIGNED))/sum(cast(hp.street1_3BChance as SIGNED))
                         end                                                                    AS fl3
                        ,case when sum(cast(hp.street2_3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_3BDone as SIGNED))/sum(cast(hp.street2_3BChance as SIGNED))
                         end                                                                    AS tn3
                        ,case when sum(cast(hp.street3_3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_3BDone as SIGNED))/sum(cast(hp.street3_3BChance as SIGNED))
                         end                                                                    AS rv3
                        ,case when sum(cast(hp.street1_FoldTo3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_FoldTo3BDone as SIGNED))/sum(cast(hp.street1_FoldTo3BChance as SIGNED))
                         end                                                                    AS ff3
                        ,case when sum(cast(hp.street2_FoldTo3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_FoldTo3BDone as SIGNED))/sum(cast(hp.street2_FoldTo3BChance as SIGNED))
                         end                                                                    AS ft3
                        ,case when sum(cast(hp.street3_FoldTo3BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_FoldTo3BDone as SIGNED))/sum(cast(hp.street3_FoldTo3BChance as SIGNED))
                         end                                                                    AS fr3
                        ,case when sum(cast(hp.street1_4BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_4BDone as SIGNED))/sum(cast(hp.street1_4BChance as SIGNED))
                         end                                                                    AS fl4
                        ,case when sum(cast(hp.street2_4BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_4BDone as SIGNED))/sum(cast(hp.street2_4BChance as SIGNED))
                         end                                                                    AS tn4
                        ,case when sum(cast(hp.street3_4BChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_4BDone as SIGNED))/sum(cast(hp.street3_4BChance as SIGNED))
                         end                                                                    AS rv4
                        ,case when sum(cast(hp.street1OpenChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street1OpenDone as SIGNED))/sum(cast(hp.street1OpenChance as SIGNED))
                         end                                                                    AS flopen
                        ,case when sum(cast(hp.street2OpenChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street2OpenDone as SIGNED))/sum(cast(hp.street2OpenChance as SIGNED))
                         end                                                                    AS tnopen
                        ,case when sum(cast(hp.street3OpenChance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street3OpenDone as SIGNED))/sum(cast(hp.street3OpenChance as SIGNED))
                         end                                                                    AS rvopen
                        ,case when sum(cast(hp.street0_4Bchance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_4Bdone as SIGNED))/sum(cast(hp.street0_4Bchance as SIGNED))
                         end                                                                    AS pf4
                        ,case when sum(cast(hp.street0_FoldTo3Bchance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo3Bdone as SIGNED))/sum(cast(hp.street0_FoldTo3Bchance as SIGNED))
                         end                                                                    AS pff3
                        ,case when sum(cast(hp.street0_FoldTo4Bchance as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo4Bdone as SIGNED))/sum(cast(hp.street0_FoldTo4Bchance as SIGNED))
                         end                                                                    AS pff4

                        ,case when sum(cast(hp.raiseFirstInChance as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.raisedFirstIn as SIGNED)) /
                                   sum(cast(hp.raiseFirstInChance as SIGNED))
                         end                                                                    AS rfi
                        ,case when sum(cast(hp.raiseToStealChance as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.raiseToStealDone as SIGNED)) /
                                   sum(cast(hp.raiseToStealChance as SIGNED))
                         end                                                                    AS raisetosteal
                        ,case when sum(cast(hp.foldBbToStealChance as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedBbToSteal as SIGNED)) /
                                   sum(cast(hp.foldBbToStealChance as SIGNED))
                         end                                                                    AS foldbbtosteal
                        ,case when sum(cast(hp.foldSbToStealChance as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedSbToSteal as SIGNED)) /
                                   sum(cast(hp.foldSbToStealChance as SIGNED))
                         end                                                                    AS foldsbtosteal
                        ,case when sum(cast(hp.stealChance as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.stealDone as SIGNED)) /
                                   sum(cast(hp.stealChance as SIGNED))
                         end                                                                    AS steals
                        ,case when sum(cast(hp.stealDone as SIGNED)) = 0 then -999
                              else 100.0 * sum(cast(hp.success_Steal as SIGNED)) /
                                   sum(cast(hp.stealDone as SIGNED))
                         end                                                                    AS suc_steal
                        ,100.0*sum(cast(hp.street1Seen as SIGNED))/count(1)            AS saw_f
                        ,100.0*sum(cast(hp.sawShowdown as SIGNED))/count(1)            AS sawsd
                        ,case when sum(cast(hp.street1Seen as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.wonWhenSeenStreet1 as SIGNED))/sum(cast(hp.street1Seen as SIGNED))
                         end                                                                    AS wmsf
                        ,case when sum(cast(hp.street1Seen as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.sawShowdown as SIGNED))/sum(cast(hp.street1Seen as SIGNED))
                         end                                                                    AS wtsdwsf
                        ,case when sum(cast(hp.sawShowdown as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.wonAtSD as SIGNED))/sum(cast(hp.sawShowdown as SIGNED))
                         end                                                                    AS wmsd
                        ,case when sum(cast(hp.street1Seen as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street1Aggr as SIGNED))/sum(cast(hp.street1Seen as SIGNED))
                         end                                                                    AS flafq
                        ,case when sum(cast(hp.street2Seen as SIGNED)) = 0 then -999
                              else 100.0*sum(cast(hp.street2Aggr as SIGNED))/sum(cast(hp.street2Seen as SIGNED))
                         end                                                                    AS tuafq
                        ,case when sum(cast(hp.street3Seen as SIGNED)) = 0 then -999
                             else 100.0*sum(cast(hp.street3Aggr as SIGNED))/sum(cast(hp.street3Seen as SIGNED))
                         end                                                                    AS rvafq
                        ,case when sum(cast(hp.street1Seen as SIGNED))+sum(cast(hp.street2Seen as SIGNED))+sum(cast(hp.street3Seen as SIGNED)) = 0 then -999
                             else 100.0*(sum(cast(hp.street1Aggr as SIGNED))+sum(cast(hp.street2Aggr as SIGNED))+sum(cast(hp.street3Aggr as SIGNED)))
                                      /(sum(cast(hp.street1Seen as SIGNED))+sum(cast(hp.street2Seen as SIGNED))+sum(cast(hp.street3Seen as SIGNED)))
                         end                                                                    AS pofafq
                        ,case when sum(cast(hp.street1Calls as SIGNED))+ sum(cast(hp.street2Calls as SIGNED))+ sum(cast(hp.street3Calls as SIGNED))+ sum(cast(hp.street4Calls as SIGNED)) = 0 then -999
                             else (sum(cast(hp.street1Aggr as SIGNED)) + sum(cast(hp.street2Aggr as SIGNED)) + sum(cast(hp.street3Aggr as SIGNED)) + sum(cast(hp.street4Aggr as SIGNED)))
                                 /(0.0+sum(cast(hp.street1Calls as SIGNED))+ sum(cast(hp.street2Calls as SIGNED))+ sum(cast(hp.street3Calls as SIGNED))+ sum(cast(hp.street4Calls as SIGNED)))
                         end                                                                    AS aggfac
                        ,100.0*(sum(cast(hp.street1Aggr as SIGNED)) + sum(cast(hp.street2Aggr as SIGNED)) + sum(cast(hp.street3Aggr as SIGNED)) + sum(cast(hp.street4Aggr as SIGNED)))
                                   / ((sum(cast(hp.foldToOtherRaisedStreet1 as SIGNED))+ sum(cast(hp.foldToOtherRaisedStreet2 as SIGNED))+ sum(cast(hp.foldToOtherRaisedStreet3 as SIGNED))+ sum(cast(hp.foldToOtherRaisedStreet4 as SIGNED))) +
                                   (sum(cast(hp.street1Calls as SIGNED))+ sum(cast(hp.street2Calls as SIGNED))+ sum(cast(hp.street3Calls as SIGNED))+ sum(cast(hp.street4Calls as SIGNED))) +
                                   (sum(cast(hp.street1Aggr as SIGNED)) + sum(cast(hp.street2Aggr as SIGNED)) + sum(cast(hp.street3Aggr as SIGNED)) + sum(cast(hp.street4Aggr as SIGNED))) )
                                                                                                AS aggfrq
                        ,100.0*(sum(cast(hp.street1CBDone as SIGNED)) + sum(cast(hp.street2CBDone as SIGNED)) + sum(cast(hp.street3CBDone as SIGNED)) + sum(cast(hp.street4CBDone as SIGNED)))
                                   / (sum(cast(hp.street1CBChance as SIGNED))+ sum(cast(hp.street2CBChance as SIGNED))+ sum(cast(hp.street3CBChance as SIGNED))+ sum(cast(hp.street4CBChance as SIGNED)))
                                                                                                AS conbet
                        ,sum(hp.totalProfit)/100.0                                              AS net
                        ,sum(hp.rake)/100.0                                                     AS rake
                        ,100.0*avg(hp.totalProfit/(gt.bigBlind+0.0))                            AS bbper100
                        ,avg(hp.totalProfit)/100.0                                              AS profitperhand
                        ,100.0*avg((hp.totalProfit+hp.rake)/(gt.bigBlind+0.0))                  AS bb100xr
                        ,avg((hp.totalProfit+hp.rake)/100.0)                                    AS profhndxr
                        ,avg(h.seats+0.0)                                                       AS avgseats
                        ,variance(hp.totalProfit/100.0)                                         AS variance
                        ,sqrt(variance(hp.totalProfit/100.0))                                                         AS stddev
                  from HandsPlayers hp
                       inner join Hands h       on  (h.id = hp.handId)
                       inner join Gametypes gt  on  (gt.Id = h.gametypeId)
                       inner join Sites s       on  (s.Id = gt.siteId)
                       inner join Players p     on  (p.Id = hp.playerId)
                  where hp.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  and   h.seats <seats_test>
                  <flagtest>
                  <cardstest>
                  <gtbigBlind_test>
                  and   date_format(h.startTime, '%Y-%m-%d %T') <datestest>
                  group by hgametypeId
                          ,pname
                          ,gt.base
                          ,gt.category
                          <groupbyseats>
                          ,plposition
                          ,upper(gt.limitType)
                          ,gt.fast
                          ,s.name
                  having 1 = 1 <havingclause>
                  order by pname
                          ,gt.base
                          ,gt.category
                          <orderbyseats>
                          ,case <position> when 'B' then 'B'
                                           when 'S' then 'S'
                                           else concat('Z', <position>)
                           end
                          <orderbyhgametypeId>
                          ,upper(gt.limitType) desc
                          ,maxbigblind desc
                          ,gt.fast
                          ,s.name
                  """
    elif db_server == "postgresql":
        query["playerDetailedStats"] = """
                 select  <hgametypeId>                                                          AS hgametypeid
                        ,<playerName>                                                           AS pname
                        ,gt.base
                        ,gt.category
                        ,upper(gt.limitType)                                                    AS limittype
                        ,s.name
                        ,min(gt.bigBlind)                                                       AS minbigblind
                        ,max(gt.bigBlind)                                                       AS maxbigblind
                        ,gt.ante                                                                AS ante
                        ,gt.currency                                                            AS currency
                        /*,<hcgametypeId>                                                       AS gtid*/
                        ,<position>                                                             AS plposition
                        ,gt.fast                                                                AS fast
                        ,count(1)                                                               AS n
                        ,case when sum(cast(hp.street0VPIChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0VPI as <signed>integer))/sum(cast(hp.street0VPIChance as <signed>integer))
                         end                                                                    AS vpip
                        ,case when sum(cast(hp.street0AggrChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0Aggr as <signed>integer))/sum(cast(hp.street0AggrChance as <signed>integer))
                         end                                                                    AS pfr
                        ,case when sum(cast(hp.street0CalledRaiseChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0CalledRaiseDone as <signed>integer))/sum(cast(hp.street0CalledRaiseChance as <signed>integer))
                         end                                                                    AS car0
                        ,case when sum(cast(hp.street0_3Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_3Bdone as <signed>integer))/sum(cast(hp.street0_3Bchance as <signed>integer))
                         end                                                                    AS pf3
                        ,case when sum(cast(hp.street1_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_3BDone as <signed>integer))/sum(cast(hp.street1_3BChance as <signed>integer))
                         end                                                                    AS fl3
                        ,case when sum(cast(hp.street2_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_3BDone as <signed>integer))/sum(cast(hp.street2_3BChance as <signed>integer))
                         end                                                                    AS tn3
                        ,case when sum(cast(hp.street3_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_3BDone as <signed>integer))/sum(cast(hp.street3_3BChance as <signed>integer))
                         end                                                                    AS rv3
                        ,case when sum(cast(hp.street1_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_FoldTo3BDone as <signed>integer))/sum(cast(hp.street1_FoldTo3BChance as <signed>integer))
                         end                                                                    AS ff3
                        ,case when sum(cast(hp.street2_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_FoldTo3BDone as <signed>integer))/sum(cast(hp.street2_FoldTo3BChance as <signed>integer))
                         end                                                                    AS ft3
                        ,case when sum(cast(hp.street3_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_FoldTo3BDone as <signed>integer))/sum(cast(hp.street3_FoldTo3BChance as <signed>integer))
                         end                                                                    AS fr3
                        ,case when sum(cast(hp.street1_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_4BDone as <signed>integer))/sum(cast(hp.street1_4BChance as <signed>integer))
                         end                                                                    AS fl4
                        ,case when sum(cast(hp.street2_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_4BDone as <signed>integer))/sum(cast(hp.street2_4BChance as <signed>integer))
                         end                                                                    AS tn4
                        ,case when sum(cast(hp.street3_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_4BDone as <signed>integer))/sum(cast(hp.street3_4BChance as <signed>integer))
                         end                                                                    AS rv4
                        ,case when sum(cast(hp.street1OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1OpenDone as <signed>integer))/sum(cast(hp.street1OpenChance as <signed>integer))
                         end                                                                    AS flopen
                        ,case when sum(cast(hp.street2OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2OpenDone as <signed>integer))/sum(cast(hp.street2OpenChance as <signed>integer))
                         end                                                                    AS tnopen
                        ,case when sum(cast(hp.street3OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3OpenDone as <signed>integer))/sum(cast(hp.street3OpenChance as <signed>integer))
                         end                                                                    AS rvopen
                        ,case when sum(cast(hp.street0_4Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_4Bdone as <signed>integer))/sum(cast(hp.street0_4Bchance as <signed>integer))
                         end                                                                    AS pf4
                        ,case when sum(cast(hp.street0_FoldTo3Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo3Bdone as <signed>integer))/sum(cast(hp.street0_FoldTo3Bchance as <signed>integer))
                         end                                                                    AS pff3
                        ,case when sum(cast(hp.street0_FoldTo4Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo4Bdone as <signed>integer))/sum(cast(hp.street0_FoldTo4Bchance as <signed>integer))
                         end                                                                    AS pff4
                        ,case when sum(cast(hp.raiseFirstInChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.raisedFirstIn as <signed>integer)) /
                                   sum(cast(hp.raiseFirstInChance as <signed>integer))
                         end                                                                    AS rfi
                        ,case when sum(cast(hp.raiseToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.raiseToStealDone as <signed>integer)) /
                                   sum(cast(hp.raiseToStealChance as <signed>integer))
                         end                                                                    AS raisetosteal
                        ,case when sum(cast(hp.foldBbToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedBbToSteal as <signed>integer)) /
                                   sum(cast(hp.foldBbToStealChance as <signed>integer))
                         end                                                                    AS foldbbtosteal
                        ,case when sum(cast(hp.foldSbToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedSbToSteal as <signed>integer)) /
                                   sum(cast(hp.foldSbToStealChance as <signed>integer))
                         end                                                                    AS foldsbtosteal
                        ,case when sum(cast(hp.stealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.stealDone as <signed>integer)) /
                                   sum(cast(hp.stealChance as <signed>integer))
                         end                                                                    AS steals
                        ,case when sum(cast(hp.stealDone as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.success_Steal as <signed>integer)) /
                                   sum(cast(hp.stealDone as <signed>integer))
                         end                                                                    AS suc_steal
                        ,100.0*sum(cast(hp.street1Seen as <signed>integer))/count(1)            AS saw_f
                        ,100.0*sum(cast(hp.sawShowdown as <signed>integer))/count(1)            AS sawsd
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.wonWhenSeenStreet1 as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS wmsf
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.sawShowdown as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS wtsdwsf
                        ,case when sum(cast(hp.sawShowdown as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.wonAtSD as <signed>integer))/sum(cast(hp.sawShowdown as <signed>integer))
                         end                                                                    AS wmsd
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1Aggr as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS flafq
                        ,case when sum(cast(hp.street2Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2Aggr as <signed>integer))/sum(cast(hp.street2Seen as <signed>integer))
                         end                                                                    AS tuafq
                        ,case when sum(cast(hp.street3Seen as <signed>integer)) = 0 then -999
                             else 100.0*sum(cast(hp.street3Aggr as <signed>integer))/sum(cast(hp.street3Seen as <signed>integer))
                         end                                                                    AS rvafq
                        ,case when sum(cast(hp.street1Seen as <signed>integer))+sum(cast(hp.street2Seen as <signed>integer))+sum(cast(hp.street3Seen as <signed>integer)) = 0 then -999
                             else 100.0*(sum(cast(hp.street1Aggr as <signed>integer))+sum(cast(hp.street2Aggr as <signed>integer))+sum(cast(hp.street3Aggr as <signed>integer)))
                                      /(sum(cast(hp.street1Seen as <signed>integer))+sum(cast(hp.street2Seen as <signed>integer))+sum(cast(hp.street3Seen as <signed>integer)))
                         end                                                                    AS pofafq
                        ,case when sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer)) = 0 then -999
                             else (sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer)))
                                 /(0.0+sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer)))
                         end                                                                    AS aggfac
                        ,case when
                            sum(cast(hp.foldToOtherRaisedStreet1 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet2 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet3 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet4 as <signed>integer))+
                            sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer))+
                            sum(cast(hp.street1Aggr as <signed>integer))+ sum(cast(hp.street2Aggr as <signed>integer))+ sum(cast(hp.street3Aggr as <signed>integer))+ sum(cast(hp.street4Aggr as <signed>integer))
                            = 0 then -999
                        else
                        100.0*(sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer)))
                                   / ((sum(cast(hp.foldToOtherRaisedStreet1 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet2 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet3 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet4 as <signed>integer))) +
                                   (sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer))) +
                                   (sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer))) )
                          end                                                                   AS aggfrq
                        ,case when
                            sum(cast(hp.street1CBChance as <signed>integer))+
                            sum(cast(hp.street2CBChance as <signed>integer))+
                            sum(cast(hp.street3CBChance as <signed>integer))+
                            sum(cast(hp.street4CBChance as <signed>integer)) = 0 then -999
                        else
                         100.0*(sum(cast(hp.street1CBDone as <signed>integer)) + sum(cast(hp.street2CBDone as <signed>integer)) + sum(cast(hp.street3CBDone as <signed>integer)) + sum(cast(hp.street4CBDone as <signed>integer)))
                                   / (sum(cast(hp.street1CBChance as <signed>integer))+ sum(cast(hp.street2CBChance as <signed>integer))+ sum(cast(hp.street3CBChance as <signed>integer))+ sum(cast(hp.street4CBChance as <signed>integer)))
                        end                                                                     AS conbet
                        ,sum(hp.totalProfit)/100.0                                              AS net
                        ,sum(hp.rake)/100.0                                                     AS rake
                        ,100.0*avg(hp.totalProfit/(gt.bigBlind+0.0))                            AS bbper100
                        ,avg(hp.totalProfit)/100.0                                              AS profitperhand
                        ,100.0*avg((hp.totalProfit+hp.rake)/(gt.bigBlind+0.0))                  AS bb100xr
                        ,avg((hp.totalProfit+hp.rake)/100.0)                                    AS profhndxr
                        ,avg(h.seats+0.0)                                                       AS avgseats
                        ,variance(hp.totalProfit/100.0)                                         AS variance
                        ,sqrt(variance(hp.totalProfit/100.0))                                                         AS stddev
                  from HandsPlayers hp
                       inner join Hands h       on  (h.id = hp.handId)
                       inner join Gametypes gt  on  (gt.Id = h.gametypeId)
                       inner join Sites s       on  (s.Id = gt.siteId)
                       inner join Players p     on  (p.Id = hp.playerId)
                  where hp.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  and   h.seats <seats_test>
                  <flagtest>
                  <cardstest>
                  <gtbigBlind_test>
                  and   to_char(h.startTime, 'YYYY-MM-DD HH24:MI:SS') <datestest>
                  group by hgametypeId
                          ,pname
                          ,gt.base
                          ,gt.category
                          ,gt.ante
                          ,gt.currency
                          <groupbyseats>
                          ,plposition
                          ,upper(gt.limitType)
                          ,gt.fast
                          ,s.name
                  having 1 = 1 <havingclause>
                  order by pname
                          ,gt.base
                          ,gt.category
                          <orderbyseats>
                          ,case <position> when 'B' then 'B'
                                           when 'S' then 'S'
                                           when '0' then 'Y'
                                           else 'Z'||<position>
                           end
                          <orderbyhgametypeId>
                          ,upper(gt.limitType) desc
                          ,maxbigblind desc
                          ,gt.fast
                          ,s.name
                  """
    elif db_server == "sqlite":
        query["playerDetailedStats"] = """
                 select  <hgametypeId>                                                          AS hgametypeid
                        ,<playerName>                                                           AS pname
                        ,gt.base
                        ,gt.category                                                            AS category
                        ,upper(gt.limitType)                                                    AS limittype
                        ,s.name                                                                 AS name
                        ,min(gt.bigBlind)                                                       AS minbigblind
                        ,max(gt.bigBlind)                                                       AS maxbigblind
                        ,gt.ante                                                                AS ante
                        ,gt.currency                                                            AS currency
                        /*,<hcgametypeId>                                                       AS gtid*/
                        ,<position>                                                             AS plposition
                        ,gt.fast                                                                AS fast
                        ,count(1)                                                               AS n
                        ,case when sum(cast(hp.street0VPIChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0VPI as <signed>integer))/sum(cast(hp.street0VPIChance as <signed>integer))
                         end                                                                    AS vpip
                        ,case when sum(cast(hp.street0AggrChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0Aggr as <signed>integer))/sum(cast(hp.street0AggrChance as <signed>integer))
                         end                                                                    AS pfr
                        ,case when sum(cast(hp.street0CalledRaiseChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0CalledRaiseDone as <signed>integer))/sum(cast(hp.street0CalledRaiseChance as <signed>integer))
                         end                                                                    AS car0
                        ,case when sum(cast(hp.street0_3Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_3Bdone as <signed>integer))/sum(cast(hp.street0_3Bchance as <signed>integer))
                         end                                                                    AS pf3
                        ,case when sum(cast(hp.street1_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_3BDone as <signed>integer))/sum(cast(hp.street1_3BChance as <signed>integer))
                         end                                                                    AS fl3
                        ,case when sum(cast(hp.street2_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_3BDone as <signed>integer))/sum(cast(hp.street2_3BChance as <signed>integer))
                         end                                                                    AS tn3
                        ,case when sum(cast(hp.street3_3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_3BDone as <signed>integer))/sum(cast(hp.street3_3BChance as <signed>integer))
                         end                                                                    AS rv3
                        ,case when sum(cast(hp.street1_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_FoldTo3BDone as <signed>integer))/sum(cast(hp.street1_FoldTo3BChance as <signed>integer))
                         end                                                                    AS ff3
                        ,case when sum(cast(hp.street2_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_FoldTo3BDone as <signed>integer))/sum(cast(hp.street2_FoldTo3BChance as <signed>integer))
                         end                                                                    AS ft3
                        ,case when sum(cast(hp.street3_FoldTo3BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_FoldTo3BDone as <signed>integer))/sum(cast(hp.street3_FoldTo3BChance as <signed>integer))
                         end                                                                    AS fr3
                        ,case when sum(cast(hp.street1_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1_4BDone as <signed>integer))/sum(cast(hp.street1_4BChance as <signed>integer))
                         end                                                                    AS fl4
                        ,case when sum(cast(hp.street2_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2_4BDone as <signed>integer))/sum(cast(hp.street2_4BChance as <signed>integer))
                         end                                                                    AS tn4
                        ,case when sum(cast(hp.street3_4BChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3_4BDone as <signed>integer))/sum(cast(hp.street3_4BChance as <signed>integer))
                         end                                                                    AS rv4
                        ,case when sum(cast(hp.street1OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1OpenDone as <signed>integer))/sum(cast(hp.street1OpenChance as <signed>integer))
                         end                                                                    AS flopen
                        ,case when sum(cast(hp.street2OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2OpenDone as <signed>integer))/sum(cast(hp.street2OpenChance as <signed>integer))
                         end                                                                    AS tnopen
                        ,case when sum(cast(hp.street3OpenChance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street3OpenDone as <signed>integer))/sum(cast(hp.street3OpenChance as <signed>integer))
                         end                                                                    AS rvopen
                        ,case when sum(cast(hp.street0_4Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_4Bdone as <signed>integer))/sum(cast(hp.street0_4Bchance as <signed>integer))
                         end                                                                    AS pf4
                        ,case when sum(cast(hp.street0_FoldTo3Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo3Bdone as <signed>integer))/sum(cast(hp.street0_FoldTo3Bchance as <signed>integer))
                         end                                                                    AS pff3
                        ,case when sum(cast(hp.street0_FoldTo4Bchance as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street0_FoldTo4Bdone as <signed>integer))/sum(cast(hp.street0_FoldTo4Bchance as <signed>integer))
                         end                                                                    AS pff4
                        ,case when sum(cast(hp.raiseFirstInChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.raisedFirstIn as <signed>integer)) /
                                   sum(cast(hp.raiseFirstInChance as <signed>integer))
                         end                                                                    AS rfi
                        ,case when sum(cast(hp.raiseToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.raiseToStealDone as <signed>integer)) /
                                   sum(cast(hp.raiseToStealChance as <signed>integer))
                         end                                                                    AS raisetosteal
                        ,case when sum(cast(hp.foldBbToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedBbToSteal as <signed>integer)) /
                                   sum(cast(hp.foldBbToStealChance as <signed>integer))
                         end                                                                    AS foldbbtosteal
                        ,case when sum(cast(hp.foldSbToStealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.foldedSbToSteal as <signed>integer)) /
                                   sum(cast(hp.foldSbToStealChance as <signed>integer))
                         end                                                                    AS foldsbtosteal
                        ,case when sum(cast(hp.stealChance as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.stealDone as <signed>integer)) /
                                   sum(cast(hp.stealChance as <signed>integer))
                         end                                                                    AS steals
                        ,case when sum(cast(hp.stealDone as <signed>integer)) = 0 then -999
                              else 100.0 * sum(cast(hp.success_Steal as <signed>integer)) /
                                   sum(cast(hp.stealDone as <signed>integer))
                         end                                                                    AS suc_steal
                        ,100.0*sum(cast(hp.street1Seen as <signed>integer))/count(1)            AS saw_f
                        ,100.0*sum(cast(hp.sawShowdown as <signed>integer))/count(1)            AS sawsd
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.wonWhenSeenStreet1 as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS wmsf
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.sawShowdown as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS wtsdwsf
                        ,case when sum(cast(hp.sawShowdown as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.wonAtSD as <signed>integer))/sum(cast(hp.sawShowdown as <signed>integer))
                         end                                                                    AS wmsd
                        ,case when sum(cast(hp.street1Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street1Aggr as <signed>integer))/sum(cast(hp.street1Seen as <signed>integer))
                         end                                                                    AS flafq
                        ,case when sum(cast(hp.street2Seen as <signed>integer)) = 0 then -999
                              else 100.0*sum(cast(hp.street2Aggr as <signed>integer))/sum(cast(hp.street2Seen as <signed>integer))
                         end                                                                    AS tuafq
                        ,case when sum(cast(hp.street3Seen as <signed>integer)) = 0 then -999
                             else 100.0*sum(cast(hp.street3Aggr as <signed>integer))/sum(cast(hp.street3Seen as <signed>integer))
                         end                                                                    AS rvafq
                        ,case when sum(cast(hp.street1Seen as <signed>integer))+sum(cast(hp.street2Seen as <signed>integer))+sum(cast(hp.street3Seen as <signed>integer)) = 0 then -999
                             else 100.0*(sum(cast(hp.street1Aggr as <signed>integer))+sum(cast(hp.street2Aggr as <signed>integer))+sum(cast(hp.street3Aggr as <signed>integer)))
                                      /(sum(cast(hp.street1Seen as <signed>integer))+sum(cast(hp.street2Seen as <signed>integer))+sum(cast(hp.street3Seen as <signed>integer)))
                         end                                                                    AS pofafq
                        ,case when sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer)) = 0 then -999
                             else (sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer)))
                                 /(0.0+sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer)))
                         end                                                                    AS aggfac
                        ,100.0*(sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer)))
                                   / ((sum(cast(hp.foldToOtherRaisedStreet1 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet2 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet3 as <signed>integer))+ sum(cast(hp.foldToOtherRaisedStreet4 as <signed>integer))) +
                                   (sum(cast(hp.street1Calls as <signed>integer))+ sum(cast(hp.street2Calls as <signed>integer))+ sum(cast(hp.street3Calls as <signed>integer))+ sum(cast(hp.street4Calls as <signed>integer))) +
                                   (sum(cast(hp.street1Aggr as <signed>integer)) + sum(cast(hp.street2Aggr as <signed>integer)) + sum(cast(hp.street3Aggr as <signed>integer)) + sum(cast(hp.street4Aggr as <signed>integer))) )
                                                                                                AS aggfrq
                        ,100.0*(sum(cast(hp.street1CBDone as <signed>integer)) + sum(cast(hp.street2CBDone as <signed>integer)) + sum(cast(hp.street3CBDone as <signed>integer)) + sum(cast(hp.street4CBDone as <signed>integer)))
                                   / (sum(cast(hp.street1CBChance as <signed>integer))+ sum(cast(hp.street2CBChance as <signed>integer))+ sum(cast(hp.street3CBChance as <signed>integer))+ sum(cast(hp.street4CBChance as <signed>integer)))
                                                                                                AS conbet
                        ,sum(hp.totalProfit)/100.0                                              AS net
                        ,sum(hp.rake)/100.0                                                     AS rake
                        ,100.0*avg(hp.totalProfit/(gt.bigBlind+0.0))                            AS bbper100
                        ,avg(hp.totalProfit)/100.0                                              AS profitperhand
                        ,100.0*avg((hp.totalProfit+hp.rake)/(gt.bigBlind+0.0))                  AS bb100xr
                        ,avg((hp.totalProfit+hp.rake)/100.0)                                    AS profhndxr
                        ,avg(h.seats+0.0)                                                       AS avgseats
                        ,variance(hp.totalProfit/100.0)                                         AS variance
                        ,sqrt(variance(hp.totalProfit/100.0))                                                         AS stddev
                  from HandsPlayers hp
                       inner join Hands h       on  (h.id = hp.handId)
                       inner join Gametypes gt  on  (gt.Id = h.gametypeId)
                       inner join Sites s       on  (s.Id = gt.siteId)
                       inner join Players p     on  (p.Id = hp.playerId)
                  where hp.playerId in <player_test>
                  <game_test>
                  <site_test>
                  <currency_test>
                  and   h.seats <seats_test>
                  <flagtest>
                  <cardstest>
                  <gtbigBlind_test>
                  and   datetime(h.startTime) <datestest>
                  group by hgametypeId
                          ,hp.playerId
                          ,gt.base
                          ,gt.category
                          <groupbyseats>
                          ,plposition
                          ,upper(gt.limitType)
                          ,gt.fast
                          ,s.name
                  having 1 = 1 <havingclause>
                  order by hp.playerId
                          ,gt.base
                          ,gt.category
                          <orderbyseats>
                          ,case <position> when 'B' then 'B'
                                           when 'S' then 'S'
                                           when '0' then 'Y'
                                           else 'Z'||<position>
                           end
                          <orderbyhgametypeId>
                          ,upper(gt.limitType) desc
                          ,max(gt.bigBlind) desc
                          ,gt.fast
                          ,s.name
                  """

    return query
