"""Backend-specific session HUD statistics query."""

from __future__ import annotations


def hud_session_stats_queries(db_server: str) -> dict[str, str]:
    """Return the per-hand HUD session query for a backend."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["get_stats_from_hand_session"] = """
                SELECT hp.playerId                                              AS player_id, /* playerId and seats must */
                       h.seats                                                  AS seats,     /* be first and second field */
                       hp.handId                                                AS hand_id,
                       hp.seatNo                                                AS seat,
                       p.name                                                   AS screen_name,
                       1                                                        AS n,
                       cast(hp2.street0VPIChance as SIGNED)            AS vpip_opp,
                       cast(hp2.street0VPI as SIGNED)                  AS vpip,
                       cast(hp2.street0AggrChance as SIGNED)           AS pfr_opp,
                       cast(hp2.street0Aggr as SIGNED)                 AS pfr,
                       cast(hp2.street0CalledRaiseChance as SIGNED)    AS CAR_opp_0,
                       cast(hp2.street0CalledRaiseDone as SIGNED)      AS CAR_0,
                       cast(hp2.street0_3BChance as SIGNED)            AS TB_opp_0,
                       cast(hp2.street0_3BDone as SIGNED)              AS TB_0,
                       cast(hp2.street1_3BChance as SIGNED)           AS fl3b_opp,
                       cast(hp2.street1_3BDone as SIGNED)             AS fl3b,
                       cast(hp2.street2_3BChance as SIGNED)           AS tn3b_opp,
                       cast(hp2.street2_3BDone as SIGNED)             AS tn3b,
                       cast(hp2.street3_3BChance as SIGNED)           AS rv3b_opp,
                       cast(hp2.street3_3BDone as SIGNED)             AS rv3b,
                       cast(hp2.street1_FoldTo3BChance as SIGNED)     AS ff3b_opp,
                       cast(hp2.street1_FoldTo3BDone as SIGNED)       AS ff3b,
                       cast(hp2.street2_FoldTo3BChance as SIGNED)     AS ft3b_opp,
                       cast(hp2.street2_FoldTo3BDone as SIGNED)       AS ft3b,
                       cast(hp2.street3_FoldTo3BChance as SIGNED)     AS fr3b_opp,
                       cast(hp2.street3_FoldTo3BDone as SIGNED)       AS fr3b,
                       cast(hp2.street1_4BChance as SIGNED)           AS fl4b_opp,
                       cast(hp2.street1_4BDone as SIGNED)             AS fl4b,
                       cast(hp2.street2_4BChance as SIGNED)           AS tn4b_opp,
                       cast(hp2.street2_4BDone as SIGNED)             AS tn4b,
                       cast(hp2.street3_4BChance as SIGNED)           AS rv4b_opp,
                       cast(hp2.street3_4BDone as SIGNED)             AS rv4b,
                       cast(hp2.street1OpenChance as SIGNED)          AS flopen_opp,
                       cast(hp2.street1OpenDone as SIGNED)            AS flopen,
                       cast(hp2.street2OpenChance as SIGNED)          AS tnopen_opp,
                       cast(hp2.street2OpenDone as SIGNED)            AS tnopen,
                       cast(hp2.street3OpenChance as SIGNED)          AS rvopen_opp,
                       cast(hp2.street3OpenDone as SIGNED)            AS rvopen,
                       cast(hp2.street0_4BChance as SIGNED)            AS FB_opp_0,
                       cast(hp2.street0_4BDone as SIGNED)              AS FB_0,
                       cast(hp2.street0_C4BChance as SIGNED)           AS CFB_opp_0,
                       cast(hp2.street0_C4BDone as SIGNED)             AS CFB_0,
                       cast(hp2.street0_FoldTo3BChance as SIGNED)      AS F3B_opp_0,
                       cast(hp2.street0_FoldTo3BDone as SIGNED)        AS F3B_0,
                       cast(hp2.street0_FoldTo4BChance as SIGNED)      AS F4B_opp_0,
                       cast(hp2.street0_FoldTo4BDone as SIGNED)        AS F4B_0,
                       cast(hp2.street0_SqueezeChance as SIGNED)       AS SQZ_opp_0,
                       cast(hp2.street0_SqueezeDone as SIGNED)         AS SQZ_0,
                       cast(hp2.raiseToStealChance as SIGNED)          AS RTS_opp,
                       cast(hp2.raiseToStealDone as SIGNED)            AS RTS,
                       cast(hp2.success_Steal as SIGNED)               AS SUC_ST,
                       cast(hp2.street1Seen as SIGNED)                 AS saw_f,
                       cast(hp2.street1Seen as SIGNED)                 AS saw_1,
                       cast(hp2.street2Seen as SIGNED)                 AS saw_2,
                       cast(hp2.street3Seen as SIGNED)                 AS saw_3,
                       cast(hp2.street4Seen as SIGNED)                 AS saw_4,
                       cast(hp2.sawShowdown as SIGNED)                 AS sd,
                       cast(hp2.street1Aggr as SIGNED)                 AS aggr_1,
                       cast(hp2.street2Aggr as SIGNED)                 AS aggr_2,
                       cast(hp2.street3Aggr as SIGNED)                 AS aggr_3,
                       cast(hp2.street4Aggr as SIGNED)                 AS aggr_4,
                       cast(hp2.otherRaisedStreet1 as SIGNED)          AS was_raised_1,
                       cast(hp2.otherRaisedStreet2 as SIGNED)          AS was_raised_2,
                       cast(hp2.otherRaisedStreet3 as SIGNED)          AS was_raised_3,
                       cast(hp2.otherRaisedStreet4 as SIGNED)          AS was_raised_4,
                       cast(hp2.foldToOtherRaisedStreet1 as SIGNED)    AS f_freq_1,
                       cast(hp2.foldToOtherRaisedStreet2 as SIGNED)    AS f_freq_2,
                       cast(hp2.foldToOtherRaisedStreet3 as SIGNED)    AS f_freq_3,
                       cast(hp2.foldToOtherRaisedStreet4 as SIGNED)    AS f_freq_4,
                       cast(hp2.wonWhenSeenStreet1 as SIGNED)          AS w_w_s_1,
                       cast(hp2.wonAtSD as SIGNED)                     AS wmsd,
                       cast(hp2.stealChance as SIGNED)                 AS steal_opp,
                       cast(hp2.stealDone as SIGNED)                   AS steal,
                       cast(hp2.foldSbToStealChance as SIGNED)         AS SBstolen,
                       cast(hp2.foldedSbToSteal as SIGNED)             AS SBnotDef,
                       cast(hp2.foldBbToStealChance as SIGNED)         AS BBstolen,
                       cast(hp2.foldedBbToSteal as SIGNED)             AS BBnotDef,
                       cast(hp2.street1CBChance as SIGNED)             AS CB_opp_1,
                       cast(hp2.street1CBDone as SIGNED)               AS CB_1,
                       cast(hp2.street2CBChance as SIGNED)             AS CB_opp_2,
                       cast(hp2.street2CBDone as SIGNED)               AS CB_2,
                       cast(hp2.street3CBChance as SIGNED)             AS CB_opp_3,
                       cast(hp2.street3CBDone as SIGNED)               AS CB_3,
                       cast(hp2.street4CBChance as SIGNED)             AS CB_opp_4,
                       cast(hp2.street4CBDone as SIGNED)               AS CB_4,
                       cast(hp2.foldToStreet1CBChance as SIGNED)       AS f_cb_opp_1,
                       cast(hp2.foldToStreet1CBDone as SIGNED)         AS f_cb_1,
                       cast(hp2.foldToStreet2CBChance as SIGNED)       AS f_cb_opp_2,
                       cast(hp2.foldToStreet2CBDone as SIGNED)         AS f_cb_2,
                       cast(hp2.foldToStreet3CBChance as SIGNED)       AS f_cb_opp_3,
                       cast(hp2.foldToStreet3CBDone as SIGNED)         AS f_cb_3,
                       cast(hp2.foldToStreet4CBChance as SIGNED)       AS f_cb_opp_4,
                       cast(hp2.foldToStreet4CBDone as SIGNED)         AS f_cb_4,
                       cast(hp2.totalProfit as SIGNED)                  AS net,
                       cast(gt.bigblind as SIGNED)                      AS bigblind,
                       cast(hp2.street1CheckCallRaiseChance as SIGNED) AS ccr_opp_1,
                       cast(hp2.street1CheckCallDone as SIGNED)        AS cc_1,
                       cast(hp2.street1CheckRaiseDone as SIGNED)       AS cr_1,
                       cast(hp2.street2CheckCallRaiseChance as SIGNED) AS ccr_opp_2,
                       cast(hp2.street2CheckCallDone as SIGNED)        AS cc_2,
                       cast(hp2.street2CheckRaiseDone as SIGNED)       AS cr_2,
                       cast(hp2.street3CheckCallRaiseChance as SIGNED) AS ccr_opp_3,
                       cast(hp2.street3CheckCallDone as SIGNED)        AS cc_3,
                       cast(hp2.street3CheckRaiseDone as SIGNED)       AS cr_3,
                       cast(hp2.street4CheckCallRaiseChance as SIGNED) AS ccr_opp_4,
                       cast(hp2.street4CheckCallDone as SIGNED)        AS cc_4,
                       cast(hp2.street4CheckRaiseDone as SIGNED)       AS cr_4,
                       cast(hp2.street0Calls as SIGNED)                AS call_0,
                       cast(hp2.street1Calls as SIGNED)                AS call_1,
                       cast(hp2.street2Calls as SIGNED)                AS call_2,
                       cast(hp2.street3Calls as SIGNED)                AS call_3,
                       cast(hp2.street4Calls as SIGNED)                AS call_4,
                       cast(hp2.street0Bets as SIGNED)                 AS bet_0,
                       cast(hp2.street1Bets as SIGNED)                 AS bet_1,
                       cast(hp2.street2Bets as SIGNED)                 AS bet_2,
                       cast(hp2.street3Bets as SIGNED)                 AS bet_3,
                       cast(hp2.street4Bets as SIGNED)                 AS bet_4,
                       cast(hp2.street0Raises as SIGNED)               AS raise_0,
                       cast(hp2.street1Raises as SIGNED)               AS raise_1,
                       cast(hp2.street2Raises as SIGNED)               AS raise_2,
                       cast(hp2.street3Raises as SIGNED)               AS raise_3,
                       cast(hp2.street4Raises as SIGNED)               AS raise_4,
                       hp2.street2DelayedCBChance                      AS street2DelayedCBChance,
                       hp2.street2DelayedCBDone                        AS street2DelayedCBDone,
                       hp2.street2ProbeChance                          AS street2ProbeChance,
                       hp2.street2ProbeDone                            AS street2ProbeDone
                FROM
                     Hands h
                     INNER JOIN Hands h2         ON (h2.id >= %s AND   h2.tableName = h.tableName)
                     INNER JOIN HandsPlayers hp  ON (h.id = hp.handId)         /* players in this hand */
                     INNER JOIN HandsPlayers hp2 ON (hp2.playerId+0 = hp.playerId+0 AND (hp2.handId = h2.id+0))  /* other hands by these players */
                     INNER JOIN Players p        ON (p.id = hp2.PlayerId+0)
                     INNER JOIN Gametypes gt     ON (gt.id = h2.gametypeId)
                WHERE hp.handId = %s
                /* check activeseats once this data returned (don't want to do that here as it might
                   assume a session ended just because the number of seats dipped for a few hands)
                */
                AND   (   /* 2 separate parts for hero and opponents */
                          (    hp2.playerId != %s
                           AND h2.seats between %s and %s
                          )
                       OR
                          (    hp2.playerId = %s
                           AND h2.seats between %s and %s
                          )
                      )
                ORDER BY h.startTime desc, hp2.PlayerId
                /* order rows by handstart descending so that we can stop reading rows when
                   there's a gap over X minutes between hands (ie. when we get back to start of
                   the session */
            """
    elif db_server == "postgresql":
        query["get_stats_from_hand_session"] = """
                SELECT hp.playerId                                              AS player_id,
                       hp.handId                                                AS hand_id,
                       hp.seatNo                                                AS seat,
                       p.name                                                   AS screen_name,
                       h.seats                                                  AS seats,
                       1                                                        AS n,
                       cast(hp2.street0VPIChance as <signed>integer)            AS vpip_opp,
                       cast(hp2.street0VPI as <signed>integer)                  AS vpip,
                       cast(hp2.street0AggrChance as <signed>integer)           AS pfr_opp,
                       cast(hp2.street0Aggr as <signed>integer)                 AS pfr,
                       cast(hp2.street0CalledRaiseChance as <signed>integer)    AS CAR_opp_0,
                       cast(hp2.street0CalledRaiseDone as <signed>integer)      AS CAR_0,
                       cast(hp2.street0_3BChance as <signed>integer)            AS TB_opp_0,
                       cast(hp2.street0_3BDone as <signed>integer)              AS TB_0,
                       cast(hp2.street1_3BChance as <signed>integer)           AS fl3b_opp,
                       cast(hp2.street1_3BDone as <signed>integer)             AS fl3b,
                       cast(hp2.street2_3BChance as <signed>integer)           AS tn3b_opp,
                       cast(hp2.street2_3BDone as <signed>integer)             AS tn3b,
                       cast(hp2.street3_3BChance as <signed>integer)           AS rv3b_opp,
                       cast(hp2.street3_3BDone as <signed>integer)             AS rv3b,
                       cast(hp2.street1_FoldTo3BChance as <signed>integer)     AS ff3b_opp,
                       cast(hp2.street1_FoldTo3BDone as <signed>integer)       AS ff3b,
                       cast(hp2.street2_FoldTo3BChance as <signed>integer)     AS ft3b_opp,
                       cast(hp2.street2_FoldTo3BDone as <signed>integer)       AS ft3b,
                       cast(hp2.street3_FoldTo3BChance as <signed>integer)     AS fr3b_opp,
                       cast(hp2.street3_FoldTo3BDone as <signed>integer)       AS fr3b,
                       cast(hp2.street1_4BChance as <signed>integer)           AS fl4b_opp,
                       cast(hp2.street1_4BDone as <signed>integer)             AS fl4b,
                       cast(hp2.street2_4BChance as <signed>integer)           AS tn4b_opp,
                       cast(hp2.street2_4BDone as <signed>integer)             AS tn4b,
                       cast(hp2.street3_4BChance as <signed>integer)           AS rv4b_opp,
                       cast(hp2.street3_4BDone as <signed>integer)             AS rv4b,
                       cast(hp2.street1OpenChance as <signed>integer)          AS flopen_opp,
                       cast(hp2.street1OpenDone as <signed>integer)            AS flopen,
                       cast(hp2.street2OpenChance as <signed>integer)          AS tnopen_opp,
                       cast(hp2.street2OpenDone as <signed>integer)            AS tnopen,
                       cast(hp2.street3OpenChance as <signed>integer)          AS rvopen_opp,
                       cast(hp2.street3OpenDone as <signed>integer)            AS rvopen,
                       cast(hp2.street0_4BChance as <signed>integer)            AS FB_opp_0,
                       cast(hp2.street0_4BDone as <signed>integer)              AS FB_0,
                       cast(hp2.street0_C4BChance as <signed>integer)           AS CFB_opp_0,
                       cast(hp2.street0_C4BDone as <signed>integer)             AS CFB_0,
                       cast(hp2.street0_FoldTo3BChance as <signed>integer)      AS F3B_opp_0,
                       cast(hp2.street0_FoldTo3BDone as <signed>integer)        AS F3B_0,
                       cast(hp2.street0_FoldTo4BChance as <signed>integer)      AS F4B_opp_0,
                       cast(hp2.street0_FoldTo4BDone as <signed>integer)        AS F4B_0,
                       cast(hp2.street0_SqueezeChance as <signed>integer)       AS SQZ_opp_0,
                       cast(hp2.street0_SqueezeDone as <signed>integer)         AS SQZ_0,
                       cast(hp2.raiseToStealChance as <signed>integer)          AS RTS_opp,
                       cast(hp2.raiseToStealDone as <signed>integer)            AS RTS,
                       cast(hp2.success_Steal as <signed>integer)               AS SUC_ST,
                       cast(hp2.street1Seen as <signed>integer)                 AS saw_f,
                       cast(hp2.street1Seen as <signed>integer)                 AS saw_1,
                       cast(hp2.street2Seen as <signed>integer)                 AS saw_2,
                       cast(hp2.street3Seen as <signed>integer)                 AS saw_3,
                       cast(hp2.street4Seen as <signed>integer)                 AS saw_4,
                       cast(hp2.sawShowdown as <signed>integer)                 AS sd,
                       cast(hp2.street1Aggr as <signed>integer)                 AS aggr_1,
                       cast(hp2.street2Aggr as <signed>integer)                 AS aggr_2,
                       cast(hp2.street3Aggr as <signed>integer)                 AS aggr_3,
                       cast(hp2.street4Aggr as <signed>integer)                 AS aggr_4,
                       cast(hp2.otherRaisedStreet1 as <signed>integer)          AS was_raised_1,
                       cast(hp2.otherRaisedStreet2 as <signed>integer)          AS was_raised_2,
                       cast(hp2.otherRaisedStreet3 as <signed>integer)          AS was_raised_3,
                       cast(hp2.otherRaisedStreet4 as <signed>integer)          AS was_raised_4,
                       cast(hp2.foldToOtherRaisedStreet1 as <signed>integer)    AS f_freq_1,
                       cast(hp2.foldToOtherRaisedStreet2 as <signed>integer)    AS f_freq_2,
                       cast(hp2.foldToOtherRaisedStreet3 as <signed>integer)    AS f_freq_3,
                       cast(hp2.foldToOtherRaisedStreet4 as <signed>integer)    AS f_freq_4,
                       cast(hp2.wonWhenSeenStreet1 as <signed>integer)          AS w_w_s_1,
                       cast(hp2.wonAtSD as <signed>integer)                     AS wmsd,
                       cast(hp2.stealChance as <signed>integer)                 AS steal_opp,
                       cast(hp2.stealDone as <signed>integer)                   AS steal,
                       cast(hp2.foldSbToStealChance as <signed>integer)         AS SBstolen,
                       cast(hp2.foldedSbToSteal as <signed>integer)             AS SBnotDef,
                       cast(hp2.foldBbToStealChance as <signed>integer)         AS BBstolen,
                       cast(hp2.foldedBbToSteal as <signed>integer)             AS BBnotDef,
                       cast(hp2.street1CBChance as <signed>integer)             AS CB_opp_1,
                       cast(hp2.street1CBDone as <signed>integer)               AS CB_1,
                       cast(hp2.street2CBChance as <signed>integer)             AS CB_opp_2,
                       cast(hp2.street2CBDone as <signed>integer)               AS CB_2,
                       cast(hp2.street3CBChance as <signed>integer)             AS CB_opp_3,
                       cast(hp2.street3CBDone as <signed>integer)               AS CB_3,
                       cast(hp2.street4CBChance as <signed>integer)             AS CB_opp_4,
                       cast(hp2.street4CBDone as <signed>integer)               AS CB_4,
                       cast(hp2.foldToStreet1CBChance as <signed>integer)       AS f_cb_opp_1,
                       cast(hp2.foldToStreet1CBDone as <signed>integer)         AS f_cb_1,
                       cast(hp2.foldToStreet2CBChance as <signed>integer)       AS f_cb_opp_2,
                       cast(hp2.foldToStreet2CBDone as <signed>integer)         AS f_cb_2,
                       cast(hp2.foldToStreet3CBChance as <signed>integer)       AS f_cb_opp_3,
                       cast(hp2.foldToStreet3CBDone as <signed>integer)         AS f_cb_3,
                       cast(hp2.foldToStreet4CBChance as <signed>integer)       AS f_cb_opp_4,
                       cast(hp2.foldToStreet4CBDone as <signed>integer)         AS f_cb_4,
                       cast(hp2.totalProfit as <signed>bigint)                  AS net,
                       cast(gt.bigblind as <signed>bigint)                      AS bigblind,
                       cast(hp2.street1CheckCallRaiseChance as <signed>integer) AS ccr_opp_1,
                       cast(hp2.street1CheckCallDone as <signed>integer)        AS cc_1,
                       cast(hp2.street1CheckRaiseDone as <signed>integer)       AS cr_1,
                       cast(hp2.street2CheckCallRaiseChance as <signed>integer) AS ccr_opp_2,
                       cast(hp2.street2CheckCallDone as <signed>integer)        AS cc_2,
                       cast(hp2.street2CheckRaiseDone as <signed>integer)       AS cr_2,
                       cast(hp2.street3CheckCallRaiseChance as <signed>integer) AS ccr_opp_3,
                       cast(hp2.street3CheckCallDone as <signed>integer)        AS cc_3,
                       cast(hp2.street3CheckRaiseDone as <signed>integer)       AS cr_3,
                       cast(hp2.street4CheckCallRaiseChance as <signed>integer) AS ccr_opp_4,
                       cast(hp2.street4CheckCallDone as <signed>integer)        AS cc_4,
                       cast(hp2.street4CheckRaiseDone as <signed>integer)       AS cr_4,
                       cast(hp2.street0Calls as <signed>integer)                AS call_0,
                       cast(hp2.street1Calls as <signed>integer)                AS call_1,
                       cast(hp2.street2Calls as <signed>integer)                AS call_2,
                       cast(hp2.street3Calls as <signed>integer)                AS call_3,
                       cast(hp2.street4Calls as <signed>integer)                AS call_4,
                       cast(hp2.street0Bets as <signed>integer)                 AS bet_0,
                       cast(hp2.street1Bets as <signed>integer)                 AS bet_1,
                       cast(hp2.street2Bets as <signed>integer)                 AS bet_2,
                       cast(hp2.street3Bets as <signed>integer)                 AS bet_3,
                       cast(hp2.street4Bets as <signed>integer)                 AS bet_4,
                       cast(hp2.street0Raises as <signed>integer)               AS raise_0,
                       cast(hp2.street1Raises as <signed>integer)               AS raise_1,
                       cast(hp2.street2Raises as <signed>integer)               AS raise_2,
                       cast(hp2.street3Raises as <signed>integer)               AS raise_3,
                       cast(hp2.street4Raises as <signed>integer)               AS raise_4,
                       hp2.street2DelayedCBChance                      AS street2DelayedCBChance,
                       hp2.street2DelayedCBDone                        AS street2DelayedCBDone,
                       hp2.street2ProbeChance                          AS street2ProbeChance,
                       hp2.street2ProbeDone                            AS street2ProbeDone
                     FROM Hands h                                                  /* this hand */
                     INNER JOIN Hands h2         ON (    h2.id >= %s           /* other hands */
                                                     AND h2.tableName = h.tableName)
                     INNER JOIN HandsPlayers hp  ON (h.id = hp.handId)        /* players in this hand */
                     INNER JOIN HandsPlayers hp2 ON (    hp2.playerId+0 = hp.playerId+0
                                                     AND hp2.handId = h2.id)  /* other hands by these players */
                     INNER JOIN Players p        ON (p.id = hp2.PlayerId+0)
                     INNER JOIN Gametypes gt     ON (gt.id = h2.gametypeId)
                WHERE h.id = %s
                /* check activeseats once this data returned (don't want to do that here as it might
                   assume a session ended just because the number of seats dipped for a few hands)
                */
                AND   (   /* 2 separate parts for hero and opponents */
                          (    hp2.playerId != %s
                           AND h2.seats between %s and %s
                          )
                       OR
                          (    hp2.playerId = %s
                           AND h2.seats between %s and %s
                          )
                      )
                ORDER BY h.startTime desc, hp2.PlayerId
                /* order rows by handstart descending so that we can stop reading rows when
                   there's a gap over X minutes between hands (ie. when we get back to start of
                   the session */
            """
    elif db_server == "sqlite":
        query["get_stats_from_hand_session"] = """
                SELECT hp.playerId                                              AS player_id,
                       hp.handId                                                AS hand_id,
                       hp.seatNo                                                AS seat,
                       p.name                                                   AS screen_name,
                       h.seats                                                  AS seats,
                       1                                                        AS n,
                       cast(hp2.street0VPIChance as <signed>integer)            AS vpip_opp,
                       cast(hp2.street0VPI as <signed>integer)                  AS vpip,
                       cast(hp2.street0AggrChance as <signed>integer)           AS pfr_opp,
                       cast(hp2.street0Aggr as <signed>integer)                 AS pfr,
                       cast(hp2.street0CalledRaiseChance as <signed>integer)    AS CAR_opp_0,
                       cast(hp2.street0CalledRaiseDone as <signed>integer)      AS CAR_0,
                       cast(hp2.street0_3BChance as <signed>integer)            AS TB_opp_0,
                       cast(hp2.street0_3BDone as <signed>integer)              AS TB_0,
                       cast(hp2.street1_3BChance as <signed>integer)           AS fl3b_opp,
                       cast(hp2.street1_3BDone as <signed>integer)             AS fl3b,
                       cast(hp2.street2_3BChance as <signed>integer)           AS tn3b_opp,
                       cast(hp2.street2_3BDone as <signed>integer)             AS tn3b,
                       cast(hp2.street3_3BChance as <signed>integer)           AS rv3b_opp,
                       cast(hp2.street3_3BDone as <signed>integer)             AS rv3b,
                       cast(hp2.street1_FoldTo3BChance as <signed>integer)     AS ff3b_opp,
                       cast(hp2.street1_FoldTo3BDone as <signed>integer)       AS ff3b,
                       cast(hp2.street2_FoldTo3BChance as <signed>integer)     AS ft3b_opp,
                       cast(hp2.street2_FoldTo3BDone as <signed>integer)       AS ft3b,
                       cast(hp2.street3_FoldTo3BChance as <signed>integer)     AS fr3b_opp,
                       cast(hp2.street3_FoldTo3BDone as <signed>integer)       AS fr3b,
                       cast(hp2.street1_4BChance as <signed>integer)           AS fl4b_opp,
                       cast(hp2.street1_4BDone as <signed>integer)             AS fl4b,
                       cast(hp2.street2_4BChance as <signed>integer)           AS tn4b_opp,
                       cast(hp2.street2_4BDone as <signed>integer)             AS tn4b,
                       cast(hp2.street3_4BChance as <signed>integer)           AS rv4b_opp,
                       cast(hp2.street3_4BDone as <signed>integer)             AS rv4b,
                       cast(hp2.street1OpenChance as <signed>integer)          AS flopen_opp,
                       cast(hp2.street1OpenDone as <signed>integer)            AS flopen,
                       cast(hp2.street2OpenChance as <signed>integer)          AS tnopen_opp,
                       cast(hp2.street2OpenDone as <signed>integer)            AS tnopen,
                       cast(hp2.street3OpenChance as <signed>integer)          AS rvopen_opp,
                       cast(hp2.street3OpenDone as <signed>integer)            AS rvopen,
                       cast(hp2.street0_4BChance as <signed>integer)            AS FB_opp_0,
                       cast(hp2.street0_4BDone as <signed>integer)              AS FB_0,
                       cast(hp2.street0_C4BChance as <signed>integer)           AS CFB_opp_0,
                       cast(hp2.street0_C4BDone as <signed>integer)             AS CFB_0,
                       cast(hp2.street0_FoldTo3BChance as <signed>integer)      AS F3B_opp_0,
                       cast(hp2.street0_FoldTo3BDone as <signed>integer)        AS F3B_0,
                       cast(hp2.street0_FoldTo4BChance as <signed>integer)      AS F4B_opp_0,
                       cast(hp2.street0_FoldTo4BDone as <signed>integer)        AS F4B_0,
                       cast(hp2.street0_SqueezeChance as <signed>integer)       AS SQZ_opp_0,
                       cast(hp2.street0_SqueezeDone as <signed>integer)         AS SQZ_0,
                       cast(hp2.raiseToStealChance as <signed>integer)          AS RTS_opp,
                       cast(hp2.raiseToStealDone as <signed>integer)            AS RTS,
                       cast(hp2.success_Steal as <signed>integer)               AS SUC_ST,
                       cast(hp2.street1Seen as <signed>integer)                 AS saw_f,
                       cast(hp2.street1Seen as <signed>integer)                 AS saw_1,
                       cast(hp2.street2Seen as <signed>integer)                 AS saw_2,
                       cast(hp2.street3Seen as <signed>integer)                 AS saw_3,
                       cast(hp2.street4Seen as <signed>integer)                 AS saw_4,
                       cast(hp2.sawShowdown as <signed>integer)                 AS sd,
                       cast(hp2.street1Aggr as <signed>integer)                 AS aggr_1,
                       cast(hp2.street2Aggr as <signed>integer)                 AS aggr_2,
                       cast(hp2.street3Aggr as <signed>integer)                 AS aggr_3,
                       cast(hp2.street4Aggr as <signed>integer)                 AS aggr_4,
                       cast(hp2.otherRaisedStreet1 as <signed>integer)          AS was_raised_1,
                       cast(hp2.otherRaisedStreet2 as <signed>integer)          AS was_raised_2,
                       cast(hp2.otherRaisedStreet3 as <signed>integer)          AS was_raised_3,
                       cast(hp2.otherRaisedStreet4 as <signed>integer)          AS was_raised_4,
                       cast(hp2.foldToOtherRaisedStreet1 as <signed>integer)    AS f_freq_1,
                       cast(hp2.foldToOtherRaisedStreet2 as <signed>integer)    AS f_freq_2,
                       cast(hp2.foldToOtherRaisedStreet3 as <signed>integer)    AS f_freq_3,
                       cast(hp2.foldToOtherRaisedStreet4 as <signed>integer)    AS f_freq_4,
                       cast(hp2.wonWhenSeenStreet1 as <signed>integer)          AS w_w_s_1,
                       cast(hp2.wonAtSD as <signed>integer)                     AS wmsd,
                       cast(hp2.stealChance as <signed>integer)                 AS steal_opp,
                       cast(hp2.stealDone as <signed>integer)                   AS steal,
                       cast(hp2.foldSbToStealChance as <signed>integer)         AS SBstolen,
                       cast(hp2.foldedSbToSteal as <signed>integer)             AS SBnotDef,
                       cast(hp2.foldBbToStealChance as <signed>integer)         AS BBstolen,
                       cast(hp2.foldedBbToSteal as <signed>integer)             AS BBnotDef,
                       cast(hp2.street1CBChance as <signed>integer)             AS CB_opp_1,
                       cast(hp2.street1CBDone as <signed>integer)               AS CB_1,
                       cast(hp2.street2CBChance as <signed>integer)             AS CB_opp_2,
                       cast(hp2.street2CBDone as <signed>integer)               AS CB_2,
                       cast(hp2.street3CBChance as <signed>integer)             AS CB_opp_3,
                       cast(hp2.street3CBDone as <signed>integer)               AS CB_3,
                       cast(hp2.street4CBChance as <signed>integer)             AS CB_opp_4,
                       cast(hp2.street4CBDone as <signed>integer)               AS CB_4,
                       cast(hp2.foldToStreet1CBChance as <signed>integer)       AS f_cb_opp_1,
                       cast(hp2.foldToStreet1CBDone as <signed>integer)         AS f_cb_1,
                       cast(hp2.foldToStreet2CBChance as <signed>integer)       AS f_cb_opp_2,
                       cast(hp2.foldToStreet2CBDone as <signed>integer)         AS f_cb_2,
                       cast(hp2.foldToStreet3CBChance as <signed>integer)       AS f_cb_opp_3,
                       cast(hp2.foldToStreet3CBDone as <signed>integer)         AS f_cb_3,
                       cast(hp2.foldToStreet4CBChance as <signed>integer)       AS f_cb_opp_4,
                       cast(hp2.foldToStreet4CBDone as <signed>integer)         AS f_cb_4,
                       cast(hp2.totalProfit as <signed>integer)                 AS net,
                       cast(gt.bigblind as <signed>integer)                     AS bigblind,
                       cast(hp2.street1CheckCallRaiseChance as <signed>integer) AS ccr_opp_1,
                       cast(hp2.street1CheckCallDone as <signed>integer)        AS cc_1,
                       cast(hp2.street1CheckRaiseDone as <signed>integer)       AS cr_1,
                       cast(hp2.street2CheckCallRaiseChance as <signed>integer) AS ccr_opp_2,
                       cast(hp2.street2CheckCallDone as <signed>integer)        AS cc_2,
                       cast(hp2.street2CheckRaiseDone as <signed>integer)       AS cr_2,
                       cast(hp2.street3CheckCallRaiseChance as <signed>integer) AS ccr_opp_3,
                       cast(hp2.street3CheckCallDone as <signed>integer)        AS cc_3,
                       cast(hp2.street3CheckRaiseDone as <signed>integer)       AS cr_3,
                       cast(hp2.street4CheckCallRaiseChance as <signed>integer) AS ccr_opp_4,
                       cast(hp2.street4CheckCallDone as <signed>integer)        AS cc_4,
                       cast(hp2.street4CheckRaiseDone as <signed>integer)       AS cr_4,
                       cast(hp2.street0Calls as <signed>integer)                AS call_0,
                       cast(hp2.street1Calls as <signed>integer)                AS call_1,
                       cast(hp2.street2Calls as <signed>integer)                AS call_2,
                       cast(hp2.street3Calls as <signed>integer)                AS call_3,
                       cast(hp2.street4Calls as <signed>integer)                AS call_4,
                       cast(hp2.street0Bets as <signed>integer)                 AS bet_0,
                       cast(hp2.street1Bets as <signed>integer)                 AS bet_1,
                       cast(hp2.street2Bets as <signed>integer)                 AS bet_2,
                       cast(hp2.street3Bets as <signed>integer)                 AS bet_3,
                       cast(hp2.street4Bets as <signed>integer)                 AS bet_4,
                       cast(hp2.street0Raises as <signed>integer)               AS raise_0,
                       cast(hp2.street1Raises as <signed>integer)               AS raise_1,
                       cast(hp2.street2Raises as <signed>integer)               AS raise_2,
                       cast(hp2.street3Raises as <signed>integer)               AS raise_3,
                       cast(hp2.street4Raises as <signed>integer)               AS raise_4,
                       hp2.street2DelayedCBChance                      AS street2DelayedCBChance,
                       hp2.street2DelayedCBDone                        AS street2DelayedCBDone,
                       hp2.street2ProbeChance                          AS street2ProbeChance,
                       hp2.street2ProbeDone                            AS street2ProbeDone
                     FROM Hands h                                                  /* this hand */
                     INNER JOIN Hands h2         ON (    h2.id >= %s           /* other hands */
                                                     AND h2.tableName = h.tableName)
                     INNER JOIN HandsPlayers hp  ON (h.id = hp.handId)        /* players in this hand */
                     INNER JOIN HandsPlayers hp2 ON (    hp2.playerId+0 = hp.playerId+0
                                                     AND hp2.handId = h2.id)  /* other hands by these players */
                     INNER JOIN Players p        ON (p.id = hp2.PlayerId+0)
                     INNER JOIN Gametypes gt     ON (gt.id = h2.gametypeId)
                WHERE h.id = %s
                /* check activeseats once this data returned (don't want to do that here as it might
                   assume a session ended just because the number of seats dipped for a few hands)
                */
                AND   (   /* 2 separate parts for hero and opponents */
                          (    hp2.playerId != %s
                           AND h2.seats between %s and %s
                          )
                       OR
                          (    hp2.playerId = %s
                           AND h2.seats between %s and %s
                          )
                      )
                ORDER BY h.startTime desc, hp2.PlayerId
                /* order rows by handstart descending so that we can stop reading rows when
                   there's a gap over X minutes between hands (ie. when we get back to start of
                   the session */
            """
    return query

