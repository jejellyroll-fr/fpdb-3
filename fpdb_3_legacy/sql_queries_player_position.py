"""Position-grouped player statistics report queries."""

from __future__ import annotations


def player_position_stats_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific position-grouped player query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["playerStatsByPosition"] = """
            SELECT
                  concat(upper(stats.limitType), ' '
                        ,concat(upper(substring(stats.category,1,1)),substring(stats.category,2) ), ' '
                        ,stats.name, ' '
                        ,cast(stats.bigBlindDesc as char)
                        )                                                      AS Game
                 ,case when stats.PlPosition = -2 then 'BB'
                       when stats.PlPosition = -1 then 'SB'
                       when stats.PlPosition =  0 then 'Btn'
                       when stats.PlPosition =  1 then 'CO'
                       when stats.PlPosition =  2 then 'MP'
                       when stats.PlPosition =  5 then 'EP'
                       else 'xx'
                  end                                                          AS PlPosition
                 ,stats.n
                 ,stats.vpip
                 ,stats.pfr
                 ,stats.car0
                 ,stats.pf3
                 ,stats.pf4
                 ,stats.pff3
                 ,stats.pff4
                 ,stats.steals
                 ,stats.saw_f
                 ,stats.sawsd
                 ,stats.wtsdwsf
                 ,stats.wmsd
                 ,stats.FlAFq
                 ,stats.TuAFq
                 ,stats.RvAFq
                 ,stats.PoFAFq
                 ,stats.Net
                 ,stats.BBper100
                 ,stats.Profitperhand
                 ,case when hprof2.variance = -999 then '-'
                       else format(hprof2.variance, 2)
                  end                                                          AS Variance
                 ,case when hprof2.stddev = -999 then '-'
                       else format(hprof2.stddev, 2)
                  end                                                          AS Stddev
                 ,stats.AvgSeats
            FROM
                (select /* stats from hudcache */
                        gt.base
                       ,gt.category
                       ,upper(gt.limitType)                                             AS limitType
                       ,s.name
                       ,<selectgt.bigBlind>                                             AS bigBlindDesc
                       ,<hcgametypeId>                                                  AS gtId
                       ,case when hc.position = 'B' then -2
                             when hc.position = 'S' then -1
                             when hc.position = 'D' then  0
                             when hc.position = 'C' then  1
                             when hc.position = 'M' then  2
                             when hc.position = 'E' then  5
                             else 9
                        end                                                             as PlPosition
                       ,sum(n)                                                          AS n
                       ,case when sum(street0VPIChance) = 0 then '0'
                             else format(100.0*sum(street0VPI)/sum(street0VPIChance),1)
                        end                                                             AS vpip
                       ,case when sum(street0AggrChance) = 0 then '0'
                             else format(100.0*sum(street0Aggr)/sum(street0AggrChance),1)
                        end                                                             AS pfr
                       ,case when sum(street0CalledRaiseChance) = 0 then '0'
                             else format(100.0*sum(street0CalledRaiseDone)/sum(street0CalledRaiseChance),1)
                        end                                                             AS car0
                       ,case when sum(street0_3Bchance) = 0 then '0'
                             else format(100.0*sum(street0_3Bdone)/sum(street0_3Bchance),1)
                        end                                                             AS pf3
                       ,case when sum(street0_4Bchance) = 0 then '0'
                             else format(100.0*sum(street0_4Bdone)/sum(street0_4Bchance),1)
                        end                                                             AS pf4
                       ,case when sum(street0_FoldTo3Bchance) = 0 then '0'
                             else format(100.0*sum(street0_FoldTo3Bdone)/sum(street0_FoldTo3Bchance),1)
                        end                                                             AS pff3
                       ,case when sum(street0_FoldTo4Bchance) = 0 then '0'
                             else format(100.0*sum(street0_FoldTo4Bdone)/sum(street0_FoldTo4Bchance),1)
                        end                                                             AS pff4
                       ,case when sum(raiseFirstInChance) = 0 then '-'
                             else format(100.0*sum(raisedFirstIn)/sum(raiseFirstInChance),1)
                        end                                                             AS steals
                       ,format(100.0*sum(street1Seen)/sum(n),1)                         AS saw_f
                       ,format(100.0*sum(sawShowdown)/sum(n),1)                         AS sawsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else format(100.0*sum(sawShowdown)/sum(street1Seen),1)
                        end                                                             AS wtsdwsf
                       ,case when sum(sawShowdown) = 0 then '-'
                             else format(100.0*sum(wonAtSD)/sum(sawShowdown),1)
                        end                                                             AS wmsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else format(100.0*sum(street1Aggr)/sum(street1Seen),1)
                        end                                                             AS FlAFq
                       ,case when sum(street2Seen) = 0 then '-'
                             else format(100.0*sum(street2Aggr)/sum(street2Seen),1)
                        end                                                             AS TuAFq
                       ,case when sum(street3Seen) = 0 then '-'
                            else format(100.0*sum(street3Aggr)/sum(street3Seen),1)
                        end                                                             AS RvAFq
                       ,case when sum(street1Seen)+sum(street2Seen)+sum(street3Seen) = 0 then '-'
                            else format(100.0*(sum(street1Aggr)+sum(street2Aggr)+sum(street3Aggr))
                                     /(sum(street1Seen)+sum(street2Seen)+sum(street3Seen)),1)
                        end                                                             AS PoFAFq
                       ,format(sum(totalProfit)/100.0,2)                                AS Net
                       ,format((sum(totalProfit/(gt.bigBlind+0.0))) / (sum(n)/100.0),2)
                                                                                        AS BBper100
                       ,format( (sum(totalProfit)/100.0) / sum(n), 4)                   AS Profitperhand
                       ,format( sum(seats*n)/(sum(n)+0.0), 2)                          AS AvgSeats
                 from Gametypes gt
                      inner join Sites s on s.Id = gt.siteId
                      inner join HudCache hc on hc.gametypeId = gt.Id
                 where hc.playerId in <player_test>
                 <gtbigBlind_test>
                 and   hc.seats <seats_test>
                 and   concat( '20', substring(hc.styleKey,2,2), '-', substring(hc.styleKey,4,2), '-'
                             , substring(hc.styleKey,6,2) ) <datestest>
                 group by gt.base
                      ,gt.category
                      ,upper(gt.limitType)
                      ,s.name
                      <groupbygt.bigBlind>
                      ,gtId
                      <groupbyseats>
                      ,PlPosition
                ) stats
            inner join
                ( select # profit from handsplayers/handsactions
                         hprof.gtId,
                         case when hprof.position = 'B' then -2
                              when hprof.position = 'S' then -1
                              when hprof.position in ('3','4') then 2
                              when hprof.position in ('6','7') then 5
                              else hprof.position
                         end                                      as PlPosition,
                         sum(hprof.profit) as sum_profit,
                         avg(hprof.profit/100.0) as profitperhand,
                         case when hprof.gtId = -1 then -999
                              else variance(hprof.profit/100.0)
                         end as variance
                         ,case when hprof.gtId = -1 then -999
                              else sqrt(variance(hprof.profit/100.0))
                         end as stddev
                  from
                      (select hp.handId, <hgametypeId> as gtId, hp.position
                            , hp.totalProfit as profit
                       from HandsPlayers hp
                       inner join Hands h  ON  (h.id = hp.handId)
                       where hp.playerId in <player_test>
                       and   hp.tourneysPlayersId IS NULL
                       and   date_format(h.startTime, '%Y-%m-%d') <datestest>
                       group by hp.handId, gtId, hp.position, hp.totalProfit
                      ) hprof
                  group by hprof.gtId, PlPosition
                 ) hprof2
                on (    hprof2.gtId = stats.gtId
                    and hprof2.PlPosition = stats.PlPosition)
            order by stats.category, stats.limitType, stats.bigBlindDesc desc
                     <orderbyseats>, cast(stats.PlPosition as signed)
            """
    elif db_server == "sqlite":
        query["playerStatsByPosition"] = """
            SELECT
                  upper(substr(stats.category,1,1)) || substr(stats.category,2) || ' ' ||
                  stats.name || ' ' ||
                  cast(stats.bigBlindDesc as char) || ' ' || stats.maxSeats || ' seat'  AS Game
                 ,case when stats.PlPosition = -2 then 'BB'
                       when stats.PlPosition = -1 then 'SB'
                       when stats.PlPosition =  0 then 'Btn'
                       when stats.PlPosition =  1 then 'CO'
                       when stats.PlPosition =  2 then 'MP'
                       when stats.PlPosition =  5 then 'EP'
                       else 'xx'
                  end                                                                   AS PlPosition
                 ,stats.n,stats.vpip,stats.pfr,stats.pf3,stats.pf4,stats.pff3,stats.pff4
                 ,stats.steals,stats.saw_f,stats.sawsd,stats.wtsdwsf,stats.wmsd,stats.FlAFq
                 ,stats.TuAFq,stats.RvAFq,stats.PoFAFq,stats.Net,stats.BBper100,stats.Profitperhand
                 ,case when hprof2.variance = -999 then '-'
                       else round(hprof2.variance, 2)
                  end                                                                   AS Variance
                 ,case when hprof2.variance = -999 then '-'
                       else round(hprof2.stddev, 2)
                  end                                                                   AS Stddev
                 ,stats.AvgSeats
            FROM
                (select /* stats from hudcache */
                        gt.base
                       ,gt.category,maxSeats,gt.bigBlind,gt.currency
                       ,upper(gt.limitType)                                             AS limitType
                       ,s.name
                       ,<selectgt.bigBlind>                                             AS bigBlindDesc
                       ,<hcgametypeId>                                                  AS gtId
                       ,case when hc.position = 'B' then -2
                             when hc.position = 'S' then -1
                             when hc.position = 'D' then  0
                             when hc.position = 'C' then  1
                             when hc.position = 'M' then  2
                             when hc.position = 'E' then  5
                             else 9
                        end                                                             AS PlPosition
                       ,sum(n)                                                          AS n
                       ,case when sum(street0VPIChance) = 0 then '0'
                             else round(100.0*sum(street0VPI)/sum(street0VPIChance),1)
                        end                                                             AS vpip
                       ,case when sum(street0AggrChance) = 0 then '0'
                             else round(100.0*sum(street0Aggr)/sum(street0AggrChance),1)
                        end                                                             AS pfr
                       ,case when sum(street0CalledRaiseChance) = 0 then '0'
                             else round(100.0*sum(street0CalledRaiseDone)/sum(street0CalledRaiseChance),1)
                        end                                                             AS car0
                       ,case when sum(street0_3Bchance) = 0 then '0'
                             else round(100.0*sum(street0_3Bdone)/sum(street0_3Bchance),1)
                        end                                                             AS pf3
                       ,case when sum(street0_4Bchance) = 0 then '0'
                             else round(100.0*sum(street0_4Bdone)/sum(street0_4Bchance),1)
                        end                                                             AS pf4
                       ,case when sum(street0_FoldTo3Bchance) = 0 then '0'
                             else round(100.0*sum(street0_FoldTo3Bdone)/sum(street0_FoldTo3Bchance),1)
                        end                                                             AS pff3
                       ,case when sum(street0_FoldTo4Bchance) = 0 then '0'
                             else round(100.0*sum(street0_FoldTo4Bdone)/sum(street0_FoldTo4Bchance),1)
                        end                                                             AS pff4
                       ,case when sum(raiseFirstInChance) = 0 then '-'
                             else round(100.0*sum(raisedFirstIn)/sum(raiseFirstInChance),1)
                        end                                                             AS steals
                       ,round(100.0*sum(street1Seen)/sum(n),1)                          AS saw_f
                       ,round(100.0*sum(sawShowdown)/sum(n),1)                          AS sawsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else round(100.0*sum(sawShowdown)/sum(street1Seen),1)
                        end                                                             AS wtsdwsf
                       ,case when sum(sawShowdown) = 0 then '-'
                             else round(100.0*sum(wonAtSD)/sum(sawShowdown),1)
                        end                                                             AS wmsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else round(100.0*sum(street1Aggr)/sum(street1Seen),1)
                        end                                                             AS FlAFq
                       ,case when sum(street2Seen) = 0 then '-'
                             else round(100.0*sum(street2Aggr)/sum(street2Seen),1)
                        end                                                             AS TuAFq
                       ,case when sum(street3Seen) = 0 then '-'
                            else round(100.0*sum(street3Aggr)/sum(street3Seen),1)
                        end                                                             AS RvAFq
                       ,case when sum(street1Seen)+sum(street2Seen)+sum(street3Seen) = 0 then '-'
                            else round(100.0*(sum(street1Aggr)+sum(street2Aggr)+sum(street3Aggr))
                                     /(sum(street1Seen)+sum(street2Seen)+sum(street3Seen)),1)
                        end                                                             AS PoFAFq
                       ,round(sum(totalProfit)/100.0,2)                                 AS Net
                       ,round((sum(totalProfit/(gt.bigBlind+0.0))) / (sum(n)/100.0),2)
                                                                                        AS BBper100
                       ,round( (sum(totalProfit)/100.0) / sum(n), 4)                    AS Profitperhand
                       ,round( sum(seats*n)/(sum(n)+0.0), 2)                            AS AvgSeats
                 from Gametypes gt
                      inner join Sites s on s.Id = gt.siteId
                      inner join HudCache hc on hc.gametypeId = gt.Id
                 where hc.playerId in <player_test>
                 <gtbigBlind_test>
                 and   hc.seats <seats_test>
                 and   '20' || substr(hc.styleKey,2,2) || '-' || substr(hc.styleKey,4,2) || '-' ||
                               substr(hc.styleKey,6,2) <datestest>
                 group by gt.base,gt.category,upper(gt.limitType),s.name
                          <groupbygt.bigBlind>,gtId<groupbyseats>,PlPosition
                ) stats
            inner join
                ( select /* profit from handsplayers/handsactions */
                         hprof.gtId,
                         cast(case when hprof.position = 'B' then -2
                              when hprof.position = 'S' then -1
                              when hprof.position in ('3','4') then 2
                              when hprof.position in ('6','7') then 5
                              else hprof.position
                         end as signed)                           as PlPosition,
                         sum(hprof.profit) as sum_profit,
                         avg(hprof.profit/100.0) as profitperhand,
                         case when hprof.gtId = -1 then -999
                              else variance(hprof.profit/100.0)
                         end as variance
                         ,case when hprof.gtId = -1 then -999
                              else sqrt(variance(hprof.profit/100.0))
                         end as stddev
                  from
                      (select hp.handId, <hgametypeId> as gtId, hp.position
                            , hp.totalProfit as profit
                       from HandsPlayers hp
                       inner join Hands h  ON  (h.id = hp.handId)
                       where hp.playerId in <player_test>
                       and   hp.tourneysPlayersId IS NULL
                       and   datetime(h.startTime) <datestest>
                       group by hp.handId, gtId, hp.position, hp.totalProfit
                      ) hprof
                  group by hprof.gtId, PlPosition
                 ) hprof2
                on (    hprof2.gtId = stats.gtId
                    and hprof2.PlPosition = stats.PlPosition)
            order by stats.category, stats.bigBlind, stats.limitType, stats.currency, stats.maxSeats <orderbyseats>
                    ,cast(stats.PlPosition as signed)
            """
    else:  # assume postgresql
        query["playerStatsByPosition"] = """
            select /* stats from hudcache */
                   upper(stats.limitType) || ' '
                   || upper(substr(stats.category,1,1)) || substr(stats.category,2) || ' '
                   || stats.name || ' '
                   || stats.bigBlindDesc                                        AS Game
                  ,case when stats.PlPosition = -2 then 'BB'
                        when stats.PlPosition = -1 then 'SB'
                        when stats.PlPosition =  0 then 'Btn'
                        when stats.PlPosition =  1 then 'CO'
                        when stats.PlPosition =  2 then 'MP'
                        when stats.PlPosition =  5 then 'EP'
                        else 'xx'
                   end                                                          AS PlPosition
                  ,stats.n
                  ,stats.vpip
                  ,stats.pfr
                  ,stats.pf3
                  ,stats.pf4
                  ,stats.pff3
                  ,stats.pff4
                  ,stats.steals
                  ,stats.saw_f
                  ,stats.sawsd
                  ,stats.wtsdwsf
                  ,stats.wmsd
                  ,stats.FlAFq
                  ,stats.TuAFq
                  ,stats.RvAFq
                  ,stats.PoFAFq
                  ,stats.Net
                  ,stats.BBper100
                  ,stats.Profitperhand
                  ,case when hprof2.variance = -999 then '-'
                        else to_char(hprof2.variance, '0D00')
                   end                                                          AS Variance
                  ,case when hprof2.stddev = -999 then '-'
                        else to_char(hprof2.stddev, '0D00')
                   end                                                          AS Stddev
                  ,stats.AvgSeats
            FROM
                (select /* stats from hudcache */
                        gt.base
                       ,gt.category
                       ,upper(gt.limitType)                                             AS limitType
                       ,s.name
                       ,<selectgt.bigBlind>                                             AS bigBlindDesc
                       ,<hcgametypeId>                                                  AS gtId
                       ,case when hc.position = 'B' then -2
                             when hc.position = 'S' then -1
                             when hc.position = 'D' then  0
                             when hc.position = 'C' then  1
                             when hc.position = 'M' then  2
                             when hc.position = 'E' then  5
                             else 9
                        end                                                             AS PlPosition
                       ,sum(n)                                                          AS n
                       ,case when sum(street0VPIChance) = 0 then '0'
                             else to_char(100.0*sum(street0VPI)/sum(street0VPIChance),'990D0')
                        end                                                             AS vpip
                       ,case when sum(street0AggrChance) = 0 then '0'
                             else to_char(100.0*sum(street0Aggr)/sum(street0AggrChance),'90D0')
                        end                                                             AS pfr
                       ,case when sum(street0CalledRaiseChance) = 0 then '0'
                             else to_char(100.0*sum(street0CalledRaiseDone)/sum(street0CalledRaiseChance),'90D0')
                        end                                                             AS car0
                       ,case when sum(street0_3Bchance) = 0 then '0'
                             else to_char(100.0*sum(street0_3Bdone)/sum(street0_3Bchance),'90D0')
                        end                                                             AS pf3
                       ,case when sum(street0_4Bchance) = 0 then '0'
                             else to_char(100.0*sum(street0_4Bdone)/sum(street0_4Bchance),'90D0')
                        end                                                             AS pf4
                       ,case when sum(street0_FoldTo3Bchance) = 0 then '0'
                             else to_char(100.0*sum(street0_FoldTo3Bdone)/sum(street0_FoldTo3Bchance),'90D0')
                        end                                                             AS pff3
                       ,case when sum(street0_FoldTo4Bchance) = 0 then '0'
                             else to_char(100.0*sum(street0_FoldTo4Bdone)/sum(street0_FoldTo4Bchance),'90D0')
                        end                                                             AS pff4
                       ,case when sum(raiseFirstInChance) = 0 then '-'
                             else to_char(100.0*sum(raisedFirstIn)/sum(raiseFirstInChance),'90D0')
                        end                                                             AS steals
                       ,to_char(round(100.0*sum(street1Seen)/sum(n)),'90D0')            AS saw_f
                       ,to_char(round(100.0*sum(sawShowdown)/sum(n)),'90D0')            AS sawsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else to_char(round(100.0*sum(sawShowdown)/sum(street1Seen)),'90D0')
                        end                                                             AS wtsdwsf
                       ,case when sum(sawShowdown) = 0 then '-'
                             else to_char(round(100.0*sum(wonAtSD)/sum(sawShowdown)),'90D0')
                        end                                                             AS wmsd
                       ,case when sum(street1Seen) = 0 then '-'
                             else to_char(round(100.0*sum(street1Aggr)/sum(street1Seen)),'90D0')
                        end                                                             AS FlAFq
                       ,case when sum(street2Seen) = 0 then '-'
                             else to_char(round(100.0*sum(street2Aggr)/sum(street2Seen)),'90D0')
                        end                                                             AS TuAFq
                       ,case when sum(street3Seen) = 0 then '-'
                            else to_char(round(100.0*sum(street3Aggr)/sum(street3Seen)),'90D0')
                        end                                                             AS RvAFq
                       ,case when sum(street1Seen)+sum(street2Seen)+sum(street3Seen) = 0 then '-'
                            else to_char(round(100.0*(sum(street1Aggr)+sum(street2Aggr)+sum(street3Aggr))
                                     /(sum(street1Seen)+sum(street2Seen)+sum(street3Seen))),'90D0')
                        end                                                             AS PoFAFq
                       ,to_char(sum(totalProfit)/100.0,'9G999G990D00')                  AS Net
                       ,case when sum(n) = 0 then '0'
                             else to_char(sum(totalProfit/(gt.bigBlind+0.0)) / (sum(n)/100.0), '990D00')
                        end                                                             AS BBper100
                       ,case when sum(n) = 0 then '0'
                             else to_char( (sum(totalProfit)/100.0) / sum(n), '90D0000')
                        end                                                             AS Profitperhand
                       ,to_char(sum(seats*n)/(sum(n)+0.0),'90D00')                      AS AvgSeats
                 from Gametypes gt
                      inner join Sites s     on (s.Id = gt.siteId)
                      inner join HudCache hc on (hc.gametypeId = gt.Id)
                 where hc.playerId in <player_test>
                 <gtbigBlind_test>
                 and   hc.seats <seats_test>
                 and   '20' || SUBSTR(hc.styleKey,2,2) || '-' || SUBSTR(hc.styleKey,4,2) || '-'
                       || SUBSTR(hc.styleKey,6,2) <datestest>
                 group by gt.base
                      ,gt.category
                      ,upper(gt.limitType)
                      ,s.name
                      <groupbygt.bigBlind>
                      ,gtId
                      <groupbyseats>
                      ,PlPosition
                ) stats
            inner join
                ( select /* profit from handsplayers/handsactions */
                         hprof.gtId,
                         case when hprof.position = 'B' then -2
                              when hprof.position = 'S' then -1
                              when hprof.position in ('3','4') then 2
                              when hprof.position in ('6','7') then 5
                              else cast(hprof.position as smallint)
                         end                                      as PlPosition,
                         sum(hprof.profit) as sum_profit,
                         avg(hprof.profit/100.0) as profitperhand,
                         case when hprof.gtId = -1 then -999
                              else variance(hprof.profit/100.0)
                         end as variance
                         ,case when hprof.gtId = -1 then -999
                              else sqrt(variance(hprof.profit/100.0))
                         end as stddev
                  from
                      (select hp.handId, <hgametypeId> as gtId, hp.position
                            , hp.totalProfit as profit
                       from HandsPlayers hp
                       inner join Hands h  ON  (h.id = hp.handId)
                       where hp.playerId in <player_test>
                       and   hp.tourneysPlayersId IS NULL
                       and   to_char(h.startTime, 'YYYY-MM-DD') <datestest>
                       group by hp.handId, gametypeId, hp.position, hp.totalProfit
                      ) hprof
                  group by hprof.gtId, PlPosition
                ) hprof2
                on (    hprof2.gtId = stats.gtId
                    and hprof2.PlPosition = stats.PlPosition)
            order by stats.category, stats.limitType, stats.bigBlindDesc desc
                     <orderbyseats>, cast(stats.PlPosition as smallint)
            """

    ####################################
    # Cash Game Graph query
    ####################################
    return query

