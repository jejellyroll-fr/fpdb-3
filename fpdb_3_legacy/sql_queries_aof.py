"""Structured All-in or Fold persistence queries."""

from __future__ import annotations


def aof_queries() -> dict[str, str]:
    """Return portable decision and analysis upsert building blocks."""
    return {
        "find_aof_decision": """select id from AofDecisions
            where handId=%s and playerId=%s and classifierVersion=%s""",
        "store_aof_decision": """insert into AofDecisions (
                handId, playerId, category, decision, role, activeOpponents,
                potBefore, amountToCommit, blindCommitted, cardsObservable,
                holeCards, flopCards, madeHand, flushDraw, straightOuts,
                classifierVersion
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )""",
        "update_aof_decision": """update AofDecisions set
                category=%s, decision=%s, role=%s, activeOpponents=%s,
                potBefore=%s, amountToCommit=%s, blindCommitted=%s,
                cardsObservable=%s, holeCards=%s, flopCards=%s,
                madeHand=%s, flushDraw=%s, straightOuts=%s,
                updatedTs=CURRENT_TIMESTAMP
            where id=%s""",
        "find_aof_decision_analysis": """select id from AofDecisionAnalyses
            where decisionId=%s and backend=%s and backendVersion=%s
              and rangeModel=%s and rangeVersion=%s and analysisVersion=%s""",
        "store_aof_decision_analysis": """insert into AofDecisionAnalyses (
                decisionId, backend, backendVersion, rangeModel, rangeVersion,
                analysisVersion, equityPpm, evChips, evBbPpm, breakEvenPpm,
                samples, stderrPpm, status, errorText
            ) values (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )""",
        "update_aof_decision_analysis": """update AofDecisionAnalyses set
                equityPpm=%s, evChips=%s, evBbPpm=%s, breakEvenPpm=%s,
                samples=%s, stderrPpm=%s, status=%s, errorText=%s,
                updatedTs=CURRENT_TIMESTAMP
            where id=%s""",
        "get_aof_decision_scope": """select p.siteId, h.startTime
            from AofDecisions d
            join Players p on p.id=d.playerId
            join Hands h on h.id=d.handId
            where d.id=%s""",
        "get_aof_range_observations": """select
                d.handId, d.playerId, p.siteId, d.category, d.role,
                d.activeOpponents, d.holeCards, h.startTime
            from AofDecisions d
            join Players p on p.id=d.playerId
            join Hands h on h.id=d.handId
            join Hands target on target.id=%s
            where p.siteId=%s
              and d.category=%s
              and d.decision='allin'
              and d.role=%s
              and d.activeOpponents=%s
              and d.cardsObservable=TRUE
              and d.holeCards is not null
              and (
                    h.startTime<target.startTime
                    or (h.startTime=target.startTime and d.handId<target.id)
                  )
            order by h.startTime desc, d.handId desc, d.id desc
            limit %s""",
        "get_aof_action_observations": """select
                d.handId, d.playerId, p.siteId, d.category, d.role,
                d.activeOpponents, d.decision, h.startTime
            from AofDecisions d
            join Players p on p.id=d.playerId
            join Hands h on h.id=d.handId
            join Hands target on target.id=%s
            where p.siteId=%s
              and d.category=%s
              and d.role=%s
              and d.activeOpponents=%s
              and d.decision in ('allin', 'fold')
              and (
                    h.startTime<target.startTime
                    or (h.startTime=target.startTime and d.handId<target.id)
                  )
            order by h.startTime desc, d.handId desc, d.id desc
            limit %s""",
        "get_aof_profile_stats": """select
                d.playerId,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end) as aof_obs,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='no made hand' then 1 else 0 end) as aof_no_made,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand<>'no made hand' then 1 else 0 end) as aof_made,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.flushDraw='nut flush draw' then 1 else 0 end) as aof_nfd,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.flushDraw='non-nut flush draw' then 1 else 0 end) as aof_non_nfd,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.straightOuts>=9 then 1 else 0 end) as aof_wrap9,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.straightOuts>=13 then 1 else 0 end) as aof_big_wrap13,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='a pair' then 1 else 0 end) as aof_pair,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='two pair' then 1 else 0 end) as aof_two_pair,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='trips' then 1 else 0 end) as aof_trips,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='a straight' then 1 else 0 end) as aof_straight,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='a flush' then 1 else 0 end) as aof_flush,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='a full house' then 1 else 0 end) as aof_full_house,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='quads' then 1 else 0 end) as aof_quads,
                sum(case when d.decision='allin' and d.cardsObservable=TRUE
                              and d.madeHand='a straight flush' then 1 else 0 end) as aof_straight_flush,
                sum(case when a.status='complete' then 1 else 0 end) as aof_known,
                sum(case when a.status='complete' then a.equityPpm else 0 end) as aof_known_equity_ppm,
                sum(case when a.status='complete' then a.evBbPpm else 0 end) as aof_known_ev_bb_ppm,
                sum(case when r.status='complete' then 1 else 0 end) as aof_range,
                sum(case when r.status='complete' then r.equityPpm else 0 end) as aof_range_equity_ppm,
                sum(case when e.status in ('weak', 'strong', 'uncertain') then 1 else 0 end)
                    as aof_decision_ev,
                sum(case when e.status='weak' then 1 else 0 end) as aof_weak,
                sum(case when e.status in ('weak', 'strong', 'uncertain')
                              then e.evBbPpm else 0 end) as aof_decision_ev_bb_ppm,
                coalesce(max(s.aof_splash_seen), 0) as aof_splash_seen,
                coalesce(max(s.aof_splash_hit), 0) as aof_splash_hit,
                coalesce(max(s.aof_splash_cents), 0) as aof_splash_cents
            from AofDecisions d
             left join AofDecisionAnalyses a
              on a.decisionId=d.id
             and a.rangeModel='actual_known'
             and a.rangeVersion=1
             and a.analysisVersion=1
             and a.backend=%s
             and a.backendVersion=%s
            left join AofDecisionAnalyses r
              on r.decisionId=d.id
             and r.rangeModel='population_observed'
             and r.rangeVersion=1
             and r.analysisVersion=1
             and r.backend=%s
             and r.backendVersion=%s
            left join AofDecisionAnalyses e
              on e.decisionId=d.id
             and e.rangeModel='population_decision_ev_prerake'
             and e.rangeVersion=1
             and e.analysisVersion=1
             and e.backend=%s
             and e.backendVersion=%s
            left join (
                select hp.playerId as splash_player_id,
                       sum(case when h.splashPot>0 then 1 else 0 end) as aof_splash_seen,
                       sum(case when hp.splashWinnings>0 then 1 else 0 end) as aof_splash_hit,
                       sum(case when hp.splashWinnings>0 then hp.splashWinnings else 0 end)
                           as aof_splash_cents
                from HandsPlayers hp
                join Hands h on h.id=hp.handId
                join Gametypes g on g.id=h.gametypeId
                where g.category=%s and hp.playerId in (<player_ids>)
                group by hp.playerId
            ) s on s.splash_player_id=d.playerId
            where d.category=%s and d.classifierVersion=%s
              and d.playerId in (<player_ids>)
            group by d.playerId""",
    }
