#!/usr/bin/env python
from __future__ import annotations

"""Returns a dict of SQL statements used in fpdb."""

import re
import sys

from fpdb_3_legacy.sql_indexes import index_queries
from fpdb_3_legacy.sql_metadata import metadata_queries
from fpdb_3_legacy.sql_queries_core import core_lookup_queries
from fpdb_3_legacy.sql_queries_filters import filter_queries
from fpdb_3_legacy.sql_queries_hand_detail import hand_detail_queries
from fpdb_3_legacy.sql_queries_history import history_window_queries
from fpdb_3_legacy.sql_queries_opponents import opponent_report_queries
from fpdb_3_legacy.sql_queries_player_detailed import player_detailed_report_queries
from fpdb_3_legacy.sql_schema_cards_cache import cards_cache_schema_queries
from fpdb_3_legacy.sql_schema_core import core_schema_queries
from fpdb_3_legacy.sql_schema_game import game_schema_queries
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries
from fpdb_3_legacy.sql_schema_hand_player import hand_player_schema_queries
from fpdb_3_legacy.sql_schema_hand_root import root_hand_schema_queries
from fpdb_3_legacy.sql_schema_hud_cache import hud_cache_schema_queries
from fpdb_3_legacy.sql_schema_import import import_schema_queries
from fpdb_3_legacy.sql_schema_lookup import lookup_schema_queries
from fpdb_3_legacy.sql_schema_player import player_schema_queries
from fpdb_3_legacy.sql_schema_position_cache import position_cache_schema_queries
from fpdb_3_legacy.sql_schema_raw import raw_schema_queries
from fpdb_3_legacy.sql_schema_session_cache import session_cache_schema_queries
from fpdb_3_legacy.sql_schema_time import time_schema_queries
from fpdb_3_legacy.sql_schema_tournament import tournament_schema_queries
from fpdb_3_legacy.sql_schema_tournament_cache import tournament_cache_schema_queries

#    Copyright 2008-2011, Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

#    NOTES:  The sql statements use the placeholder %s for bind variables
#            which is then replaced by ? for sqlite. Comments can be included
#            within sql statements using C style /* ... */ comments, BUT
#            THE COMMENTS MUST NOT INCLUDE %s OR ?.

########################################################################

#    Standard Library modules


#    pyGTK modules

#    FreePokerTools modules


class Sql:
    def __init__(self, game="holdem", db_server="mysql") -> None:
        self.query = {}
        self.query.update(metadata_queries(db_server))
        self.query.update(cards_cache_schema_queries(db_server))
        self.query.update(core_schema_queries(db_server))
        self.query.update(game_schema_queries(db_server))
        self.query.update(hand_schema_queries(db_server))
        self.query.update(hand_player_schema_queries(db_server))
        self.query.update(root_hand_schema_queries(db_server))
        self.query.update(hud_cache_schema_queries(db_server))
        self.query.update(import_schema_queries(db_server))
        self.query.update(lookup_schema_queries(db_server))
        self.query.update(player_schema_queries(db_server))
        self.query.update(position_cache_schema_queries(db_server))
        self.query.update(raw_schema_queries(db_server))
        self.query.update(session_cache_schema_queries(db_server))
        self.query.update(tournament_schema_queries(db_server))
        self.query.update(tournament_cache_schema_queries(db_server))
        self.query.update(time_schema_queries(db_server))
        self.query.update(index_queries(db_server))
        self.query.update(core_lookup_queries())
        self.query.update(filter_queries(db_server))
        self.query.update(hand_detail_queries())
        self.query.update(history_window_queries(db_server))
        self.query.update(opponent_report_queries(db_server))
        self.query.update(player_detailed_report_queries(db_server))
        ###############################################################################3
        #    Support for the Free Poker DataBase = fpdb   http://fpdb.sourceforge.net/
        #

        self.query["get_stats_from_hand"] = """
                SELECT hc.playerId                      AS player_id,
                    hp.seatNo                           AS seat,
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
                    sum(hc.street4CheckCallDone)        AS cc_4
                    sum(hc.street4CheckRaiseDone)       AS cr_4
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
                    sum(hc.street4Raises)               AS raise_4
                FROM Hands h
                     INNER JOIN HandsPlayers hp ON (hp.handId = h.id)
                     INNER JOIN HudCache hc ON (    hc.PlayerId = hp.PlayerId+0
                                                AND hc.gametypeId+0 = h.gametypeId+0)
                     INNER JOIN Players p ON (p.id = hp.PlayerId+0)
                     INNER JOIN Gametypes gt ON (gt.id = hc.gametypeId)
                WHERE h.id = %s
                AND   hc.styleKey > %s
                      /* styleKey is currently 'd' (for date) followed by a yyyymmdd
                         date key. Set it to 0000000 or similar to get all records  */
                /* also check activeseats here even if only 3 groups eg 2-3/4-6/7+
                   e.g. could use a multiplier:
                   AND   h.seats > X / 1.25  and  hp.seats < X * 1.25
                   where X is the number of active players at the current table (and
                   1.25 would be a config value so user could change it)
                */
                GROUP BY hc.PlayerId, hp.seatNo, p.name
                ORDER BY hc.PlayerId, hp.seatNo, p.name
            """

        #    same as above except stats are aggregated for all blind/limit levels
        self.query["get_stats_from_hand_aggregated"] = """
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

        if db_server == "mysql":
            self.query["get_stats_from_hand_session"] = """
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
            self.query["get_stats_from_hand_session"] = """
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
            self.query["get_stats_from_hand_session"] = """
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

        if db_server == "mysql":
            self.query["tourneyPlayerDetailedStats"] = """
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
            self.query["tourneyPlayerDetailedStats"] = """
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
            self.query["tourneyPlayerDetailedStats"] = """
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

        if db_server == "mysql":
            self.query["playerStats"] = """
                SELECT
                      concat(upper(stats.limitType), ' '
                            ,concat(upper(substring(stats.category,1,1)),substring(stats.category,2) ), ' '
                            ,stats.name, ' '
                            ,cast(stats.bigBlindDesc as char)
                            )                                                      AS Game
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
                           ,upper(gt.limitType) as limitType
                           ,s.name
                           ,<selectgt.bigBlind>                                             AS bigBlindDesc
                           ,<hcgametypeId>                                                  AS gtId
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
                           ,format( sum(seats*n)/(sum(n)+0.0), 2)                           AS AvgSeats
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
                    ) stats
                inner join
                    ( select # profit from handsplayers/handsactions
                             hprof.gtId, sum(hprof.profit) sum_profit,
                             avg(hprof.profit/100.0) profitperhand,
                             case when hprof.gtId = -1 then -999
                                  else variance(hprof.profit/100.0)
                             end as variance
                            ,sqrt(variance(hprof.profit/100.0))                                                         AS stddev
                      from
                          (select hp.handId, <hgametypeId> as gtId, hp.totalProfit as profit
                           from HandsPlayers hp
                           inner join Hands h        ON h.id            = hp.handId
                           where hp.playerId in <player_test>
                           and   hp.tourneysPlayersId IS NULL
                           and   date_format(h.startTime, '%Y-%m-%d') <datestest>
                           group by hp.handId, gtId, hp.totalProfit
                          ) hprof
                      group by hprof.gtId
                     ) hprof2
                    on hprof2.gtId = stats.gtId
                order by stats.category, stats.limittype, stats.bigBlindDesc desc <orderbyseats>"""
        elif db_server == "sqlite":
            self.query["playerStats"] = """
                SELECT
                      upper(substr(stats.category,1,1)) || substr(stats.category,2) || ' ' ||
                      stats.name || ' ' ||
                      cast(stats.bigBlindDesc as char) || ' ' || stats.maxSeats || ' seat'  AS Game
                     ,stats.n,stats.vpip,stats.pfr,stats.pf3,stats.pf4,stats.pff3,stats.pff4
                     ,stats.steals,stats.saw_f,stats.sawsd,stats.wtsdwsf,stats.wmsd,stats.FlAFq
                     ,stats.TuAFq,stats.RvAFq,stats.PoFAFq,stats.Net,stats.BBper100,stats.Profitperhand
                     ,case when hprof2.variance = -999 then '-' else round(hprof2.variance, 2)
                      end                                                                   AS Variance
                     ,case when hprof2.stddev = -999 then '-' else round(hprof2.stddev, 2)
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
                     group by gt.base,gt.category,upper(gt.limitType),s.name <groupbygt.bigBlind>,gtId
                    ) stats
                inner join
                    ( select /* profit from handsplayers/handsactions */
                             hprof.gtId, sum(hprof.profit) sum_profit,
                             avg(hprof.profit/100.0) profitperhand,
                             case when hprof.gtId = -1 then -999
                                  else variance(hprof.profit/100.0)
                             end as variance
                             ,case when hprof.gtId = -1 then -999
                                  else sqrt(variance(hprof.profit/100.0))
                             end as stddev
                      from
                          (select hp.handId, <hgametypeId> as gtId, hp.totalProfit as profit
                           from HandsPlayers hp
                           inner join Hands h        ON h.id            = hp.handId
                           where hp.playerId in <player_test>
                           and   hp.tourneysPlayersId IS NULL
                           and   datetime(h.startTime) <datestest>
                           group by hp.handId, gtId, hp.totalProfit
                          ) hprof
                      group by hprof.gtId
                     ) hprof2
                    on hprof2.gtId = stats.gtId
                order by stats.category, stats.bigBlind, stats.limittype, stats.currency, stats.maxSeats <orderbyseats>"""
        else:  # assume postgres
            self.query["playerStats"] = """
                SELECT upper(stats.limitType) || ' '
                       || initcap(stats.category) || ' '
                       || stats.name || ' '
                       || stats.bigBlindDesc                                          AS Game
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
                      ,AvgSeats
                FROM
                    (select gt.base
                           ,gt.category
                           ,upper(gt.limitType)                                             AS limitType
                           ,s.name
                           ,<selectgt.bigBlind>                                             AS bigBlindDesc
                           ,<hcgametypeId>                                                  AS gtId
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
                                 else round(100.0*sum(street0_4Bdone)/sum(street0_4Bchance),1)
                            end                                                             AS pf4
                           ,case when sum(street0_FoldTo3Bchance) = 0 then '0'
                                 else round(100.0*sum(street0_FoldTo3Bdone)/sum(street0_FoldTo3Bchance),1)
                            end                                                             AS pff3
                           ,case when sum(street0_FoldTo4Bchance) = 0 then '0'
                                 else round(100.0*sum(street0_FoldTo4Bdone)/sum(street0_FoldTo4Bchance),1)
                            end                                                             AS pff4
                           ,case when sum(raiseFirstInChance) = 0 then '-'
                                 else to_char(100.0*sum(raisedFirstIn)/sum(raiseFirstInChance),'90D0')
                            end                                                             AS steals
                           ,to_char(100.0*sum(street1Seen)/sum(n),'90D0')                   AS saw_f
                           ,to_char(100.0*sum(sawShowdown)/sum(n),'90D0')                   AS sawsd
                           ,case when sum(street1Seen) = 0 then '-'
                                 else to_char(100.0*sum(sawShowdown)/sum(street1Seen),'90D0')
                            end                                                             AS wtsdwsf
                           ,case when sum(sawShowdown) = 0 then '-'
                                 else to_char(100.0*sum(wonAtSD)/sum(sawShowdown),'90D0')
                            end                                                             AS wmsd
                           ,case when sum(street1Seen) = 0 then '-'
                                 else to_char(100.0*sum(street1Aggr)/sum(street1Seen),'90D0')
                            end                                                             AS FlAFq
                           ,case when sum(street2Seen) = 0 then '-'
                                 else to_char(100.0*sum(street2Aggr)/sum(street2Seen),'90D0')
                            end                                                             AS TuAFq
                           ,case when sum(street3Seen) = 0 then '-'
                                else to_char(100.0*sum(street3Aggr)/sum(street3Seen),'90D0')
                            end                                                             AS RvAFq
                           ,case when sum(street1Seen)+sum(street2Seen)+sum(street3Seen) = 0 then '-'
                                else to_char(100.0*(sum(street1Aggr)+sum(street2Aggr)+sum(street3Aggr))
                                         /(sum(street1Seen)+sum(street2Seen)+sum(street3Seen)),'90D0')
                            end                                                             AS PoFAFq
                           ,round(sum(totalProfit)/100.0,2)                                 AS Net
                           ,to_char((sum(totalProfit/(gt.bigBlind+0.0))) / (sum(n)/100.0), '990D00')
                                                                                            AS BBper100
                           ,to_char(sum(totalProfit/100.0) / (sum(n)+0.0), '990D0000')    AS Profitperhand
                           ,to_char(sum(seats*n)/(sum(n)+0.0),'90D00')            AS AvgSeats
                     from Gametypes gt
                          inner join Sites s on s.Id = gt.siteId
                          inner join HudCache hc on hc.gametypeId = gt.Id
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
                    ) stats
                inner join
                    ( select
                             hprof.gtId, sum(hprof.profit) AS sum_profit,
                             avg(hprof.profit/100.0) AS profitperhand,
                             case when hprof.gtId = -1 then -999
                                  else variance(hprof.profit/100.0)
                             end as variance
                             ,case when hprof.gtId = -1 then -999
                                  else sqrt(variance(hprof.profit/100.0))
                             end as stddev
                      from
                          (select hp.handId, <hgametypeId> as gtId, hp.totalProfit as profit
                           from HandsPlayers hp
                           inner join Hands h   ON (h.id = hp.handId)
                           where hp.playerId in <player_test>
                           and   hp.tourneysPlayersId IS NULL
                           and   to_char(h.startTime, 'YYYY-MM-DD') <datestest>
                           group by hp.handId, gtId, hp.totalProfit
                          ) hprof
                      group by hprof.gtId
                     ) hprof2
                    on hprof2.gtId = stats.gtId
                order by stats.base, stats.limittype, stats.bigBlindDesc desc <orderbyseats>"""

        if db_server == "mysql":
            self.query["playerStatsByPosition"] = """
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
            self.query["playerStatsByPosition"] = """
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
            self.query["playerStatsByPosition"] = """
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
        self.query["getRingProfitAllHandsPlayerIdSite"] = """
            SELECT hp.handId, hp.totalProfit, hp.sawShowdown
            FROM HandsPlayers hp
            INNER JOIN Players pl      ON  (pl.id = hp.playerId)
            INNER JOIN Hands h         ON  (h.id  = hp.handId)
            INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
            WHERE pl.id in <player_test>
            AND   tt.siteId in <site_test>
            AND   h.startTime > '<startdate_test>'
            AND   h.startTime < '<enddate_test>'
            <limit_test>
            <game_test>
            AND   gt.type = 'ring'
            GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit
            ORDER BY h.startTime"""

        self.query["getRingProfitAllHandsPlayerIdSiteInBB"] = """
            SELECT hp.handId, ( hp.totalProfit / ( gt.bigBlind  * 2.0 ) ) * 100 , hp.sawShowdown, ( hp.allInEV / ( gt.bigBlind * 2.0 ) ) * 100
            FROM HandsPlayers hp
            INNER JOIN Players pl      ON  (pl.id = hp.playerId)
            INNER JOIN Hands h         ON  (h.id  = hp.handId)
            INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND   h.startTime > '<startdate_test>'
            AND   h.startTime < '<enddate_test>'
            <limit_test>
            <game_test>
            <currency_test>
            AND   hp.tourneysPlayersId IS NULL
            GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV, gt.bigBlind
            ORDER BY h.startTime"""

        self.query["getRingProfitAllHandsPlayerIdSiteInDollars"] = """
            SELECT hp.handId, hp.totalProfit, hp.sawShowdown, hp.allInEV
            FROM HandsPlayers hp
            INNER JOIN Players pl      ON  (pl.id = hp.playerId)
            INNER JOIN Hands h         ON  (h.id  = hp.handId)
            INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND   h.startTime > '<startdate_test>'
            AND   h.startTime < '<enddate_test>'
            <limit_test>
            <game_test>
            <currency_test>
            AND   hp.tourneysPlayersId IS NULL
            GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV
            ORDER BY h.startTime"""

        ####################################
        # Tourney Results query
        ####################################
        self.query["tourneyResults"] = """
            SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
            FROM TourneysPlayers tp
            INNER JOIN Players pl      ON  (pl.id = tp.playerId)
            INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
            INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                    OR t.startTime is NULL)
            GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                     tp.winnings, tp.koCount,
                     tp.rebuyCount, tp.addOnCount,
                     tt.buyIn, tt.fee, t.siteTourneyNo
            ORDER BY t.startTime"""

        # AND   gt.type = 'ring'
        # <limit_test>
        # <game_test>

        ####################################
        # Tourney Graph query
        # FIXME this is a horrible hack to prevent nonsense data
        #  being graphed - needs proper fix mantis #180 +#182
        ####################################
        self.query["tourneyGraph"] = """
            SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
            FROM TourneysPlayers tp
            INNER JOIN Players pl      ON  (pl.id = tp.playerId)
            INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
            INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND   (t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                 <currency_test>
            GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                     tp.winnings, tp.koCount,
                     tp.rebuyCount, tp.addOnCount,
                     tt.buyIn, tt.fee, t.siteTourneyNo
            ORDER BY t.startTime"""

        # AND   gt.type = 'ring'
        # <limit_test>
        # <game_test>
        ####################################
        # Tourney Graph query with tourneytypefilter
        # FIXME this is a horrible hack to prevent nonsense data
        #  being graphed - needs proper fix mantis #180 +#182
        ####################################
        self.query["tourneyGraphType"] = """
            SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
            FROM TourneysPlayers tp
            INNER JOIN Players pl      ON  (pl.id = tp.playerId)
            INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
            INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND tt.category in <tourney_cat>
            AND tt.limitType in <tourney_lim>
            AND tt.buyin in <tourney_buyin>
            AND   (t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                 <currency_test>
            GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                     tp.winnings, tp.koCount,
                     tp.rebuyCount, tp.addOnCount,
                     tt.buyIn, tt.fee, t.siteTourneyNo
            ORDER BY t.startTime"""

        # AND   gt.type = 'ring'
        # <limit_test>
        # <game_test>

        ####################################
        # ChipEV-by-position curves (declarative stats, see stat_registry.py)
        #
        # Per-hand tournament rows ordered by time. <chipev_columns> is filled
        # at runtime by GraphAdapter.select_clause() with one dimension-gated
        # CASE expression per ChipEV-by-position curve, so the cumulative
        # series can be computed in Python. Reuses the same filter placeholders
        # as tourneyGraphType.
        ####################################
        self.query["tourneyChipEVByPosition"] = """
            SELECT h.startTime AS startTime <chipev_columns>
            FROM HandsPlayers hp
            INNER JOIN Hands h          ON  (h.id = hp.handId)
            INNER JOIN Players pl       ON  (pl.id = hp.playerId)
            INNER JOIN Tourneys t       ON  (t.id = h.tourneyId)
            INNER JOIN TourneyTypes tt  ON  (tt.id = t.tourneyTypeId)
            WHERE pl.id in <player_test>
            AND   pl.siteId in <site_test>
            AND tt.category in <tourney_cat>
            AND tt.limitType in <tourney_lim>
            AND tt.buyin in <tourney_buyin>
            AND   (h.startTime > '<startdate_test>' AND h.startTime < '<enddate_test>')
                 <currency_test>
            ORDER BY h.startTime"""

        ####################################
        # ChipEV-by-position aggregated per (tourneyType, player) for the
        # tournament player-stats grid. <chipev_columns> is filled at runtime by
        # GridAdapter.select_clause(). Reuses the refineQuery placeholders
        # (<nametest>, <sitetest>, dates) of tourneyPlayerDetailedStats.
        ####################################
        self.query["tourneyChipEVByPositionGrid"] = """
            SELECT t.tourneyTypeId AS tourneyTypeId
                  ,hp.playerId     AS playerId
                  <chipev_columns>
            FROM HandsPlayers hp
            INNER JOIN Hands h          ON  (h.id = hp.handId)
            INNER JOIN Tourneys t       ON  (t.id = h.tourneyId)
            INNER JOIN TourneyTypes tt  ON  (tt.id = t.tourneyTypeId)
            INNER JOIN Players p        ON  (p.id = hp.playerId)
            WHERE hp.playerId in <nametest> <sitetest>
            AND   ((h.startTime > '<startdate_test>' AND h.startTime < '<enddate_test>')
                        OR h.startTime is NULL)
            GROUP BY t.tourneyTypeId, hp.playerId"""

        ####################################
        # Session stats query
        ####################################
        if db_server == "mysql":
            self.query["sessionStats"] = """
                SELECT UNIX_TIMESTAMP(h.startTime) as time, hp.totalProfit
                FROM HandsPlayers hp
                 INNER JOIN Hands h       on  (h.id = hp.handId)
                 INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
                 INNER JOIN Sites s       on  (s.Id = gt.siteId)
                 INNER JOIN Players p     on  (p.Id = hp.playerId)
                WHERE hp.playerId in <player_test>
                 AND  date_format(h.startTime, '%Y-%m-%d') <datestest>
                 AND  gt.type LIKE 'ring'
                 <limit_test>
                 <game_test>
                 <seats_test>
                 <currency_test>
                ORDER by time"""
        elif db_server == "postgresql":
            self.query["sessionStats"] = """
                SELECT EXTRACT(epoch from h.startTime) as time, hp.totalProfit
                FROM HandsPlayers hp
                 INNER JOIN Hands h       on  (h.id = hp.handId)
                 INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
                 INNER JOIN Sites s       on  (s.Id = gt.siteId)
                 INNER JOIN Players p     on  (p.Id = hp.playerId)
                WHERE hp.playerId in <player_test>
                 AND  h.startTime <datestest>
                 AND  gt.type LIKE 'ring'
                 <limit_test>
                 <game_test>
                 <seats_test>
                 <currency_test>
                ORDER by time"""
        elif db_server == "sqlite":
            self.query["sessionStats"] = """
                SELECT STRFTIME('<ampersand_s>', h.startTime) as time, hp.totalProfit
                FROM HandsPlayers hp
                 INNER JOIN Hands h       on  (h.id = hp.handId)
                 INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
                 INNER JOIN Sites s       on  (s.Id = gt.siteId)
                 INNER JOIN Players p     on  (p.Id = hp.playerId)
                WHERE hp.playerId in <player_test>
                 AND  h.startTime <datestest>
                 AND  gt.type is 'ring'
                 <limit_test>
                 <game_test>
                 <seats_test>
                 <currency_test>
                ORDER by time"""

        ####################################
        # Querry to get all hands in a date range
        ####################################
        self.query["handsInRange"] = """
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
        self.query["handsInRangeSession"] = """
            select h.id
                from Hands h

            where h.startTime <datetest>
               """

        ####################################
        # Querry to get all hands in a date range for cash games session variation filter
        ####################################
        self.query["handsInRangeSessionFilter"] = """
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

        self.query["getPlayerId"] = """
            SELECT id
            FROM Players
            WHERE siteId = %s
            AND name = %s
        """

        ####################################
        # Query to get a single hand for the replayer
        ####################################
        self.query["singleHand"] = """
                 SELECT h.*
                    FROM Hands h
                    WHERE id = %s"""

        ####################################
        # Query to get run it twice boards for the replayer
        ####################################
        self.query["singleHandBoards"] = """
                 SELECT b.*
                    FROM Boards b
                    WHERE handId = %s"""

        ####################################
        # Query to get a single player hand for the replayer
        ####################################
        self.query["playerHand"] = """
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
        self.query["handActions"] = """
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

        self.query["clearHudCache"] = """DELETE FROM HudCache"""
        self.query["clearCardsCache"] = """DELETE FROM CardsCache"""
        self.query["clearPositionsCache"] = """DELETE FROM PositionsCache"""

        self.query["clearHudCacheTourneyType"] = """DELETE FROM HudCache WHERE tourneyTypeId = %s"""
        self.query["clearCardsCacheTourneyType"] = """DELETE FROM CardsCache WHERE tourneyTypeId = %s"""
        self.query["clearPositionsCacheTourneyType"] = """DELETE FROM PositionsCache WHERE tourneyTypeId = %s"""

        self.query["fetchNewHudCacheTourneyTypeIds"] = """SELECT TT.id
                                                    FROM TourneyTypes TT
                                                    LEFT OUTER JOIN HudCache HC ON (TT.id = HC.tourneyTypeId)
                                                    WHERE HC.tourneyTypeId is NULL
                """

        self.query["fetchNewCardsCacheTourneyTypeIds"] = """SELECT TT.id
                                                    FROM TourneyTypes TT
                                                    LEFT OUTER JOIN CardsCache CC ON (TT.id = CC.tourneyTypeId)
                                                    WHERE CC.tourneyTypeId is NULL
                """

        self.query["fetchNewPositionsCacheTourneyTypeIds"] = """SELECT TT.id
                                                    FROM TourneyTypes TT
                                                    LEFT OUTER JOIN PositionsCache PC ON (TT.id = PC.tourneyTypeId)
                                                    WHERE PC.tourneyTypeId is NULL
                """

        self.query["clearCardsCacheWeeksMonths"] = """DELETE FROM CardsCache WHERE weekId = %s AND monthId = %s"""
        self.query["clearPositionsCacheWeeksMonths"] = (
            """DELETE FROM PositionsCache WHERE weekId = %s AND monthId = %s"""
        )

        self.query["selectSessionWithWeekId"] = """SELECT id FROM Sessions WHERE weekId = %s"""
        self.query["selectSessionWithMonthId"] = """SELECT id FROM Sessions WHERE monthId = %s"""

        self.query["deleteWeekId"] = """DELETE FROM Weeks WHERE id = %s"""
        self.query["deleteMonthId"] = """DELETE FROM Months WHERE id = %s"""

        self.query["fetchNewCardsCacheWeeksMonths"] = """SELECT SCG.weekId, SCG.monthId
                                            FROM (SELECT DISTINCT weekId, monthId FROM Sessions) SCG
                                            LEFT OUTER JOIN CardsCache CC ON (SCG.weekId = CC.weekId AND SCG.monthId = CC.monthId)
                                            WHERE CC.weekId is NULL OR CC.monthId is NULL
        """

        self.query["fetchNewPositionsCacheWeeksMonths"] = """SELECT SCG.weekId, SCG.monthId
                                            FROM (SELECT DISTINCT weekId, monthId FROM Sessions) SCG
                                            LEFT OUTER JOIN PositionsCache PC ON (SCG.weekId = PC.weekId AND SCG.monthId = PC.monthId)
                                            WHERE PC.weekId is NULL OR PC.monthId is NULL
        """

        if db_server == "mysql":
            self.query["rebuildCache"] = """insert into <insert>
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
                ,street3Discards
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
                      ,sum(street3Discards)
                FROM Hands h
                INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
                INNER JOIN Gametypes g ON (h.gametypeId = g.id)
                <sessions_join_clause>
                <tourney_join_clause>
                <where_clause>
                GROUP BY <group>
"""
        elif db_server == "postgresql":
            self.query["rebuildCache"] = """insert into <insert>
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
                ,street3Discards
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
                      ,sum(CAST(street3Discards as integer))
                FROM Hands h
                INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
                INNER JOIN Gametypes g ON (h.gametypeId = g.id)
                <sessions_join_clause>
                <tourney_join_clause>
                <where_clause>
                GROUP BY <group>
"""
        elif db_server == "sqlite":
            self.query["rebuildCache"] = """insert into <insert>
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
                ,street3Discards
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
                      ,sum(CAST(street3Discards as integer))
                FROM Hands h
                INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
                INNER JOIN Gametypes g ON (h.gametypeId = g.id)
                <sessions_join_clause>
                <tourney_join_clause>
                <where_clause>
                GROUP BY <group>
"""

        self.query["insert_hudcache"] = """insert into HudCache (
                gametypeId,
                playerId,
                seats,
                position,
                tourneyTypeId,
                styleKey,
                n,
                street0VPIChance,
                street0VPI,
                street0AggrChance,
                street0Aggr,
                street0CalledRaiseChance,
                street0CalledRaiseDone,
                street0FaceRaise,
                street0_2BChance,
                street0_2BDone,
                street0_3BChance,
                street0_3BDone,
                street0_4BChance,
                street0_4BDone,
                street0_C4BChance,
                street0_C4BDone,
                street0_FoldTo2BChance,
                street0_FoldTo2BDone,
                street0_FoldTo3BChance,
                street0_FoldTo3BDone,
                street0_FoldTo4BChance,
                street0_FoldTo4BDone,
                street0_SqueezeChance,
                street0_SqueezeDone,
                raiseToStealChance,
                raiseToStealDone,
                stealChance,
                stealDone,
                success_Steal,
                street1Seen,
                street2Seen,
                street3Seen,
                street4Seen,
                sawShowdown,
                street1Aggr,
                street2Aggr,
                street3Aggr,
                street4Aggr,
                otherRaisedStreet0,
                otherRaisedStreet1,
                otherRaisedStreet2,
                otherRaisedStreet3,
                otherRaisedStreet4,
                foldToOtherRaisedStreet0,
                foldToOtherRaisedStreet1,
                foldToOtherRaisedStreet2,
                foldToOtherRaisedStreet3,
                foldToOtherRaisedStreet4,
                wonWhenSeenStreet1,
                wonWhenSeenStreet2,
                wonWhenSeenStreet3,
                wonWhenSeenStreet4,
                wonAtSD,
                raiseFirstInChance,
                raisedFirstIn,
                foldBbToStealChance,
                foldedBbToSteal,
                foldSbToStealChance,
                foldedSbToSteal,
                street1CBChance,
                street1CBDone,
                street2CBChance,
                street2CBDone,
                street3CBChance,
                street3CBDone,
                street4CBChance,
                street4CBDone,
                foldToStreet1CBChance,
                foldToStreet1CBDone,
                foldToStreet2CBChance,
                foldToStreet2CBDone,
                foldToStreet3CBChance,
                foldToStreet3CBDone,
                foldToStreet4CBChance,
                foldToStreet4CBDone,
                common,
                committed,
                winnings,
                rake,
                rakeDealt,
                rakeContributed,
                rakeWeighted,
                totalProfit,
                allInEV,
                showdownWinnings,
                nonShowdownWinnings,
                street1CheckCallRaiseChance,
                street1CheckCallDone,
                street1CheckRaiseDone,
                street2CheckCallRaiseChance,
                street2CheckCallDone,
                street2CheckRaiseDone,
                street3CheckCallRaiseChance,
                street3CheckCallDone,
                street3CheckRaiseDone,
                street4CheckCallRaiseChance,
                street4CheckCallDone,
                street4CheckRaiseDone,
                street0Calls,
                street1Calls,
                street2Calls,
                street3Calls,
                street4Calls,
                street0Bets,
                street1Bets,
                street2Bets,
                street3Bets,
                street4Bets,
                street0Raises,
                street1Raises,
                street2Raises,
                street3Raises,
                street4Raises,
                street1Discards,
                street2Discards,
                street3Discards,
                street0Limp,
                street0OpenLimpChance,
                street0OpenLimp,
                street1_3BChance,
                street1_3BDone,
                street2_3BChance,
                street2_3BDone,
                street3_3BChance,
                street3_3BDone,
                street1_4BChance,
                street1_4BDone,
                street1_FoldTo4BChance,
                street1_FoldTo4BDone,
                street2_4BChance,
                street2_4BDone,
                street2_FoldTo4BChance,
                street2_FoldTo4BDone,
                street3_4BChance,
                street3_4BDone,
                street3_FoldTo4BChance,
                street3_FoldTo4BDone,
                street1OpenChance,
                street1OpenDone,
                street2OpenChance,
                street2OpenDone,
                street3OpenChance,
                street3OpenDone,
                flg_f_fold,
                flg_t_fold,
                flg_r_fold,
                street1FirstRaise,
                street2FirstRaise,
                street3FirstRaise,
                street1FaceRaise,
                street2FaceRaise,
                street3FaceRaise,
                flg_f_donk_def_opp,
                flg_t_float_opp,
                flg_t_float,
                flg_t_float_def_opp,
                flg_r_float_opp,
                flg_r_float,
                flg_r_float_def_opp,
                flg_t_donk_def_opp,
                flg_r_donk_def_opp,
                street1_FoldTo3BChance,
                street1_FoldTo3BDone,
                street2_FoldTo3BChance,
                street2_FoldTo3BDone,
                street3_FoldTo3BChance,
                street3_FoldTo3BDone,
                street0_FoldToSqueezeChance,
                street0_FoldToSqueezeDone,
                street0_FaceLimpers,
                cnt_gp_open_opp,
                cnt_gp_2x,
                cnt_gp_os,
                cnt_gp_limp,
                flg_blind_ds,
                flg_blind_db,
                flg_blind_k,
                flg_faced_allin,
                flg_fold_to_allin,
                cnt_f_bet_facing,
                val_f_bet_facing_bp,
                cnt_t_bet_facing,
                val_t_bet_facing_bp,
                cnt_r_bet_facing,
                val_r_bet_facing_bp,
                cnt_p_2bet_facing,
                val_p_2bet_facing_bp,
                cnt_p_3bet_facing,
                val_p_3bet_facing_bp,
                cnt_p_4bet_facing,
                val_p_4bet_facing_bp,
                cnt_f_bet_made,
                val_f_bet_made_bp,
                cnt_t_bet_made,
                val_t_bet_made_bp,
                cnt_r_bet_made,
                val_r_bet_made_bp,
                cnt_f_spr,
                val_f_spr,
                cnt_t_spr,
                val_t_spr,
                cnt_r_spr,
                val_r_spr,
                cnt_p_raise_made,
                val_p_raise_made_bp,
                cnt_f_raise_made,
                val_f_raise_made_bp,
                cnt_t_raise_made,
                val_t_raise_made_bp,
                cnt_r_raise_made,
                val_r_raise_made_bp,
                cnt_f_2bet_facing,
                val_f_2bet_facing_bp,
                cnt_f_3bet_facing,
                val_f_3bet_facing_bp,
                cnt_f_4bet_facing,
                val_f_4bet_facing_bp,
                cnt_t_2bet_facing,
                val_t_2bet_facing_bp,
                cnt_t_3bet_facing,
                val_t_3bet_facing_bp,
                cnt_t_4bet_facing,
                val_t_4bet_facing_bp,
                cnt_r_2bet_facing,
                val_r_2bet_facing_bp,
                cnt_r_3bet_facing,
                val_r_3bet_facing_bp,
                cnt_r_4bet_facing,
                val_r_4bet_facing_bp,
                amt_blind,
                amt_bet_p,
                amt_bet_f,
                amt_bet_t,
                amt_bet_r,
                amt_bet_ttl,
                cnt_p_raise_facing,
                val_p_raise_facing_bp,
                cnt_f_raise_facing,
                val_f_raise_facing_bp,
                cnt_t_raise_facing,
                val_t_raise_facing_bp,
                cnt_r_raise_facing,
                val_r_raise_facing_bp,
                cnt_p_raise_made_2,
                val_p_raise_made_2_bp,
                cnt_f_raise_made_2,
                val_f_raise_made_2_bp,
                cnt_t_raise_made_2,
                val_t_raise_made_2_bp,
                cnt_r_raise_made_2,
                val_r_raise_made_2_bp,
                cnt_p_5bet_facing,
                val_p_5bet_facing_bp,
                street2DelayedCBChance,
                street2DelayedCBDone,
                street2ProbeChance,
                street2ProbeDone)
            values (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s)"""

        self.query["update_hudcache"] = """
            UPDATE HudCache SET
            n=n+%s,
            street0VPIChance=street0VPIChance+%s,
            street0VPI=street0VPI+%s,
            street0AggrChance=street0AggrChance+%s,
            street0Aggr=street0Aggr+%s,
            street0CalledRaiseChance=street0CalledRaiseChance+%s,
            street0CalledRaiseDone=street0CalledRaiseDone+%s,
            street0FaceRaise=street0FaceRaise+%s,
            street0_2BChance=street0_2BChance+%s,
            street0_2BDone=street0_2BDone+%s,
            street0_3BChance=street0_3BChance+%s,
            street0_3BDone=street0_3BDone+%s,
            street0_4BChance=street0_4BChance+%s,
            street0_4BDone=street0_4BDone+%s,
            street0_C4BChance=street0_C4BChance+%s,
            street0_C4BDone=street0_C4BDone+%s,
            street0_FoldTo2BChance=street0_FoldTo2BChance+%s,
            street0_FoldTo2BDone=street0_FoldTo2BDone+%s,
            street0_FoldTo3BChance=street0_FoldTo3BChance+%s,
            street0_FoldTo3BDone=street0_FoldTo3BDone+%s,
            street0_FoldTo4BChance=street0_FoldTo4BChance+%s,
            street0_FoldTo4BDone=street0_FoldTo4BDone+%s,
            street0_SqueezeChance=street0_SqueezeChance+%s,
            street0_SqueezeDone=street0_SqueezeDone+%s,
            raiseToStealChance=raiseToStealChance+%s,
            raiseToStealDone=raiseToStealDone+%s,
            stealChance=stealChance+%s,
            stealDone=stealDone+%s,
            success_Steal=success_Steal+%s,
            street1Seen=street1Seen+%s,
            street2Seen=street2Seen+%s,
            street3Seen=street3Seen+%s,
            street4Seen=street4Seen+%s,
            sawShowdown=sawShowdown+%s,
            street1Aggr=street1Aggr+%s,
            street2Aggr=street2Aggr+%s,
            street3Aggr=street3Aggr+%s,
            street4Aggr=street4Aggr+%s,
            otherRaisedStreet0=otherRaisedStreet0+%s,
            otherRaisedStreet1=otherRaisedStreet1+%s,
            otherRaisedStreet2=otherRaisedStreet2+%s,
            otherRaisedStreet3=otherRaisedStreet3+%s,
            otherRaisedStreet4=otherRaisedStreet4+%s,
            foldToOtherRaisedStreet0=foldToOtherRaisedStreet0+%s,
            foldToOtherRaisedStreet1=foldToOtherRaisedStreet1+%s,
            foldToOtherRaisedStreet2=foldToOtherRaisedStreet2+%s,
            foldToOtherRaisedStreet3=foldToOtherRaisedStreet3+%s,
            foldToOtherRaisedStreet4=foldToOtherRaisedStreet4+%s,
            wonWhenSeenStreet1=wonWhenSeenStreet1+%s,
            wonWhenSeenStreet2=wonWhenSeenStreet2+%s,
            wonWhenSeenStreet3=wonWhenSeenStreet3+%s,
            wonWhenSeenStreet4=wonWhenSeenStreet4+%s,
            wonAtSD=wonAtSD+%s,
            raiseFirstInChance=raiseFirstInChance+%s,
            raisedFirstIn=raisedFirstIn+%s,
            foldBbToStealChance=foldBbToStealChance+%s,
            foldedBbToSteal=foldedBbToSteal+%s,
            foldSbToStealChance=foldSbToStealChance+%s,
            foldedSbToSteal=foldedSbToSteal+%s,
            street1CBChance=street1CBChance+%s,
            street1CBDone=street1CBDone+%s,
            street2CBChance=street2CBChance+%s,
            street2CBDone=street2CBDone+%s,
            street3CBChance=street3CBChance+%s,
            street3CBDone=street3CBDone+%s,
            street4CBChance=street4CBChance+%s,
            street4CBDone=street4CBDone+%s,
            foldToStreet1CBChance=foldToStreet1CBChance+%s,
            foldToStreet1CBDone=foldToStreet1CBDone+%s,
            foldToStreet2CBChance=foldToStreet2CBChance+%s,
            foldToStreet2CBDone=foldToStreet2CBDone+%s,
            foldToStreet3CBChance=foldToStreet3CBChance+%s,
            foldToStreet3CBDone=foldToStreet3CBDone+%s,
            foldToStreet4CBChance=foldToStreet4CBChance+%s,
            foldToStreet4CBDone=foldToStreet4CBDone+%s,
            common=common+%s,
            committed=committed+%s,
            winnings=winnings+%s,
            rake=rake+%s,
            rakeDealt=rakeDealt+%s,
            rakeContributed=rakeContributed+%s,
            rakeWeighted=rakeWeighted+%s,
            totalProfit=totalProfit+%s,
            allInEV=allInEV+%s,
            showdownWinnings=showdownWinnings+%s,
            nonShowdownWinnings=nonShowdownWinnings+%s,
            street1CheckCallRaiseChance=street1CheckCallRaiseChance+%s,
            street1CheckCallDone=street1CheckCallDone+%s,
            street1CheckRaiseDone=street1CheckRaiseDone+%s,
            street2CheckCallRaiseChance=street2CheckCallRaiseChance+%s,
            street2CheckCallDone=street2CheckCallDone+%s,
            street2CheckRaiseDone=street2CheckRaiseDone+%s,
            street3CheckCallRaiseChance=street3CheckCallRaiseChance+%s,
            street3CheckCallDone=street3CheckCallDone+%s,
            street3CheckRaiseDone=street3CheckRaiseDone+%s,
            street4CheckCallRaiseChance=street4CheckCallRaiseChance+%s,
            street4CheckCallDone=street4CheckCallDone+%s,
            street4CheckRaiseDone=street4CheckRaiseDone+%s,
            street0Calls=street0Calls+%s,
            street1Calls=street1Calls+%s,
            street2Calls=street2Calls+%s,
            street3Calls=street3Calls+%s,
            street4Calls=street4Calls+%s,
            street0Bets=street0Bets+%s,
            street1Bets=street1Bets+%s,
            street2Bets=street2Bets+%s,
            street3Bets=street3Bets+%s,
            street4Bets=street4Bets+%s,
            street0Raises=street0Raises+%s,
            street1Raises=street1Raises+%s,
            street2Raises=street2Raises+%s,
            street3Raises=street3Raises+%s,
            street4Raises=street4Raises+%s,
            street1Discards=street1Discards+%s,
            street2Discards=street2Discards+%s,
            street3Discards=street3Discards+%s,
            street0Limp=street0Limp+%s,
            street0OpenLimpChance=street0OpenLimpChance+%s,
            street0OpenLimp=street0OpenLimp+%s,
            street1_3BChance=street1_3BChance+%s,
            street1_3BDone=street1_3BDone+%s,
            street2_3BChance=street2_3BChance+%s,
            street2_3BDone=street2_3BDone+%s,
            street3_3BChance=street3_3BChance+%s,
            street3_3BDone=street3_3BDone+%s,
            street1_4BChance=street1_4BChance+%s,
            street1_4BDone=street1_4BDone+%s,
            street1_FoldTo4BChance=street1_FoldTo4BChance+%s,
            street1_FoldTo4BDone=street1_FoldTo4BDone+%s,
            street2_4BChance=street2_4BChance+%s,
            street2_4BDone=street2_4BDone+%s,
            street2_FoldTo4BChance=street2_FoldTo4BChance+%s,
            street2_FoldTo4BDone=street2_FoldTo4BDone+%s,
            street3_4BChance=street3_4BChance+%s,
            street3_4BDone=street3_4BDone+%s,
            street3_FoldTo4BChance=street3_FoldTo4BChance+%s,
            street3_FoldTo4BDone=street3_FoldTo4BDone+%s,
            street1OpenChance=street1OpenChance+%s,
            street1OpenDone=street1OpenDone+%s,
            street2OpenChance=street2OpenChance+%s,
            street2OpenDone=street2OpenDone+%s,
            street3OpenChance=street3OpenChance+%s,
            street3OpenDone=street3OpenDone+%s,
            flg_f_fold=flg_f_fold+%s,
            flg_t_fold=flg_t_fold+%s,
            flg_r_fold=flg_r_fold+%s,
            street1FirstRaise=street1FirstRaise+%s,
            street2FirstRaise=street2FirstRaise+%s,
            street3FirstRaise=street3FirstRaise+%s,
            street1FaceRaise=street1FaceRaise+%s,
            street2FaceRaise=street2FaceRaise+%s,
            street3FaceRaise=street3FaceRaise+%s,
            flg_f_donk_def_opp=flg_f_donk_def_opp+%s,
            flg_t_float_opp=flg_t_float_opp+%s,
            flg_t_float=flg_t_float+%s,
            flg_t_float_def_opp=flg_t_float_def_opp+%s,
            flg_r_float_opp=flg_r_float_opp+%s,
            flg_r_float=flg_r_float+%s,
            flg_r_float_def_opp=flg_r_float_def_opp+%s,
            flg_t_donk_def_opp=flg_t_donk_def_opp+%s,
            flg_r_donk_def_opp=flg_r_donk_def_opp+%s,
            street1_FoldTo3BChance=street1_FoldTo3BChance+%s,
            street1_FoldTo3BDone=street1_FoldTo3BDone+%s,
            street2_FoldTo3BChance=street2_FoldTo3BChance+%s,
            street2_FoldTo3BDone=street2_FoldTo3BDone+%s,
            street3_FoldTo3BChance=street3_FoldTo3BChance+%s,
            street3_FoldTo3BDone=street3_FoldTo3BDone+%s,
            street0_FoldToSqueezeChance=street0_FoldToSqueezeChance+%s,
            street0_FoldToSqueezeDone=street0_FoldToSqueezeDone+%s,
            street0_FaceLimpers=street0_FaceLimpers+%s,
            cnt_gp_open_opp=cnt_gp_open_opp+%s,
            cnt_gp_2x=cnt_gp_2x+%s,
            cnt_gp_os=cnt_gp_os+%s,
            cnt_gp_limp=cnt_gp_limp+%s,
            flg_blind_ds=flg_blind_ds+%s,
            flg_blind_db=flg_blind_db+%s,
            flg_blind_k=flg_blind_k+%s,
            flg_faced_allin=flg_faced_allin+%s,
            flg_fold_to_allin=flg_fold_to_allin+%s,
            cnt_f_bet_facing=cnt_f_bet_facing+%s,
            val_f_bet_facing_bp=val_f_bet_facing_bp+%s,
            cnt_t_bet_facing=cnt_t_bet_facing+%s,
            val_t_bet_facing_bp=val_t_bet_facing_bp+%s,
            cnt_r_bet_facing=cnt_r_bet_facing+%s,
            val_r_bet_facing_bp=val_r_bet_facing_bp+%s,
            cnt_p_2bet_facing=cnt_p_2bet_facing+%s,
            val_p_2bet_facing_bp=val_p_2bet_facing_bp+%s,
            cnt_p_3bet_facing=cnt_p_3bet_facing+%s,
            val_p_3bet_facing_bp=val_p_3bet_facing_bp+%s,
            cnt_p_4bet_facing=cnt_p_4bet_facing+%s,
            val_p_4bet_facing_bp=val_p_4bet_facing_bp+%s,
            cnt_f_bet_made=cnt_f_bet_made+%s,
            val_f_bet_made_bp=val_f_bet_made_bp+%s,
            cnt_t_bet_made=cnt_t_bet_made+%s,
            val_t_bet_made_bp=val_t_bet_made_bp+%s,
            cnt_r_bet_made=cnt_r_bet_made+%s,
            val_r_bet_made_bp=val_r_bet_made_bp+%s,
            cnt_f_spr=cnt_f_spr+%s,
            val_f_spr=val_f_spr+%s,
            cnt_t_spr=cnt_t_spr+%s,
            val_t_spr=val_t_spr+%s,
            cnt_r_spr=cnt_r_spr+%s,
            val_r_spr=val_r_spr+%s,
            cnt_p_raise_made=cnt_p_raise_made+%s,
            val_p_raise_made_bp=val_p_raise_made_bp+%s,
            cnt_f_raise_made=cnt_f_raise_made+%s,
            val_f_raise_made_bp=val_f_raise_made_bp+%s,
            cnt_t_raise_made=cnt_t_raise_made+%s,
            val_t_raise_made_bp=val_t_raise_made_bp+%s,
            cnt_r_raise_made=cnt_r_raise_made+%s,
            val_r_raise_made_bp=val_r_raise_made_bp+%s,
            cnt_f_2bet_facing=cnt_f_2bet_facing+%s,
            val_f_2bet_facing_bp=val_f_2bet_facing_bp+%s,
            cnt_f_3bet_facing=cnt_f_3bet_facing+%s,
            val_f_3bet_facing_bp=val_f_3bet_facing_bp+%s,
            cnt_f_4bet_facing=cnt_f_4bet_facing+%s,
            val_f_4bet_facing_bp=val_f_4bet_facing_bp+%s,
            cnt_t_2bet_facing=cnt_t_2bet_facing+%s,
            val_t_2bet_facing_bp=val_t_2bet_facing_bp+%s,
            cnt_t_3bet_facing=cnt_t_3bet_facing+%s,
            val_t_3bet_facing_bp=val_t_3bet_facing_bp+%s,
            cnt_t_4bet_facing=cnt_t_4bet_facing+%s,
            val_t_4bet_facing_bp=val_t_4bet_facing_bp+%s,
            cnt_r_2bet_facing=cnt_r_2bet_facing+%s,
            val_r_2bet_facing_bp=val_r_2bet_facing_bp+%s,
            cnt_r_3bet_facing=cnt_r_3bet_facing+%s,
            val_r_3bet_facing_bp=val_r_3bet_facing_bp+%s,
            cnt_r_4bet_facing=cnt_r_4bet_facing+%s,
            val_r_4bet_facing_bp=val_r_4bet_facing_bp+%s,
            amt_blind=amt_blind+%s,
            amt_bet_p=amt_bet_p+%s,
            amt_bet_f=amt_bet_f+%s,
            amt_bet_t=amt_bet_t+%s,
            amt_bet_r=amt_bet_r+%s,
            amt_bet_ttl=amt_bet_ttl+%s,
            cnt_p_raise_facing=cnt_p_raise_facing+%s,
            val_p_raise_facing_bp=val_p_raise_facing_bp+%s,
            cnt_f_raise_facing=cnt_f_raise_facing+%s,
            val_f_raise_facing_bp=val_f_raise_facing_bp+%s,
            cnt_t_raise_facing=cnt_t_raise_facing+%s,
            val_t_raise_facing_bp=val_t_raise_facing_bp+%s,
            cnt_r_raise_facing=cnt_r_raise_facing+%s,
            val_r_raise_facing_bp=val_r_raise_facing_bp+%s,
            cnt_p_raise_made_2=cnt_p_raise_made_2+%s,
            val_p_raise_made_2_bp=val_p_raise_made_2_bp+%s,
            cnt_f_raise_made_2=cnt_f_raise_made_2+%s,
            val_f_raise_made_2_bp=val_f_raise_made_2_bp+%s,
            cnt_t_raise_made_2=cnt_t_raise_made_2+%s,
            val_t_raise_made_2_bp=val_t_raise_made_2_bp+%s,
            cnt_r_raise_made_2=cnt_r_raise_made_2+%s,
            val_r_raise_made_2_bp=val_r_raise_made_2_bp+%s,
            cnt_p_5bet_facing=cnt_p_5bet_facing+%s,
            val_p_5bet_facing_bp=val_p_5bet_facing_bp+%s,
            street2DelayedCBChance=street2DelayedCBChance+%s,
            street2DelayedCBDone=street2DelayedCBDone+%s,
            street2ProbeChance=street2ProbeChance+%s,
            street2ProbeDone=street2ProbeDone+%s
        WHERE id=%s"""

        self.query["select_hudcache_ring"] = """
                    SELECT id
                    FROM HudCache
                    WHERE gametypeId=%s
                    AND   playerId=%s
                    AND   seats=%s
                    AND   position=%s
                    AND   tourneyTypeId is NULL
                    AND   styleKey = %s"""

        self.query["select_hudcache_tour"] = """
                    SELECT id
                    FROM HudCache
                    WHERE gametypeId=%s
                    AND   playerId=%s
                    AND   seats=%s
                    AND   position=%s
                    AND   tourneyTypeId=%s
                    AND   styleKey = %s"""

        self.query["get_hero_hudcache_start"] = """select min(hc.styleKey)
                                                   from HudCache hc
                                                   where hc.playerId in <playerid_list>
                                                   and   hc.styleKey like 'd%'"""

        ####################################
        # Queries to insert/update cardscache
        ####################################

        self.query["insert_cardscache"] = """insert into CardsCache (
                weekId,
                monthId,
                gametypeId,
                tourneyTypeId,
                playerId,
                startCards,
                n,
                street0VPIChance,
                street0VPI,
                street0AggrChance,
                street0Aggr,
                street0CalledRaiseChance,
                street0CalledRaiseDone,
                street0_3BChance,
                street0_3BDone,
                street0_2BChance,
                street0_2BDone,
                street0_4BChance,
                street0_4BDone,
                street0_C4BChance,
                street0_C4BDone,
                street0_FoldTo2BChance,
                street0_FoldTo2BDone,
                street0_FoldTo3BChance,
                street0_FoldTo3BDone,
                street0_FoldTo4BChance,
                street0_FoldTo4BDone,
                street0_SqueezeChance,
                street0_SqueezeDone,
                raiseToStealChance,
                raiseToStealDone,
                stealChance,
                stealDone,
                success_Steal,
                street1Seen,
                street2Seen,
                street3Seen,
                street4Seen,
                sawShowdown,
                street1Aggr,
                street2Aggr,
                street3Aggr,
                street4Aggr,
                otherRaisedStreet0,
                otherRaisedStreet1,
                otherRaisedStreet2,
                otherRaisedStreet3,
                otherRaisedStreet4,
                foldToOtherRaisedStreet0,
                foldToOtherRaisedStreet1,
                foldToOtherRaisedStreet2,
                foldToOtherRaisedStreet3,
                foldToOtherRaisedStreet4,
                wonWhenSeenStreet1,
                wonWhenSeenStreet2,
                wonWhenSeenStreet3,
                wonWhenSeenStreet4,
                wonAtSD,
                raiseFirstInChance,
                raisedFirstIn,
                foldBbToStealChance,
                foldedBbToSteal,
                foldSbToStealChance,
                foldedSbToSteal,
                street1CBChance,
                street1CBDone,
                street2CBChance,
                street2CBDone,
                street3CBChance,
                street3CBDone,
                street4CBChance,
                street4CBDone,
                foldToStreet1CBChance,
                foldToStreet1CBDone,
                foldToStreet2CBChance,
                foldToStreet2CBDone,
                foldToStreet3CBChance,
                foldToStreet3CBDone,
                foldToStreet4CBChance,
                foldToStreet4CBDone,
                common,
                committed,
                winnings,
                rake,
                rakeDealt,
                rakeContributed,
                rakeWeighted,
                totalProfit,
                allInEV,
                showdownWinnings,
                nonShowdownWinnings,
                street1CheckCallRaiseChance,
                street1CheckCallDone,
                street1CheckRaiseDone,
                street2CheckCallRaiseChance,
                street2CheckCallDone,
                street2CheckRaiseDone,
                street3CheckCallRaiseChance,
                street3CheckCallDone,
                street3CheckRaiseDone,
                street4CheckCallRaiseChance,
                street4CheckCallDone,
                street4CheckRaiseDone,
                street0Calls,
                street1Calls,
                street2Calls,
                street3Calls,
                street4Calls,
                street0Bets,
                street1Bets,
                street2Bets,
                street3Bets,
                street4Bets,
                street0Raises,
                street1Raises,
                street2Raises,
                street3Raises,
                street4Raises,
                street1Discards,
                street2Discards,
                street3Discards)
            values (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s)"""

        self.query["update_cardscache"] = """
            UPDATE CardsCache SET
                    n=n+%s,
                    street0VPIChance=street0VPIChance+%s,
                    street0VPI=street0VPI+%s,
                    street0AggrChance=street0AggrChance+%s,
                    street0Aggr=street0Aggr+%s,
                    street0CalledRaiseChance=street0CalledRaiseChance+%s,
                    street0CalledRaiseDone=street0CalledRaiseDone+%s,
                    street0_2BChance=street0_2BChance+%s,
                    street0_2BDone=street0_2BDone+%s,
                    street0_3BChance=street0_3BChance+%s,
                    street0_3BDone=street0_3BDone+%s,
                    street0_4BChance=street0_4BChance+%s,
                    street0_4BDone=street0_4BDone+%s,
                    street0_C4BChance=street0_C4BChance+%s,
                    street0_C4BDone=street0_C4BDone+%s,
                    street0_FoldTo2BChance=street0_FoldTo2BChance+%s,
                    street0_FoldTo2BDone=street0_FoldTo2BDone+%s,
                    street0_FoldTo3BChance=street0_FoldTo3BChance+%s,
                    street0_FoldTo3BDone=street0_FoldTo3BDone+%s,
                    street0_FoldTo4BChance=street0_FoldTo4BChance+%s,
                    street0_FoldTo4BDone=street0_FoldTo4BDone+%s,
                    street0_SqueezeChance=street0_SqueezeChance+%s,
                    street0_SqueezeDone=street0_SqueezeDone+%s,
                    raiseToStealChance=raiseToStealChance+%s,
                    raiseToStealDone=raiseToStealDone+%s,
                    stealChance=stealChance+%s,
                    stealDone=stealDone+%s,
                    success_Steal=success_Steal+%s,
                    street1Seen=street1Seen+%s,
                    street2Seen=street2Seen+%s,
                    street3Seen=street3Seen+%s,
                    street4Seen=street4Seen+%s,
                    sawShowdown=sawShowdown+%s,
                    street1Aggr=street1Aggr+%s,
                    street2Aggr=street2Aggr+%s,
                    street3Aggr=street3Aggr+%s,
                    street4Aggr=street4Aggr+%s,
                    otherRaisedStreet0=otherRaisedStreet0+%s,
                    otherRaisedStreet1=otherRaisedStreet1+%s,
                    otherRaisedStreet2=otherRaisedStreet2+%s,
                    otherRaisedStreet3=otherRaisedStreet3+%s,
                    otherRaisedStreet4=otherRaisedStreet4+%s,
                    foldToOtherRaisedStreet0=foldToOtherRaisedStreet0+%s,
                    foldToOtherRaisedStreet1=foldToOtherRaisedStreet1+%s,
                    foldToOtherRaisedStreet2=foldToOtherRaisedStreet2+%s,
                    foldToOtherRaisedStreet3=foldToOtherRaisedStreet3+%s,
                    foldToOtherRaisedStreet4=foldToOtherRaisedStreet4+%s,
                    wonWhenSeenStreet1=wonWhenSeenStreet1+%s,
                    wonWhenSeenStreet2=wonWhenSeenStreet2+%s,
                    wonWhenSeenStreet3=wonWhenSeenStreet3+%s,
                    wonWhenSeenStreet4=wonWhenSeenStreet4+%s,
                    wonAtSD=wonAtSD+%s,
                    raiseFirstInChance=raiseFirstInChance+%s,
                    raisedFirstIn=raisedFirstIn+%s,
                    foldBbToStealChance=foldBbToStealChance+%s,
                    foldedBbToSteal=foldedBbToSteal+%s,
                    foldSbToStealChance=foldSbToStealChance+%s,
                    foldedSbToSteal=foldedSbToSteal+%s,
                    street1CBChance=street1CBChance+%s,
                    street1CBDone=street1CBDone+%s,
                    street2CBChance=street2CBChance+%s,
                    street2CBDone=street2CBDone+%s,
                    street3CBChance=street3CBChance+%s,
                    street3CBDone=street3CBDone+%s,
                    street4CBChance=street4CBChance+%s,
                    street4CBDone=street4CBDone+%s,
                    foldToStreet1CBChance=foldToStreet1CBChance+%s,
                    foldToStreet1CBDone=foldToStreet1CBDone+%s,
                    foldToStreet2CBChance=foldToStreet2CBChance+%s,
                    foldToStreet2CBDone=foldToStreet2CBDone+%s,
                    foldToStreet3CBChance=foldToStreet3CBChance+%s,
                    foldToStreet3CBDone=foldToStreet3CBDone+%s,
                    foldToStreet4CBChance=foldToStreet4CBChance+%s,
                    foldToStreet4CBDone=foldToStreet4CBDone+%s,
                    common=common+%s,
                    committed=committed+%s,
                    winnings=winnings+%s,
                    rake=rake+%s,
                    rakeDealt=rakeDealt+%s,
                    rakeContributed=rakeContributed+%s,
                    rakeWeighted=rakeWeighted+%s,
                    totalProfit=totalProfit+%s,
                    allInEV=allInEV+%s,
                    showdownWinnings=showdownWinnings+%s,
                    nonShowdownWinnings=nonShowdownWinnings+%s,
                    street1CheckCallRaiseChance=street1CheckCallRaiseChance+%s,
                    street1CheckCallDone=street1CheckCallDone+%s,
                    street1CheckRaiseDone=street1CheckRaiseDone+%s,
                    street2CheckCallRaiseChance=street2CheckCallRaiseChance+%s,
                    street2CheckCallDone=street2CheckCallDone+%s,
                    street2CheckRaiseDone=street2CheckRaiseDone+%s,
                    street3CheckCallRaiseChance=street3CheckCallRaiseChance+%s,
                    street3CheckCallDone=street3CheckCallDone+%s,
                    street3CheckRaiseDone=street3CheckRaiseDone+%s,
                    street4CheckCallRaiseChance=street4CheckCallRaiseChance+%s,
                    street4CheckCallDone=street4CheckCallDone+%s,
                    street4CheckRaiseDone=street4CheckRaiseDone+%s,
                    street0Calls=street0Calls+%s,
                    street1Calls=street1Calls+%s,
                    street2Calls=street2Calls+%s,
                    street3Calls=street3Calls+%s,
                    street4Calls=street4Calls+%s,
                    street0Bets=street0Bets+%s,
                    street1Bets=street1Bets+%s,
                    street2Bets=street2Bets+%s,
                    street3Bets=street3Bets+%s,
                    street4Bets=street4Bets+%s,
                    street0Raises=street0Raises+%s,
                    street1Raises=street1Raises+%s,
                    street2Raises=street2Raises+%s,
                    street3Raises=street3Raises+%s,
                    street4Raises=street4Raises+%s,
                    street1Discards=street1Discards+%s,
                    street2Discards=street2Discards+%s,
                    street3Discards=street3Discards+%s
        WHERE     id=%s"""

        self.query["select_cardscache_ring"] = """
                    SELECT id
                    FROM CardsCache
                    WHERE weekId=%s
                    AND   monthId=%s
                    AND   gametypeId=%s
                    AND   tourneyTypeId is NULL
                    AND   playerId=%s
                    AND   startCards=%s"""

        self.query["select_cardscache_tour"] = """
                    SELECT id
                    FROM CardsCache
                    WHERE weekId=%s
                    AND   monthId=%s
                    AND   gametypeId=%s
                    AND   tourneyTypeId=%s
                    AND   playerId=%s
                    AND   startCards=%s"""

        ####################################
        # create comment on players
        ####################################

        self.query["get_player_comment"] = """
            SELECT comment FROM Players WHERE id=%s
        """

        self.query["update_player_comment"] = """
            UPDATE Players SET comment=%s, commentTs=CURRENT_TIMESTAMP WHERE id=%s
        """
        self.query["get_player_name"] = "SELECT name FROM Players WHERE id=%s"

        ####################################

        ####################################
        # Queries to insert/update positionscache
        ####################################

        self.query["insert_positionscache"] = """insert into PositionsCache (
                weekId,
                monthId,
                gametypeId,
                tourneyTypeId,
                playerId,
                seats,
                maxPosition,
                position,
                n,
                street0VPIChance,
                street0VPI,
                street0AggrChance,
                street0Aggr,
                street0CalledRaiseChance,
                street0CalledRaiseDone,
                street0FaceRaise,
                street0_2BChance,
                street0_2BDone,
                street0_3BChance,
                street0_3BDone,
                street0_4BChance,
                street0_4BDone,
                street0_C4BChance,
                street0_C4BDone,
                street0_FoldTo2BChance,
                street0_FoldTo2BDone,
                street0_FoldTo3BChance,
                street0_FoldTo3BDone,
                street0_FoldTo4BChance,
                street0_FoldTo4BDone,
                street0_SqueezeChance,
                street0_SqueezeDone,
                raiseToStealChance,
                raiseToStealDone,
                stealChance,
                stealDone,
                success_Steal,
                street1Seen,
                street2Seen,
                street3Seen,
                street4Seen,
                sawShowdown,
                street1Aggr,
                street2Aggr,
                street3Aggr,
                street4Aggr,
                otherRaisedStreet0,
                otherRaisedStreet1,
                otherRaisedStreet2,
                otherRaisedStreet3,
                otherRaisedStreet4,
                foldToOtherRaisedStreet0,
                foldToOtherRaisedStreet1,
                foldToOtherRaisedStreet2,
                foldToOtherRaisedStreet3,
                foldToOtherRaisedStreet4,
                wonWhenSeenStreet1,
                wonWhenSeenStreet2,
                wonWhenSeenStreet3,
                wonWhenSeenStreet4,
                wonAtSD,
                raiseFirstInChance,
                raisedFirstIn,
                foldBbToStealChance,
                foldedBbToSteal,
                foldSbToStealChance,
                foldedSbToSteal,
                street1CBChance,
                street1CBDone,
                street2CBChance,
                street2CBDone,
                street3CBChance,
                street3CBDone,
                street4CBChance,
                street4CBDone,
                foldToStreet1CBChance,
                foldToStreet1CBDone,
                foldToStreet2CBChance,
                foldToStreet2CBDone,
                foldToStreet3CBChance,
                foldToStreet3CBDone,
                foldToStreet4CBChance,
                foldToStreet4CBDone,
                common,
                committed,
                winnings,
                rake,
                rakeDealt,
                rakeContributed,
                rakeWeighted,
                totalProfit,
                allInEV,
                showdownWinnings,
                nonShowdownWinnings,
                street1CheckCallRaiseChance,
                street1CheckCallDone,
                street1CheckRaiseDone,
                street2CheckCallRaiseChance,
                street2CheckCallDone,
                street2CheckRaiseDone,
                street3CheckCallRaiseChance,
                street3CheckCallDone,
                street3CheckRaiseDone,
                street4CheckCallRaiseChance,
                street4CheckCallDone,
                street4CheckRaiseDone,
                street0Calls,
                street1Calls,
                street2Calls,
                street3Calls,
                street4Calls,
                street0Bets,
                street1Bets,
                street2Bets,
                street3Bets,
                street4Bets,
                street0Raises,
                street1Raises,
                street2Raises,
                street3Raises,
                street4Raises,
                street1Discards,
                street2Discards,
                street3Discards)
            values (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                    )"""

        self.query["update_positionscache"] = """
            UPDATE PositionsCache SET
                    n=n+%s,
                    street0VPIChance=street0VPIChance+%s,
                    street0VPI=street0VPI+%s,
                    street0AggrChance=street0AggrChance+%s,
                    street0Aggr=street0Aggr+%s,
                    street0CalledRaiseChance=street0CalledRaiseChance+%s,
                    street0CalledRaiseDone=street0CalledRaiseDone+%s,
                    street0_2BChance=street0_2BChance+%s,
                    street0_2BDone=street0_2BDone+%s,
                    street0_3BChance=street0_3BChance+%s,
                    street0_3BDone=street0_3BDone+%s,
                    street0_4BChance=street0_4BChance+%s,
                    street0_4BDone=street0_4BDone+%s,
                    street0_C4BChance=street0_C4BChance+%s,
                    street0_C4BDone=street0_C4BDone+%s,
                    street0_FoldTo2BChance=street0_FoldTo2BChance+%s,
                    street0_FoldTo2BDone=street0_FoldTo2BDone+%s,
                    street0_FoldTo3BChance=street0_FoldTo3BChance+%s,
                    street0_FoldTo3BDone=street0_FoldTo3BDone+%s,
                    street0_FoldTo4BChance=street0_FoldTo4BChance+%s,
                    street0_FoldTo4BDone=street0_FoldTo4BDone+%s,
                    street0_SqueezeChance=street0_SqueezeChance+%s,
                    street0_SqueezeDone=street0_SqueezeDone+%s,
                    raiseToStealChance=raiseToStealChance+%s,
                    raiseToStealDone=raiseToStealDone+%s,
                    stealChance=stealChance+%s,
                    stealDone=stealDone+%s,
                    success_Steal=success_Steal+%s,
                    street1Seen=street1Seen+%s,
                    street2Seen=street2Seen+%s,
                    street3Seen=street3Seen+%s,
                    street4Seen=street4Seen+%s,
                    sawShowdown=sawShowdown+%s,
                    street1Aggr=street1Aggr+%s,
                    street2Aggr=street2Aggr+%s,
                    street3Aggr=street3Aggr+%s,
                    street4Aggr=street4Aggr+%s,
                    otherRaisedStreet0=otherRaisedStreet0+%s,
                    otherRaisedStreet1=otherRaisedStreet1+%s,
                    otherRaisedStreet2=otherRaisedStreet2+%s,
                    otherRaisedStreet3=otherRaisedStreet3+%s,
                    otherRaisedStreet4=otherRaisedStreet4+%s,
                    foldToOtherRaisedStreet0=foldToOtherRaisedStreet0+%s,
                    foldToOtherRaisedStreet1=foldToOtherRaisedStreet1+%s,
                    foldToOtherRaisedStreet2=foldToOtherRaisedStreet2+%s,
                    foldToOtherRaisedStreet3=foldToOtherRaisedStreet3+%s,
                    foldToOtherRaisedStreet4=foldToOtherRaisedStreet4+%s,
                    wonWhenSeenStreet1=wonWhenSeenStreet1+%s,
                    wonWhenSeenStreet2=wonWhenSeenStreet2+%s,
                    wonWhenSeenStreet3=wonWhenSeenStreet3+%s,
                    wonWhenSeenStreet4=wonWhenSeenStreet4+%s,
                    wonAtSD=wonAtSD+%s,
                    raiseFirstInChance=raiseFirstInChance+%s,
                    raisedFirstIn=raisedFirstIn+%s,
                    foldBbToStealChance=foldBbToStealChance+%s,
                    foldedBbToSteal=foldedBbToSteal+%s,
                    foldSbToStealChance=foldSbToStealChance+%s,
                    foldedSbToSteal=foldedSbToSteal+%s,
                    street1CBChance=street1CBChance+%s,
                    street1CBDone=street1CBDone+%s,
                    street2CBChance=street2CBChance+%s,
                    street2CBDone=street2CBDone+%s,
                    street3CBChance=street3CBChance+%s,
                    street3CBDone=street3CBDone+%s,
                    street4CBChance=street4CBChance+%s,
                    street4CBDone=street4CBDone+%s,
                    foldToStreet1CBChance=foldToStreet1CBChance+%s,
                    foldToStreet1CBDone=foldToStreet1CBDone+%s,
                    foldToStreet2CBChance=foldToStreet2CBChance+%s,
                    foldToStreet2CBDone=foldToStreet2CBDone+%s,
                    foldToStreet3CBChance=foldToStreet3CBChance+%s,
                    foldToStreet3CBDone=foldToStreet3CBDone+%s,
                    foldToStreet4CBChance=foldToStreet4CBChance+%s,
                    foldToStreet4CBDone=foldToStreet4CBDone+%s,
                    common=common+%s,
                    committed=committed+%s,
                    winnings=winnings+%s,
                    rake=rake+%s,
                    rakeDealt=rakeDealt+%s,
                    rakeContributed=rakeContributed+%s,
                    rakeWeighted=rakeWeighted+%s,
                    totalProfit=totalProfit+%s,
                    allInEV=allInEV+%s,
                    showdownWinnings=showdownWinnings+%s,
                    nonShowdownWinnings=nonShowdownWinnings+%s,
                    street1CheckCallRaiseChance=street1CheckCallRaiseChance+%s,
                    street1CheckCallDone=street1CheckCallDone+%s,
                    street1CheckRaiseDone=street1CheckRaiseDone+%s,
                    street2CheckCallRaiseChance=street2CheckCallRaiseChance+%s,
                    street2CheckCallDone=street2CheckCallDone+%s,
                    street2CheckRaiseDone=street2CheckRaiseDone+%s,
                    street3CheckCallRaiseChance=street3CheckCallRaiseChance+%s,
                    street3CheckCallDone=street3CheckCallDone+%s,
                    street3CheckRaiseDone=street3CheckRaiseDone+%s,
                    street4CheckCallRaiseChance=street4CheckCallRaiseChance+%s,
                    street4CheckCallDone=street4CheckCallDone+%s,
                    street4CheckRaiseDone=street4CheckRaiseDone+%s,
                    street0Calls=street0Calls+%s,
                    street1Calls=street1Calls+%s,
                    street2Calls=street2Calls+%s,
                    street3Calls=street3Calls+%s,
                    street4Calls=street4Calls+%s,
                    street0Bets=street0Bets+%s,
                    street1Bets=street1Bets+%s,
                    street2Bets=street2Bets+%s,
                    street3Bets=street3Bets+%s,
                    street4Bets=street4Bets+%s,
                    street0Raises=street0Raises+%s,
                    street1Raises=street1Raises+%s,
                    street2Raises=street2Raises+%s,
                    street3Raises=street3Raises+%s,
                    street4Raises=street4Raises+%s,
                    street1Discards=street1Discards+%s,
                    street2Discards=street2Discards+%s,
street3Discards=street3Discards+%s,
                          street0Limp=street0Limp+%s,
                          street0OpenLimpChance=street0OpenLimpChance+%s,
                          street0OpenLimp=street0OpenLimp+%s
                          WHERE id=%s"""

        self.query["select_positionscache_ring"] = """
                    SELECT id
                    FROM PositionsCache
                    WHERE weekId=%s
                    AND   monthId=%s
                    AND   gametypeId=%s
                    AND   tourneyTypeId is NULL
                    AND   playerId=%s
                    AND   seats=%s
                    AND   maxPosition=%s
                    AND   position=%s"""

        self.query["select_positionscache_tour"] = """
                    SELECT id
                    FROM PositionsCache
                    WHERE weekId=%s
                    AND   monthId=%s
                    AND   gametypeId=%s
                    AND   tourneyTypeId=%s
                    AND   playerId=%s
                    AND   seats=%s
                    AND   maxPosition=%s
                    AND   position=%s"""

        ####################################
        # Queries to rebuild/modify sessionscache
        ####################################

        self.query["clear_S_H"] = "UPDATE Hands SET sessionId = NULL"
        self.query["clear_S_T"] = "UPDATE Tourneys SET sessionId = NULL"
        self.query["clear_S_SC"] = "UPDATE SessionsCache SET sessionId = NULL"
        self.query["clear_S_TC"] = "UPDATE TourneysCache SET sessionId = NULL"
        self.query["clear_W_S"] = "UPDATE Sessions SET weekId = NULL"
        self.query["clear_M_S"] = "UPDATE Sessions SET monthId = NULL"
        self.query["clearSessionsCache"] = "DELETE FROM SessionsCache WHERE 1"
        self.query["clearTourneysCache"] = "DELETE FROM TourneysCache WHERE 1"
        self.query["clearSessions"] = "DELETE FROM Sessions WHERE 1"
        self.query["clearWeeks"] = "DELETE FROM Weeks WHERE 1"
        self.query["clearMonths"] = "DELETE FROM Months WHERE 1"
        self.query["update_RSC_H"] = "UPDATE Hands SET sessionId = %s WHERE id = %s"

        ####################################
        # select
        ####################################

        self.query["select_S_all"] = """
                    SELECT SC.id as id,
                    sessionStart,
                    weekStart,
                    monthStart,
                    weekId,
                    monthId
                    FROM Sessions SC
                    INNER JOIN Weeks WC ON (SC.weekId = WC.id)
                    INNER JOIN Months MC ON (SC.monthId = MC.id)
                    WHERE sessionEnd>=%s
                    AND sessionStart<=%s"""

        self.query["select_S"] = """
                    SELECT SC.id as id,
                    sessionStart,
                    sessionEnd,
                    weekStart,
                    monthStart,
                    weekId,
                    monthId
                    FROM Sessions SC
                    INNER JOIN Weeks WC ON (SC.weekId = WC.id)
                    INNER JOIN Months MC ON (SC.monthId = MC.id)
                    WHERE (sessionEnd>=%s AND sessionStart<=%s)
                    <TOURSELECT>"""

        self.query["select_W"] = """
                    SELECT id
                    FROM Weeks
                    WHERE weekStart = %s"""

        self.query["select_M"] = """
                    SELECT id
                    FROM Months
                    WHERE monthStart = %s"""

        self.query["select_SC"] = """
                    SELECT id,
                    sessionId,
                    startTime,
                    endTime,
                    n,
                    street0VPIChance,
                    street0VPI,
                    street0AggrChance,
                    street0Aggr,
                    street0CalledRaiseChance,
                    street0CalledRaiseDone,
                    street0_2BChance,
                    street0_2BDone,
                    street0_3BChance,
                    street0_3BDone,
                    street0_4BChance,
                    street0_4BDone,
                    street0_C4BChance,
                    street0_C4BDone,
                    street0_FoldTo2BChance,
                    street0_FoldTo2BDone,
                    street0_FoldTo3BChance,
                    street0_FoldTo3BDone,
                    street0_FoldTo4BChance,
                    street0_FoldTo4BDone,
                    street0_SqueezeChance,
                    street0_SqueezeDone,
                    raiseToStealChance,
                    raiseToStealDone,
                    stealChance,
                    stealDone,
                    success_Steal,
                    street1Seen,
                    street2Seen,
                    street3Seen,
                    street4Seen,
                    sawShowdown,
                    street1Aggr,
                    street2Aggr,
                    street3Aggr,
                    street4Aggr,
                    otherRaisedStreet0,
                    otherRaisedStreet1,
                    otherRaisedStreet2,
                    otherRaisedStreet3,
                    otherRaisedStreet4,
                    foldToOtherRaisedStreet0,
                    foldToOtherRaisedStreet1,
                    foldToOtherRaisedStreet2,
                    foldToOtherRaisedStreet3,
                    foldToOtherRaisedStreet4,
                    wonWhenSeenStreet1,
                    wonWhenSeenStreet2,
                    wonWhenSeenStreet3,
                    wonWhenSeenStreet4,
                    wonAtSD,
                    raiseFirstInChance,
                    raisedFirstIn,
                    foldBbToStealChance,
                    foldedBbToSteal,
                    foldSbToStealChance,
                    foldedSbToSteal,
                    street1CBChance,
                    street1CBDone,
                    street2CBChance,
                    street2CBDone,
                    street3CBChance,
                    street3CBDone,
                    street4CBChance,
                    street4CBDone,
                    foldToStreet1CBChance,
                    foldToStreet1CBDone,
                    foldToStreet2CBChance,
                    foldToStreet2CBDone,
                    foldToStreet3CBChance,
                    foldToStreet3CBDone,
                    foldToStreet4CBChance,
                    foldToStreet4CBDone,
                    common,
                    committed,
                    winnings,
                    rake,
                    rakeDealt,
                    rakeContributed,
                    rakeWeighted,
                    totalProfit,
                    allInEV,
                    showdownWinnings,
                    nonShowdownWinnings,
                    street1CheckCallRaiseChance,
                    street1CheckCallDone,
                    street1CheckRaiseDone,
                    street2CheckCallRaiseChance,
                    street2CheckCallDone,
                    street2CheckRaiseDone,
                    street3CheckCallRaiseChance,
                    street3CheckCallDone,
                    street3CheckRaiseDone,
                    street4CheckCallRaiseChance,
                    street4CheckCallDone,
                    street4CheckRaiseDone,
                    street0Calls,
                    street1Calls,
                    street2Calls,
                    street3Calls,
                    street4Calls,
                    street0Bets,
                    street1Bets,
                    street2Bets,
                    street3Bets,
                    street4Bets,
                    street0Raises,
                    street1Raises,
                    street2Raises,
                    street3Raises,
                    street4Raises,
                    street1Discards,
                    street2Discards,
                    street3Discards
                    FROM SessionsCache
                    WHERE endTime>=%s
                    AND startTime<=%s
                    AND gametypeId=%s
                    AND playerId=%s"""

        self.query["select_TC"] = """
                    SELECT id, startTime, endTime
                    FROM TourneysCache TC
                    WHERE tourneyId=%s
                    AND playerId=%s"""

        ####################################
        # insert
        ####################################

        self.query["insert_W"] = """insert into Weeks (
                    weekStart)
                    values (%s)"""

        self.query["insert_M"] = """insert into Months (
                    monthStart)
                    values (%s)"""

        self.query["insert_S"] = """insert into Sessions (
                    weekId,
                    monthId,
                    sessionStart,
                    sessionEnd)
                    values (%s, %s, %s, %s)"""

        self.query["insert_SC"] = """insert into SessionsCache (
                    sessionId,
                    startTime,
                    endTime,
                    gametypeId,
                    playerId,
                    n,
                    street0VPIChance,
                    street0VPI,
                    street0AggrChance,
                    street0Aggr,
                    street0CalledRaiseChance,
                    street0CalledRaiseDone,
                    street0_2BChance,
                    street0_2BDone,
                    street0_3BChance,
                    street0_3BDone,
                    street0_4BChance,
                    street0_4BDone,
                    street0_C4BChance,
                    street0_C4BDone,
                    street0_FoldTo2BChance,
                    street0_FoldTo2BDone,
                    street0_FoldTo3BChance,
                    street0_FoldTo3BDone,
                    street0_FoldTo4BChance,
                    street0_FoldTo4BDone,
                    street0_SqueezeChance,
                    street0_SqueezeDone,
                    raiseToStealChance,
                    raiseToStealDone,
                    stealChance,
                    stealDone,
                    success_Steal,
                    street1Seen,
                    street2Seen,
                    street3Seen,
                    street4Seen,
                    sawShowdown,
                    street1Aggr,
                    street2Aggr,
                    street3Aggr,
                    street4Aggr,
                    otherRaisedStreet0,
                    otherRaisedStreet1,
                    otherRaisedStreet2,
                    otherRaisedStreet3,
                    otherRaisedStreet4,
                    foldToOtherRaisedStreet0,
                    foldToOtherRaisedStreet1,
                    foldToOtherRaisedStreet2,
                    foldToOtherRaisedStreet3,
                    foldToOtherRaisedStreet4,
                    wonWhenSeenStreet1,
                    wonWhenSeenStreet2,
                    wonWhenSeenStreet3,
                    wonWhenSeenStreet4,
                    wonAtSD,
                    raiseFirstInChance,
                    raisedFirstIn,
                    foldBbToStealChance,
                    foldedBbToSteal,
                    foldSbToStealChance,
                    foldedSbToSteal,
                    street1CBChance,
                    street1CBDone,
                    street2CBChance,
                    street2CBDone,
                    street3CBChance,
                    street3CBDone,
                    street4CBChance,
                    street4CBDone,
                    foldToStreet1CBChance,
                    foldToStreet1CBDone,
                    foldToStreet2CBChance,
                    foldToStreet2CBDone,
                    foldToStreet3CBChance,
                    foldToStreet3CBDone,
                    foldToStreet4CBChance,
                    foldToStreet4CBDone,
                    common,
                    committed,
                    winnings,
                    rake,
                    rakeDealt,
                    rakeContributed,
                    rakeWeighted,
                    totalProfit,
                    allInEV,
                    showdownWinnings,
                    nonShowdownWinnings,
                    street1CheckCallRaiseChance,
                    street1CheckCallDone,
                    street1CheckRaiseDone,
                    street2CheckCallRaiseChance,
                    street2CheckCallDone,
                    street2CheckRaiseDone,
                    street3CheckCallRaiseChance,
                    street3CheckCallDone,
                    street3CheckRaiseDone,
                    street4CheckCallRaiseChance,
                    street4CheckCallDone,
                    street4CheckRaiseDone,
                    street0Calls,
                    street1Calls,
                    street2Calls,
                    street3Calls,
                    street4Calls,
                    street0Bets,
                    street1Bets,
                    street2Bets,
                    street3Bets,
                    street4Bets,
                    street0Raises,
                    street1Raises,
                    street2Raises,
                    street3Raises,
                    street4Raises,
                    street1Discards,
                    street2Discards,
                    street3Discards
                    )
                    values (%s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)"""

        self.query["insert_TC"] = """insert into TourneysCache (
                    sessionId,
                    startTime,
                    endTime,
                    tourneyId,
                    playerId,
                    n,
                    street0VPIChance,
                    street0VPI,
                    street0AggrChance,
                    street0Aggr,
                    street0CalledRaiseChance,
                    street0CalledRaiseDone,
                    street0_2BChance,
                    street0_2BDone,
                    street0_3BChance,
                    street0_3BDone,
                    street0_4BChance,
                    street0_4BDone,
                    street0_C4BChance,
                    street0_C4BDone,
                    street0_FoldTo2BChance,
                    street0_FoldTo2BDone,
                    street0_FoldTo3BChance,
                    street0_FoldTo3BDone,
                    street0_FoldTo4BChance,
                    street0_FoldTo4BDone,
                    street0_SqueezeChance,
                    street0_SqueezeDone,
                    raiseToStealChance,
                    raiseToStealDone,
                    stealChance,
                    stealDone,
                    success_Steal,
                    street1Seen,
                    street2Seen,
                    street3Seen,
                    street4Seen,
                    sawShowdown,
                    street1Aggr,
                    street2Aggr,
                    street3Aggr,
                    street4Aggr,
                    otherRaisedStreet0,
                    otherRaisedStreet1,
                    otherRaisedStreet2,
                    otherRaisedStreet3,
                    otherRaisedStreet4,
                    foldToOtherRaisedStreet0,
                    foldToOtherRaisedStreet1,
                    foldToOtherRaisedStreet2,
                    foldToOtherRaisedStreet3,
                    foldToOtherRaisedStreet4,
                    wonWhenSeenStreet1,
                    wonWhenSeenStreet2,
                    wonWhenSeenStreet3,
                    wonWhenSeenStreet4,
                    wonAtSD,
                    raiseFirstInChance,
                    raisedFirstIn,
                    foldBbToStealChance,
                    foldedBbToSteal,
                    foldSbToStealChance,
                    foldedSbToSteal,
                    street1CBChance,
                    street1CBDone,
                    street2CBChance,
                    street2CBDone,
                    street3CBChance,
                    street3CBDone,
                    street4CBChance,
                    street4CBDone,
                    foldToStreet1CBChance,
                    foldToStreet1CBDone,
                    foldToStreet2CBChance,
                    foldToStreet2CBDone,
                    foldToStreet3CBChance,
                    foldToStreet3CBDone,
                    foldToStreet4CBChance,
                    foldToStreet4CBDone,
                    common,
                    committed,
                    winnings,
                    rake,
                    rakeDealt,
                    rakeContributed,
                    rakeWeighted,
                    totalProfit,
                    allInEV,
                    showdownWinnings,
                    nonShowdownWinnings,
                    street1CheckCallRaiseChance,
                    street1CheckCallDone,
                    street1CheckRaiseDone,
                    street2CheckCallRaiseChance,
                    street2CheckCallDone,
                    street2CheckRaiseDone,
                    street3CheckCallRaiseChance,
                    street3CheckCallDone,
                    street3CheckRaiseDone,
                    street4CheckCallRaiseChance,
                    street4CheckCallDone,
                    street4CheckRaiseDone,
                    street0Calls,
                    street1Calls,
                    street2Calls,
                    street3Calls,
                    street4Calls,
                    street0Bets,
                    street1Bets,
                    street2Bets,
                    street3Bets,
                    street4Bets,
                    street0Raises,
                    street1Raises,
                    street2Raises,
                    street3Raises,
                    street4Raises,
                    street1Discards,
                    street2Discards,
                    street3Discards
                    )
                    values (%s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)"""

        ####################################
        # update
        ####################################

        self.query["update_WM_S"] = """
                    UPDATE Sessions SET
                    weekId=%s,
                    monthId=%s
                    WHERE id=%s"""

        self.query["update_S"] = """
                    UPDATE Sessions SET
                    weekId=%s,
                    monthId=%s,
                    sessionStart=%s,
                    sessionEnd=%s
                    WHERE id=%s"""

        self.query["update_SC"] = """
                    UPDATE SessionsCache SET
                    startTime=%s,
                    endTime=%s,
                    n=n+%s,
                    street0VPIChance=street0VPIChance+%s,
                    street0VPI=street0VPI+%s,
                    street0AggrChance=street0AggrChance+%s,
                    street0Aggr=street0Aggr+%s,
                    street0CalledRaiseChance=street0CalledRaiseChance+%s,
                    street0CalledRaiseDone=street0CalledRaiseDone+%s,
                    street0_2BChance=street0_2BChance+%s,
                    street0_2BDone=street0_2BDone+%s,
                    street0_3BChance=street0_3BChance+%s,
                    street0_3BDone=street0_3BDone+%s,
                    street0_4BChance=street0_4BChance+%s,
                    street0_4BDone=street0_4BDone+%s,
                    street0_C4BChance=street0_C4BChance+%s,
                    street0_C4BDone=street0_C4BDone+%s,
                    street0_FoldTo2BChance=street0_FoldTo2BChance+%s,
                    street0_FoldTo2BDone=street0_FoldTo2BDone+%s,
                    street0_FoldTo3BChance=street0_FoldTo3BChance+%s,
                    street0_FoldTo3BDone=street0_FoldTo3BDone+%s,
                    street0_FoldTo4BChance=street0_FoldTo4BChance+%s,
                    street0_FoldTo4BDone=street0_FoldTo4BDone+%s,
                    street0_SqueezeChance=street0_SqueezeChance+%s,
                    street0_SqueezeDone=street0_SqueezeDone+%s,
                    raiseToStealChance=raiseToStealChance+%s,
                    raiseToStealDone=raiseToStealDone+%s,
                    stealChance=stealChance+%s,
                    stealDone=stealDone+%s,
                    success_Steal=success_Steal+%s,
                    street1Seen=street1Seen+%s,
                    street2Seen=street2Seen+%s,
                    street3Seen=street3Seen+%s,
                    street4Seen=street4Seen+%s,
                    sawShowdown=sawShowdown+%s,
                    street1Aggr=street1Aggr+%s,
                    street2Aggr=street2Aggr+%s,
                    street3Aggr=street3Aggr+%s,
                    street4Aggr=street4Aggr+%s,
                    otherRaisedStreet0=otherRaisedStreet0+%s,
                    otherRaisedStreet1=otherRaisedStreet1+%s,
                    otherRaisedStreet2=otherRaisedStreet2+%s,
                    otherRaisedStreet3=otherRaisedStreet3+%s,
                    otherRaisedStreet4=otherRaisedStreet4+%s,
                    foldToOtherRaisedStreet0=foldToOtherRaisedStreet0+%s,
                    foldToOtherRaisedStreet1=foldToOtherRaisedStreet1+%s,
                    foldToOtherRaisedStreet2=foldToOtherRaisedStreet2+%s,
                    foldToOtherRaisedStreet3=foldToOtherRaisedStreet3+%s,
                    foldToOtherRaisedStreet4=foldToOtherRaisedStreet4+%s,
                    wonWhenSeenStreet1=wonWhenSeenStreet1+%s,
                    wonWhenSeenStreet2=wonWhenSeenStreet2+%s,
                    wonWhenSeenStreet3=wonWhenSeenStreet3+%s,
                    wonWhenSeenStreet4=wonWhenSeenStreet4+%s,
                    wonAtSD=wonAtSD+%s,
                    raiseFirstInChance=raiseFirstInChance+%s,
                    raisedFirstIn=raisedFirstIn+%s,
                    foldBbToStealChance=foldBbToStealChance+%s,
                    foldedBbToSteal=foldedBbToSteal+%s,
                    foldSbToStealChance=foldSbToStealChance+%s,
                    foldedSbToSteal=foldedSbToSteal+%s,
                    street1CBChance=street1CBChance+%s,
                    street1CBDone=street1CBDone+%s,
                    street2CBChance=street2CBChance+%s,
                    street2CBDone=street2CBDone+%s,
                    street3CBChance=street3CBChance+%s,
                    street3CBDone=street3CBDone+%s,
                    street4CBChance=street4CBChance+%s,
                    street4CBDone=street4CBDone+%s,
                    foldToStreet1CBChance=foldToStreet1CBChance+%s,
                    foldToStreet1CBDone=foldToStreet1CBDone+%s,
                    foldToStreet2CBChance=foldToStreet2CBChance+%s,
                    foldToStreet2CBDone=foldToStreet2CBDone+%s,
                    foldToStreet3CBChance=foldToStreet3CBChance+%s,
                    foldToStreet3CBDone=foldToStreet3CBDone+%s,
                    foldToStreet4CBChance=foldToStreet4CBChance+%s,
                    foldToStreet4CBDone=foldToStreet4CBDone+%s,
                    common=common+%s,
                    committed=committed+%s,
                    winnings=winnings+%s,
                    rake=rake+%s,
                    rakeDealt=rakeDealt+%s,
                    rakeContributed=rakeContributed+%s,
                    rakeWeighted=rakeWeighted+%s,
                    totalProfit=totalProfit+%s,
                    allInEV=allInEV+%s,
                    showdownWinnings=showdownWinnings+%s,
                    nonShowdownWinnings=nonShowdownWinnings+%s,
                    street1CheckCallRaiseChance=street1CheckCallRaiseChance+%s,
                    street1CheckCallDone=street1CheckCallDone+%s,
                    street1CheckRaiseDone=street1CheckRaiseDone+%s,
                    street2CheckCallRaiseChance=street2CheckCallRaiseChance+%s,
                    street2CheckCallDone=street2CheckCallDone+%s,
                    street2CheckRaiseDone=street2CheckRaiseDone+%s,
                    street3CheckCallRaiseChance=street3CheckCallRaiseChance+%s,
                    street3CheckCallDone=street3CheckCallDone+%s,
                    street3CheckRaiseDone=street3CheckRaiseDone+%s,
                    street4CheckCallRaiseChance=street4CheckCallRaiseChance+%s,
                    street4CheckCallDone=street4CheckCallDone+%s,
                    street4CheckRaiseDone=street4CheckRaiseDone+%s,
                    street0Calls=street0Calls+%s,
                    street1Calls=street1Calls+%s,
                    street2Calls=street2Calls+%s,
                    street3Calls=street3Calls+%s,
                    street4Calls=street4Calls+%s,
                    street0Bets=street0Bets+%s,
                    street1Bets=street1Bets+%s,
                    street2Bets=street2Bets+%s,
                    street3Bets=street3Bets+%s,
                    street4Bets=street4Bets+%s,
                    street0Raises=street0Raises+%s,
                    street1Raises=street1Raises+%s,
                    street2Raises=street2Raises+%s,
                    street3Raises=street3Raises+%s,
                    street4Raises=street4Raises+%s,
                    street1Discards=street1Discards+%s,
                    street2Discards=street2Discards+%s,
                    street3Discards=street3Discards+%s
                    WHERE id=%s"""

        self.query["update_TC"] = """
                    UPDATE TourneysCache SET
                    <UPDATE>
                    n=n+%s,
                    street0VPIChance=street0VPIChance+%s,
                    street0VPI=street0VPI+%s,
                    street0AggrChance=street0AggrChance+%s,
                    street0Aggr=street0Aggr+%s,
                    street0CalledRaiseChance=street0CalledRaiseChance+%s,
                    street0CalledRaiseDone=street0CalledRaiseDone+%s,
                    street0_2BChance=street0_2BChance+%s,
                    street0_2BDone=street0_2BDone+%s,
                    street0_3BChance=street0_3BChance+%s,
                    street0_3BDone=street0_3BDone+%s,
                    street0_4BChance=street0_4BChance+%s,
                    street0_4BDone=street0_4BDone+%s,
                    street0_C4BChance=street0_C4BChance+%s,
                    street0_C4BDone=street0_C4BDone+%s,
                    street0_FoldTo2BChance=street0_FoldTo2BChance+%s,
                    street0_FoldTo2BDone=street0_FoldTo2BDone+%s,
                    street0_FoldTo3BChance=street0_FoldTo3BChance+%s,
                    street0_FoldTo3BDone=street0_FoldTo3BDone+%s,
                    street0_FoldTo4BChance=street0_FoldTo4BChance+%s,
                    street0_FoldTo4BDone=street0_FoldTo4BDone+%s,
                    street0_SqueezeChance=street0_SqueezeChance+%s,
                    street0_SqueezeDone=street0_SqueezeDone+%s,
                    raiseToStealChance=raiseToStealChance+%s,
                    raiseToStealDone=raiseToStealDone+%s,
                    stealChance=stealChance+%s,
                    stealDone=stealDone+%s,
                    success_Steal=success_Steal+%s,
                    street1Seen=street1Seen+%s,
                    street2Seen=street2Seen+%s,
                    street3Seen=street3Seen+%s,
                    street4Seen=street4Seen+%s,
                    sawShowdown=sawShowdown+%s,
                    street1Aggr=street1Aggr+%s,
                    street2Aggr=street2Aggr+%s,
                    street3Aggr=street3Aggr+%s,
                    street4Aggr=street4Aggr+%s,
                    otherRaisedStreet0=otherRaisedStreet0+%s,
                    otherRaisedStreet1=otherRaisedStreet1+%s,
                    otherRaisedStreet2=otherRaisedStreet2+%s,
                    otherRaisedStreet3=otherRaisedStreet3+%s,
                    otherRaisedStreet4=otherRaisedStreet4+%s,
                    foldToOtherRaisedStreet0=foldToOtherRaisedStreet0+%s,
                    foldToOtherRaisedStreet1=foldToOtherRaisedStreet1+%s,
                    foldToOtherRaisedStreet2=foldToOtherRaisedStreet2+%s,
                    foldToOtherRaisedStreet3=foldToOtherRaisedStreet3+%s,
                    foldToOtherRaisedStreet4=foldToOtherRaisedStreet4+%s,
                    wonWhenSeenStreet1=wonWhenSeenStreet1+%s,
                    wonWhenSeenStreet2=wonWhenSeenStreet2+%s,
                    wonWhenSeenStreet3=wonWhenSeenStreet3+%s,
                    wonWhenSeenStreet4=wonWhenSeenStreet4+%s,
                    wonAtSD=wonAtSD+%s,
                    raiseFirstInChance=raiseFirstInChance+%s,
                    raisedFirstIn=raisedFirstIn+%s,
                    foldBbToStealChance=foldBbToStealChance+%s,
                    foldedBbToSteal=foldedBbToSteal+%s,
                    foldSbToStealChance=foldSbToStealChance+%s,
                    foldedSbToSteal=foldedSbToSteal+%s,
                    street1CBChance=street1CBChance+%s,
                    street1CBDone=street1CBDone+%s,
                    street2CBChance=street2CBChance+%s,
                    street2CBDone=street2CBDone+%s,
                    street3CBChance=street3CBChance+%s,
                    street3CBDone=street3CBDone+%s,
                    street4CBChance=street4CBChance+%s,
                    street4CBDone=street4CBDone+%s,
                    foldToStreet1CBChance=foldToStreet1CBChance+%s,
                    foldToStreet1CBDone=foldToStreet1CBDone+%s,
                    foldToStreet2CBChance=foldToStreet2CBChance+%s,
                    foldToStreet2CBDone=foldToStreet2CBDone+%s,
                    foldToStreet3CBChance=foldToStreet3CBChance+%s,
                    foldToStreet3CBDone=foldToStreet3CBDone+%s,
                    foldToStreet4CBChance=foldToStreet4CBChance+%s,
                    foldToStreet4CBDone=foldToStreet4CBDone+%s,
                    common=common+%s,
                    committed=committed+%s,
                    winnings=winnings+%s,
                    rake=rake+%s,
                    rakeDealt=rakeDealt+%s,
                    rakeContributed=rakeContributed+%s,
                    rakeWeighted=rakeWeighted+%s,
                    totalProfit=totalProfit+%s,
                    allInEV=allInEV+%s,
                    showdownWinnings=showdownWinnings+%s,
                    nonShowdownWinnings=nonShowdownWinnings+%s,
                    street1CheckCallRaiseChance=street1CheckCallRaiseChance+%s,
                    street1CheckCallDone=street1CheckCallDone+%s,
                    street1CheckRaiseDone=street1CheckRaiseDone+%s,
                    street2CheckCallRaiseChance=street2CheckCallRaiseChance+%s,
                    street2CheckCallDone=street2CheckCallDone+%s,
                    street2CheckRaiseDone=street2CheckRaiseDone+%s,
                    street3CheckCallRaiseChance=street3CheckCallRaiseChance+%s,
                    street3CheckCallDone=street3CheckCallDone+%s,
                    street3CheckRaiseDone=street3CheckRaiseDone+%s,
                    street4CheckCallRaiseChance=street4CheckCallRaiseChance+%s,
                    street4CheckCallDone=street4CheckCallDone+%s,
                    street4CheckRaiseDone=street4CheckRaiseDone+%s,
                    street0Calls=street0Calls+%s,
                    street1Calls=street1Calls+%s,
                    street2Calls=street2Calls+%s,
                    street3Calls=street3Calls+%s,
                    street4Calls=street4Calls+%s,
                    street0Bets=street0Bets+%s,
                    street1Bets=street1Bets+%s,
                    street2Bets=street2Bets+%s,
                    street3Bets=street3Bets+%s,
                    street4Bets=street4Bets+%s,
                    street0Raises=street0Raises+%s,
                    street1Raises=street1Raises+%s,
                    street2Raises=street2Raises+%s,
                    street3Raises=street3Raises+%s,
                    street4Raises=street4Raises+%s,
                    street1Discards=street1Discards+%s,
                    street2Discards=street2Discards+%s,
                    street3Discards=street3Discards+%s
                    WHERE tourneyId=%s
                    AND playerId=%s"""

        ####################################
        # delete
        ####################################

        self.query["delete_S"] = """
                    DELETE FROM Sessions
                    WHERE id=%s"""

        self.query["delete_SC"] = """
                    DELETE FROM SessionsCache
                    WHERE id=%s"""

        ####################################
        # update SessionsCache, Hands, Tourneys
        ####################################

        self.query["update_S_SC"] = """
                    UPDATE SessionsCache SET
                    sessionId=%s
                    WHERE sessionId=%s"""

        self.query["update_S_TC"] = """
                    UPDATE TourneysCache SET
                    sessionId=%s
                    WHERE sessionId=%s"""

        self.query["update_S_T"] = """
                    UPDATE Tourneys SET
                    sessionId=%s
                    WHERE sessionId=%s"""

        self.query["update_S_H"] = """
                    UPDATE Hands SET
                    sessionId=%s
                    WHERE sessionId=%s"""

        ####################################
        # update Tourneys w. sessionIds, hands, start/end
        ####################################

        self.query["updateTourneysSessions"] = """
                    UPDATE Tourneys SET
                    sessionId=%s
                    WHERE id=%s"""

        ####################################
        # Database management queries
        ####################################

        if db_server == "mysql":
            self.query["analyze"] = """
            analyze table Actions, Autorates, Backings, Boards, Files, Gametypes, Hands, HandsActions, HandsPlayers,
                          HandsStove, HudCache, Players, RawHands, RawTourneys, Sessions, Settings, Sites,
                          Tourneys, TourneysPlayers, TourneyTypes
            """
        elif db_server in ("postgresql", "sqlite"):
            self.query["analyze"] = "analyze"

        if db_server == "mysql":
            self.query["vacuum"] = """
            optimize table Actions, Autorates, Backings, Boards, Files, Gametypes, Hands, HandsActions, HandsPlayers,
                           HandsStove, HudCache, Players, RawHands, RawTourneys, Sessions, Settings, Sites,
                           Tourneys, TourneysPlayers, TourneyTypes
            """
        elif db_server in ("postgresql", "sqlite"):
            self.query["vacuum"] = """ vacuum """

        if db_server == "mysql":
            self.query["switchLockOn"] = """
                        UPDATE InsertLock k1,
                        (SELECT count(locked) as locks FROM InsertLock WHERE locked=True) as k2 SET
                        k1.locked=%s
                        WHERE k1.id=%s
                        AND k2.locks = 0"""

        if db_server == "mysql":
            self.query["switchLockOff"] = """
                        UPDATE InsertLock SET
                        locked=%s
                        WHERE id=%s"""

        if db_server == "mysql":
            self.query["lockForInsert"] = """
                lock tables Hands write, HandsPlayers write, HandsActions write, Players write
                          , HudCache write, Gametypes write, Sites write, Tourneys write
                          , TourneysPlayers write, TourneyTypes write, Autorates write
                """
        elif db_server in ("postgresql", "sqlite"):
            self.query["lockForInsert"] = ""

        self.query["getGametypeFL"] = """SELECT id
                                           FROM Gametypes
                                           WHERE siteId=%s
                                           AND   type=%s
                                           AND   category=%s
                                           AND   limitType=%s
                                           AND   smallBet=%s
                                           AND   bigBet=%s
                                           AND   maxSeats=%s
                                           AND   ante=%s
        """  # TODO: seems odd to have limitType variable in this query

        self.query["getGametypeNL"] = """SELECT id
                                           FROM Gametypes
                                           WHERE siteId=%s
                                           AND   type=%s
                                           AND   category=%s
                                           AND   limitType=%s
                                           AND   currency=%s
                                           AND   mix=%s
                                           AND   smallBlind=%s
                                           AND   bigBlind=%s
                                           AND   maxSeats=%s
                                           AND   ante=%s
                                           AND   buyinType=%s
                                           AND   fast=%s
                                           AND   newToGame=%s
                                           AND   homeGame=%s
                                           AND   split=%s
        """  # TODO: seems odd to have limitType variable in this query

        self.query[
            "insertGameTypes"
        ] = """insert into Gametypes (siteId, currency, type, base, category, limitType, hiLo, mix,
                                               smallBlind, bigBlind, smallBet, bigBet, maxSeats, ante, buyinType, fast, newToGame, homeGame, split)
                                           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        self.query["isAlreadyInDB"] = """SELECT H.id FROM Hands H
                                         INNER JOIN Gametypes G ON (H.gametypeId = G.id)
                                         WHERE siteHandNo=%s AND G.siteId=%s<heroSeat>
        """

        self.query["getTourneyTypeIdByTourneyNo"] = """SELECT tt.id,
                                                              tt.siteId,
                                                              tt.currency,
                                                              tt.buyin,
                                                              tt.fee,
                                                              tt.category,
                                                              tt.limitType,
                                                              tt.maxSeats,
                                                              tt.sng,
                                                              tt.knockout,
                                                              tt.koBounty,
                                                              tt.progressive,
                                                              tt.rebuy,
                                                              tt.rebuyCost,
                                                              tt.addOn,
                                                              tt.addOnCost,
                                                              tt.speed,
                                                              tt.shootout,
                                                              tt.matrix,
                                                              tt.fast,
                                                              tt.stack,
                                                              tt.step,
                                                              tt.stepNo,
                                                              tt.chance,
                                                              tt.chanceCount,
                                                              tt.multiEntry,
                                                              tt.reEntry,
                                                              tt.homeGame,
                                                              tt.newToGame,
                                                              tt.split,
                                                              tt.fifty50,
                                                              tt.time,
                                                              tt.timeAmt,
                                                              tt.satellite,
                                                              tt.doubleOrNothing,
                                                              tt.cashOut,
                                                              tt.onDemand,
                                                              tt.flighted,
                                                              tt.guarantee,
                                                              tt.guaranteeAmt,
                                                              tt.lottery,
                                                              tt.multiplier
                                                    FROM TourneyTypes tt
                                                    INNER JOIN Tourneys t ON (t.tourneyTypeId = tt.id)
                                                    WHERE t.siteTourneyNo=%s AND tt.siteId=%s
        """

        self.query["getTourneyTypeId"] = """SELECT  id
                                            FROM TourneyTypes
                                            WHERE siteId=%s
                                            AND currency=%s
                                            AND buyin=%s
                                            AND fee=%s
                                            AND category=%s
                                            AND limitType=%s
                                            AND maxSeats=%s
                                            AND sng=%s
                                            AND knockout=%s
                                            AND koBounty=%s
                                            AND progressive=%s
                                            AND rebuy=%s
                                            AND rebuyCost=%s
                                            AND addOn=%s
                                            AND addOnCost=%s
                                            AND speed=%s
                                            AND shootout=%s
                                            AND matrix=%s
                                            AND fast=%s
                                            AND stack=%s
                                            AND step=%s
                                            AND stepNo=%s
                                            AND chance=%s
                                            AND chanceCount=%s
                                            AND multiEntry=%s
                                            AND reEntry=%s
                                            AND homeGame=%s
                                            AND newToGame=%s
                                            AND split=%s
                                            AND fifty50=%s
                                            AND time=%s
                                            AND timeAmt=%s
                                            AND satellite=%s
                                            AND doubleOrNothing=%s
                                            AND cashOut=%s
                                            AND onDemand=%s
                                            AND flighted=%s
                                            AND guarantee=%s
                                            AND guaranteeAmt=%s
                                            AND lottery=%s
                                            AND multiplier=%s
        """

        self.query["insertTourneyType"] = """insert into TourneyTypes (
                                                   siteId, currency, buyin, fee, category, limitType, maxSeats, sng, knockout, koBounty, progressive,
                                                   rebuy, rebuyCost, addOn, addOnCost, speed, shootout, matrix, fast,
                                                   stack, step, stepNo, chance, chanceCount, multiEntry, reEntry, homeGame, newToGame, split,
                                                   fifty50, time, timeAmt, satellite, doubleOrNothing, cashOut, onDemand, flighted, guarantee, guaranteeAmt,
                                                   lottery, multiplier
                                                   )
                                              values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        if db_server == "sqlite":
            self.query["updateTourneyTypeId"] = """UPDATE Tourneys
                                                SET tourneyTypeId = %s
                                                WHERE tourneyTypeId in (SELECT id FROM TourneyTypes WHERE siteId=%s)
                                                AND siteTourneyNo=%s
            """
        elif db_server == "postgresql":
            self.query["updateTourneyTypeId"] = """UPDATE Tourneys t
                                                SET tourneyTypeId = %s
                                                FROM TourneyTypes tt
                                                WHERE t.tourneyTypeId = tt.id
                                                AND tt.siteId=%s
                                                AND t.siteTourneyNo=%s
            """
        else:
            self.query[
                "updateTourneyTypeId"
            ] = """UPDATE Tourneys t INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                                SET tourneyTypeId = %s
                                                WHERE tt.siteId=%s AND t.siteTourneyNo=%s
            """

        self.query["selectTourneyWithTypeId"] = """SELECT id
                                                FROM Tourneys
                                                WHERE tourneyTypeId = %s
        """

        self.query["deleteTourneyTypeId"] = """DELETE FROM TourneyTypes WHERE id = %s
        """

        self.query["getTourneyByTourneyNo"] = """SELECT t.*
                                        FROM Tourneys t
                                        INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                        WHERE tt.siteId=%s AND t.siteTourneyNo=%s
        """

        self.query["getTourneyInfo"] = """SELECT tt.*, t.*
                                        FROM Tourneys t
                                        INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                        INNER JOIN Sites s ON (tt.siteId = s.id)
                                        WHERE s.name=%s AND t.siteTourneyNo=%s
        """

        self.query["getSiteTourneyNos"] = """SELECT t.siteTourneyNo
                                        FROM Tourneys t
                                        INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                        INNER JOIN Sites s ON (tt.siteId = s.id)
                                        WHERE tt.siteId=%s
        """

        self.query["getTourneyPlayerInfo"] = """SELECT tp.*
                                        FROM Tourneys t
                                        INNER JOIN TourneyTypes tt ON (t.tourneyTypeId = tt.id)
                                        INNER JOIN Sites s ON (tt.siteId = s.id)
                                        INNER JOIN TourneysPlayers tp ON (tp.tourneyId = t.id)
                                        INNER JOIN Players p ON (p.id = tp.playerId)
                                        WHERE s.name=%s AND t.siteTourneyNo=%s AND p.name=%s
        """

        self.query["insertTourney"] = """insert into Tourneys (
                                             tourneyTypeId, sessionId, siteTourneyNo, entries, prizepool,
                                             startTime, endTime, tourneyName, totalRebuyCount, totalAddOnCount,
                                             comment, commentTs, added, addedCurrency)
                                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        self.query["updateTourney"] = """UPDATE Tourneys
                                             SET entries = %s,
                                                 prizepool = %s,
                                                 startTime = %s,
                                                 endTime = %s,
                                                 tourneyName = %s,
                                                 totalRebuyCount = %s,
                                                 totalAddOnCount = %s,
                                                 comment = %s,
                                                 commentTs = %s,
                                                 added = %s,
                                                 addedCurrency = %s
                                        WHERE id=%s
        """

        self.query["updateTourneyStart"] = """UPDATE Tourneys
                                             SET startTime = %s
                                        WHERE id=%s
        """

        self.query["updateTourneyEnd"] = """UPDATE Tourneys
                                             SET endTime = %s
                                        WHERE id=%s
        """

        self.query["getTourneysPlayersByIds"] = """SELECT *
                                                FROM TourneysPlayers
                                                WHERE tourneyId=%s AND playerId=%s AND entryId=%s
        """

        self.query["getTourneysPlayersByTourney"] = """SELECT playerId, entryId
                                                       FROM TourneysPlayers
                                                       WHERE tourneyId=%s
        """

        self.query["updateTourneysPlayer"] = """UPDATE TourneysPlayers
                                                 SET rank = %s,
                                                     winnings = %s,
                                                     winningsCurrency = %s,
                                                     rebuyCount = %s,
                                                     addOnCount = %s,
                                                     koCount = %s
                                                 WHERE id=%s
        """

        self.query["updateTourneysPlayerBounties"] = """UPDATE TourneysPlayers
                                                 SET koCount = case when koCount is null then %s else koCount+%s end
                                                 WHERE id=%s
        """

        self.query["updateTourneysPlayerResults"] = """UPDATE TourneysPlayers
                                                 SET rank = CASE WHEN %s IS NULL THEN rank ELSE %s END,
                                                     winnings = CASE WHEN %s IS NULL THEN winnings ELSE %s END,
                                                     winningsCurrency = CASE WHEN %s IS NULL THEN winningsCurrency ELSE %s END
                                                 WHERE id=%s
        """

        self.query["insertTourneysPlayer"] = """insert into TourneysPlayers (
                                                    tourneyId,
                                                    playerId,
                                                    entryId,
                                                    rank,
                                                    winnings,
                                                    winningsCurrency,
                                                    rebuyCount,
                                                    addOnCount,
                                                    koCount
                                                )
                                                values (%s, %s, %s, %s, %s,
                                                        %s, %s, %s, %s)
        """

        self.query["selectHandsPlayersWithWrongTTypeId"] = """SELECT id
                                                              FROM HandsPlayers
                                                              WHERE tourneyTypeId <> %s AND (TourneysPlayersId+0=%s)
        """

        #            self.query['updateHandsPlayersForTTypeId2'] = """UPDATE HandsPlayers
        #                                                            SET tourneyTypeId= %s
        #                                                            WHERE (TourneysPlayersId+0=%s)
        #            """

        self.query["updateHandsPlayersForTTypeId"] = """UPDATE HandsPlayers
                                                         SET tourneyTypeId= %s
                                                         WHERE (id=%s)
        """

        self.query["handsPlayersTTypeId_joiner"] = " OR TourneysPlayersId+0="
        self.query["handsPlayersTTypeId_joiner_id"] = " OR id="

        self.query["store_hand"] = """insert into Hands (
                                            tablename,
                                            sitehandno,
                                            tourneyId,
                                            gametypeid,
                                            sessionId,
                                            fileId,
                                            startTime,
                                            importtime,
                                            seats,
                                            heroSeat,
                                            maxPosition,
                                            texture,
                                            playersVpi,
                                            boardcard1,
                                            boardcard2,
                                            boardcard3,
                                            boardcard4,
                                            boardcard5,
                                            runItTwice,
                                            playersAtStreet1,
                                            playersAtStreet2,
                                            playersAtStreet3,
                                            playersAtStreet4,
                                            playersAtShowdown,
                                            street0Raises,
                                            street1Raises,
                                            street2Raises,
                                            street3Raises,
                                            street4Raises,
                                            street0Pot,
                                            street1Pot,
                                            street2Pot,
                                            street3Pot,
                                            street4Pot,
                                            finalPot,
                                            bombPot
                                             )
                                             values
                                              (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                               %s, %s, %s)"""

        self.query["store_hands_players"] = """insert into HandsPlayers (
                handId,
                playerId,
                startCash,
                effStack,
                startBounty,
                endBounty,
                seatNo,
                sitout,
                card1,
                card2,
                card3,
                card4,
                card5,
                card6,
                card7,
                card8,
                card9,
                card10,
                card11,
                card12,
                card13,
                card14,
                card15,
                card16,
                card17,
                card18,
                card19,
                card20,
                common,
                committed,
                winnings,
                rake,
                rakeDealt,
                rakeContributed,
                rakeWeighted,
                totalProfit,
                allInEV,
                street0VPIChance,
                street0VPI,
                street1Seen,
                street2Seen,
                street3Seen,
                street4Seen,
                sawShowdown,
                showed,
                street0AllIn,
                street1AllIn,
                street2AllIn,
                street3AllIn,
                street4AllIn,
                wentAllIn,
                street0AggrChance,
                street0Aggr,
                street1Aggr,
                street2Aggr,
                street3Aggr,
                street4Aggr,
                street1CBChance,
                street2CBChance,
                street3CBChance,
                street4CBChance,
                street1CBDone,
                street2CBDone,
                street3CBDone,
                street4CBDone,
                wonWhenSeenStreet1,
                wonWhenSeenStreet2,
                wonWhenSeenStreet3,
                wonWhenSeenStreet4,
                wonAtSD,
                position,
                street0InPosition,
                street1InPosition,
                street2InPosition,
                street3InPosition,
                street4InPosition,
                street0FirstToAct,
                street1FirstToAct,
                street2FirstToAct,
                street3FirstToAct,
                street4FirstToAct,
                tourneysPlayersId,
                startCards,
                street0CalledRaiseChance,
                street0CalledRaiseDone,
                street0FaceRaise,
                street0_2BChance,
                street0_2BDone,
                street0_3BChance,
                street0_3BDone,
                street0_4BChance,
                street0_4BDone,
                street0_C4BChance,
                street0_C4BDone,
                street0_FoldTo2BChance,
                street0_FoldTo2BDone,
                street0_FoldTo3BChance,
                street0_FoldTo3BDone,
                street0_FoldTo4BChance,
                street0_FoldTo4BDone,
                street0_SqueezeChance,
                street0_SqueezeDone,
                raiseToStealChance,
                raiseToStealDone,
                stealChance,
                stealDone,
                success_Steal,
                otherRaisedStreet0,
                otherRaisedStreet1,
                otherRaisedStreet2,
                otherRaisedStreet3,
                otherRaisedStreet4,
                foldToOtherRaisedStreet0,
                foldToOtherRaisedStreet1,
                foldToOtherRaisedStreet2,
                foldToOtherRaisedStreet3,
                foldToOtherRaisedStreet4,
                raiseFirstInChance,
                raisedFirstIn,
                foldBbToStealChance,
                foldedBbToSteal,
                foldSbToStealChance,
                foldedSbToSteal,
                foldToStreet1CBChance,
                foldToStreet1CBDone,
                foldToStreet2CBChance,
                foldToStreet2CBDone,
                foldToStreet3CBChance,
                foldToStreet3CBDone,
                foldToStreet4CBChance,
                foldToStreet4CBDone,
                street1CheckCallRaiseChance,
                street1CheckCallDone,
                street1CheckRaiseDone,
                street2CheckCallRaiseChance,
                street2CheckCallDone,
                street2CheckRaiseDone,
                street3CheckCallRaiseChance,
                street3CheckCallDone,
                street3CheckRaiseDone,
                street4CheckCallRaiseChance,
                street4CheckCallDone,
                street4CheckRaiseDone,
                street0Calls,
                street1Calls,
                street2Calls,
                street3Calls,
                street4Calls,
                street0Bets,
                street1Bets,
                street2Bets,
                street3Bets,
                street4Bets,
                street0Raises,
                street1Raises,
                street2Raises,
                street3Raises,
                street4Raises,
street1Discards,
                 street2Discards,
                 street3Discards,
                 street0Limp,
                 street0OpenLimp,
                 handString,
                 cashOutFee,
                 isCashOut,
                 street1_3BChance,
                 street1_3BDone,
                 street2_3BChance,
                 street2_3BDone,
                 street3_3BChance,
                 street3_3BDone,
                 street1_4BChance,
                 street1_4BDone,
                 street1_FoldTo4BChance,
                 street1_FoldTo4BDone,
                 street2_4BChance,
                 street2_4BDone,
                 street2_FoldTo4BChance,
                 street2_FoldTo4BDone,
                 street3_4BChance,
                 street3_4BDone,
                 street3_FoldTo4BChance,
                 street3_FoldTo4BDone,
                 street1OpenChance,
                 street1OpenDone,
                 street2OpenChance,
                 street2OpenDone,
                 street3OpenChance,
                 street3OpenDone,
                 flg_f_fold,
                 flg_t_fold,
                 flg_r_fold,
                 street1FirstRaise,
                 street2FirstRaise,
                 street3FirstRaise,
                 street1FaceRaise,
                 street2FaceRaise,
                 street3FaceRaise,
                 flg_f_donk_def_opp,
                 flg_t_float_opp,
                 flg_t_float,
                 flg_t_float_def_opp,
                 flg_r_float_opp,
                 flg_r_float,
                 flg_r_float_def_opp,
                 flg_t_donk_def_opp,
                 flg_r_donk_def_opp,
                 street1_FoldTo3BChance,
                 street1_FoldTo3BDone,
                 street2_FoldTo3BChance,
                 street2_FoldTo3BDone,
                 street3_FoldTo3BChance,
                 street3_FoldTo3BDone,
                 street0_FoldToSqueezeChance,
                 street0_FoldToSqueezeDone,
                 street0_FaceLimpers,
                 cnt_gp_open_opp,
                 cnt_gp_2x,
                 cnt_gp_os,
                 cnt_gp_limp,
                 flg_blind_ds,
                 flg_blind_db,
                 flg_blind_k,
                 flg_faced_allin,
                 flg_fold_to_allin,
                 cnt_f_bet_facing,
                 val_f_bet_facing_bp,
                 cnt_t_bet_facing,
                 val_t_bet_facing_bp,
                 cnt_r_bet_facing,
                 val_r_bet_facing_bp,
                 cnt_p_2bet_facing,
                 val_p_2bet_facing_bp,
                 cnt_p_3bet_facing,
                 val_p_3bet_facing_bp,
                 cnt_p_4bet_facing,
                 val_p_4bet_facing_bp,
                 cnt_f_bet_made,
                 val_f_bet_made_bp,
                 cnt_t_bet_made,
                 val_t_bet_made_bp,
                 cnt_r_bet_made,
                 val_r_bet_made_bp,
                 cnt_f_spr,
                 val_f_spr,
                 cnt_t_spr,
                 val_t_spr,
                 cnt_r_spr,
                 val_r_spr,
                 cnt_p_raise_made,
                 val_p_raise_made_bp,
                 cnt_f_raise_made,
                 val_f_raise_made_bp,
                 cnt_t_raise_made,
                 val_t_raise_made_bp,
                 cnt_r_raise_made,
                 val_r_raise_made_bp,
                 cnt_f_2bet_facing,
                 val_f_2bet_facing_bp,
                 cnt_f_3bet_facing,
                 val_f_3bet_facing_bp,
                 cnt_f_4bet_facing,
                 val_f_4bet_facing_bp,
                 cnt_t_2bet_facing,
                 val_t_2bet_facing_bp,
                 cnt_t_3bet_facing,
                 val_t_3bet_facing_bp,
                 cnt_t_4bet_facing,
                 val_t_4bet_facing_bp,
                 cnt_r_2bet_facing,
                 val_r_2bet_facing_bp,
                 cnt_r_3bet_facing,
                 val_r_3bet_facing_bp,
                 cnt_r_4bet_facing,
                 val_r_4bet_facing_bp,
                 amt_blind,
                 amt_bet_p,
                 amt_bet_f,
                 amt_bet_t,
                 amt_bet_r,
                 amt_bet_ttl,
                 cnt_p_raise_facing,
                 val_p_raise_facing_bp,
                 cnt_f_raise_facing,
                 val_f_raise_facing_bp,
                 cnt_t_raise_facing,
                 val_t_raise_facing_bp,
                 cnt_r_raise_facing,
                 val_r_raise_facing_bp,
                 cnt_p_raise_made_2,
                 val_p_raise_made_2_bp,
                 cnt_f_raise_made_2,
                 val_f_raise_made_2_bp,
                 cnt_t_raise_made_2,
                 val_t_raise_made_2_bp,
                 cnt_r_raise_made_2,
                 val_r_raise_made_2_bp,
                 cnt_p_5bet_facing,
                 val_p_5bet_facing_bp,
                 street2DelayedCBChance,
                 street2DelayedCBDone,
                 street2ProbeChance,
                 street2ProbeDone
                )
                values (
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s,
                     %s, %s,
                     %s, %s,
                     %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
                )"""

        self.query["store_hands_actions"] = """insert into HandsActions (
                        handId,
                        playerId,
                        street,
                        actionNo,
                        streetActionNo,
                        actionId,
                        amount,
                        raiseTo,
                        amountCalled,
                        numDiscarded,
                        cardsDiscarded,
                        allIn
               )
               values (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )"""

        self.query["store_hands_stove"] = """insert into HandsStove (
                        handId,
                        playerId,
                        streetId,
                        boardId,
                        hiLo,
                        rankId,
                        value,
                        cards,
                        ev
               )
               values (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
               )"""

        self.query["store_hands_showdown"] = """insert into HandsShowdown (
                        handId,
                        playerId,
                        combo,
                        cards
               )
               values (
                    %s, %s, %s, %s
               )"""

        self.query["get_hands_showdown"] = """select p.name, hs.combo, hs.cards
                from HandsShowdown hs, Players p
                where hs.handId=%s and hs.playerId=p.id"""

        self.query["store_hands_cashout"] = """insert into HandsCashout (
                        handId,
                        playerId,
                        amount,
                        fee
               )
               values (
                    %s, %s, %s, %s
               )"""

        self.query["get_hands_cashout"] = """select p.name, hc.amount, hc.fee
                from HandsCashout hc, Players p
                where hc.handId=%s and hc.playerId=p.id"""

        self.query["find_player_auto_note"] = """select id
                from PlayerAutoNotes
                where playerId=%s and handId=%s and ruleId=%s and ruleVersion=%s"""

        self.query["store_player_auto_note"] = """insert into PlayerAutoNotes (
                        playerId,
                        handId,
                        ruleId,
                        ruleVersion,
                        noteText,
                        evidence
               )
               values (
                    %s, %s, %s, %s, %s, %s
               )"""

        self.query["update_player_auto_note"] = """update PlayerAutoNotes
                set noteText=%s, evidence=%s, updatedTs=CURRENT_TIMESTAMP
                where id=%s"""

        self.query["count_player_auto_notes"] = """select count(*)
                from PlayerAutoNotes
                where playerId=%s"""

        self.query["get_player_auto_notes"] = """select
                    pan.id,
                    pan.handId,
                    pan.ruleId,
                    pan.ruleVersion,
                    pan.noteText,
                    pan.evidence,
                    pan.createdTs,
                    pan.updatedTs,
                    h.siteHandNo,
                    h.startTime
                from PlayerAutoNotes pan
                left join Hands h on pan.handId=h.id
                where pan.playerId=%s
                order by pan.createdTs desc, pan.id desc"""

        self.query["search_players_with_auto_notes"] = """select distinct
                    p.id,
                    p.name,
                    p.siteId
                from Players p
                join PlayerAutoNotes pan on pan.playerId=p.id
                where lower(p.name) like lower(%s)
                order by p.name
                limit 50"""

        self.query["get_recent_player_auto_notes"] = """select
                    pan.id,
                    pan.playerId,
                    p.name,
                    pan.handId,
                    h.siteHandNo,
                    pan.ruleId,
                    pan.ruleVersion,
                    pan.noteText,
                    pan.evidence,
                    pan.createdTs,
                    pan.updatedTs,
                    h.startTime
                from PlayerAutoNotes pan
                join Players p on pan.playerId=p.id
                left join Hands h on pan.handId=h.id
                left join Gametypes g on h.gametypeId=g.id
                /*AUTONOTE_FILTERS*/
                order by pan.createdTs desc, pan.id desc
                limit %s"""

        self.query["get_auto_note_player_summary"] = """select
                    pan.playerId,
                    p.name,
                    count(*) as noteCount,
                    max(pan.createdTs) as lastNoteTs
                from PlayerAutoNotes pan
                join Players p on pan.playerId=p.id
                left join Hands h on pan.handId=h.id
                left join Gametypes g on h.gametypeId=g.id
                /*AUTONOTE_FILTERS*/
                group by pan.playerId, p.name
                order by noteCount desc, p.name
                limit %s"""

        self.query["get_auto_note_rule_summary"] = """select
                    pan.ruleId,
                    count(*) as noteCount
                from PlayerAutoNotes pan
                join Players p on pan.playerId=p.id
                left join Hands h on pan.handId=h.id
                left join Gametypes g on h.gametypeId=g.id
                /*AUTONOTE_FILTERS*/
                group by pan.ruleId
                order by noteCount desc, pan.ruleId
                limit %s"""

        self.query["player_has_any_notes"] = """select
                case
                    when exists (
                        select 1 from Players
                        where id=%s and comment is not null and comment <> ''
                    ) then 1
                    when exists (
                        select 1 from PlayerAutoNotes
                        where playerId=%s
                    ) then 1
                    else 0
                end"""

        self.query["store_boards"] = """insert into Boards (
                        handId,
                        boardId,
                        boardcard1,
                        boardcard2,
                        boardcard3,
                        boardcard4,
                        boardcard5
               )
               values (
                    %s, %s, %s, %s, %s,
                    %s, %s
                )"""

        self.query["store_hands_pots"] = """insert into HandsPots (
                        handId,
                        potId,
                        boardId,
                        hiLo,
                        playerId,
                        pot,
                        collected,
                        rake
               )
               values (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
               )"""

        ################################
        # queries for Files Table
        ################################

        self.query["get_id"] = """
                        SELECT id
                        FROM Files
                        WHERE file=%s"""

        self.query["store_file"] = """  insert into Files (
                        file,
                        site,
                        startTime,
                        lastUpdate,
                        hands,
                        storedHands,
                        dups,
                        partial,
                        skipped,
                        errs,
                        ttime100,
                        finished)
               values (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )"""

        self.query["update_file"] = """
                    UPDATE Files SET
                    type=%s,
                    lastUpdate=%s,
                    endTime=%s,
                    hands=hands+%s,
                    storedHands=storedHands+%s,
                    dups=dups+%s,
                    partial=partial+%s,
                    skipped=skipped+%s,
                    errs=errs+%s,
                    ttime100=ttime100+%s,
                    finished=%s
                    WHERE id=%s"""

        ################################
        # Counts for DB stats window
        ################################
        self.query["getHandCount"] = "SELECT COUNT(*) FROM Hands"
        self.query["getTourneyCount"] = "SELECT COUNT(*) FROM Tourneys"
        self.query["getTourneyTypeCount"] = "SELECT COUNT(*) FROM TourneyTypes"

        ################################
        # queries for dumpDatabase
        ################################
        for table in (
            "Autorates",
            "Backings",
            "Gametypes",
            "Hands",
            "HandsActions",
            "HandsPlayers",
            "HudCache",
            "Players",
            "RawHands",
            "RawTourneys",
            "Settings",
            "Sites",
            "TourneyTypes",
            "Tourneys",
            "TourneysPlayers",
        ):
            self.query["get" + table] = "SELECT * FROM " + table

        ################################
        # placeholders and substitution stuff
        ################################
        if db_server in ("mysql", "postgresql"):
            self.query["placeholder"] = "%s"
        elif db_server == "sqlite":
            self.query["placeholder"] = "?"

        # If using sqlite, use the ? placeholder instead of %s
        if db_server == "sqlite":
            for k, q in list(self.query.items()):
                self.query[k] = re.sub("%s", "?", q)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB SQL utility")
    parser.add_argument("--list-queries", action="store_true", help="List all available SQL queries")
    parser.add_argument("--show-query", metavar="QUERY_NAME", help="Show a specific SQL query")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    try:
        s = Sql()
    except Exception as e:  # intentional broad catch: CLI top-level Sql() init boundary
        print(f"Error initializing SQL: {e}")
        return 1

    if args.list_queries:
        print("=== Available SQL Queries ===")
        print(f"Total queries: {len(s.query)}")
        for i, query_name in enumerate(sorted(s.query.keys()), 1):
            print(f"  {i:3}. {query_name}")

    if args.show_query:
        query_name = args.show_query
        if query_name in s.query:
            print(f"\n=== Query: {query_name} ===")
            print(s.query[query_name])
        else:
            print(f"Query '{query_name}' not found")
            print("Use --list-queries to see available queries")
            return 1

    if args.interactive:
        print("Running original interactive test...")
        s = Sql()
        for _key in s.query:
            pass
        print("Interactive test complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
