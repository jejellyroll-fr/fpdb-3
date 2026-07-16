"""Blind-level aggregated current-hand HUD statistics query."""

from __future__ import annotations


def hud_aggregated_stats_queries() -> dict[str, str]:
    """Return the current-hand HUD query aggregated across blind levels."""
    query: dict[str, str] = {}
    query["get_stats_from_hand_aggregated"] = """
            /* explain query plan */
            SELECT hc.playerId                         AS player_id,
                   max(case when hc.gametypeId = h.gametypeId
                            then hp.seatNo
                            else -1
                       end)                            AS seat,
                   p.name                              AS screen_name,
                   sum(hc.n)                           AS n,
                   sum(hc.street0VPIChance)            AS vpip_opp,
                   sum(hc.street0VPI)                  AS vpip,
                   sum(hc.street0AggrChance)           AS pfr_opp,
                   sum(hc.street0Aggr)                 AS pfr,
                   sum(hc.street0CalledRaiseChance)    AS CAR_opp_0,
                   sum(hc.street0CalledRaiseDone)      AS CAR_0,
                   sum(hc.street0_3BChance)            AS TB_opp_0,
                   sum(hc.street0_3BDone)              AS TB_0,
                   sum(hc.street1_3BChance)            AS fl3b_opp,
                   sum(hc.street1_3BDone)              AS fl3b,
                   sum(hc.street2_3BChance)            AS tn3b_opp,
                   sum(hc.street2_3BDone)              AS tn3b,
                   sum(hc.street3_3BChance)            AS rv3b_opp,
                   sum(hc.street3_3BDone)              AS rv3b,
                sum(hc.street1_FoldTo3BChance)      AS ff3b_opp,
                sum(hc.street1_FoldTo3BDone)        AS ff3b,
                sum(hc.street2_FoldTo3BChance)      AS ft3b_opp,
                sum(hc.street2_FoldTo3BDone)        AS ft3b,
                sum(hc.street3_FoldTo3BChance)      AS fr3b_opp,
                sum(hc.street3_FoldTo3BDone)        AS fr3b,
                   sum(hc.street1_4BChance)            AS fl4b_opp,
                   sum(hc.street1_4BDone)              AS fl4b,
                   sum(hc.street2_4BChance)            AS tn4b_opp,
                   sum(hc.street2_4BDone)              AS tn4b,
                   sum(hc.street3_4BChance)            AS rv4b_opp,
                   sum(hc.street3_4BDone)              AS rv4b,
                   sum(hc.street1OpenChance)           AS flopen_opp,
                   sum(hc.street1OpenDone)             AS flopen,
                   sum(hc.street2OpenChance)           AS tnopen_opp,
                   sum(hc.street2OpenDone)             AS tnopen,
                   sum(hc.street3OpenChance)           AS rvopen_opp,
                   sum(hc.street3OpenDone)             AS rvopen,
                   sum(hc.flg_f_fold)                  AS f_fold,
                   sum(hc.flg_t_fold)                  AS t_fold,
                   sum(hc.flg_r_fold)                  AS r_fold,
                   sum(hc.street1FirstRaise)           AS f_first_raise,
                   sum(hc.street2FirstRaise)           AS t_first_raise,
                   sum(hc.street3FirstRaise)           AS r_first_raise,
                   sum(hc.street0FaceRaise)            AS p_face_raise,
                   sum(hc.street1FaceRaise)            AS f_face_raise,
                   sum(hc.street2FaceRaise)            AS t_face_raise,
                   sum(hc.street3FaceRaise)            AS r_face_raise,
                   sum(hc.flg_t_float_opp)             AS float_turn_chance,
                   sum(hc.flg_t_float)                 AS float_turn_done,
                   sum(hc.flg_t_float_def_opp)         AS float_turn_def_opp,
                   sum(hc.flg_r_float_opp)             AS float_river_chance,
                   sum(hc.flg_r_float)                 AS float_river_done,
                   sum(hc.flg_r_float_def_opp)         AS float_river_def_opp,
                   sum(hc.street0_FoldToSqueezeChance) AS sqzdef_opp,
                   sum(hc.street0_FoldToSqueezeDone)   AS sqzdef_fold,
                   sum(hc.street0_FaceLimpers)         AS face_limpers,
                   sum(hc.cnt_gp_open_opp)            AS gp_open_opp,
                   sum(hc.cnt_gp_2x)                  AS gp_2x,
                   sum(hc.cnt_gp_os)                  AS gp_os,
                   sum(hc.cnt_gp_limp)                AS gp_limp,
                   sum(hc.flg_blind_ds)                AS blind_ds,
                   sum(hc.flg_blind_db)                AS blind_db,
                   sum(hc.flg_blind_k)                 AS straddle_done,
                   sum(hc.flg_faced_allin)             AS faced_allin,
                   sum(hc.flg_fold_to_allin)           AS fold_allin,
                   sum(hc.cnt_f_bet_facing)            AS f_bet_facing_cnt,
                   sum(hc.val_f_bet_facing_bp)         AS f_bet_facing_bp,
                   sum(hc.cnt_t_bet_facing)            AS t_bet_facing_cnt,
                   sum(hc.val_t_bet_facing_bp)         AS t_bet_facing_bp,
                   sum(hc.cnt_r_bet_facing)            AS r_bet_facing_cnt,
                   sum(hc.val_r_bet_facing_bp)         AS r_bet_facing_bp,
                   sum(hc.cnt_p_2bet_facing)           AS p_2bet_facing_cnt,
                   sum(hc.val_p_2bet_facing_bp)        AS p_2bet_facing_bp,
                   sum(hc.cnt_p_3bet_facing)           AS p_3bet_facing_cnt,
                   sum(hc.val_p_3bet_facing_bp)        AS p_3bet_facing_bp,
                   sum(hc.cnt_p_4bet_facing)           AS p_4bet_facing_cnt,
                   sum(hc.val_p_4bet_facing_bp)        AS p_4bet_facing_bp,
                   sum(hc.cnt_f_bet_made)              AS f_bet_made_cnt,
                   sum(hc.val_f_bet_made_bp)           AS f_bet_made_bp,
                   sum(hc.cnt_t_bet_made)              AS t_bet_made_cnt,
                   sum(hc.val_t_bet_made_bp)           AS t_bet_made_bp,
                   sum(hc.cnt_r_bet_made)              AS r_bet_made_cnt,
                   sum(hc.val_r_bet_made_bp)           AS r_bet_made_bp,
                   sum(hc.cnt_f_spr)                   AS f_spr_cnt,
                   sum(hc.val_f_spr)                   AS f_spr_val,
                   sum(hc.cnt_t_spr)                   AS t_spr_cnt,
                   sum(hc.val_t_spr)                   AS t_spr_val,
                   sum(hc.cnt_r_spr)                   AS r_spr_cnt,
                   sum(hc.val_r_spr)                   AS r_spr_val,
                   sum(hc.cnt_p_raise_made)            AS p_raise_made_cnt,
                   sum(hc.val_p_raise_made_bp)         AS p_raise_made_bp,
                   sum(hc.cnt_f_raise_made)            AS f_raise_made_cnt,
                   sum(hc.val_f_raise_made_bp)         AS f_raise_made_bp,
                   sum(hc.cnt_t_raise_made)            AS t_raise_made_cnt,
                   sum(hc.val_t_raise_made_bp)         AS t_raise_made_bp,
                   sum(hc.cnt_r_raise_made)            AS r_raise_made_cnt,
                   sum(hc.val_r_raise_made_bp)         AS r_raise_made_bp,
                   sum(hc.cnt_f_2bet_facing)           AS f_2bet_facing_cnt,
                   sum(hc.val_f_2bet_facing_bp)        AS f_2bet_facing_bp,
                   sum(hc.cnt_f_3bet_facing)           AS f_3bet_facing_cnt,
                   sum(hc.val_f_3bet_facing_bp)        AS f_3bet_facing_bp,
                   sum(hc.cnt_f_4bet_facing)           AS f_4bet_facing_cnt,
                   sum(hc.val_f_4bet_facing_bp)        AS f_4bet_facing_bp,
                   sum(hc.cnt_t_2bet_facing)           AS t_2bet_facing_cnt,
                   sum(hc.val_t_2bet_facing_bp)        AS t_2bet_facing_bp,
                   sum(hc.cnt_t_3bet_facing)           AS t_3bet_facing_cnt,
                   sum(hc.val_t_3bet_facing_bp)        AS t_3bet_facing_bp,
                   sum(hc.cnt_t_4bet_facing)           AS t_4bet_facing_cnt,
                   sum(hc.val_t_4bet_facing_bp)        AS t_4bet_facing_bp,
                   sum(hc.cnt_r_2bet_facing)           AS r_2bet_facing_cnt,
                   sum(hc.val_r_2bet_facing_bp)        AS r_2bet_facing_bp,
                   sum(hc.cnt_r_3bet_facing)           AS r_3bet_facing_cnt,
                   sum(hc.val_r_3bet_facing_bp)        AS r_3bet_facing_bp,
                   sum(hc.cnt_r_4bet_facing)           AS r_4bet_facing_cnt,
                   sum(hc.val_r_4bet_facing_bp)        AS r_4bet_facing_bp,
                   sum(hc.amt_blind)                 AS amt_blind,
                   sum(hc.amt_bet_p)                 AS amt_bet_p,
                   sum(hc.amt_bet_f)                 AS amt_bet_f,
                   sum(hc.amt_bet_t)                 AS amt_bet_t,
                   sum(hc.amt_bet_r)                 AS amt_bet_r,
                   sum(hc.amt_bet_ttl)               AS amt_bet_ttl,
                   sum(hc.cnt_p_raise_facing)        AS p_raise_facing_cnt,
                   sum(hc.val_p_raise_facing_bp)     AS p_raise_facing_bp,
                   sum(hc.cnt_f_raise_facing)        AS f_raise_facing_cnt,
                   sum(hc.val_f_raise_facing_bp)     AS f_raise_facing_bp,
                   sum(hc.cnt_t_raise_facing)        AS t_raise_facing_cnt,
                   sum(hc.val_t_raise_facing_bp)     AS t_raise_facing_bp,
                   sum(hc.cnt_r_raise_facing)        AS r_raise_facing_cnt,
                   sum(hc.val_r_raise_facing_bp)     AS r_raise_facing_bp,
                   sum(hc.cnt_p_raise_made_2)        AS p_raise_made_2_cnt,
                   sum(hc.val_p_raise_made_2_bp)     AS p_raise_made_2_bp,
                   sum(hc.cnt_f_raise_made_2)        AS f_raise_made_2_cnt,
                   sum(hc.val_f_raise_made_2_bp)     AS f_raise_made_2_bp,
                   sum(hc.cnt_t_raise_made_2)        AS t_raise_made_2_cnt,
                   sum(hc.val_t_raise_made_2_bp)     AS t_raise_made_2_bp,
                   sum(hc.cnt_r_raise_made_2)        AS r_raise_made_2_cnt,
                   sum(hc.val_r_raise_made_2_bp)     AS r_raise_made_2_bp,
                   sum(hc.cnt_p_5bet_facing)         AS p_5bet_facing_cnt,
                   sum(hc.val_p_5bet_facing_bp)      AS p_5bet_facing_bp,
                   sum(hc.street0_4BChance)            AS FB_opp_0,
                   sum(hc.street0_4BDone)              AS FB_0,
                   sum(hc.street0_C4BChance)           AS CFB_opp_0,
                   sum(hc.street0_C4BDone)             AS CFB_0,
                   sum(hc.street0_FoldTo3BChance)      AS F3B_opp_0,
                   sum(hc.street0_FoldTo3BDone)        AS F3B_0,
                   sum(hc.street0_FoldTo4BChance)      AS F4B_opp_0,
                   sum(hc.street0_FoldTo4BDone)        AS F4B_0,
                   sum(hc.street0_SqueezeChance)       AS SQZ_opp_0,
                   sum(hc.street0_SqueezeDone)         AS SQZ_0,
                   sum(hc.raiseToStealChance)          AS RTS_opp,
                   sum(hc.raiseToStealDone)            AS RTS,
                   sum(hc.success_Steal)               AS SUC_ST,
                   sum(hc.street1Seen)                 AS saw_f,
                   sum(hc.street1Seen)                 AS saw_1,
                   sum(hc.street2Seen)                 AS saw_2,
                   sum(hc.street3Seen)                 AS saw_3,
                   sum(hc.street4Seen)                 AS saw_4,
                   sum(hc.sawShowdown)                 AS sd,
                   sum(hc.street1Aggr)                 AS aggr_1,
                   sum(hc.street2Aggr)                 AS aggr_2,
                   sum(hc.street3Aggr)                 AS aggr_3,
                   sum(hc.street4Aggr)                 AS aggr_4,
                   sum(hc.otherRaisedStreet1)          AS was_raised_1,
                   sum(hc.otherRaisedStreet2)          AS was_raised_2,
                   sum(hc.otherRaisedStreet3)          AS was_raised_3,
                   sum(hc.otherRaisedStreet4)          AS was_raised_4,
                   sum(hc.foldToOtherRaisedStreet1)    AS f_freq_1,
                   sum(hc.foldToOtherRaisedStreet2)    AS f_freq_2,
                   sum(hc.foldToOtherRaisedStreet3)    AS f_freq_3,
                   sum(hc.foldToOtherRaisedStreet4)    AS f_freq_4,
                   sum(hc.wonWhenSeenStreet1)          AS w_w_s_1,
                   sum(hc.wonAtSD)                     AS wmsd,
                   sum(hc.stealChance)                 AS steal_opp,
                   sum(hc.stealDone)                   AS steal,
                   sum(hc.foldSbToStealChance)         AS SBstolen,
                   sum(hc.foldedSbToSteal)             AS SBnotDef,
                   sum(hc.foldBbToStealChance)         AS BBstolen,
                   sum(hc.foldedBbToSteal)             AS BBnotDef,
                   sum(hc.street1CBChance)             AS CB_opp_1,
                   sum(hc.street1CBDone)               AS CB_1,
                   sum(hc.street2CBChance)             AS CB_opp_2,
                   sum(hc.street2CBDone)               AS CB_2,
                   sum(hc.street3CBChance)             AS CB_opp_3,
                   sum(hc.street3CBDone)               AS CB_3,
                   sum(hc.street4CBChance)             AS CB_opp_4,
                   sum(hc.street4CBDone)               AS CB_4,
                   sum(hc.foldToStreet1CBChance)       AS f_cb_opp_1,
                   sum(hc.foldToStreet1CBDone)         AS f_cb_1,
                   sum(hc.foldToStreet2CBChance)       AS f_cb_opp_2,
                   sum(hc.foldToStreet2CBDone)         AS f_cb_2,
                   sum(hc.foldToStreet3CBChance)       AS f_cb_opp_3,
                   sum(hc.foldToStreet3CBDone)         AS f_cb_3,
                   sum(hc.foldToStreet4CBChance)       AS f_cb_opp_4,
                   sum(hc.foldToStreet4CBDone)         AS f_cb_4,
                   sum(hc.totalProfit)                 AS net,
                   sum(gt.bigblind * hc.n)             AS bigblind,
                   sum(hc.street1CheckCallRaiseChance) AS ccr_opp_1,
                   sum(hc.street1CheckCallDone)        AS cc_1,
                   sum(hc.street1CheckRaiseDone)       AS cr_1,
                   sum(hc.street2CheckCallRaiseChance) AS ccr_opp_2,
                   sum(hc.street2CheckCallDone)        AS cc_2,
                   sum(hc.street2CheckRaiseDone)       AS cr_2,
                   sum(hc.street3CheckCallRaiseChance) AS ccr_opp_3,
                   sum(hc.street3CheckCallDone)        AS cc_3,
                   sum(hc.street3CheckRaiseDone)       AS cr_3,
                   sum(hc.street4CheckCallRaiseChance) AS ccr_opp_4,
                   sum(hc.street4CheckCallDone)        AS cc_4,
                   sum(hc.street4CheckRaiseDone)       AS cr_4,
                   sum(hc.street0Calls)                AS call_0,
                   sum(hc.street1Calls)                AS call_1,
                   sum(hc.street2Calls)                AS call_2,
                   sum(hc.street3Calls)                AS call_3,
                   sum(hc.street4Calls)                AS call_4,
                   sum(hc.street0Bets)                 AS bet_0,
                   sum(hc.street1Bets)                 AS bet_1,
                   sum(hc.street2Bets)                 AS bet_2,
                   sum(hc.street3Bets)                 AS bet_3,
                   sum(hc.street4Bets)                 AS bet_4,
    sum(hc.street0Raises)               AS raise_0,
                    sum(hc.street1Raises)               AS raise_1,
    sum(hc.street2Raises)               AS raise_2,
                    sum(hc.street3Raises)               AS raise_3,
                    sum(hc.street4Raises)               AS raise_4,
    sum(hc.street0Limp)                 AS limp,
                     sum(hc.street0OpenLimpChance)         AS open_limp_opp,
                     sum(hc.street0OpenLimp)               AS open_limp,
                    /* HudCache.position is stored as a letter bucket by storeHudCache():
                       D=button, C=cutoff, M=middle, E=early (B/S=blinds). */
                    sum(CASE WHEN hc.position = 'D' THEN hc.raiseFirstInChance ELSE 0 END) AS rfi_opp_btn,
                    sum(CASE WHEN hc.position = 'D' THEN hc.raisedFirstIn      ELSE 0 END) AS rfi_btn,
                    sum(CASE WHEN hc.position = 'C' THEN hc.raiseFirstInChance ELSE 0 END) AS rfi_opp_lp,
                    sum(CASE WHEN hc.position = 'C' THEN hc.raisedFirstIn      ELSE 0 END) AS rfi_lp,
                    sum(CASE WHEN hc.position = 'M' THEN hc.raiseFirstInChance ELSE 0 END) AS rfi_opp_mp,
                    sum(CASE WHEN hc.position = 'M' THEN hc.raisedFirstIn      ELSE 0 END) AS rfi_mp,
                    sum(CASE WHEN hc.position = 'E' THEN hc.raiseFirstInChance ELSE 0 END) AS rfi_opp_ep,
                    sum(CASE WHEN hc.position = 'E' THEN hc.raisedFirstIn      ELSE 0 END) AS rfi_ep,
                    /* Preflop aggression by position.  Keep both the action and
                       its true opportunity count in each bucket. */
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_bb,
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_3BDone   ELSE 0 END) AS tb_bb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_sb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_3BDone   ELSE 0 END) AS tb_sb,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_btn,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_3BDone   ELSE 0 END) AS tb_btn,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_co,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_3BDone   ELSE 0 END) AS tb_co,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_mp,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_3BDone   ELSE 0 END) AS tb_mp,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_3BChance ELSE 0 END) AS tb_opp_ep,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_3BDone   ELSE 0 END) AS tb_ep,
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_bb,
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_4BDone   ELSE 0 END) AS fb_bb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_sb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_4BDone   ELSE 0 END) AS fb_sb,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_btn,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_4BDone   ELSE 0 END) AS fb_btn,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_co,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_4BDone   ELSE 0 END) AS fb_co,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_mp,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_4BDone   ELSE 0 END) AS fb_mp,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_4BChance ELSE 0 END) AS fb_opp_ep,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_4BDone   ELSE 0 END) AS fb_ep,
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_bb,
                    sum(CASE WHEN hc.position = 'B' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_bb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_sb,
                    sum(CASE WHEN hc.position = 'S' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_sb,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_btn,
                    sum(CASE WHEN hc.position = 'D' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_btn,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_co,
                    sum(CASE WHEN hc.position = 'C' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_co,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_mp,
                    sum(CASE WHEN hc.position = 'M' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_mp,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_SqueezeChance ELSE 0 END) AS sqz_opp_ep,
                    sum(CASE WHEN hc.position = 'E' THEN hc.street0_SqueezeDone   ELSE 0 END) AS sqz_ep,
                    /* Delayed turn c-bet — raw aliases so the declarative
                       descriptor 'delayed_cbet_turn' renders via do_stat. */
                    sum(hc.street2DelayedCBChance)      AS street2DelayedCBChance,
                    sum(hc.street2DelayedCBDone)        AS street2DelayedCBDone,
                    sum(hc.street2ProbeChance)          AS street2ProbeChance,
                    sum(hc.street2ProbeDone)            AS street2ProbeDone
                    /* Declarative descriptor stats (stat_registry.py) inject
                       bucket-encoded ChipEV-by-position columns here. */
                    <chipev_columns>
             FROM Hands h
                 INNER JOIN HandsPlayers hp ON (hp.handId = h.id)
                 INNER JOIN HudCache hc     ON (hc.playerId = hp.playerId)
                 INNER JOIN Players p       ON (p.id = hc.playerId)
                 INNER JOIN Gametypes gt    ON (gt.id = hc.gametypeId)
            WHERE h.id = %s
            AND   (   /* 2 separate parts for hero and opponents */
                      (    hp.playerId != %s
                       AND hc.styleKey > %s
                       AND hc.gametypeId+0 in
                             (SELECT gt1.id from Gametypes gt1, Gametypes gt2
                              WHERE  gt1.siteid = gt2.siteid  /* find gametypes where these match: */
                              AND    gt1.type = gt2.type               /* ring/tourney */
                              AND    gt1.category = gt2.category       /* holdem/stud*/
                              AND    gt1.limittype = gt2.limittype     /* fl/nl */
                              AND    gt1.bigblind <= gt2.bigblind * %s  /* bigblind similar size */
                              AND    gt1.bigblind >= gt2.bigblind / %s
                              AND    gt2.id = %s)
                       AND hc.seats between %s and %s
                      )
                   OR
                      (    hp.playerId = %s
                       AND hc.styleKey > %s
                       AND hc.gametypeId+0 in
                             (SELECT gt1.id from Gametypes gt1, Gametypes gt2
                              WHERE  gt1.siteid = gt2.siteid  /* find gametypes where these match: */
                              AND    gt1.type = gt2.type               /* ring/tourney */
                              AND    gt1.category = gt2.category       /* holdem/stud*/
                              AND    gt1.limittype = gt2.limittype     /* fl/nl */
                              AND    gt1.bigblind <= gt2.bigblind * %s  /* bigblind similar size */
                              AND    gt1.bigblind >= gt2.bigblind / %s
                              AND    gt2.id = %s)
                       AND hc.seats between %s and %s
                      )
                  )
            GROUP BY hc.PlayerId, p.name
            ORDER BY hc.PlayerId, p.name
        """
    #  NOTES on above cursor:
    #  - Do NOT include %s inside query in a comment - the db api thinks
    #  they are actual arguments.
    #  - styleKey is currently 'd' (for date) followed by a yyyymmdd
    #  date key. Set it to 0000000 or similar to get all records
    #  Could also check activeseats here even if only 3 groups eg 2-3/4-6/7+
    #  e.g. could use a multiplier:
    #  AND   h.seats > %s / 1.25  and  hp.seats < %s * 1.25
    #  where %s is the number of active players at the current table (and
    #  1.25 would be a config value so user could change it)
    return query

