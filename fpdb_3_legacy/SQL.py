#!/usr/bin/env python
from __future__ import annotations

"""Returns a dict of SQL statements used in fpdb."""

import re
import sys

from fpdb_3_legacy.sql_indexes import index_queries
from fpdb_3_legacy.sql_metadata import metadata_queries
from fpdb_3_legacy.sql_queries_cache_maintenance import cache_maintenance_queries
from fpdb_3_legacy.sql_queries_cache_rebuild import cache_rebuild_queries
from fpdb_3_legacy.sql_queries_cards_cache_write import cards_cache_write_queries
from fpdb_3_legacy.sql_queries_cash_profit import cash_profit_queries
from fpdb_3_legacy.sql_queries_core import core_lookup_queries
from fpdb_3_legacy.sql_queries_database_admin import database_admin_queries
from fpdb_3_legacy.sql_queries_filters import filter_queries
from fpdb_3_legacy.sql_queries_game_types import game_type_queries
from fpdb_3_legacy.sql_queries_hand_artifacts import hand_artifact_queries
from fpdb_3_legacy.sql_queries_hand_detail import hand_detail_queries
from fpdb_3_legacy.sql_queries_hand_player_persistence import hand_player_persistence_queries
from fpdb_3_legacy.sql_queries_hand_root_persistence import hand_root_persistence_queries
from fpdb_3_legacy.sql_queries_history import history_window_queries
from fpdb_3_legacy.sql_queries_hud_cache_write import hud_cache_write_queries
from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries
from fpdb_3_legacy.sql_queries_opponents import opponent_report_queries
from fpdb_3_legacy.sql_queries_player_auto_notes import player_auto_note_queries
from fpdb_3_legacy.sql_queries_player_detailed import player_detailed_report_queries
from fpdb_3_legacy.sql_queries_player_position import player_position_stats_queries
from fpdb_3_legacy.sql_queries_player_stats import player_stats_queries
from fpdb_3_legacy.sql_queries_positions_cache_write import positions_cache_write_queries
from fpdb_3_legacy.sql_queries_replayer import replayer_queries
from fpdb_3_legacy.sql_queries_session_cache_write import session_cache_write_queries
from fpdb_3_legacy.sql_queries_session_stats import session_stats_queries
from fpdb_3_legacy.sql_queries_tournament_graph import tournament_graph_queries
from fpdb_3_legacy.sql_queries_tournament_persistence import tournament_persistence_queries
from fpdb_3_legacy.sql_queries_tournament_player import tournament_player_detailed_queries
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
        self.query.update(database_admin_queries(db_server))
        self.query.update(cash_profit_queries())
        self.query.update(cache_maintenance_queries())
        self.query.update(cache_rebuild_queries(db_server))
        self.query.update(cards_cache_write_queries())
        self.query.update(filter_queries(db_server))
        self.query.update(game_type_queries(db_server))
        self.query.update(hand_artifact_queries())
        self.query.update(hand_detail_queries())
        self.query.update(hand_player_persistence_queries())
        self.query.update(hand_root_persistence_queries())
        self.query.update(history_window_queries(db_server))
        self.query.update(hud_cache_write_queries())
        self.query.update(import_auxiliary_queries())
        self.query.update(opponent_report_queries(db_server))
        self.query.update(player_detailed_report_queries(db_server))
        self.query.update(player_position_stats_queries(db_server))
        self.query.update(player_auto_note_queries())
        self.query.update(player_stats_queries(db_server))
        self.query.update(positions_cache_write_queries())
        self.query.update(replayer_queries())
        self.query.update(session_cache_write_queries())
        self.query.update(session_stats_queries(db_server))
        self.query.update(tournament_player_detailed_queries(db_server))
        self.query.update(tournament_graph_queries())
        self.query.update(tournament_persistence_queries())
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

        ####################################
        # Queries to rebuild/modify sessionscache
        ####################################

        ####################################
        # Database management queries
        ####################################









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
