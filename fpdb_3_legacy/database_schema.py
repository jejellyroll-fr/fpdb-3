"""Schema construction and reference data for the fpdb database.

Split out of Database.py: these methods own the DDL -- creating and dropping
tables, indexes and foreign keys -- and the reference rows every fresh database
needs. The per-backend index and foreign-key catalogues live here too, with the
code that applies them.

The mixin borrows connection and cursor handling from its host; the borrowings
are declared below so the coupling is visible.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.database_caches import CACHE_KEYS, HUDCACHE_EXTRA_KEYS
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

# Schema version written into Settings by create_tables and checked on connect.
DB_VERSION = 224

# Keys used to index into player data in storeHandsPlayers.
HANDS_PLAYERS_KEYS = [
    "startCash",
    "effStack",
    "startBounty",
    "endBounty",
    "seatNo",
    "sitout",
    "card1",
    "card2",
    "card3",
    "card4",
    "card5",
    "card6",
    "card7",
    "card8",
    "card9",
    "card10",
    "card11",
    "card12",
    "card13",
    "card14",
    "card15",
    "card16",
    "card17",
    "card18",
    "card19",
    "card20",
    "common",
    "committed",
    "winnings",
    "rake",
    "rakeDealt",
    "rakeContributed",
    "rakeWeighted",
    "totalProfit",
    "allInEV",
    "street0VPIChance",
    "street0VPI",
    "street1Seen",
    "street2Seen",
    "street3Seen",
    "street4Seen",
    "sawShowdown",
    "showed",
    "street0AllIn",
    "street1AllIn",
    "street2AllIn",
    "street3AllIn",
    "street4AllIn",
    "wentAllIn",
    "splashWinnings",
    "street0AggrChance",
    "street0Aggr",
    "street1Aggr",
    "street2Aggr",
    "street3Aggr",
    "street4Aggr",
    "street1CBChance",
    "street2CBChance",
    "street3CBChance",
    "street4CBChance",
    "street1CBDone",
    "street2CBDone",
    "street3CBDone",
    "street4CBDone",
    "wonWhenSeenStreet1",
    "wonWhenSeenStreet2",
    "wonWhenSeenStreet3",
    "wonWhenSeenStreet4",
    "wonAtSD",
    "position",
    "street0InPosition",
    "street1InPosition",
    "street2InPosition",
    "street3InPosition",
    "street4InPosition",
    "street0FirstToAct",
    "street1FirstToAct",
    "street2FirstToAct",
    "street3FirstToAct",
    "street4FirstToAct",
    "tourneysPlayersId",
    "startCards",
    "street0CalledRaiseChance",
    "street0CalledRaiseDone",
    "street0FaceRaise",
    "street0_2BChance",
    "street0_2BDone",
    "street0_3BChance",
    "street0_3BDone",
    "street0_4BChance",
    "street0_4BDone",
    "street0_C4BChance",
    "street0_C4BDone",
    "street0_FoldTo2BChance",
    "street0_FoldTo2BDone",
    "street0_FoldTo3BChance",
    "street0_FoldTo3BDone",
    "street0_FoldTo4BChance",
    "street0_FoldTo4BDone",
    "street0_SqueezeChance",
    "street0_SqueezeDone",
    "raiseToStealChance",
    "raiseToStealDone",
    "stealChance",
    "stealDone",
    "success_Steal",
    "otherRaisedStreet0",
    "otherRaisedStreet1",
    "otherRaisedStreet2",
    "otherRaisedStreet3",
    "otherRaisedStreet4",
    "foldToOtherRaisedStreet0",
    "foldToOtherRaisedStreet1",
    "foldToOtherRaisedStreet2",
    "foldToOtherRaisedStreet3",
    "foldToOtherRaisedStreet4",
    "raiseFirstInChance",
    "raisedFirstIn",
    "foldBbToStealChance",
    "foldedBbToSteal",
    "foldSbToStealChance",
    "foldedSbToSteal",
    "foldToStreet1CBChance",
    "foldToStreet1CBDone",
    "foldToStreet2CBChance",
    "foldToStreet2CBDone",
    "foldToStreet3CBChance",
    "foldToStreet3CBDone",
    "foldToStreet4CBChance",
    "foldToStreet4CBDone",
    "street1CheckCallRaiseChance",
    "street1CheckCallDone",
    "street1CheckRaiseDone",
    "street2CheckCallRaiseChance",
    "street2CheckCallDone",
    "street2CheckRaiseDone",
    "street3CheckCallRaiseChance",
    "street3CheckCallDone",
    "street3CheckRaiseDone",
    "street4CheckCallRaiseChance",
    "street4CheckCallDone",
    "street4CheckRaiseDone",
    "street0Calls",
    "street1Calls",
    "street2Calls",
    "street3Calls",
    "street4Calls",
    "street0Bets",
    "street1Bets",
    "street2Bets",
    "street3Bets",
    "street4Bets",
    "street0Raises",
    "street1Raises",
    "street2Raises",
    "street3Raises",
    "street4Raises",
    "street1Discards",
    "street2Discards",
    "street3Discards",
    "street0Limp",
    "street0OpenLimp",
    "handString",
    "cashOutFee",
    "isCashOut",
    # Postflop per-street 3-bet (re-raise) — appended at the end so existing
    # insert column positions are unchanged (see store_hands_players).
    "street1_3BChance",
    "street1_3BDone",
    "street2_3BChance",
    "street2_3BDone",
    "street3_3BChance",
    "street3_3BDone",
    "street1_4BChance",
    "street1_4BDone",
    "street1_FoldTo4BChance",
    "street1_FoldTo4BDone",
    "street2_4BChance",
    "street2_4BDone",
    "street2_FoldTo4BChance",
    "street2_FoldTo4BDone",
    "street3_4BChance",
    "street3_4BDone",
    "street3_FoldTo4BChance",
    "street3_FoldTo4BDone",
    "street1OpenChance",
    "street1OpenDone",
    "street2OpenChance",
    "street2OpenDone",
    "street3OpenChance",
    "street3OpenDone",
    "flg_f_fold",
    "flg_t_fold",
    "flg_r_fold",
    "street1FirstRaise",
    "street2FirstRaise",
    "street3FirstRaise",
    "street1FaceRaise",
    "street2FaceRaise",
    "street3FaceRaise",
    "flg_f_donk_def_opp",
    "flg_t_float_opp",
    "flg_t_float",
    "flg_t_float_def_opp",
    "flg_r_float_opp",
    "flg_r_float",
    "flg_r_float_def_opp",
    "flg_t_donk_def_opp",
    "flg_r_donk_def_opp",
    # Fold-to-3bet postflop (computed in calc3BetPostflop) — appended at the end.
    "street1_FoldTo3BChance",
    "street1_FoldTo3BDone",
    "street2_FoldTo3BChance",
    "street2_FoldTo3BDone",
    "street3_FoldTo3BChance",
    "street3_FoldTo3BDone",
    # Preflop squeeze defense + limpers faced — appended at the end.
    "street0_FoldToSqueezeChance",
    "street0_FoldToSqueezeDone",
    "street0_FaceLimpers",
    # GenerationPoker open-sizing / limp counts (PT4 cnt_gp_* custom pack).
    "cnt_gp_open_opp",
    "cnt_gp_2x",
    "cnt_gp_os",
    "cnt_gp_limp",
    # Special blinds (dead small/big blind, straddle) — appended at the end.
    "flg_blind_ds",
    "flg_blind_db",
    "flg_blind_k",
    # Faced an all-in + fold response — appended at the end.
    "flg_faced_allin",
    "flg_fold_to_allin",
    # Bet-sizing: flop bet faced (count + basis points of pot) — appended at the end.
    "cnt_f_bet_facing",
    "val_f_bet_facing_bp",
    # Bet-sizing: turn + river bet faced — appended at the end.
    "cnt_t_bet_facing",
    "val_t_bet_facing_bp",
    "cnt_r_bet_facing",
    "val_r_bet_facing_bp",
    # Bet-sizing: preflop raise faced per level (count + basis points) — appended at the end.
    "cnt_p_2bet_facing",
    "val_p_2bet_facing_bp",
    "cnt_p_3bet_facing",
    "val_p_3bet_facing_bp",
    "cnt_p_4bet_facing",
    "val_p_4bet_facing_bp",
    # Bet-sizing: postflop bet made per street (count + basis points) — appended at the end.
    "cnt_f_bet_made",
    "val_f_bet_made_bp",
    "cnt_t_bet_made",
    "val_t_bet_made_bp",
    "cnt_r_bet_made",
    "val_r_bet_made_bp",
    # Bet-sizing: postflop SPR per street (count + SPR*100) — appended at the end.
    "cnt_f_spr",
    "val_f_spr",
    "cnt_t_spr",
    "val_t_spr",
    "cnt_r_spr",
    "val_r_spr",
    # Bet-sizing: size of the first raise made per street (count + basis points) — appended at the end.
    "cnt_p_raise_made",
    "val_p_raise_made_bp",
    "cnt_f_raise_made",
    "val_f_raise_made_bp",
    "cnt_t_raise_made",
    "val_t_raise_made_bp",
    "cnt_r_raise_made",
    "val_r_raise_made_bp",
    # Bet-sizing: postflop raise faced per street and level (count + basis points) — appended at the end.
    "cnt_f_2bet_facing",
    "val_f_2bet_facing_bp",
    "cnt_f_3bet_facing",
    "val_f_3bet_facing_bp",
    "cnt_f_4bet_facing",
    "val_f_4bet_facing_bp",
    "cnt_t_2bet_facing",
    "val_t_2bet_facing_bp",
    "cnt_t_3bet_facing",
    "val_t_3bet_facing_bp",
    "cnt_t_4bet_facing",
    "val_t_4bet_facing_bp",
    "cnt_r_2bet_facing",
    "val_r_2bet_facing_bp",
    "cnt_r_3bet_facing",
    "val_r_3bet_facing_bp",
    "cnt_r_4bet_facing",
    "val_r_4bet_facing_bp",
    # Bet-sizing completion (raw amounts, generic raise faced, 2nd raise, 5bet) — appended at the end.
    "amt_blind",
    "amt_bet_p",
    "amt_bet_f",
    "amt_bet_t",
    "amt_bet_r",
    "amt_bet_ttl",
    "cnt_p_raise_facing",
    "val_p_raise_facing_bp",
    "cnt_f_raise_facing",
    "val_f_raise_facing_bp",
    "cnt_t_raise_facing",
    "val_t_raise_facing_bp",
    "cnt_r_raise_facing",
    "val_r_raise_facing_bp",
    "cnt_p_raise_made_2",
    "val_p_raise_made_2_bp",
    "cnt_f_raise_made_2",
    "val_f_raise_made_2_bp",
    "cnt_t_raise_made_2",
    "val_t_raise_made_2_bp",
    "cnt_r_raise_made_2",
    "val_r_raise_made_2_bp",
    "cnt_p_5bet_facing",
    "val_p_5bet_facing_bp",
    # Delayed turn c-bet (DerivedStats._calc_delayed_turn_cbet). Appended at the
    # end so existing insert column positions stay unchanged; older databases get
    # the columns via ensure_handsplayers_columns().
    "street2DelayedCBChance",
    "street2DelayedCBDone",
    # Turn probe bet (DerivedStats._calc_turn_probe).
    "street2ProbeChance",
    "street2ProbeDone",
]

# Just like STATS_KEYS, this lets us efficiently add data at the
# "beginning" later.
HANDS_PLAYERS_KEYS.reverse()

# db differences:
# - note that mysql automatically creates indexes on constrained columns when
#   foreign keys are created, while postgres does not. Hence the much longer list
#   of indexes is required for postgres.
# all primary keys are left on all the time
#
#             table     column           drop_code

INDEXES: list[list[dict[str, Any]]] = [
    [],  # no db with index 0
    [],  # no db with index 1
    [  # indexes for mysql (list index 2) (foreign keys not here, in next data structure)
        #  {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
        #  {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
        # , {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
    ],
    [  # indexes for postgres (list index 3)
        {"tab": "Gametypes", "col": "siteId", "drop": 0},
        {"tab": "Hands", "col": "tourneyId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "gametypeId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "sessionId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "fileId", "drop": 0},  # mct 22/3/09
        # , {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
        {"tab": "HandsActions", "col": "handId", "drop": 1},
        {"tab": "HandsActions", "col": "playerId", "drop": 1},
        {"tab": "HandsActions", "col": "actionId", "drop": 1},
        {"tab": "HandsStove", "col": "handId", "drop": 1},
        {"tab": "HandsStove", "col": "playerId", "drop": 1},
        {"tab": "HandsStove", "col": "hiLo", "drop": 1},
        {"tab": "HandsPots", "col": "handId", "drop": 1},
        {"tab": "HandsPots", "col": "playerId", "drop": 1},
        {"tab": "Boards", "col": "handId", "drop": 1},
        {"tab": "HandsPlayers", "col": "handId", "drop": 1},
        {"tab": "HandsPlayers", "col": "playerId", "drop": 1},
        {"tab": "HandsPlayers", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "HandsPlayers", "col": "startCards", "drop": 1},
        {"tab": "HudCache", "col": "gametypeId", "drop": 1},
        {"tab": "HudCache", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "tourneyTypeId", "drop": 0},
        {"tab": "Sessions", "col": "weekId", "drop": 1},
        {"tab": "Sessions", "col": "monthId", "drop": 1},
        {"tab": "SessionsCache", "col": "sessionId", "drop": 1},
        {"tab": "SessionsCache", "col": "gametypeId", "drop": 1},
        {"tab": "SessionsCache", "col": "playerId", "drop": 0},
        {"tab": "TourneysCache", "col": "sessionId", "drop": 1},
        {"tab": "TourneysCache", "col": "tourneyId", "drop": 1},
        {"tab": "TourneysCache", "col": "playerId", "drop": 0},
        {"tab": "Players", "col": "siteId", "drop": 1},
        # , {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
        {"tab": "Tourneys", "col": "tourneyTypeId", "drop": 1},
        {"tab": "Tourneys", "col": "sessionId", "drop": 1},
        # , {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
        {"tab": "TourneysPlayers", "col": "playerId", "drop": 0},
        # , {'tab':'TourneysPlayers', 'col':'tourneyId',         'drop':0}  unique indexes not dropped
        {"tab": "TourneyTypes", "col": "siteId", "drop": 0},
        {"tab": "Backings", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "Backings", "col": "playerId", "drop": 0},
        {"tab": "RawHands", "col": "id", "drop": 0},
        {"tab": "RawTourneys", "col": "id", "drop": 0},
    ],
    [  # indexes for sqlite (list index 4)
        {"tab": "Hands", "col": "tourneyId", "drop": 0},
        {"tab": "Hands", "col": "gametypeId", "drop": 0},
        {"tab": "Hands", "col": "sessionId", "drop": 0},
        {"tab": "Hands", "col": "fileId", "drop": 0},
        {"tab": "Boards", "col": "handId", "drop": 0},
        {"tab": "Gametypes", "col": "siteId", "drop": 0},
        {"tab": "HandsPlayers", "col": "handId", "drop": 0},
        {"tab": "HandsPlayers", "col": "playerId", "drop": 0},
        {"tab": "HandsPlayers", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "HandsActions", "col": "handId", "drop": 0},
        {"tab": "HandsActions", "col": "playerId", "drop": 0},
        {"tab": "HandsActions", "col": "actionId", "drop": 1},
        {"tab": "HandsStove", "col": "handId", "drop": 0},
        {"tab": "HandsStove", "col": "playerId", "drop": 0},
        {"tab": "HandsPots", "col": "handId", "drop": 0},
        {"tab": "HandsPots", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "gametypeId", "drop": 1},
        {"tab": "HudCache", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "tourneyTypeId", "drop": 0},
        {"tab": "Sessions", "col": "weekId", "drop": 1},
        {"tab": "Sessions", "col": "monthId", "drop": 1},
        {"tab": "SessionsCache", "col": "sessionId", "drop": 1},
        {"tab": "SessionsCache", "col": "gametypeId", "drop": 1},
        {"tab": "SessionsCache", "col": "playerId", "drop": 0},
        {"tab": "TourneysCache", "col": "sessionId", "drop": 1},
        {"tab": "TourneysCache", "col": "tourneyId", "drop": 1},
        {"tab": "TourneysCache", "col": "playerId", "drop": 0},
        {"tab": "Players", "col": "siteId", "drop": 1},
        {"tab": "Tourneys", "col": "tourneyTypeId", "drop": 1},
        {"tab": "Tourneys", "col": "sessionId", "drop": 1},
        {"tab": "TourneysPlayers", "col": "playerId", "drop": 0},
        {"tab": "TourneyTypes", "col": "siteId", "drop": 0},
        {"tab": "Backings", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "Backings", "col": "playerId", "drop": 0},
        {"tab": "RawHands", "col": "id", "drop": 0},
        {"tab": "RawTourneys", "col": "id", "drop": 0},
    ],
]

FOREIGN_KEYS: list[list[dict[str, Any]]] = [
    [],  # no db with index 0
    [],  # no db with index 1
    [  # foreign keys for mysql (index 2)
        {
            "fktab": "Hands",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "fileId",
            "rtab": "Files",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Boards",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "tourneysPlayersId",
            "rtab": "TourneysPlayers",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "startCards",
            "rtab": "StartCards",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "actionId",
            "rtab": "Actions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "rankId",
            "rtab": "Rank",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "HudCache",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "weekId",
            "rtab": "Weeks",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "monthId",
            "rtab": "Months",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
    ],
    [  # foreign keys for postgres (index 3)
        {
            "fktab": "Hands",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "fileId",
            "rtab": "Files",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Boards",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "tourneysPlayersId",
            "rtab": "TourneysPlayers",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "startCards",
            "rtab": "StartCards",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "actionId",
            "rtab": "Actions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "rankId",
            "rtab": "Rank",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "HudCache",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "weekId",
            "rtab": "Weeks",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "monthId",
            "rtab": "Months",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
    ],
    [],  # no foreign keys in sqlite (index 4)
]

class DatabaseSchemaMixin:
    """Builds the schema and seeds its reference data.

    Mixed into Database, which supplies the connection, the query catalogue and
    the backend identity named below.
    """

    # The per-backend catalogues this mixin applies. prepareBulkImport and
    # afterBulkImport, still on the host, read them through the MRO.
    indexes = INDEXES
    foreignKeys = FOREIGN_KEYS

    # Provided by Database.
    sql: Any
    backend: int
    publicDB: bool
    MYSQL_INNODB: int
    PGSQL: int
    SQLITE: int

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def commit(self, force: bool = False) -> None: ...

        def rollback(self, force: bool = False) -> None: ...

        def get_sites(self) -> None: ...

        def resetCache(self) -> None: ...

        def resetBulkCache(self, reconnect: bool = False) -> None: ...

        def _pg_set_isolation(self, level: int) -> None: ...

    def drop_referential_integrity(self) -> None:
        """Update all tables to remove foreign keys (MySQL/MariaDB).

        Reads the constraint names from information_schema instead of guessing
        them from ``SHOW CREATE TABLE``: the old regex only matched the default
        ``<table>_ibfk_N`` names, so any explicitly named constraint survived
        and the subsequent DROP TABLE failed with errno 1451.
        """
        c = self.get_cursor()
        c.execute(
            "SELECT DISTINCT table_name, constraint_name "
            "FROM information_schema.table_constraints "
            "WHERE constraint_type = 'FOREIGN KEY' AND table_schema = DATABASE()",
        )
        constraints = c.fetchall()
        for table, constraint in constraints:
            c.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{constraint}`")
        self.commit()

    # end drop_referential_inegrity

    def recreate_tables(self) -> None:
        """(Re-)creates the tables of the current DB."""
        self.drop_tables()
        self.resetCache()
        self.resetBulkCache()
        self.create_tables()
        self.createAllIndexes()
        self.commit()
        self.get_sites()
        log.info("Finished recreating tables")

    # end def recreate_tables

    def ensure_feature_tables(self) -> None:
        """Create tables added after the original schema if they are missing, so
        that databases created by older versions keep working (used for the
        showdown combinations, cashout details, and additive HudCache stats)."""
        for query_name in (
            "createHandsShowdownTable",
            "createHandsCashoutTable",
            "createPlayerAutoNotesTable",
            "createAofDecisionsTable",
            "createAofDecisionAnalysesTable",
        ):
            try:
                c = self.get_cursor()
                c.execute(self.sql.query[query_name])
                self.commit()
            except Exception:  # noqa: BLE001 - table already exists: nothing to do.
                self.rollback()

        for query_name in (
            "addPlayerAutoNotesPlayerIndex",
            "addPlayerAutoNotesHandIndex",
            "addPlayerAutoNotesRuleIndex",
            "addAofDecisionsPlayerIndex",
            "addAofDecisionsHandIndex",
            "addAofDecisionsRangeIndex",
            "addAofAnalysesDecisionIndex",
            "addAofAnalysesStatusIndex",
        ):
            try:
                c = self.get_cursor()
                c.execute(self.sql.query[query_name])
                self.commit()
            except Exception:  # noqa: BLE001 - index/table already exists or feature table absent.
                self.rollback()

        self._ensure_gametype_category_width()

        self.ensure_hudcache_columns()
        self.ensure_handsplayers_columns()
        self.ensure_hands_columns()

    def _get_table_columns(self, table: str) -> set[str]:
        c = self.get_cursor()
        if self.backend == self.SQLITE:
            c.execute(f"PRAGMA table_info({table})")
            return {row[1] for row in c.fetchall()}
        if self.backend == self.MYSQL_INNODB:
            c.execute(f"SHOW COLUMNS FROM {table}")
            return {row[0] for row in c.fetchall()}

        c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s OR table_name = %s",
            (table, table.lower()),
        )
        return {row[0] for row in c.fetchall()}

    def ensure_hudcache_columns(self) -> None:
        """Add missing additive HudCache stat columns for databases created by older code."""
        definitions = {column: "INT DEFAULT 0" for column in CACHE_KEYS}
        # HudCache-only columns (not in the shared CACHE_KEYS).
        definitions.update({column: "INT DEFAULT 0" for column in HUDCACHE_EXTRA_KEYS})
        self._ensure_table_columns("HudCache", definitions)

    def ensure_handsplayers_columns(self) -> None:
        """Add missing HandsPlayers stat columns for databases created by older code."""
        definitions = {column: "INT DEFAULT 0" for column in HANDS_PLAYERS_KEYS}
        definitions["handString"] = "TEXT"
        definitions["cashOutFee"] = "INT DEFAULT 0"
        definitions["isCashOut"] = "BOOLEAN DEFAULT 0"
        self._ensure_table_columns("HandsPlayers", definitions)

    def ensure_hands_columns(self) -> None:
        """Add missing additive Hands columns for databases created by older code."""
        definitions = {
            "bombPot": "INT DEFAULT 0",
            "splashPot": "INT DEFAULT 0",
        }
        self._ensure_table_columns("Hands", definitions)

    def _ensure_gametype_category_width(self) -> None:
        """Widen Gametypes.category to varchar(10) for aof_holdem support.

        The original schema used varchar(9), which fits aof_omaha (8 chars)
        but not aof_holdem (10 chars). Avoided on SQLite (TEXT is unbounded)
        and skipped when the column is already wide enough.
        """
        if self.backend == self.SQLITE:
            return
        try:
            existing = self._get_table_columns("Gametypes")
        except Exception:  # noqa: BLE001
            self.rollback()
            return
        if not existing or "category" not in {c.lower() for c in existing}:
            return
        try:
            c = self.get_cursor()
            if self.backend == self.MYSQL_INNODB:
                c.execute("ALTER TABLE Gametypes MODIFY category VARCHAR(10) NOT NULL")
            else:
                c.execute("ALTER TABLE Gametypes ALTER COLUMN category TYPE VARCHAR(10)")
            self.commit()
            log.info("Widened Gametypes.category to varchar(10)")
        except Exception:  # noqa: BLE001 - column may already be wide enough or table locked.
            self.rollback()

    def _ensure_table_columns(self, table: str, definitions: dict[str, str]) -> None:
        try:
            existing = self._get_table_columns(table)
        except Exception:  # noqa: BLE001 - the table may not exist yet during first-time setup.
            self.rollback()
            return

        if not existing:
            return

        existing_lower = {column.lower() for column in existing}
        missing = [column for column in definitions if column.lower() not in existing_lower]
        if not missing:
            return

        c = self.get_cursor()
        try:
            for column in missing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definitions[column]}")
            self.commit()
            log.info("Added %s missing %s columns: %s", len(missing), table, ", ".join(missing))
        except Exception:
            self.rollback()
            raise

    def create_tables(self) -> None:
        log.debug(f"{self.sql.query['createSettingsTable']}")
        c = self.get_cursor()
        c.execute(self.sql.query["createSettingsTable"])

        log.debug("Creating tables")
        c.execute(self.sql.query["createActionsTable"])
        c.execute(self.sql.query["createRankTable"])
        c.execute(self.sql.query["createStartCardsTable"])
        c.execute(self.sql.query["createSitesTable"])
        c.execute(self.sql.query["createGametypesTable"])
        c.execute(self.sql.query["createFilesTable"])
        c.execute(self.sql.query["createPlayersTable"])
        c.execute(self.sql.query["createAutoratesTable"])
        c.execute(self.sql.query["createWeeksTable"])
        c.execute(self.sql.query["createMonthsTable"])
        c.execute(self.sql.query["createSessionsTable"])
        c.execute(self.sql.query["createTourneyTypesTable"])
        c.execute(self.sql.query["createTourneysTable"])
        c.execute(self.sql.query["createTourneysPlayersTable"])
        c.execute(self.sql.query["createSessionsCacheTable"])
        c.execute(self.sql.query["createTourneysCacheTable"])
        c.execute(self.sql.query["createHandsTable"])
        c.execute(self.sql.query["createHandsPlayersTable"])
        c.execute(self.sql.query["createHandsActionsTable"])
        c.execute(self.sql.query["createHandsStoveTable"])
        c.execute(self.sql.query["createHandsShowdownTable"])
        c.execute(self.sql.query["createHandsCashoutTable"])
        c.execute(self.sql.query["createPlayerAutoNotesTable"])
        c.execute(self.sql.query["createAofDecisionsTable"])
        c.execute(self.sql.query["createAofDecisionAnalysesTable"])
        c.execute(self.sql.query["createHandsPotsTable"])
        c.execute(self.sql.query["createHudCacheTable"])
        c.execute(self.sql.query["createCardsCacheTable"])
        c.execute(self.sql.query["createPositionsCacheTable"])
        c.execute(self.sql.query["createBoardsTable"])
        c.execute(self.sql.query["createBackingsTable"])
        c.execute(self.sql.query["createRawHands"])
        c.execute(self.sql.query["createRawTourneys"])

        # Create unique indexes:
        log.debug("Creating unique indexes")
        c.execute(self.sql.query["addTourneyIndex"])
        c.execute(
            self.sql.query["addHandsIndex"].replace(
                "<heroseat>",
                ", heroSeat" if self.publicDB else "",
            ),
        )
        c.execute(self.sql.query["addPlayersIndex"])
        c.execute(self.sql.query["addTPlayersIndex"])
        c.execute(self.sql.query["addPlayersSeat"])
        c.execute(self.sql.query["addHeroSeat"])
        c.execute(self.sql.query["addStartCardsIndex"])
        c.execute(self.sql.query["addSeatsIndex"])
        c.execute(self.sql.query["addPositionIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesPlayerIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesHandIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesRuleIndex"])
        c.execute(self.sql.query["addAofDecisionsPlayerIndex"])
        c.execute(self.sql.query["addAofDecisionsHandIndex"])
        c.execute(self.sql.query["addAofDecisionsRangeIndex"])
        c.execute(self.sql.query["addAofAnalysesDecisionIndex"])
        c.execute(self.sql.query["addAofAnalysesStatusIndex"])
        c.execute(self.sql.query["addFilesIndex"])
        c.execute(self.sql.query["addTableNameIndex"])
        c.execute(self.sql.query["addPlayerNameIndex"])
        c.execute(self.sql.query["addPlayerHeroesIndex"])
        c.execute(self.sql.query["addStartCashIndex"])
        c.execute(self.sql.query["addEffStackIndex"])
        c.execute(self.sql.query["addTotalProfitIndex"])
        c.execute(self.sql.query["addWinningsIndex"])
        c.execute(self.sql.query["addFinalPotIndex"])
        c.execute(self.sql.query["addStreetIndex"])
        c.execute(self.sql.query["addSessionsCacheCompundIndex"])
        c.execute(self.sql.query["addTourneysCacheCompundIndex"])
        c.execute(self.sql.query["addHudCacheCompundIndex"])
        c.execute(self.sql.query["addCardsCacheCompundIndex"])
        c.execute(self.sql.query["addPositionsCacheCompundIndex"])

        self.fillDefaultData()
        self.commit()

    def drop_tables(self) -> None:
        """Drops the fpdb tables from the current db.

        Delegates to the backend Dialect, which drops every table whatever the
        foreign-key order is (FK checks off on MySQL/SQLite, CASCADE on
        PostgreSQL). The previous MySQL path relied on
        ``drop_referential_integrity`` removing the constraints one by one and
        failed with "Cannot delete or update a parent row: a foreign key
        constraint fails" (errno 1451) as soon as one constraint was not named
        ``<table>_ibfk_N``; the error was then swallowed, leaving tables behind
        and making the following ``create_tables`` fail in turn.
        """
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).drop_all_tables(self)

    # end def drop_tables

    def createAllIndexes(self) -> None:
        """Create new indexes."""
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        c = self.get_cursor()
        for idx in self.indexes[self.backend]:
            log.info(f"Creating index {idx['tab']} {idx['col']}")
            if self.backend == self.MYSQL_INNODB:
                s = "CREATE INDEX {} ON {}({})".format(idx["col"], idx["tab"], idx["col"])
                c.execute(s)
            elif self.backend in (self.PGSQL, self.SQLITE):
                s = "CREATE INDEX {}_{}_idx ON {}({})".format(
                    idx["tab"],
                    idx["col"],
                    idx["tab"],
                    idx["col"],
                )
                c.execute(s)

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level

    # end def createAllIndexes

    def dropAllIndexes(self) -> int | None:
        """Drop all standalone indexes (i.e. not including primary keys or foreign keys)
        using list of indexes in indexes data structure.
        """
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for idx in self.indexes[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                try:
                    self.get_cursor().execute(
                        "alter table %s drop index %s",
                        (idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (MySQL) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            elif self.backend == self.PGSQL:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                # mod to use tab_col for index name?
                try:
                    self.get_cursor().execute(
                        "drop index {}_{}_idx".format(idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (PG) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            elif self.backend == self.SQLITE:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                try:
                    self.get_cursor().execute(
                        "drop index {}_{}_idx".format(idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (SQLite) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            else:
                return -1
        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
            return None
        return None

    # end def dropAllIndexes

    def createAllForeignKeys(self) -> None:
        """Create foreign keys."""
        try:
            if self.backend == self.PGSQL:
                self._pg_set_isolation(
                    0,
                )  # allow table/index operations to work
            c = self.get_cursor()
        except Exception:  # intentional broad catch: set_isolation_level (PG) best-effort before DDL
            log.exception(f"set_isolation_level failed: {sys.exc_info()}")

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                c.execute(
                    "SELECT constraint_name "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    # "WHERE REFERENCED_TABLE_SCHEMA = 'fpdb'
                    "WHERE 1=1 "
                    "AND table_name = %s AND column_name = %s "
                    "AND referenced_table_name = %s "
                    "AND referenced_column_name = %s ",
                    (fk["fktab"], fk["fkcol"], fk["rtab"], fk["rcol"]),
                )
                cons = c.fetchone()
                # print "afterbulk: cons=", cons
                if cons:
                    pass
                else:
                    log.debug(
                        f"Creating foreign key: {fk['fktab']} {fk['fkcol']} -> {fk['rtab']} {fk['rcol']}",
                    )
                    try:
                        c.execute(
                            "alter table "
                            + fk["fktab"]
                            + " add foreign key ("
                            + fk["fkcol"]
                            + ") references "
                            + fk["rtab"]
                            + "("
                            + fk["rcol"]
                            + ")",
                        )
                    except Exception:  # intentional broad catch: create FK (MySQL) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
            elif self.backend == self.PGSQL:
                log.debug(
                    f"Creating foreign key: {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
                )
                try:
                    c.execute(
                        "alter table "
                        + fk["fktab"]
                        + " add constraint "
                        + fk["fktab"]
                        + "_"
                        + fk["fkcol"]
                        + "_fkey"
                        + " foreign key ("
                        + fk["fkcol"]
                        + ") references "
                        + fk["rtab"]
                        + "("
                        + fk["rcol"]
                        + ")",
                    )
                except Exception:  # intentional broad catch: create FK (PG) best-effort, continue
                    log.exception(f"Create foreign key failed: {sys.exc_info()!s}")
            else:
                pass

        try:
            if self.backend == self.PGSQL:
                self._pg_set_isolation(
                    1,
                )  # go back to normal isolation level
        except Exception:  # intentional broad catch: reset isolation_level (PG) best-effort after DDL
            log.exception(f"set_isolation_level failed: {sys.exc_info()!s}")

    # end def createAllForeignKeys

    def dropAllForeignKeys(self) -> None:
        """Drop all standalone indexes (i.e. not including primary keys or foreign keys)
        using list of indexes in indexes data structure.
        """
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        c = self.get_cursor()

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                c.execute(
                    "SELECT constraint_name "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    # "WHERE REFERENCED_TABLE_SHEMA = 'fpdb'
                    "WHERE 1=1 "
                    "AND table_name = %s AND column_name = %s "
                    "AND referenced_table_name = %s "
                    "AND referenced_column_name = %s ",
                    (fk["fktab"], fk["fkcol"], fk["rtab"], fk["rcol"]),
                )
                cons = c.fetchone()
                # print "preparebulk find fk: cons=", cons
                if cons:
                    log.debug(
                        f"Dropping foreign key: {cons[0]} {fk['fktab']}.{fk['fkcol']}",
                    )
                    try:
                        c.execute(
                            "alter table " + fk["fktab"] + " drop foreign key " + cons[0],
                        )
                    except Exception:  # intentional broad catch: drop FK (MySQL) best-effort, continue
                        log.exception(
                            f"Warning: Drop foreign key {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
            elif self.backend == self.PGSQL:
                #    DON'T FORGET TO RECREATE THEM!!
                log.debug(f"Dropping foreign key: {fk['fktab']}.{fk['fkcol']}")
                try:
                    # try to lock table to see if index drop will work:
                    # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                    # then drop still hangs :-(  does work in some tests though??
                    # will leave code here for now pending further tests/enhancement ...
                    c.execute("BEGIN TRANSACTION")
                    c.execute("lock table {} in exclusive mode nowait".format(fk["fktab"]))
                    # print "after lock, status:", c.statusmessage
                    # print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                    try:
                        c.execute(
                            "alter table {} drop constraint {}_{}_fkey".format(fk["fktab"], fk["fktab"], fk["fkcol"]),
                        )
                        log.debug(
                            f"dropped foreign key {fk['fktab']}_{fk['fkcol']}_fkey, continuing ...",
                        )
                    except Exception:  # intentional broad catch: drop FK constraint (PG) ignores 'does not exist'
                        if "does not exist" not in str(sys.exc_info()[1]):
                            log.exception(
                                f"Drop foreign key {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                            )
                    c.execute("END TRANSACTION")
                except Exception:  # intentional broad catch: drop FK (PG lock/txn) best-effort, continue
                    log.exception(
                        f"Constraint {fk['fktab']}_{fk['fkcol']}_fkey not dropped: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                    )
            else:
                # print ("Only MySQL and Postgres supported so far")
                pass

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level

    # end def dropAllForeignKeys

    def fillDefaultData(self) -> None:
        c = self.get_cursor()
        c.execute(f"INSERT INTO Settings (version) VALUES ({DB_VERSION});")
        # Fill Sites
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('1', 'Full Tilt Poker', 'FT')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('2', 'PokerStars', 'PS')")
        # PokerStars variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('32', 'PokerStars.COM', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('33', 'PokerStars.FR', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('34', 'PokerStars.IT', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('35', 'PokerStars.ES', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('36', 'PokerStars.PT', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('37', 'PokerStars.EU', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('130', 'PokerStars.DE', 'PS')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('3', 'Everleaf', 'EV')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('4', 'Boss', 'BM')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('5', 'OnGame', 'OG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('6', 'UltimateBet', 'UB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('7', 'Betfair', 'BF')")
        # c.execute("INSERT INTO Sites (id,name,code) VALUES ('8', 'Absolute', 'AB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('9', 'PartyPoker', 'PP')")
        # PartyPoker variants
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('38', 'Party Poker', 'PP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('39', 'Bwin Poker', 'PP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('40', 'Bwin.fr Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('41', 'Bwin.it Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('42', 'Bwin.es Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('43', 'Bwin.de Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('44', 'PartyPoker.fr', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('45', 'PartyPoker.it', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('46', 'PartyPoker.es', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('47', 'PartyPoker.de', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('48', 'Empire Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('49', 'Gamebookers Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('50', 'Intertops Poker', 'PP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('51', 'MultiPoker', 'PP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('52', 'PokerRoom', 'PP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('53', 'PartyPoker NJ', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('54', 'BorgataPoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('55', 'Borgata Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('120', 'WPT Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('121', 'WPTPoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('122', 'PartyPoker.pt', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('123', 'PartyPoker.com', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('124', 'PartyPoker.eu', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('125', 'partycasino', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('126', 'PartyCasino', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('127', 'partypoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('128', 'bwin', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('129', 'PMU Poker (PartyPoker)', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('10', 'PacificPoker', 'P8')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('11', 'Partouche', 'PA')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('12', 'Merge', 'MN')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('13', 'PKR', 'PK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('14', 'iPoker', 'IP')")
        # iPoker network variants
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('56', 'PMU Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('57', 'FDJ Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('58', 'Poker770', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('131', 'Betclic Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('140', 'CoinPoker', 'CP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('59', 'NetBet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('60', 'Barrière Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('61', 'Red Star Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('62', 'Titan Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('63', 'Bet365 Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('64', 'William Hill Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('65', 'Paddy Power Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('66', 'Betfair Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('67', 'Coral Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('68', 'Genting Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('69', 'Mansion Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('70', 'Winner Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('71', 'Ladbrokes Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('72', 'Sky Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('73', 'Sisal Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('74', 'Lottomatica Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('75', 'Eurobet Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('76', 'Snai Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('77', 'Goldbet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('78', 'Casino Barcelona Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('79', 'Sportium Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('80', 'Marca Apuestas Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('81', 'Everest Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('82', 'Bet-at-home Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('83', 'Mybet Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('84', 'Betsson Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('85', 'Betsafe Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('86', 'NordicBet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('87', 'Unibet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('88', 'Maria Casino Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('89', 'LeoVegas Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('90', 'Mr Green Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('91', 'Redbet Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('15', 'Winamax', 'WM')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('16', 'Everest', 'EP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('17', 'Cake', 'CK')")
        # Cake network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('92', 'Everygame Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('93', 'Everygame', 'CK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('94', 'Cake Poker', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('95', 'Juicy Stakes', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('96', 'Juicy Stakes Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('97', 'JuicyStakes', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('98', 'RedStar Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('99', 'RedStar', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('100', 'Sportsbetting.ag Poker', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('101', 'Sportsbetting Poker', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('102', 'SportsBetting.ag', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('18', 'Entraction', 'TR')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('19', 'BetOnline', 'BO')")
        # BetOnline network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('103', 'BetOnline Poker', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('104', 'BetOnline.ag', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('105', 'Tiger Gaming', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('106', 'TigerGaming', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('107', 'Doyles Room', 'BO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('108', 'DoylesRoom', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('109', 'Poker4Ever', 'BO')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('110', 'Poker 4 Ever', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('111', 'PlayersOnly', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('112', 'Players Only', 'BO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('113', 'SunPoker', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('114', 'Sun Poker', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('20', 'Microgaming', 'MG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('21', 'Bovada', 'BV')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('22', 'Enet', 'EN')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('23', 'SealsWithClubs', 'SW')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('24', 'WinningPoker', 'WP')",
        )
        # WPN network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('115', 'Americas Cardroom', 'WP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('116', 'ACR Poker', 'WP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('117', 'BlackChipPoker', 'WP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('118', 'TruePoker', 'WP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('119', 'Ya Poker', 'WP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('25', 'PokerMaster', 'PM')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('26', 'Run It Once Poker', 'RO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('27', 'GGPoker', 'GG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('28', 'KingsClub', 'KC')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('29', 'PokerBros', 'PB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('30', 'Unibet', 'UN')")
        # c.execute("INSERT INTO Sites (id,name,code) VALUES ('31', 'PMU Poker', 'PM')")
        # Fill Actions
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('1', 'ante', 'A')")
        c.execute(
            "INSERT INTO Actions (id,name,code) VALUES ('2', 'small blind', 'SB')",
        )
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('3', 'secondsb', 'SSB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('4', 'big blind', 'BB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('5', 'both', 'SBBB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('6', 'calls', 'C')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('7', 'raises', 'R')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('8', 'bets', 'B')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('9', 'stands pat', 'S')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('10', 'folds', 'F')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('11', 'checks', 'K')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('12', 'discards', 'D')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('13', 'bringin', 'I')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('14', 'completes', 'P')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('15', 'straddle', 'ST')")
        c.execute(
            "INSERT INTO Actions (id,name,code) VALUES ('16', 'button blind', 'BUB')",
        )
        # Fill Rank
        c.execute("INSERT INTO Rank (id,name) VALUES ('1', 'Nothing')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('2', 'NoPair')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('3', 'OnePair')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('4', 'TwoPair')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('5', 'Trips')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('6', 'Straight')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('7', 'Flush')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('8', 'FlHouse')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('9', 'Quads')")
        c.execute("INSERT INTO Rank (id,name) VALUES ('10', 'StFlush')")
        # Fill StartCards
        sql = "INSERT INTO StartCards (category, name, rank, combinations) VALUES (%s, %s, %s, %s)".replace(
            "%s",
            self.sql.query["placeholder"],
        )
        for i in range(170):
            (name, rank, combinations) = Card.StartCardRank(i)
            c.execute(sql, ("holdem", name, rank, combinations))
        for idx in range(-13, 1184):
            name = Card.decodeRazzStartHand(idx)
            c.execute(sql, ("razz", name, idx, 0))
        sql = "INSERT INTO StartCards (id, category, name, rank, combinations) VALUES (%s, %s, %s, %s, %s)".replace(
            "%s",
            self.sql.query["placeholder"],
        )
        omaha_count = len(Card._omaha_rank_combos()) * len(Card.OMAHA_SUIT_CLASSES)
        for idx in range(Card.OMAHA_START_HAND_OFFSET, Card.OMAHA_START_HAND_OFFSET + omaha_count):
            c.execute(sql, (idx, "omaha", Card.fourStartCardString(idx), idx, 0))

    # end def fillDefaultData

    def rebuild_indexes(self, start=None) -> None:
        self.dropAllIndexes()
        self.createAllIndexes()
        self.dropAllForeignKeys()
        self.createAllForeignKeys()

    # end def rebuild_indexes
