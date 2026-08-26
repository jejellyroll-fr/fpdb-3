"""HUD cache rebuild queries."""

from __future__ import annotations


def cache_rebuild_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific cache rebuild aggregation query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["rebuildCache"] = """insert into <insert>
            ,n
            ,street0VPIChance
            ,street0VPI
            ,street0AggrChance
            ,street0Aggr
            ,street0CalledRaiseChance
            ,street0CalledRaiseDone
            ,street0_2BChance
            ,street0_2BDone
            ,street0_3BChance
            ,street0_3BDone
            ,street0_4BChance
            ,street0_4BDone
            ,street0_C4BChance
            ,street0_C4BDone
            ,street0_FoldTo2BChance
            ,street0_FoldTo2BDone
            ,street0_FoldTo3BChance
            ,street0_FoldTo3BDone
            ,street0_FoldTo4BChance
            ,street0_FoldTo4BDone
            ,street0_SqueezeChance
            ,street0_SqueezeDone
            ,raiseToStealChance
            ,raiseToStealDone
            ,stealChance
            ,stealDone
            ,success_Steal
            ,street1Seen
            ,street2Seen
            ,street3Seen
            ,street4Seen
            ,sawShowdown
            ,street1Aggr
            ,street2Aggr
            ,street3Aggr
            ,street4Aggr
            ,otherRaisedStreet0
            ,otherRaisedStreet1
            ,otherRaisedStreet2
            ,otherRaisedStreet3
            ,otherRaisedStreet4
            ,foldToOtherRaisedStreet0
            ,foldToOtherRaisedStreet1
            ,foldToOtherRaisedStreet2
            ,foldToOtherRaisedStreet3
            ,foldToOtherRaisedStreet4
            ,wonWhenSeenStreet1
            ,wonWhenSeenStreet2
            ,wonWhenSeenStreet3
            ,wonWhenSeenStreet4
            ,wonAtSD
            ,raiseFirstInChance
            ,raisedFirstIn
            ,foldBbToStealChance
            ,foldedBbToSteal
            ,foldSbToStealChance
            ,foldedSbToSteal
            ,street1CBChance
            ,street1CBDone
            ,street2CBChance
            ,street2CBDone
            ,street3CBChance
            ,street3CBDone
            ,street4CBChance
            ,street4CBDone
            ,foldToStreet1CBChance
            ,foldToStreet1CBDone
            ,foldToStreet2CBChance
            ,foldToStreet2CBDone
            ,foldToStreet3CBChance
            ,foldToStreet3CBDone
            ,foldToStreet4CBChance
            ,foldToStreet4CBDone
            ,common
            ,committed
            ,winnings
            ,rake
            ,rakeDealt
            ,rakeContributed
            ,rakeWeighted
            ,totalProfit
            ,allInEV
            ,showdownWinnings
            ,nonShowdownWinnings
            ,street1CheckCallRaiseChance
            ,street1CheckCallDone
            ,street1CheckRaiseDone
            ,street2CheckCallRaiseChance
            ,street2CheckCallDone
            ,street2CheckRaiseDone
            ,street3CheckCallRaiseChance
            ,street3CheckCallDone
            ,street3CheckRaiseDone
            ,street4CheckCallRaiseChance
            ,street4CheckCallDone
            ,street4CheckRaiseDone
            ,street0Calls
            ,street1Calls
            ,street2Calls
            ,street3Calls
            ,street4Calls
            ,street0Bets
            ,street1Bets
            ,street2Bets
            ,street3Bets
            ,street4Bets
            ,street0Raises
            ,street1Raises
            ,street2Raises
            ,street3Raises
            ,street4Raises
            ,street1Discards
            ,street2Discards
            ,street3Discards<extra_insert_columns>
            )
            SELECT <select>
                  ,count(1)
                  ,sum(street0VPIChance)
                  ,sum(street0VPI)
                  ,sum(street0AggrChance)
                  ,sum(street0Aggr)
                  ,sum(street0CalledRaiseChance)
                  ,sum(street0CalledRaiseDone)
                  ,sum(street0_2BChance)
                  ,sum(street0_2BDone)
                  ,sum(street0_3BChance)
                  ,sum(street0_3BDone)
                  ,sum(street0_4BChance)
                  ,sum(street0_4BDone)
                  ,sum(street0_C4BChance)
                  ,sum(street0_C4BDone)
                  ,sum(street0_FoldTo2BChance)
                  ,sum(street0_FoldTo2BDone)
                  ,sum(street0_FoldTo3BChance)
                  ,sum(street0_FoldTo3BDone)
                  ,sum(street0_FoldTo4BChance)
                  ,sum(street0_FoldTo4BDone)
                  ,sum(street0_SqueezeChance)
                  ,sum(street0_SqueezeDone)
                  ,sum(raiseToStealChance)
                  ,sum(raiseToStealDone)
                  ,sum(stealChance)
                  ,sum(stealDone)
                  ,sum(success_Steal)
                  ,sum(street1Seen)
                  ,sum(street2Seen)
                  ,sum(street3Seen)
                  ,sum(street4Seen)
                  ,sum(sawShowdown)
                  ,sum(street1Aggr)
                  ,sum(street2Aggr)
                  ,sum(street3Aggr)
                  ,sum(street4Aggr)
                  ,sum(otherRaisedStreet0)
                  ,sum(otherRaisedStreet1)
                  ,sum(otherRaisedStreet2)
                  ,sum(otherRaisedStreet3)
                  ,sum(otherRaisedStreet4)
                  ,sum(foldToOtherRaisedStreet0)
                  ,sum(foldToOtherRaisedStreet1)
                  ,sum(foldToOtherRaisedStreet2)
                  ,sum(foldToOtherRaisedStreet3)
                  ,sum(foldToOtherRaisedStreet4)
                  ,sum(wonWhenSeenStreet1)
                  ,sum(wonWhenSeenStreet2)
                  ,sum(wonWhenSeenStreet3)
                  ,sum(wonWhenSeenStreet4)
                  ,sum(wonAtSD)
                  ,sum(raiseFirstInChance)
                  ,sum(raisedFirstIn)
                  ,sum(foldBbToStealChance)
                  ,sum(foldedBbToSteal)
                  ,sum(foldSbToStealChance)
                  ,sum(foldedSbToSteal)
                  ,sum(street1CBChance)
                  ,sum(street1CBDone)
                  ,sum(street2CBChance)
                  ,sum(street2CBDone)
                  ,sum(street3CBChance)
                  ,sum(street3CBDone)
                  ,sum(street4CBChance)
                  ,sum(street4CBDone)
                  ,sum(foldToStreet1CBChance)
                  ,sum(foldToStreet1CBDone)
                  ,sum(foldToStreet2CBChance)
                  ,sum(foldToStreet2CBDone)
                  ,sum(foldToStreet3CBChance)
                  ,sum(foldToStreet3CBDone)
                  ,sum(foldToStreet4CBChance)
                  ,sum(foldToStreet4CBDone)
                  ,sum(common)
                  ,sum(committed)
                  ,sum(winnings)
                  ,sum(rake)
                  ,sum(rakeDealt)
                  ,sum(rakeContributed)
                  ,sum(rakeWeighted)
                  ,sum(totalProfit)
                  ,sum(allInEV)
                  ,sum(case when sawShowdown = 1 then totalProfit else 0 end)
                  ,sum(case when sawShowdown = 0 then totalProfit else 0 end)
                  ,sum(street1CheckCallRaiseChance)
                  ,sum(street1CheckCallDone)
                  ,sum(street1CheckRaiseDone)
                  ,sum(street2CheckCallRaiseChance)
                  ,sum(street2CheckCallDone)
                  ,sum(street2CheckRaiseDone)
                  ,sum(street3CheckCallRaiseChance)
                  ,sum(street3CheckCallDone)
                  ,sum(street3CheckRaiseDone)
                  ,sum(street4CheckCallRaiseChance)
                  ,sum(street4CheckCallDone)
                  ,sum(street4CheckRaiseDone)
                  ,sum(street0Calls)
                  ,sum(street1Calls)
                  ,sum(street2Calls)
                  ,sum(street3Calls)
                  ,sum(street4Calls)
                  ,sum(street0Bets)
                  ,sum(street1Bets)
                  ,sum(street2Bets)
                  ,sum(street3Bets)
                  ,sum(street4Bets)
                  ,sum(hp.street0Raises)
                  ,sum(hp.street1Raises)
                  ,sum(hp.street2Raises)
                  ,sum(hp.street3Raises)
                  ,sum(hp.street4Raises)
                  ,sum(street1Discards)
                  ,sum(street2Discards)
                  ,sum(street3Discards)<extra_select_columns>
            FROM Hands h
            INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
            INNER JOIN Gametypes g ON (h.gametypeId = g.id)
            <sessions_join_clause>
            <tourney_join_clause>
            <where_clause>
            GROUP BY <group>
"""
    elif db_server == "postgresql":
        query["rebuildCache"] = """insert into <insert>
            ,n
            ,street0VPIChance
            ,street0VPI
            ,street0AggrChance
            ,street0Aggr
            ,street0CalledRaiseChance
            ,street0CalledRaiseDone
            ,street0_2BChance
            ,street0_2BDone
            ,street0_3BChance
            ,street0_3BDone
            ,street0_4BChance
            ,street0_4BDone
            ,street0_C4BChance
            ,street0_C4BDone
            ,street0_FoldTo2BChance
            ,street0_FoldTo2BDone
            ,street0_FoldTo3BChance
            ,street0_FoldTo3BDone
            ,street0_FoldTo4BChance
            ,street0_FoldTo4BDone
            ,street0_SqueezeChance
            ,street0_SqueezeDone
            ,raiseToStealChance
            ,raiseToStealDone
            ,stealChance
            ,stealDone
            ,success_Steal
            ,street1Seen
            ,street2Seen
            ,street3Seen
            ,street4Seen
            ,sawShowdown
            ,street1Aggr
            ,street2Aggr
            ,street3Aggr
            ,street4Aggr
            ,otherRaisedStreet0
            ,otherRaisedStreet1
            ,otherRaisedStreet2
            ,otherRaisedStreet3
            ,otherRaisedStreet4
            ,foldToOtherRaisedStreet0
            ,foldToOtherRaisedStreet1
            ,foldToOtherRaisedStreet2
            ,foldToOtherRaisedStreet3
            ,foldToOtherRaisedStreet4
            ,wonWhenSeenStreet1
            ,wonWhenSeenStreet2
            ,wonWhenSeenStreet3
            ,wonWhenSeenStreet4
            ,wonAtSD
            ,raiseFirstInChance
            ,raisedFirstIn
            ,foldBbToStealChance
            ,foldedBbToSteal
            ,foldSbToStealChance
            ,foldedSbToSteal
            ,street1CBChance
            ,street1CBDone
            ,street2CBChance
            ,street2CBDone
            ,street3CBChance
            ,street3CBDone
            ,street4CBChance
            ,street4CBDone
            ,foldToStreet1CBChance
            ,foldToStreet1CBDone
            ,foldToStreet2CBChance
            ,foldToStreet2CBDone
            ,foldToStreet3CBChance
            ,foldToStreet3CBDone
            ,foldToStreet4CBChance
            ,foldToStreet4CBDone
            ,common
            ,committed
            ,winnings
            ,rake
            ,rakeDealt
            ,rakeContributed
            ,rakeWeighted
            ,totalProfit
            ,allInEV
            ,showdownWinnings
            ,nonShowdownWinnings
            ,street1CheckCallRaiseChance
            ,street1CheckCallDone
            ,street1CheckRaiseDone
            ,street2CheckCallRaiseChance
            ,street2CheckCallDone
            ,street2CheckRaiseDone
            ,street3CheckCallRaiseChance
            ,street3CheckCallDone
            ,street3CheckRaiseDone
            ,street4CheckCallRaiseChance
            ,street4CheckCallDone
            ,street4CheckRaiseDone
            ,street0Calls
            ,street1Calls
            ,street2Calls
            ,street3Calls
            ,street4Calls
            ,street0Bets
            ,street1Bets
            ,street2Bets
            ,street3Bets
            ,street4Bets
            ,street0Raises
            ,street1Raises
            ,street2Raises
            ,street3Raises
            ,street4Raises
            ,street1Discards
            ,street2Discards
            ,street3Discards<extra_insert_columns>
            )
            SELECT <select>
                  ,count(1)
                  ,sum(CAST(street0VPIChance as integer))
                  ,sum(CAST(street0VPI as integer))
                  ,sum(CAST(street0AggrChance as integer))
                  ,sum(CAST(street0Aggr as integer))
                  ,sum(CAST(street0CalledRaiseChance as integer))
                  ,sum(CAST(street0CalledRaiseDone as integer))
                  ,sum(CAST(street0_2BChance as integer))
                  ,sum(CAST(street0_2BDone as integer))
                  ,sum(CAST(street0_3BChance as integer))
                  ,sum(CAST(street0_3BDone as integer))
                  ,sum(CAST(street0_4BChance as integer))
                  ,sum(CAST(street0_4BDone as integer))
                  ,sum(CAST(street0_C4BChance as integer))
                  ,sum(CAST(street0_C4BDone as integer))
                  ,sum(CAST(street0_FoldTo2BChance as integer))
                  ,sum(CAST(street0_FoldTo2BDone as integer))
                  ,sum(CAST(street0_FoldTo3BChance as integer))
                  ,sum(CAST(street0_FoldTo3BDone as integer))
                  ,sum(CAST(street0_FoldTo4BChance as integer))
                  ,sum(CAST(street0_FoldTo4BDone as integer))
                  ,sum(CAST(street0_SqueezeChance as integer))
                  ,sum(CAST(street0_SqueezeDone as integer))
                  ,sum(CAST(raiseToStealChance as integer))
                  ,sum(CAST(raiseToStealDone as integer))
                  ,sum(CAST(stealChance as integer))
                  ,sum(CAST(stealDone as integer))
                  ,sum(CAST(success_Steal as integer))
                  ,sum(CAST(street1Seen as integer))
                  ,sum(CAST(street2Seen as integer))
                  ,sum(CAST(street3Seen as integer))
                  ,sum(CAST(street4Seen as integer))
                  ,sum(CAST(sawShowdown as integer))
                  ,sum(CAST(street1Aggr as integer))
                  ,sum(CAST(street2Aggr as integer))
                  ,sum(CAST(street3Aggr as integer))
                  ,sum(CAST(street4Aggr as integer))
                  ,sum(CAST(otherRaisedStreet0 as integer))
                  ,sum(CAST(otherRaisedStreet1 as integer))
                  ,sum(CAST(otherRaisedStreet2 as integer))
                  ,sum(CAST(otherRaisedStreet3 as integer))
                  ,sum(CAST(otherRaisedStreet4 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet0 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet1 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet2 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet3 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet4 as integer))
                  ,sum(CAST(wonWhenSeenStreet1 as integer))
                  ,sum(CAST(wonWhenSeenStreet2 as integer))
                  ,sum(CAST(wonWhenSeenStreet3 as integer))
                  ,sum(CAST(wonWhenSeenStreet4 as integer))
                  ,sum(CAST(wonAtSD as integer))
                  ,sum(CAST(raiseFirstInChance as integer))
                  ,sum(CAST(raisedFirstIn as integer))
                  ,sum(CAST(foldBbToStealChance as integer))
                  ,sum(CAST(foldedBbToSteal as integer))
                  ,sum(CAST(foldSbToStealChance as integer))
                  ,sum(CAST(foldedSbToSteal as integer))
                  ,sum(CAST(street1CBChance as integer))
                  ,sum(CAST(street1CBDone as integer))
                  ,sum(CAST(street2CBChance as integer))
                  ,sum(CAST(street2CBDone as integer))
                  ,sum(CAST(street3CBChance as integer))
                  ,sum(CAST(street3CBDone as integer))
                  ,sum(CAST(street4CBChance as integer))
                  ,sum(CAST(street4CBDone as integer))
                  ,sum(CAST(foldToStreet1CBChance as integer))
                  ,sum(CAST(foldToStreet1CBDone as integer))
                  ,sum(CAST(foldToStreet2CBChance as integer))
                  ,sum(CAST(foldToStreet2CBDone as integer))
                  ,sum(CAST(foldToStreet3CBChance as integer))
                  ,sum(CAST(foldToStreet3CBDone as integer))
                  ,sum(CAST(foldToStreet4CBChance as integer))
                  ,sum(CAST(foldToStreet4CBDone as integer))
                  ,sum(common)
                  ,sum(committed)
                  ,sum(winnings)
                  ,sum(rake)
                  ,sum(rakeDealt)
                  ,sum(rakeContributed)
                  ,sum(rakeWeighted)
                  ,sum(totalProfit)
                  ,sum(allInEV)
                  ,sum(case when sawShowdown then totalProfit else 0 end)
                  ,sum(case when sawShowdown then 0 else totalProfit end)
                  ,sum(CAST(street1CheckCallRaiseChance as integer))
                  ,sum(CAST(street1CheckCallDone as integer))
                  ,sum(CAST(street1CheckRaiseDone as integer))
                  ,sum(CAST(street2CheckCallRaiseChance as integer))
                  ,sum(CAST(street2CheckCallDone as integer))
                  ,sum(CAST(street2CheckRaiseDone as integer))
                  ,sum(CAST(street3CheckCallRaiseChance as integer))
                  ,sum(CAST(street3CheckCallDone as integer))
                  ,sum(CAST(street3CheckRaiseDone as integer))
                  ,sum(CAST(street4CheckCallRaiseChance as integer))
                  ,sum(CAST(street4CheckCallDone as integer))
                  ,sum(CAST(street4CheckRaiseDone as integer))
                  ,sum(CAST(street0Calls as integer))
                  ,sum(CAST(street1Calls as integer))
                  ,sum(CAST(street2Calls as integer))
                  ,sum(CAST(street3Calls as integer))
                  ,sum(CAST(street4Calls as integer))
                  ,sum(CAST(street0Bets as integer))
                  ,sum(CAST(street1Bets as integer))
                  ,sum(CAST(street2Bets as integer))
                  ,sum(CAST(street3Bets as integer))
                  ,sum(CAST(street4Bets as integer))
                  ,sum(CAST(hp.street0Raises as integer))
                  ,sum(CAST(hp.street1Raises as integer))
                  ,sum(CAST(hp.street2Raises as integer))
                  ,sum(CAST(hp.street3Raises as integer))
                  ,sum(CAST(hp.street4Raises as integer))
                  ,sum(CAST(street1Discards as integer))
                  ,sum(CAST(street2Discards as integer))
                  ,sum(CAST(street3Discards as integer))<extra_select_columns>
            FROM Hands h
            INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
            INNER JOIN Gametypes g ON (h.gametypeId = g.id)
            <sessions_join_clause>
            <tourney_join_clause>
            <where_clause>
            GROUP BY <group>
"""
    elif db_server == "sqlite":
        query["rebuildCache"] = """insert into <insert>
            ,n
            ,street0VPIChance
            ,street0VPI
            ,street0AggrChance
            ,street0Aggr
            ,street0CalledRaiseChance
            ,street0CalledRaiseDone
            ,street0_2BChance
            ,street0_2BDone
            ,street0_3BChance
            ,street0_3BDone
            ,street0_4BChance
            ,street0_4BDone
            ,street0_C4BChance
            ,street0_C4BDone
            ,street0_FoldTo2BChance
            ,street0_FoldTo2BDone
            ,street0_FoldTo3BChance
            ,street0_FoldTo3BDone
            ,street0_FoldTo4BChance
            ,street0_FoldTo4BDone
            ,street0_SqueezeChance
            ,street0_SqueezeDone
            ,raiseToStealChance
            ,raiseToStealDone
            ,stealChance
            ,stealDone
            ,success_Steal
            ,street1Seen
            ,street2Seen
            ,street3Seen
            ,street4Seen
            ,sawShowdown
            ,street1Aggr
            ,street2Aggr
            ,street3Aggr
            ,street4Aggr
            ,otherRaisedStreet0
            ,otherRaisedStreet1
            ,otherRaisedStreet2
            ,otherRaisedStreet3
            ,otherRaisedStreet4
            ,foldToOtherRaisedStreet0
            ,foldToOtherRaisedStreet1
            ,foldToOtherRaisedStreet2
            ,foldToOtherRaisedStreet3
            ,foldToOtherRaisedStreet4
            ,wonWhenSeenStreet1
            ,wonWhenSeenStreet2
            ,wonWhenSeenStreet3
            ,wonWhenSeenStreet4
            ,wonAtSD
            ,raiseFirstInChance
            ,raisedFirstIn
            ,foldBbToStealChance
            ,foldedBbToSteal
            ,foldSbToStealChance
            ,foldedSbToSteal
            ,street1CBChance
            ,street1CBDone
            ,street2CBChance
            ,street2CBDone
            ,street3CBChance
            ,street3CBDone
            ,street4CBChance
            ,street4CBDone
            ,foldToStreet1CBChance
            ,foldToStreet1CBDone
            ,foldToStreet2CBChance
            ,foldToStreet2CBDone
            ,foldToStreet3CBChance
            ,foldToStreet3CBDone
            ,foldToStreet4CBChance
            ,foldToStreet4CBDone
            ,common
            ,committed
            ,winnings
            ,rake
            ,rakeDealt
            ,rakeContributed
            ,rakeWeighted
            ,totalProfit
            ,allInEV
            ,showdownWinnings
            ,nonShowdownWinnings
            ,street1CheckCallRaiseChance
            ,street1CheckCallDone
            ,street1CheckRaiseDone
            ,street2CheckCallRaiseChance
            ,street2CheckCallDone
            ,street2CheckRaiseDone
            ,street3CheckCallRaiseChance
            ,street3CheckCallDone
            ,street3CheckRaiseDone
            ,street4CheckCallRaiseChance
            ,street4CheckCallDone
            ,street4CheckRaiseDone
            ,street0Calls
            ,street1Calls
            ,street2Calls
            ,street3Calls
            ,street4Calls
            ,street0Bets
            ,street1Bets
            ,street2Bets
            ,street3Bets
            ,street4Bets
            ,street0Raises
            ,street1Raises
            ,street2Raises
            ,street3Raises
            ,street4Raises
            ,street1Discards
            ,street2Discards
            ,street3Discards<extra_insert_columns>
            )
            SELECT <select>
                  ,count(1)
                  ,sum(CAST(street0VPIChance as integer))
                  ,sum(CAST(street0VPI as integer))
                  ,sum(CAST(street0AggrChance as integer))
                  ,sum(CAST(street0Aggr as integer))
                  ,sum(CAST(street0CalledRaiseChance as integer))
                  ,sum(CAST(street0CalledRaiseDone as integer))
                  ,sum(CAST(street0_2BChance as integer))
                  ,sum(CAST(street0_2BDone as integer))
                  ,sum(CAST(street0_3BChance as integer))
                  ,sum(CAST(street0_3BDone as integer))
                  ,sum(CAST(street0_4BChance as integer))
                  ,sum(CAST(street0_4BDone as integer))
                  ,sum(CAST(street0_C4BChance as integer))
                  ,sum(CAST(street0_C4BDone as integer))
                  ,sum(CAST(street0_FoldTo2BChance as integer))
                  ,sum(CAST(street0_FoldTo2BDone as integer))
                  ,sum(CAST(street0_FoldTo3BChance as integer))
                  ,sum(CAST(street0_FoldTo3BDone as integer))
                  ,sum(CAST(street0_FoldTo4BChance as integer))
                  ,sum(CAST(street0_FoldTo4BDone as integer))
                  ,sum(CAST(street0_SqueezeChance as integer))
                  ,sum(CAST(street0_SqueezeDone as integer))
                  ,sum(CAST(raiseToStealChance as integer))
                  ,sum(CAST(raiseToStealDone as integer))
                  ,sum(CAST(stealChance as integer))
                  ,sum(CAST(stealDone as integer))
                  ,sum(CAST(success_Steal as integer))
                  ,sum(CAST(street1Seen as integer))
                  ,sum(CAST(street2Seen as integer))
                  ,sum(CAST(street3Seen as integer))
                  ,sum(CAST(street4Seen as integer))
                  ,sum(CAST(sawShowdown as integer))
                  ,sum(CAST(street1Aggr as integer))
                  ,sum(CAST(street2Aggr as integer))
                  ,sum(CAST(street3Aggr as integer))
                  ,sum(CAST(street4Aggr as integer))
                  ,sum(CAST(otherRaisedStreet0 as integer))
                  ,sum(CAST(otherRaisedStreet1 as integer))
                  ,sum(CAST(otherRaisedStreet2 as integer))
                  ,sum(CAST(otherRaisedStreet3 as integer))
                  ,sum(CAST(otherRaisedStreet4 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet0 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet1 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet2 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet3 as integer))
                  ,sum(CAST(foldToOtherRaisedStreet4 as integer))
                  ,sum(CAST(wonWhenSeenStreet1 as integer))
                  ,sum(CAST(wonWhenSeenStreet2 as integer))
                  ,sum(CAST(wonWhenSeenStreet3 as integer))
                  ,sum(CAST(wonWhenSeenStreet4 as integer))
                  ,sum(CAST(wonAtSD as integer))
                  ,sum(CAST(raiseFirstInChance as integer))
                  ,sum(CAST(raisedFirstIn as integer))
                  ,sum(CAST(foldBbToStealChance as integer))
                  ,sum(CAST(foldedBbToSteal as integer))
                  ,sum(CAST(foldSbToStealChance as integer))
                  ,sum(CAST(foldedSbToSteal as integer))
                  ,sum(CAST(street1CBChance as integer))
                  ,sum(CAST(street1CBDone as integer))
                  ,sum(CAST(street2CBChance as integer))
                  ,sum(CAST(street2CBDone as integer))
                  ,sum(CAST(street3CBChance as integer))
                  ,sum(CAST(street3CBDone as integer))
                  ,sum(CAST(street4CBChance as integer))
                  ,sum(CAST(street4CBDone as integer))
                  ,sum(CAST(foldToStreet1CBChance as integer))
                  ,sum(CAST(foldToStreet1CBDone as integer))
                  ,sum(CAST(foldToStreet2CBChance as integer))
                  ,sum(CAST(foldToStreet2CBDone as integer))
                  ,sum(CAST(foldToStreet3CBChance as integer))
                  ,sum(CAST(foldToStreet3CBDone as integer))
                  ,sum(CAST(foldToStreet4CBChance as integer))
                  ,sum(CAST(foldToStreet4CBDone as integer))
                  ,sum(CAST(common as integer))
                  ,sum(CAST(committed as integer))
                  ,sum(CAST(winnings as integer))
                  ,sum(CAST(rake as integer))
                  ,sum(CAST(rakeDealt as integer))
                  ,sum(CAST(rakeContributed as integer))
                  ,sum(CAST(rakeWeighted as integer))
                  ,sum(CAST(totalProfit as integer))
                  ,sum(allInEV)
                  ,sum(CAST(case when sawShowdown = 1 then totalProfit else 0 end as integer))
                  ,sum(CAST(case when sawShowdown = 0 then totalProfit else 0 end as integer))
                  ,sum(CAST(street1CheckCallRaiseChance as integer))
                  ,sum(CAST(street1CheckCallDone as integer))
                  ,sum(CAST(street1CheckRaiseDone as integer))
                  ,sum(CAST(street2CheckCallRaiseChance as integer))
                  ,sum(CAST(street2CheckCallDone as integer))
                  ,sum(CAST(street2CheckRaiseDone as integer))
                  ,sum(CAST(street3CheckCallRaiseChance as integer))
                  ,sum(CAST(street3CheckCallDone as integer))
                  ,sum(CAST(street3CheckRaiseDone as integer))
                  ,sum(CAST(street4CheckCallRaiseChance as integer))
                  ,sum(CAST(street4CheckCallDone as integer))
                  ,sum(CAST(street4CheckRaiseDone as integer))
                  ,sum(CAST(street0Calls as integer))
                  ,sum(CAST(street1Calls as integer))
                  ,sum(CAST(street2Calls as integer))
                  ,sum(CAST(street3Calls as integer))
                  ,sum(CAST(street4Calls as integer))
                  ,sum(CAST(street0Bets as integer))
                  ,sum(CAST(street1Bets as integer))
                  ,sum(CAST(street2Bets as integer))
                  ,sum(CAST(street3Bets as integer))
                  ,sum(CAST(street4Bets as integer))
                  ,sum(CAST(hp.street0Raises as integer))
                  ,sum(CAST(hp.street1Raises as integer))
                  ,sum(CAST(hp.street2Raises as integer))
                  ,sum(CAST(hp.street3Raises as integer))
                  ,sum(CAST(hp.street4Raises as integer))
                  ,sum(CAST(street1Discards as integer))
                  ,sum(CAST(street2Discards as integer))
                  ,sum(CAST(street3Discards as integer))<extra_select_columns>
            FROM Hands h
            INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
            INNER JOIN Gametypes g ON (h.gametypeId = g.id)
            <sessions_join_clause>
            <tourney_join_clause>
            <where_clause>
            GROUP BY <group>
"""

    return query

