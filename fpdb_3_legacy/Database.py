"""Database module for FPDB.
from __future__ import annotations
Copyright 2008-2011, Ray E. Barker

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

Create and manage the database objects.
"""

import contextlib
import csv
import math

#    Standard Library modules
import os
import random
import re
import string
import sys
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from importlib import import_module
from time import sleep, time
from typing import Any

import pytz

from fpdb_3_legacy import SQL, Card, Configuration
from fpdb_3_legacy.database_auto_notes import DatabaseAutoNotesMixin
from fpdb_3_legacy.database_caches import CACHE_KEYS, HUDCACHE_EXTRA_KEYS, DatabaseCachesMixin
from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.database_tournaments import DatabaseTournamentsMixin
from fpdb_3_legacy.Exceptions import (
    FpdbError,
    FpdbMySQLAccessDenied,
    FpdbMySQLNoDatabase,
    FpdbPostgresqlAccessDenied,
    FpdbPostgresqlNoDatabase,
)
from fpdb_3_legacy.loggingFpdb import get_logger

# #import L10n
# #_ = L10n.get_translation()

########################################################################

# Database maintenance is available through ``rebuild_indexes()``,
# ``analyzeDB()`` and ``vacuumDB()`` as well as the command-line utility below.

# postmaster -D /var/lib/pgsql/data


re_char = re.compile("[^a-zA-Z]")
re_insert = re.compile(
    r"insert\sinto\s(?P<TABLENAME>[A-Za-z]+)\s(?P<COLUMNS>\(.+?\))\s+values",
    re.DOTALL,
)

#    FreePokerTools modules


if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("database")

#    Other library modules
# Note: SQLAlchemy pool.manage was removed in 2.0
# Each database driver (MySQLdb, psycopg, sqlite3) now handles its own connection pooling
# SQLAlchemy import kept for potential future use of core features
try:
    import sqlalchemy  # noqa: F401 -- availability probe

    use_sqlalchemy = True
except ImportError:
    log.info("SQLAlchemy not available (optional dependency)")
    use_sqlalchemy = False

try:
    var = getattr(import_module("numpy"), "var")

    use_numpy = True
except ImportError:
    log.exception("Not using numpy to define variance in sqlite.")
    use_numpy = False


DB_VERSION = 224

# Variance created as sqlite has a bunch of undefined aggregate functions.


class VARIANCE:
    def __init__(self) -> None:
        self.store: list[Any] = []

    def step(self, value) -> None:
        self.store.append(value)

    def finalize(self):
        return float(var(self.store))


class sqlitemath:
    def mod(self, a, b):
        return a % b


def adapt_decimal(d):
    return str(d)


def convert_decimal(s):
    log.debug(f"Converting value: {s}")
    s = s.decode()
    return Decimal(s)


# These are for appendStats. Insert new stats at the right place, because
# SQL needs strict order.
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





class DatabaseTransaction:
    """Context manager for grouping database operations into a single transaction.

    Nested context managers increment the transaction depth, and only the outermost
    context manager executes the commit or rollback.
    """
    def __init__(self, db) -> None:
        self.db = db

    def __enter__(self) -> "DatabaseTransaction":
        self.db._in_transaction += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.db._in_transaction -= 1
        if exc_type is not None:
            log.warning(f"Transaction rolling back due to exception: {exc_val}")
            try:
                self.db.rollback(force=True)
                # IDs inserted during the failed transaction may already be in
                # the lazy caches. They no longer exist after rollback and must
                # never be reused by the next auto-import cycle.
                self.db.resetCache()
                self.db.resetBulkCache()
            except Exception as e:  # intentional broad catch: transaction rollback during teardown is best-effort, just log
                log.exception(f"Rollback failed: {e}")
        else:
            if self.db._in_transaction == 0:
                try:
                    self.db.commit(force=True)
                except Exception as e:  # intentional broad catch: transaction commit during teardown; rolls back then re-raises
                    log.exception(f"Commit failed: {e}")
                    try:
                        self.db.rollback(force=True)
                        self.db.resetCache()
                        self.db.resetBulkCache()
                    except Exception as roll_err:  # intentional broad catch: rollback after a failed commit is best-effort, just log
                        log.exception(f"Rollback after failed commit also failed: {roll_err}")
                    raise e


class Database(DatabaseAutoNotesMixin, DatabaseCachesMixin, DatabaseTournamentsMixin):
    MYSQL_INNODB = 2
    PGSQL = 3
    SQLITE = 4

    hero_hudstart_def = "1999-12-31"  # default for length of Hero's stats in HUD
    villain_hudstart_def = "1999-12-31"  # default for length of Villain's stats in HUD

    # Data Structures for index and foreign key creation
    # drop_code is an int with possible values:  0 - don't drop for bulk import
    #                                            1 - drop during bulk import
    # db differences:
    # - note that mysql automatically creates indexes on constrained columns when
    #   foreign keys are created, while postgres does not. Hence the much longer list
    #   of indexes is required for postgres.
    # all primary keys are left on all the time
    #
    #             table     column           drop_code

    indexes = [
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

    foreignKeys = [
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

    # MySQL Notes:
    #    "FOREIGN KEY (handId) REFERENCES Hands(id)" - requires index on Hands.id
    #                                                - creates index handId on <thistable>.handId
    # alter table t drop foreign key fk
    # alter table t add foreign key (fkcol) references tab(rcol)
    # alter table t add constraint c foreign key (fkcol) references tab(rcol)
    # (fkcol is used for foreigh key name)

    # mysql to list indexes: (CG - "LIST INDEXES" should work too)
    #   SELECT table_name, index_name, non_unique, column_name
    #   FROM INFORMATION_SCHEMA.STATISTICS
    #     WHERE table_name = 'tbl_name'
    #     AND table_schema = 'db_name'
    #   ORDER BY table_name, index_name, seq_in_index
    #
    # ALTER TABLE Tourneys ADD INDEX siteTourneyNo(siteTourneyNo)
    # ALTER TABLE tab DROP INDEX idx

    # mysql to list fks:
    #   SELECT constraint_name, table_name, column_name, referenced_table_name, referenced_column_name
    #   FROM information_schema.KEY_COLUMN_USAGE
    #   WHERE REFERENCED_TABLE_SCHEMA = (your schema name here)
    #   AND REFERENCED_TABLE_NAME is not null
    #   ORDER BY TABLE_NAME, COLUMN_NAME;

    # this may indicate missing object
    # _mysql_exceptions.OperationalError: (1025, "Error on rename of '.\\fpdb\\hands' to '.\\fpdb\\#sql2-7f0-1b' (errno: 152)")

    # PG notes:

    #  To add a foreign key constraint to a table:
    #  ALTER TABLE tab ADD CONSTRAINT c FOREIGN KEY (col) REFERENCES t2(col2) MATCH FULL;
    #  ALTER TABLE tab DROP CONSTRAINT zipchk
    #
    #  Note: index names must be unique across a schema
    #  CREATE INDEX idx ON tab(col)
    #  DROP INDEX idx
    #  SELECT * FROM PG_INDEXES

    # SQLite notes:

    # To add an index:
    # create index indexname on tablename (col);

    def __init__(self, c, sql=None, autoconnect=True) -> None:
        self.config = c
        # Connection/cursor implementations differ across SQLite, PostgreSQL,
        # MySQLdb and pymysql, so the common database facade treats them as a
        # backend-defined runtime interface.
        self.connection: Any = None
        self.cursor: Any = None
        self.__connected = False
        self.wrongDbVersion = False
        self.settings = {}
        self.settings["os"] = "linuxmac" if os.name != "nt" else "windows"
        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params["db-backend"]
        self.db_server = db_params["db-server"]
        self.database = db_params["db-databaseName"]
        self.host = db_params["db-host"]
        self.db_path = ""
        gen = c.get_general_params()
        self.day_start = 0.0
        self._hero = None
        self._has_lock = False
        self.printdata = False
        self.resetCache()
        self.resetBulkCache()
        self._in_transaction = 0

        if "day_start" in gen:
            self.day_start = float(gen["day_start"])

        self.sessionTimeout = float(self.import_options["sessionTimeout"])
        self.publicDB = self.import_options["publicDB"]

        # where possible avoid creating new SQL instance by using the global one passed in
        if sql is None:
            self.sql = SQL.Sql(db_server=self.db_server)
        else:
            self.sql = sql

        if autoconnect:
            # connect to db
            self.do_connect(c)

            if self.backend == self.PGSQL:
                pass
                # ISOLATION_LEVEL_AUTOCOMMIT     = 0
                # ISOLATION_LEVEL_READ_COMMITTED = 1
                # ISOLATION_LEVEL_SERIALIZABLE   = 2

            if (
                self.backend == self.SQLITE
                and self.database == ":memory:"
                and self.wrongDbVersion
                and self.is_connected()
            ):
                log.info("sqlite/:memory: - creating")
                self.recreate_tables()
                self.wrongDbVersion = False
            elif self.is_connected():
                # Create feature tables added after the original schema so that
                # existing databases keep working (showdown / cashout details).
                self.ensure_feature_tables()

            self.gtcache: Any = None  # GameTypeId cache
            self.tcache: Any = None  # TourneyId cache
            self.pcache: Any = None  # PlayerId cache
            self.tpcache: Any = None  # TourneysPlayersId cache

            # if fastStoreHudCache is true then the hudcache will be build using the limited configuration which ignores date, seats, and position
            self.build_full_hudcache = not self.import_options["fastStoreHudCache"]
            self.cacheSessions = self.import_options["cacheSessions"]
            self.callHud = self.import_options["callFpdbHud"]

            # self.hud_hero_style = 'T'  # Duplicate set of vars just for hero - not used yet.
            # self.hud_hero_hands = 2000 # Idea is that you might want all-time stats for others
            # self.hud_hero_days  = 30   # but last T days or last H hands for yourself

            # vars for hand ids or dates fetched according to above config:
            self.hand_1day_ago = 0  # max hand id more than 24 hrs earlier than now
            self.date_ndays_ago = "d000000"  # date N days ago ('d' + YYMMDD)
            self.h_date_ndays_ago = "d000000"  # date N days ago ('d' + YYMMDD) for hero
            self.date_nhands_ago: dict[Any, Any] = {}  # dates N hands ago per player

            self.saveActions = self.import_options["saveActions"] is not False

            if self.is_connected():
                if not self.wrongDbVersion:
                    self.get_sites()
                if self.connection is not None:
                    self.connection.rollback()  # release locks taken during setup

    # end def __init__

    def dumpDatabase(self):
        result = "fpdb database dump\nDB version=" + str(DB_VERSION) + "\n\n"

        # tables = self.cursor.execute(self.sql.query["list_tables"])
        # tables = self.cursor.fetchall()
        for table in (
            "Actions",
            "Autorates",
            "Backings",
            "Gametypes",
            "Hands",
            "Boards",
            "HandsActions",
            "HandsPlayers",
            "HandsStove",
            "Files",
            "HudCache",
            "Sessions",
            "SessionsCache",
            "TourneysCache",
            "Players",
            "RawHands",
            "RawTourneys",
            "Settings",
            "Sites",
            "TourneyTypes",
            "Tourneys",
            "TourneysPlayers",
        ):
            log.debug(f"table: {table}")
            result += "###################\nTable " + table + "\n###################\n"
            rows = self.cursor.execute(self.sql.query["get" + table])
            rows = self.cursor.fetchall()
            columnNames = self.cursor.description
            if not rows:
                result += "empty table\n"
            else:
                for row in rows:
                    for columnNumber in range(len(columnNames)):
                        if columnNames[columnNumber][0] == "importTime" or columnNames[columnNumber][0] == "styleKey":
                            result += "  " + columnNames[columnNumber][0] + "=ignore\n"
                        else:
                            result += "  " + columnNames[columnNumber][0] + "=" + str(row[columnNumber]) + "\n"
                    result += "\n"
            result += "\n"
        return result

    # end def dumpDatabase

    # could be used by hud to change hud style
    def set_hud_style(self, style) -> None:
        self.hud_style = style

    def do_connect(self, c) -> None:
        if c is None:
            msg = "Configuration not defined"
            raise FpdbError(msg)

        db = c.get_db_parameters()
        try:
            self.connect(
                backend=db["db-backend"],
                host=db["db-host"],
                port=db["db-port"],
                database=db["db-databaseName"],
                user=db["db-user"],
                password=db["db-password"],
            )
        except Exception:  # intentional broad catch: connect failure marks disconnected then re-raises
            # error during connect
            self.__connected = False
            raise

        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params["db-backend"]
        self.db_server = db_params["db-server"]
        self.database = db_params["db-databaseName"]
        self.host = db_params["db-host"]
        self.port = db_params["db-port"]

    def connect(
        self,
        backend=None,
        host=None,
        port=None,
        database=None,
        user=None,
        password=None,
        create=False,
    ) -> None:
        """Connects a database with the given parameters."""
        if backend is None:
            msg = "Database backend not defined"
            raise FpdbError(msg)
        self.backend = backend
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        self.cursor = None
        self.hand_inc = 1

        if backend == Database.MYSQL_INNODB:
            # Prefer mysqlclient (MySQLdb); fall back to the pure-Python pymysql
            # shim so MySQL works without the system libraries mysqlclient needs.
            try:
                import MySQLdb
            except ImportError:
                import pymysql

                pymysql.install_as_MySQLdb()
                import MySQLdb

            # Note: SQLAlchemy 2.0 removed pool.manage
            # MySQLdb has its own connection pooling, so we don't need it
            try:
                kwargs = {
                    "host": host,
                    "user": user,
                    "passwd": password,
                    "db": database,
                    "charset": "utf8",
                    "use_unicode": True,
                }
                if port:
                    kwargs["port"] = int(port)

                self.connection = MySQLdb.connect(**kwargs)
                self.__connected = True
            except MySQLdb.Error as ex:
                if ex.args[0] == 1045:
                    raise FpdbMySQLAccessDenied(ex.args[0], ex.args[1])
                if ex.args[0] == 2002 or ex.args[0] == 2003:  # 2002 is no unix socket, 2003 is no tcp socket
                    raise FpdbMySQLNoDatabase(ex.args[0], ex.args[1])
                log.exception("UNKNOWN MYSQL ERROR: {ex}")
            c = self.get_cursor()
            c.execute("show variables like 'auto_increment_increment'")
            self.hand_inc = int(c.fetchone()[1])
        elif backend == Database.PGSQL:
            import psycopg

            # Note: SQLAlchemy 2.0 removed pool.manage
            # psycopg has its own connection pooling, so we don't need it
            # psycopg3 handles Unicode natively, no need for register_type(UNICODE)
            # psycopg3 has native Decimal support, no adapter registration needed

            self.__connected = False
            if self.host in ("localhost", "127.0.0.1"):
                try:
                    self.connection = psycopg.connect(dbname=database)
                    self.__connected = True
                except psycopg.OperationalError:
                    # direct connection failed so try user/pass/... version
                    pass

            if not self.is_connected():
                try:
                    self.connection = psycopg.connect(
                        host=host,
                        port=port,
                        user=user,
                        password=password,
                        dbname=database,
                    )
                    self.__connected = True
                except Exception as ex:  # intentional broad catch: psycopg connection error inspected and re-raised as a typed FpdbError
                    if "Connection refused" in ex.args[0] or (
                        'database "' in ex.args[0] and '" does not exist' in ex.args[0]
                    ):
                        raise FpdbPostgresqlNoDatabase(errmsg=ex.args[0])
                    if "password authentication" in ex.args[0]:
                        raise FpdbPostgresqlAccessDenied(errmsg=ex.args[0])
                    if 'role "' in ex.args[0] and '" does not exist' in ex.args[0]:  # role "fpdb" does not exist
                        raise FpdbPostgresqlAccessDenied(errmsg=ex.args[0])
                    msg = ex.args[0]
                    log.exception(f"error postgreslq: {msg}")
                    raise FpdbError(msg)

        elif backend == Database.SQLITE:
            create = True
            import sqlite3

            # Note: SQLAlchemy 2.0 removed pool.manage
            # SQLite handles concurrent connections well natively with proper settings
            # (see check_same_thread=False and timeout settings below)

            if database != ":memory:":
                if not os.path.isdir(self.config.dir_database) and create:
                    log.info(f"Creating directory: '{self.config.dir_database}'")
                    os.makedirs(self.config.dir_database)
                database = os.path.join(self.config.dir_database, database).replace(
                    "\\",
                    "/",
                )
            self.db_path = database
            log.info(f"Connecting to SQLite: {self.db_path}")
            if os.path.exists(database) or create:
                self.connection = sqlite3.connect(
                    self.db_path,
                    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                    timeout=60.0,  # Increased timeout to prevent connection timeouts
                    check_same_thread=False,  # Allow multi-threaded access
                )
                self.__connected = True
                sqlite3.register_converter("bool", lambda x: bool(int(x)))
                sqlite3.register_adapter(bool, lambda x: 1 if x else 0)
                sqlite3.register_converter("decimal", convert_decimal)
                sqlite3.register_adapter(Decimal, adapt_decimal)
                self.connection.create_function("floor", 1, math.floor)
                self.connection.create_function("sqrt", 1, math.sqrt)
                tmp = sqlitemath()
                self.connection.create_function("mod", 2, tmp.mod)
                if use_numpy:
                    self.connection.create_aggregate("variance", 1, VARIANCE)
                else:
                    log.warning(
                        ("Some database functions will not work without NumPy support"),
                    )
                self.cursor = self.connection.cursor()
                self.cursor.execute(
                    "PRAGMA temp_store=2",
                )  # use memory for temp tables/indexes
                self.cursor.execute(
                    "PRAGMA journal_mode=WAL",
                )  # use memory for temp tables/indexes
                self.cursor.execute(
                    "PRAGMA synchronous=0",
                )  # don't wait for file writes to finish
                self.cursor.execute(
                    "PRAGMA busy_timeout=60000",
                )  # wait up to 60 seconds for locks
                self.cursor.execute(
                    "PRAGMA cache_size=10000",
                )  # increase cache size for better performance
            else:
                raise FpdbError("sqlite database " + database + " does not exist")
        else:
            raise FpdbError("unrecognised database backend:" + str(backend))

        if self.is_connected():
            self.cursor = self.connection.cursor()
            self.cursor.execute(self.sql.query["set tx level"])
            self.check_version(database=database, create=create)

    def get_sites(self) -> None:
        self.cursor.execute("SELECT name,id FROM Sites")
        db_sites = dict(self.cursor.fetchall())
        configured_sites = getattr(self.config, "site_ids", {})
        sites = {**configured_sites, **db_sites}
        self.config.set_site_ids(sorted(sites.items(), key=lambda item: (item[1], item[0])))

    def check_version(self, database, create) -> None:
        self.wrongDbVersion = False
        try:
            self.cursor.execute("SELECT * FROM Settings")
            settings = self.cursor.fetchone()
            if settings[0] != DB_VERSION:
                log.error(
                    f"Outdated or too new database version ({settings[0]}). Please recreate tables.",
                )
                self.wrongDbVersion = True
        except Exception:  # intentional broad catch: settings-table read failure triggers cross-backend table recreate
            if database != ":memory:":
                if create:
                    # print (("Failed to read settings table.") + " - " + ("Recreating tables."))
                    log.info("Failed to read settings table...Recreating tables.")
                    self.recreate_tables()
                    self.check_version(database=database, create=False)
                else:
                    # print (("Failed to read settings table.") + " - " + ("Please recreate tables."))
                    log.info(
                        ("Failed to read settings table...Please recreate tables."),
                    )
                    self.wrongDbVersion = True
            else:
                self.wrongDbVersion = True

    # end def connect

    def _pg_set_isolation(self, level: int) -> None:
        """psycopg2/psycopg3 compatibility for the old ``set_isolation_level(int)``.

        Level 0 meant autocommit (needed around DDL such as CREATE/DROP INDEX,
        VACUUM and ANALYZE) and 1 meant a normal transaction. The psycopg2/psycopg3
        compatibility now lives in the Dialect; this maps the old integer onto its
        ``set_autocommit`` flag.
        """
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).set_autocommit(self.connection, level == 0)

    def transaction(self) -> DatabaseTransaction:
        """Return a transaction context manager for this database."""
        return DatabaseTransaction(self)

    def commit(self, force: bool = False) -> None:
        if self._in_transaction > 0 and not force:
            log.debug("Database.commit: deferred because we are inside a transaction block")
            return
        if self.backend != self.SQLITE:
            self.connection.commit()
        else:
            # sqlite commits can fail because of shared locks on the database (SQLITE_BUSY)
            # re-try commit if it fails in case this happened
            maxtimes = 5
            pause = 1
            ok = False
            for i in range(maxtimes):
                try:
                    self.connection.commit()
                    # log.debug(("commit finished ok, i = ")+str(i))
                    ok = True
                except Exception as e:  # intentional broad catch: sqlite commit retried on transient SQLITE_BUSY lock
                    log.exception(f"commit {i} failed: info={sys.exc_info()}, value={e}")
                    sleep(pause)
                if ok:
                    break
            if not ok:
                log.error("commit failed")
                msg = "sqlite commit failed"
                raise FpdbError(msg)

    def rollback(self, force: bool = False) -> None:
        if self._in_transaction > 0 and not force:
            log.debug("Database.rollback: deferred because we are inside a transaction block")
            return
        self.connection.rollback()

    def connected(self):
        """Now deprecated, use is_connected() instead."""
        return self.__connected

    def is_connected(self):
        return self.__connected

    def get_cursor(self, connect=False):
        if self.backend == Database.MYSQL_INNODB and os.name == "nt":
            self.connection.ping(True)
        return self.connection.cursor()

    def close_connection(self) -> None:
        if getattr(self, "connection", None):
            self.connection.close()
            self.connection = None
        self.__connected = False

    def _close_cursor_quietly(self) -> None:
        cursor = getattr(self, "cursor", None)
        if not cursor:
            return
        with contextlib.suppress(Exception):
            cursor.close()
        self.cursor = None

    def disconnect(self, due_to_error=False) -> None:
        """Disconnects the DB (rolls back if param is true, otherwise commits."""
        if due_to_error:
            self.connection.rollback()
        else:
            self.connection.commit()
        self._close_cursor_quietly()
        self.close_connection()
        self.__connected = False

    def reconnect(self, due_to_error=False) -> None:
        """Reconnects the DB."""
        # print "started reconnect"
        self.disconnect(due_to_error)
        self.connect(self.backend, self.host, self.database, self.user, self.password)

    def get_backend_name(self) -> str:
        """Returns the name of the currently used backend."""
        if self.backend == 2:
            return "MySQL InnoDB"
        if self.backend == 3:
            return "PostgreSQL"
        if self.backend == 4:
            return "SQLite"
        msg = "invalid backend"
        raise FpdbError(msg)

    def get_db_info(self):
        return (self.host, self.database, self.user, self.password)

    def get_table_name(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        return c.fetchone()

    def get_table_info(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        row = c.fetchone()
        if row is None:
            # Hand not yet committed to the DB (race between the HUD reading the
            # hand id from stdin and the importer writing the row). Let the caller
            # skip and retry on a later notification instead of crashing.
            log.debug("No table info found yet for hand %s", hand_id)
            return None
        table_info = list(row)
        if row[3] == "ring":  # cash game
            table_info.append(None)
            table_info.append(None)
            table_info.append(None)
            return table_info
        # tournament
        tour_no, tab_no = re.split(" ", row[0], 1)
        table_info.append(tour_no)
        table_info.append(tab_no)

        # Query tournament name
        tourney_name = None
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = f"SELECT tourneyName FROM Tourneys WHERE siteTourneyNo = {ph}"
            c.execute(q, (int(tour_no),))
            trow = c.fetchone()
            if trow:
                tourney_name = trow[0]
        except Exception:
            log.exception("Error querying tourneyName for siteTourneyNo=%s", tour_no)
            self._rollback_after_failed_read()

        table_info.append(tourney_name)
        return table_info

    def get_last_hand(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_last_hand"])
        row = c.fetchone()
        return row[0]

    def get_xml(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_xml"], (hand_id))
        row = c.fetchone()
        return row[0]

    def get_recent_hands(self, last_hand):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_recent_hands"], {"last_hand": last_hand})
        return c.fetchall()

    def get_gameinfo_from_hid(self, hand_id):
        # returns a gameinfo (gametype) dictionary suitable for passing
        # to Hand.hand_factory
        c = self.connection.cursor()
        q = self.sql.query["get_gameinfo_from_hid"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (hand_id,))
        row = c.fetchone()

        if row is None:
            log.warning(f"No game info found for hand ID {hand_id}")
            return None

        return {
            "sitename": row[0],
            "category": row[1],
            "base": row[2],
            "type": row[3],
            "limitType": row[4],
            "hilo": row[5],
            "sb": row[6],
            "bb": row[7],
            "sbet": row[8],
            "bbet": row[9],
            "currency": row[10],
            "gametypeId": row[11],
            "split": row[12],
        }

    #   Query 'get_hand_info' does not exist, so it seems
    #    def get_hand_info(self, new_hand_id):
    #        c = self.connection.cursor()
    #        c.execute(self.sql.query['get_hand_info'], new_hand_id)
    #        return c.fetchall()

    def getHandCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getHandCount"])
        return c.fetchone()[0]

    # end def getHandCount

    def getTourneyCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getTourneyTypeCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyTypeCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getSiteTourneyNos(self, site):
        c = self.connection.cursor()
        q = self.sql.query["getSiteId"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (site,))
        siteid = c.fetchone()[0]
        q = self.sql.query["getSiteTourneyNos"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (siteid,))
        alist = []
        for row in c.fetchall():
            alist.append(row)
        return alist

    def get_actual_seat(self, hand_id, name):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_actual_seat"], (hand_id, name))
        row = c.fetchone()
        return row[0]

    def get_cards(self, hand):
        """Get and return the cards for each player in the hand."""
        cards = {}  # dict of cards, the key is the seat number,
        # the value is a tuple of the players cards
        # example: {1: (0, 0, 20, 21, 22, 0 , 0)}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_cards"], [hand])
        for row in c.fetchall():
            cards[row[0]] = row[1:]
        return cards

    def _rollback_after_failed_read(self) -> None:
        """Clear an aborted transaction left by a best-effort HUD read.

        Under PostgreSQL a single failed statement blocks every later query on
        the connection until an explicit ROLLBACK, so a swallowed read error
        would otherwise resurface as InFailedSqlTransaction in unrelated code.
        """
        try:
            self.connection.rollback()
        except Exception:
            log.debug("rollback after failed read did not succeed")

    def get_hand_positions(self, hand):
        """Return {playerId: position} for a hand, for position-conditional HUD panels.

        Position values are as stored by DerivedStats in HandsPlayers.position:
        0 = button, 'S' = small blind, 'B' = big blind, 1.. = seats after the BB.
        """
        positions = {}
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = "SELECT playerId, position FROM HandsPlayers WHERE handId = %s".replace("%s", ph)
            c = self.connection.cursor()
            c.execute(q, (hand,))
            for row in c.fetchall():
                # int keys, so `pid in stat_dict` in _merge_positions matches.
                positions[row[0]] = row[1]
        except Exception:
            log.exception("get_hand_positions failed for hand %s", hand)
            self._rollback_after_failed_read()
        return positions

    def get_seat_players(self, hand_id: str) -> dict[int, dict[str, object]]:
        """Return seatNo -> {player_id, screen_name} dict for a hand.

        player_id is a native int to match the keys of the stat_dict built by
        get_stats_from_hand; get_id_from_seat() feeds it straight into
        stat_dict[player_id] lookups.
        """
        players = {}
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = (
                "SELECT hp.seatNo, hp.playerId, p.name "
                "FROM HandsPlayers hp "
                "INNER JOIN Players p ON hp.playerId = p.id "
                "WHERE hp.handId = %s"
            ).replace("%s", ph)
            c = self.connection.cursor()
            c.execute(q, (hand_id,))
            for row in c.fetchall():
                players[int(row[0])] = {"player_id": int(row[1]), "screen_name": row[2]}
        except Exception:
            log.exception("get_seat_players failed for hand %s", hand_id)
            self._rollback_after_failed_read()
        return players

    def get_table_min_stack_bb(self, hand_id: str) -> float | None:
        """Smallest end-of-hand stack at the table, in big blinds (PT4 live stat).

        From the given (most recently imported) hand, take each seated player's
        end-of-hand stack (startCash - committed + winnings), drop eliminated
        players (stack <= 0), and divide the minimum by the big blind. Returns
        None when it cannot be computed.

        Note: the big blind comes from Gametypes, so for multi-level tournaments
        this is the gametype's blind, not necessarily the current level's.
        """
        try:
            ph = self.sql.query.get("placeholder", "%s")
            c = self.get_cursor()
            c.execute(
                (
                    "SELECT gt.bigBlind FROM Hands h "
                    "INNER JOIN Gametypes gt ON h.gametypeId = gt.id "
                    "WHERE h.id = %s"
                ).replace("%s", ph),
                (hand_id,),
            )
            row = c.fetchone()
            if not row or not row[0]:
                return None
            big_blind = float(row[0])
            if big_blind <= 0:
                return None
            c.execute(
                (
                    "SELECT startCash, committed, winnings FROM HandsPlayers "
                    "WHERE handId = %s AND sitout = FALSE"
                ).replace("%s", ph),
                (hand_id,),
            )
            stacks = []
            for start_cash, committed, winnings in c.fetchall():
                end_cash = float(start_cash) - float(committed) + float(winnings)
                if end_cash > 0:
                    stacks.append(end_cash)
            if not stacks:
                return None
            return min(stacks) / big_blind
        except Exception:
            log.exception("get_table_min_stack_bb failed for hand %s", hand_id)
            self._rollback_after_failed_read()
            return None

    def get_common_cards(self, hand):
        """Get and return the community cards for the specified hand."""
        cards = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_common_cards"], [hand])
        #        row = c.fetchone()
        cards["common"] = c.fetchone()
        return cards

    def get_action_from_hand(self, hand_no):
        action: list[list[Any]] = [[], [], [], [], []]
        c = self.connection.cursor()
        c.execute(self.sql.query["get_action_from_hand"], (hand_no,))
        for row in c.fetchall():
            street = row[0]
            act = row[1:]
            action[street].append(act)
        return action

    def get_winners_from_hand(self, hand):
        """Returns a hash of winners:amount won, given a hand number."""
        winners = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_winners_from_hand"], (hand,))
        for row in c.fetchall():
            winners[row[0]] = row[1]
        return winners

    def set_printdata(self, val) -> None:
        self.printdata = val

    def _inject_hud_chipev_columns(self, sql_text):
        """Replace the <chipev_columns> placeholder in the HUD aggregation query.

        Substitutes bucket-encoded ChipEV-by-position SUM(CASE...) columns from
        the declarative stat registry so descriptor stats become stat_dict keys.
        The compiled clause is cached (the HUD calls this once per hand) and the
        substitution is best-effort: on any error the placeholder is removed and
        the base query runs unchanged.
        """
        if "<chipev_columns>" not in sql_text:
            return sql_text
        if not hasattr(self, "_hud_chipev_clause"):
            try:
                from fpdb_3_legacy.stat_adapters import HudAdapter
                from fpdb_3_legacy.stat_registry import get_registry

                descriptors = [d for d in get_registry().series_for_scope("tour") if d.dimension]
                self._hud_chipev_clause = HudAdapter().select_clause(descriptors)
            except Exception:
                log.exception("failed to build HUD ChipEV columns; disabling")
                self._hud_chipev_clause = ""
        return sql_text.replace("<chipev_columns>", self._hud_chipev_clause)

    def init_hud_stat_vars(self, hud_days, h_hud_days) -> None:
        """Initialise variables used by Hud to fetch stats:
        self.hand_1day_ago     handId of latest hand played more than a day ago
        self.date_ndays_ago    date n days ago
        self.h_date_ndays_ago  date n days ago for hero (different n).
        """
        self.hand_1day_ago = 1
        c = self.get_cursor()
        c.execute(self.sql.query["get_hand_1day_ago"])
        row = c.fetchone()
        if row and row[0]:
            self.hand_1day_ago = int(row[0])

        tz = datetime.utcnow() - datetime.today()
        tz_offset = (tz.seconds) // (3600)
        tz_day_start_offset = self.day_start + tz_offset

        d = timedelta(days=hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

        d = timedelta(days=h_hud_days, hours=tz_day_start_offset)
        now = datetime.utcnow() - d
        self.h_date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

    # is get_stats_from_hand slow?
    # Gimick - yes  - reason being that the gametypeid join on hands
    # increases exec time on SQLite and postgres by a factor of 6 to 10
    # method below changed to lookup hand.gametypeid and pass that as
    # a constant to the underlying query.

    def get_stats_from_hand(
        self,
        hand,
        game_type=None,  # "ring" or "tour"; currently inferred from hand metadata
        hud_params=None,
        hero_id=-1,
        num_seats=6,
        **kwargs,
    ):
        if game_type is None and "type" in kwargs:
            game_type = kwargs.pop("type")
        if kwargs:
            log.warning("Ignoring unknown get_stats_from_hand arguments: %s", ", ".join(sorted(kwargs)))

        if hud_params is None:
            hud_params = {
                "stat_range": "A",
                "agg_bb_mult": 1000,
                "seats_style": "A",
                "seats_cust_nums_low": 1,
                "seats_cust_nums_high": 10,
                "h_stat_range": "S",
                "h_agg_bb_mult": 1000,
                "h_seats_style": "A",
                "h_seats_cust_nums_low": 1,
                "h_seats_cust_nums_high": 10,
            }
        stat_range = hud_params["stat_range"]
        agg_bb_mult = hud_params["agg_bb_mult"]
        seats_style = hud_params["seats_style"]
        seats_cust_nums_low = hud_params["seats_cust_nums_low"]
        seats_cust_nums_high = hud_params["seats_cust_nums_high"]
        h_stat_range = hud_params["h_stat_range"]
        h_agg_bb_mult = hud_params["h_agg_bb_mult"]
        h_seats_style = hud_params["h_seats_style"]
        h_seats_cust_nums_low = hud_params["h_seats_cust_nums_low"]
        h_seats_cust_nums_high = hud_params["h_seats_cust_nums_high"]

        stat_dict: dict[Any, Any] = {}

        if seats_style == "A":
            seats_min, seats_max = 0, 10
        elif seats_style == "C":
            seats_min, seats_max = seats_cust_nums_low, seats_cust_nums_high
        elif seats_style == "E":
            seats_min, seats_max = num_seats, num_seats
        else:
            seats_min, seats_max = 0, 10
            log.warning(f"bad seats_style value: {seats_style}")

        if h_seats_style == "A":
            h_seats_min, h_seats_max = 0, 10
        elif h_seats_style == "C":
            h_seats_min, h_seats_max = h_seats_cust_nums_low, h_seats_cust_nums_high
        elif h_seats_style == "E":
            h_seats_min, h_seats_max = num_seats, num_seats
        else:
            h_seats_min, h_seats_max = 0, 10
            log.warning(f"bad h_seats_style value: {h_seats_style}")

        if stat_range == "S" or h_stat_range == "S":
            self.get_stats_from_hand_session(
                hand,
                stat_dict,
                hero_id,
                stat_range,
                seats_min,
                seats_max,
                h_stat_range,
                h_seats_min,
                h_seats_max,
            )

            if stat_range == "S" and h_stat_range == "S":
                return stat_dict

        if stat_range == "T":
            stylekey = self.date_ndays_ago
        elif stat_range == "A":
            stylekey = "0000000"  # all stylekey values should be higher than this
        elif stat_range == "S":
            stylekey = "zzzzzzz"  # all stylekey values should be lower than this
        else:
            stylekey = "0000000"
            log.info(f"stat_range: {stat_range}")

        if h_stat_range == "T":
            h_stylekey = self.h_date_ndays_ago
        elif h_stat_range == "A":
            h_stylekey = "0000000"  # all stylekey values should be higher than this
        elif h_stat_range == "S":
            h_stylekey = "zzzzzzz"  # all stylekey values should be lower than this
        else:
            h_stylekey = "00000000"
            log.info(f"h_stat_range: {h_stat_range}")

        # lookup gametypeId from hand
        handinfo = self.get_gameinfo_from_hid(hand)
        if handinfo is None:
            log.warning(f"No game info found for hand ID {hand}")
            return stat_dict  # Return an empty stat_dict if no game info is found

        gametypeId = handinfo["gametypeId"]

        query = "get_stats_from_hand_aggregated"
        subs = (
            hand,
            hero_id,
            stylekey,
            agg_bb_mult,
            agg_bb_mult,
            gametypeId,
            seats_min,
            seats_max,  # hero params
            hero_id,
            h_stylekey,
            h_agg_bb_mult,
            h_agg_bb_mult,
            gametypeId,
            h_seats_min,
            h_seats_max,
        )  # villain params

        stime = time()
        c = self.connection.cursor()

        # Inject declarative ChipEV-by-position columns (stat_registry.py) into
        # the HUD aggregation. These are bucket-encoded SUM(CASE...) columns that
        # become stat_dict keys, so descriptor stats render live in the HUD.
        sql_text = self._inject_hud_chipev_columns(self.sql.query[query])

        # Now get the stats
        c.execute(sql_text, subs)
        ptime = time() - stime
        log.info(
            f"HudCache query get_stats_from_hand_aggregated took {ptime:.3f} seconds",
        )
        colnames = [desc[0] for desc in c.description]
        for row in c.fetchall():
            # Keep player ids as native DB integers: do_stat() coerces the player
            # to int and every stat function indexes stat_dict[int]. Coercing keys
            # to str here silently makes all stat lookups miss. String ids only
            # appear at the JSON persistence boundary (see merge_stats).
            playerid = row[0]
            is_hero = False
            if hero_id is not None:
                try:
                    is_hero = int(playerid) == int(hero_id)
                except (ValueError, TypeError):
                    is_hero = str(playerid) == str(hero_id)
            if (is_hero and h_stat_range != "S") or (not is_hero and stat_range != "S"):
                t_dict = {}
                for name, val in zip(colnames, row, strict=False):
                    t_dict[name.lower()] = val
                stat_dict[t_dict["player_id"]] = t_dict

        return stat_dict

    # uses query on handsplayers instead of hudcache to get stats on just this session
    def get_stats_from_hand_session(
        self,
        hand,
        stat_dict,
        hero_id,
        stat_range,
        seats_min,
        seats_max,
        h_stat_range,
        h_seats_min,
        h_seats_max,
    ) -> None:
        """Get stats for just this session (currently defined as any play in the last 24 hours - to
        be improved at some point ...)
        h_stat_range and stat_range params indicate whether to get stats for hero and/or others
        - only fetch heroes stats if h_stat_range == 'S',
        and only fetch others stats if stat_range == 'S'
        seats_min/max params give seats limits, only include stats if between these values.
        """
        query = self.sql.query["get_stats_from_hand_session"]
        query = query.replace("<signed>", "signed ") if self.db_server == "mysql" else query.replace("<signed>", "")

        subs = (
            self.hand_1day_ago,
            hand,
            hero_id,
            seats_min,
            seats_max,
            hero_id,
            h_seats_min,
            h_seats_max,
        )
        c = self.get_cursor()

        # now get the stats
        # print "sess_stats: subs =", subs, "subs[0] =", subs[0]
        c.execute(query, subs)
        colnames = [desc[0] for desc in c.description]
        row = c.fetchone()
        if colnames[0].lower() == "player_id":
            # Loop through stats adding them to appropriate stat_dict:
            while row:
                # Native int keys, matching do_stat()/stat functions. See the
                # aggregated loop above for why str coercion breaks stat lookups.
                playerid = row[0]
                is_hero = False
                if hero_id is not None:
                    try:
                        is_hero = int(playerid) == int(hero_id)
                    except (ValueError, TypeError):
                        is_hero = str(playerid) == str(hero_id)
                if (is_hero and h_stat_range == "S") or (not is_hero and stat_range == "S"):
                    for name, val in zip(colnames, row, strict=False):
                        if playerid not in stat_dict:
                            stat_dict[playerid] = {}
                            stat_dict[playerid][name.lower()] = val
                        elif name.lower() not in stat_dict[playerid]:
                            stat_dict[playerid][name.lower()] = val
                        elif name.lower() not in (
                            "hand_id",
                            "player_id",
                            "seat",
                            "screen_name",
                            "seats",
                        ):
                            stat_dict[playerid][name.lower()] += val
                row = c.fetchone()
        else:
            log.error(f"query {query} result does not have player_id as first column")

        # print "session stat_dict =", stat_dict
        # return stat_dict

    def get_player_id(self, config, siteName, playerName):
        c = self.connection.cursor()
        # conversion to UTF-8 in Python 3 is not needed
        c.execute(self.sql.query["get_player_id"], (playerName, siteName))
        row = c.fetchone()
        if row:
            return row[0]

        # Fallback to search for playerName on any site if not found on the specified site
        ph = self.sql.query.get("placeholder", "%s")
        q1 = "SELECT id FROM Players WHERE name = %s".replace("%s", ph)
        c.execute(q1, (playerName,))
        rows = c.fetchall()
        if len(rows) == 1:
            log.info(f"Database.get_player_id: Fallback found unique player ID {rows[0][0]} for '{playerName}' (searched across all sites)")
            return rows[0][0]
        elif len(rows) > 1:
            # If there are multiple players with this name, let's try to match siteName prefix or sub-network
            q2 = """
                SELECT p.id
                FROM Players p
                JOIN Sites s ON p.siteId = s.id
                WHERE p.name = %s
                AND (s.name LIKE %s OR %s LIKE s.name || %s)
            """.replace("%s", ph)
            c.execute(q2, (playerName, siteName + "%", siteName, "%"))
            match_rows = c.fetchall()
            if match_rows:
                log.info(f"Database.get_player_id: Fallback matched site prefix player ID {match_rows[0][0]} for '{playerName}' on site '{siteName}' variant")
                return match_rows[0][0]
            # Otherwise return the first one
            log.info(f"Database.get_player_id: Fallback returned first player ID {rows[0][0]} of multiple matches for '{playerName}'")
            return rows[0][0]
        return False

    def get_player_site_id(self, playerId):
        c = self.connection.cursor()
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT siteId FROM Players WHERE id = %s".replace("%s", ph)
        c.execute(q, (playerId,))
        row = c.fetchone()
        if row:
            return row[0]
        return None

    def get_player_name_by_id(self, playerId):
        c = self.get_cursor()
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT name FROM Players WHERE id = %s".replace("%s", ph)
        c.execute(q, (playerId,))
        row = c.fetchone()
        if row:
            return row[0]
        return None

    def get_player_names(self, config, site_id=None, like_player_name="%"):
        """Fetch player names from players. Use site_id and like_player_name if provided."""
        if site_id is None:
            site_id = -1
        c = self.get_cursor()
        # conversion to UTF-8 in Python 3 is not needed
        c.execute(
            self.sql.query["get_player_names"],
            (like_player_name, site_id, site_id),
        )
        return c.fetchall()

    def get_site_id(self, site):
        c = self.get_cursor()
        c.execute(self.sql.query["getSiteId"], (site,))
        return c.fetchall()

    def resetCache(self) -> None:
        self.ttold: set[Any] = set()  # TourneyTypes old
        self.ttnew: set[Any] = set()  # TourneyTypes new
        self.wmold: set[Any] = set()  # WeeksMonths old
        self.wmnew: set[Any] = set()  # WeeksMonths new
        self.gtcache = None  # GameTypeId cache
        self.tcache = None  # TourneyId cache
        self.pcache = None  # PlayerId cache
        self.tpcache = None  # TourneysPlayersId cache

    def get_last_insert_id(self, cursor=None):
        ret = None
        try:
            if self.backend == self.MYSQL_INNODB:
                ret = self.connection.insert_id()
                if ret < 1 or ret > 999999999:
                    log.warning(
                        f"getLastInsertId(): problem fetching insert_id? ret={ret}",
                    )
                    ret = -1
            elif self.backend == self.PGSQL:
                # some options:
                # currval(hands_id_seq) - use name of implicit seq here
                # lastval() - still needs sequences set up?
                # insert ... returning  is useful syntax (but postgres specific?)
                # see rules (fancy trigger type things)
                c = self.get_cursor()
                ret = c.execute("SELECT lastval()")
                row = c.fetchone()
                if not row:
                    log.warning(
                        f"getLastInsertId(): problem fetching lastval? row={row}",
                    )
                    ret = -1
                else:
                    ret = row[0]
            elif self.backend == self.SQLITE:
                ret = cursor.lastrowid
            else:
                log.error(f"getLastInsertId(): unknown backend: {self.backend}")
                ret = -1
        except Exception:  # intentional broad catch: getLastInsertId logs full traceback then re-raises
            ret = -1
            err = traceback.extract_tb(sys.exc_info()[2])
            log.exception(f"Database get_last_insert_id error: {sys.exc_info()[1]}")
            log.exception("\n".join(f"{e[0]}:{e[1]} {e[2]}" for e in err))
            raise
        return ret

    def prepareBulkImport(self) -> int | None:
        """Drop some indexes/foreign keys to prepare for bulk import.
        Currently keeping the standalone indexes as needed to import quickly.
        """
        stime = time()
        c = self.get_cursor()
        # sc: don't think autocommit=0 is needed, should already be in that mode
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=0")
            c.execute("SET autocommit=0")
            return None
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for fk in self.foreignKeys[self.backend]:
            if fk["drop"] == 1:
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
                    # print "preparebulk find fk: cons=", cons
                    if cons:
                        log.debug(
                            f"dropping mysql fk {cons[0]} {fk['fktab']} {fk['fkcol']}",
                        )
                        try:
                            c.execute(
                                "alter table " + fk["fktab"] + " drop foreign key " + cons[0],
                            )
                        except Exception:  # intentional broad catch: cross-backend FK drop (MySQL) best-effort, continue
                            log.exception(f"    drop failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    #    DON'T FORGET TO RECREATE THEM!!
                    log.debug(f"dropping pg fk {fk['fktab']} {fk['fkcol']}")
                    try:
                        # try to lock table to see if index drop will work:
                        # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                        # then drop still hangs :-(  does work in some tests though??
                        # will leave code here for now pending further tests/enhancement ...
                        c.execute("BEGIN TRANSACTION")
                        c.execute(
                            "lock table {} in exclusive mode nowait".format(fk["fktab"]),
                        )
                        # print "after lock, status:", c.statusmessage
                        # print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                        try:
                            c.execute(
                                "alter table {} drop constraint {}_{}_fkey".format(
                                    fk["fktab"], fk["fktab"], fk["fkcol"]
                                ),
                            )
                            log.debug(f"dropping pg fk {fk['fktab']} {fk['fkcol']}")
                        except Exception:  # intentional broad catch: cross-backend FK drop (PG) ignores 'does not exist'
                            if "does not exist" not in str(sys.exc_info()[1]):
                                log.exception(
                                    f"warning: drop pg fk {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip()}, continuing ...",
                                )
                        c.execute("END TRANSACTION")
                    except Exception:  # intentional broad catch: cross-backend FK drop (PG lock/txn) best-effort, continue
                        log.exception(
                            rf"warning: constraint {fk['fktab']}_{fk['fkcol']}_fkey not dropped: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
                else:
                    return -1

        for idx in self.indexes[self.backend]:
            if idx["drop"] == 1:
                if self.backend == self.MYSQL_INNODB:
                    log.info(f"dropping mysql index {idx['tab']} {idx['col']}")
                    try:
                        # apparently nowait is not implemented in mysql so this just hangs if there are locks
                        # preventing the index drop :-(
                        c.execute(
                            "alter table %s drop index %s;",
                            (idx["tab"], idx["col"]),
                        )
                    except Exception:  # intentional broad catch: cross-backend index drop (MySQL) best-effort, continue
                        log.exception(f"    drop index failed: {sys.exc_info()}")
                        # ALTER TABLE `fpdb`.`handsplayers` DROP INDEX `playerId`;
                        # using: 'HandsPlayers' drop index 'playerId'
                elif self.backend == self.PGSQL:
                    #    DON'T FORGET TO RECREATE THEM!!
                    log.info(f"dropping pg index {idx['tab']} {idx['col']}")
                    try:
                        # try to lock table to see if index drop will work:
                        c.execute("BEGIN TRANSACTION")
                        c.execute(
                            "lock table {} in exclusive mode nowait".format(idx["tab"]),
                        )
                        # print "after lock, status:", c.statusmessage
                        try:
                            # table locked ok so index drop should work:
                            # print "drop index %s_%s_idx" % (idx['tab'],idx['col'])
                            c.execute(
                                "drop index if exists {}_{}_idx".format(idx["tab"], idx["col"]),
                            )
                            # print "dropped  pg index ", idx['tab'], idx['col']
                        except Exception:  # intentional broad catch: cross-backend index drop (PG) ignores 'does not exist'
                            if "does not exist" not in str(sys.exc_info()[1]):
                                log.exception(
                                    f"drop index {idx['tab']}_{idx['col']}_idx failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                                )
                        c.execute("END TRANSACTION")
                    except Exception:  # intentional broad catch: cross-backend index drop (PG lock/txn) best-effort, continue
                        log.exception(
                            f"index {idx['tab']}_{idx['col']}_idx not dropped {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
                else:
                    return -1

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()  # seems to clear up errors if there were any in postgres
        ptime = time() - stime
        log.debug(f"prepare import took {ptime} seconds")
        return None

    # end def prepareBulkImport

    def afterBulkImport(self) -> int | None:
        """Re-create any dropped indexes/foreign keys after bulk import."""
        stime = time()

        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=1")
            c.execute("SET autocommit=1")
            return None

        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for fk in self.foreignKeys[self.backend]:
            if fk["drop"] == 1:
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
                            f"Creating foreign key {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
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
                        except Exception:  # intentional broad catch: cross-backend FK create (MySQL) best-effort, continue
                            log.exception(f"Create foreign key failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    log.debug(
                        f"Creating foreign key {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
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
                    except Exception:  # intentional broad catch: cross-backend FK create (PG) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
                else:
                    return -1

        for idx in self.indexes[self.backend]:
            if idx["drop"] == 1:
                if self.backend == self.MYSQL_INNODB:
                    log.debug(f"Creating MySQL index {idx['tab']} {idx['col']}")
                    try:
                        s = "alter table {} add index {}({})".format(
                            idx["tab"],
                            idx["col"],
                            idx["col"],
                        )
                        c.execute(s)
                    except Exception:  # intentional broad catch: cross-backend index create (MySQL) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    #                pass
                    # mod to use tab_col for index name?
                    log.debug(f"Creating PostgreSQL index {idx['tab']} {idx['col']}")
                    try:
                        s = "create index {}_{}_idx on {}({})".format(
                            idx["tab"],
                            idx["col"],
                            idx["tab"],
                            idx["col"],
                        )
                        c.execute(s)
                    except Exception:  # intentional broad catch: cross-backend index create (PG) best-effort, continue
                        log.exception(f"Create index failed: {sys.exc_info()}")
                else:
                    return -1

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()  # seems to clear up errors if there were any in postgres
        atime = time() - stime
        log.debug(f"After import took {atime} seconds")
        return None

    # end def afterBulkImport

    def drop_referential_integrity(self) -> None:
        """Update all tables to remove foreign keys."""
        c = self.get_cursor()
        c.execute(self.sql.query["list_tables"])
        result = c.fetchall()

        for i in range(len(result)):
            c.execute("SHOW CREATE TABLE " + result[i][0])
            inner = c.fetchall()

            for j in range(len(inner)):
                # result[i][0] - Table name
                # result[i][1] - CREATE TABLE parameters
                # Searching for CONSTRAINT `tablename_ibfk_1`
                for m in re.finditer("(ibfk_[0-9]+)", inner[j][1]):
                    key = "`" + inner[j][0] + "_" + m.group() + "`"
                    c.execute("ALTER TABLE " + inner[j][0] + " DROP FOREIGN KEY " + key)
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
        for query_name in ("createHandsShowdownTable", "createHandsCashoutTable", "createPlayerAutoNotesTable"):
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
        ):
            try:
                c = self.get_cursor()
                c.execute(self.sql.query[query_name])
                self.commit()
            except Exception:  # noqa: BLE001 - index/table already exists or feature table absent.
                self.rollback()

        self.ensure_hudcache_columns()
        self.ensure_handsplayers_columns()

    def _get_table_columns(self, table: str) -> set[str]:
        c = self.get_cursor()
        if self.backend == self.SQLITE:
            c.execute(f"PRAGMA table_info({table})")
            return {row[1] for row in c.fetchall()}
        if self.backend == self.MYSQL_INNODB:
            c.execute(f"SHOW COLUMNS FROM {table}")
            return {row[0] for row in c.fetchall()}

        c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s OR table_name = %s",
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
        """Drops the fpdb tables from the current db."""
        c = self.get_cursor()

        backend = self.get_backend_name()
        if backend == "MySQL InnoDB":  # what happens if someone is using MyISAM?
            try:
                self.drop_referential_integrity()  # needed to drop tables with foreign keys
                c.execute(self.sql.query["list_tables"])
                tables = c.fetchall()
                for table in tables:
                    c.execute(self.sql.query["drop_table"] + table[0])
                c.execute("SET FOREIGN_KEY_CHECKS=1")
            except Exception:  # intentional broad catch: drop all tables (MySQL) best-effort, rollback on failure
                err = traceback.extract_tb(sys.exc_info()[2])[-1]
                log.exception(
                    f"Error dropping tables: {err[2]}({err[1]}): {sys.exc_info()[1]}",
                )
                self.rollback()
        elif backend == "PostgreSQL":
            try:
                self.commit()
                c.execute(self.sql.query["list_tables"])
                tables = c.fetchall()
                for table in tables:
                    c.execute(self.sql.query["drop_table"] + table[0] + " cascade")
            except Exception:  # intentional broad catch: drop all tables (PG) best-effort, rollback on failure
                err = traceback.extract_tb(sys.exc_info()[2])[-1]
                log.exception(
                    f"Error dropping tables: {err[2]} ({err[1]}): {sys.exc_info()[1]}",
                )
                self.rollback()
        elif backend == "SQLite":
            c.execute(self.sql.query["list_tables"])
            for table in c.fetchall():
                table_name = table[0]
                if table_name.startswith("sqlite_"):
                    continue
                log.info(f"{self.sql.query['drop_table']} '{table_name}'")
                c.execute(self.sql.query["drop_table"] + table_name)
        self.commit()

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

    def replace_statscache(self, type, table, query):
        if table == "HudCache":
            insert = """HudCache
                (gametypeId
                ,playerId
                ,seats
                ,position
                <tourney_insert_clause>
                ,styleKey"""

            select = """h.gametypeId
                      ,hp.playerId
                      ,h.seats as seat_num
                      <hc_position>
                      <tourney_select_clause>
                      <styleKey>"""

            group = """h.gametypeId
                        ,hp.playerId
                        ,seat_num
                        ,hc_position
                        <tourney_group_clause>
                        <styleKeyGroup>"""

            query = query.replace("<insert>", insert)
            query = query.replace("<select>", select)
            query = query.replace("<group>", group)
            query = query.replace("<sessions_join_clause>", "")

            if self.build_full_hudcache:
                query = query.replace(
                    "<hc_position>",
                    """,case when hp.position = 'B' then 'B'
                            when hp.position = 'S' then 'S'
                            when hp.position = '0' then 'D'
                            when hp.position = '1' then 'C'
                            when hp.position = '2' then 'M'
                            when hp.position = '3' then 'M'
                            when hp.position = '4' then 'M'
                            when hp.position = '5' then 'E'
                            when hp.position = '6' then 'E'
                            when hp.position = '7' then 'E'
                            when hp.position = '8' then 'E'
                            when hp.position = '9' then 'E'
                            else 'E'
                       end                                            as hc_position""",
                )
                if self.backend == self.PGSQL:
                    query = query.replace(
                        "<styleKey>",
                        ",'d' || to_char(h.startTime, 'YYMMDD')",
                    )
                    query = query.replace(
                        "<styleKeyGroup>",
                        ",to_char(h.startTime, 'YYMMDD')",
                    )
                elif self.backend == self.SQLITE:
                    query = query.replace(
                        "<styleKey>",
                        ",'d' || substr(strftime('%Y%m%d', h.startTime),3,7)",
                    )
                    query = query.replace(
                        "<styleKeyGroup>",
                        ",substr(strftime('%Y%m%d', h.startTime),3,7)",
                    )
                elif self.backend == self.MYSQL_INNODB:
                    query = query.replace(
                        "<styleKey>",
                        ",date_format(h.startTime, 'd%y%m%d')",
                    )
                    query = query.replace(
                        "<styleKeyGroup>",
                        ",date_format(h.startTime, 'd%y%m%d')",
                    )
            else:
                query = query.replace(
                    "<hc_position>",
                    """,case when hp.position = 'B' then 'B'
                            when hp.position = 'S' then 'S'
                            when hp.position = '0' then 'D'
                            when hp.position = '1' then 'C'
                            when hp.position = '2' then 'M'
                            when hp.position = '3' then 'M'
                            when hp.position = '4' then 'M'
                            when hp.position = '5' then 'E'
                            when hp.position = '6' then 'E'
                            when hp.position = '7' then 'E'
                            when hp.position = '8' then 'E'
                            when hp.position = '9' then 'E'
                            else 'E'
                       end                                            as hc_position""",
                )
                query = query.replace("<styleKey>", ",'A000000' as styleKey")
                query = query.replace("<styleKeyGroup>", ",styleKey")

            if type == "tour":
                query = query.replace("<tourney_insert_clause>", ",tourneyTypeId")
                query = query.replace("<tourney_select_clause>", ",t.tourneyTypeId")
                query = query.replace("<tourney_group_clause>", ",t.tourneyTypeId")
            else:
                query = query.replace("<tourney_insert_clause>", "")
                query = query.replace("<tourney_select_clause>", "")
                query = query.replace("<tourney_group_clause>", "")

            query = query.replace("<hero_where>", "")
            query = query.replace("<hero_join>", "")

        elif table == "CardsCache":
            insert = """CardsCache
                (weekId
                ,monthId
                ,gametypeId
                <tourney_insert_clause>
                ,playerId
                ,startCards"""

            select = """s.weekId
                      ,s.monthId
                      ,h.gametypeId
                      <tourney_select_clause>
                      ,hp.playerId
                      ,hp.startCards"""

            group = """s.weekId
                        ,s.monthId
                        ,h.gametypeId
                        <tourney_group_clause>
                        ,hp.playerId
                        ,hp.startCards"""

            query = query.replace("<insert>", insert)
            query = query.replace("<select>", select)
            query = query.replace("<group>", group)
            query = query.replace("<hero_join>", "")
            query = query.replace(
                "<sessions_join_clause>",
                """INNER JOIN Sessions s ON (s.id = h.sessionId)
                INNER JOIN Players p ON (hp.playerId = p.id)""",
            )
            query = query.replace("<hero_where>", "")

            if type == "tour":
                query = query.replace("<tourney_insert_clause>", ",tourneyTypeId")
                query = query.replace("<tourney_select_clause>", ",t.tourneyTypeId")
                query = query.replace("<tourney_group_clause>", ",t.tourneyTypeId")
            else:
                query = query.replace("<tourney_insert_clause>", "")
                query = query.replace("<tourney_select_clause>", "")
                query = query.replace("<tourney_group_clause>", "")

        elif table == "PositionsCache":
            insert = """PositionsCache
                (weekId
                ,monthId
                ,gametypeId
                <tourney_insert_clause>
                ,playerId
                ,seats
                ,maxPosition
                ,position"""

            select = """s.weekId
                      ,s.monthId
                      ,h.gametypeId
                      <tourney_select_clause>
                      ,hp.playerId
                      ,h.seats
                      ,h.maxPosition
                      ,hp.position"""

            group = """s.weekId
                        ,s.monthId
                        ,h.gametypeId
                        <tourney_group_clause>
                        ,hp.playerId
                        ,h.seats
                        ,h.maxPosition
                        ,hp.position"""

            query = query.replace("<insert>", insert)
            query = query.replace("<select>", select)
            query = query.replace("<group>", group)
            query = query.replace("<hero_join>", "")
            query = query.replace(
                "<sessions_join_clause>",
                """INNER JOIN Sessions s ON (s.id = h.sessionId)
                INNER JOIN Players p ON (hp.playerId = p.id)""",
            )
            query = query.replace("<hero_where>", "")

            if type == "tour":
                query = query.replace("<tourney_insert_clause>", ",tourneyTypeId")
                query = query.replace("<tourney_select_clause>", ",t.tourneyTypeId")
                query = query.replace("<tourney_group_clause>", ",t.tourneyTypeId")
            else:
                query = query.replace("<tourney_insert_clause>", "")
                query = query.replace("<tourney_select_clause>", "")
                query = query.replace("<tourney_group_clause>", "")

        return query

    def rebuild_cache(
        self,
        h_start=None,
        v_start=None,
        table="HudCache",
        ttid=None,
        wmid=None,
    ) -> None:
        """Clears hudcache and rebuilds from the individual handsplayers records."""
        # stime = time()
        # derive list of program owner's player ids
        self.hero = {}  # name of program owner indexed by site id
        self.hero_ids: Any = {
            "dummy": -53,
            "dummy2": -52,
        }  # playerid of owner indexed by site id
        # make sure at least two values in list
        # so that tuple generation creates doesn't use
        # () or (1,) style
        if not h_start and not v_start:
            self.hero_ids = None
        else:
            for site in self.config.get_supported_sites():
                result = self.get_site_id(site)
                if result:
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    for idx, p_id in enumerate(self.get_hero_player_ids(site)):
                        self.hero_ids[f"{site_id}_{idx}"] = int(p_id)

            if not h_start:
                h_start = self.hero_hudstart_def
            if not v_start:
                v_start = self.villain_hudstart_def

        if not ttid and not wmid:
            self.get_cursor().execute(self.sql.query[f"clear{table}"])
            self.commit()

        if not ttid:
            if self.hero_ids is None:
                if wmid:
                    where = "WHERE g.type = 'ring' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
                else:
                    where = "WHERE g.type = 'ring'<hero_where>"
            else:
                where = (
                    "where (((    hp.playerId not in "
                    + str(tuple(self.hero_ids.values()))
                    + "       and h.startTime > '"
                    + v_start
                    + "')"
                    + "   or (    hp.playerId in "
                    + str(tuple(self.hero_ids.values()))
                    + "       and h.startTime > '"
                    + h_start
                    + "'))"
                    + "   AND hp.tourneysPlayersId IS NULL)"
                )
            rebuild_sql_cash = self.sql.query["rebuildCache"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            rebuild_sql_cash = rebuild_sql_cash.replace("<tourney_join_clause>", "")
            rebuild_sql_cash = rebuild_sql_cash.replace("<where_clause>", where)
            rebuild_sql_cash = self.replace_statscache("ring", table, rebuild_sql_cash)
            # print rebuild_sql_cash
            self.get_cursor().execute(rebuild_sql_cash)
            self.commit()
            # print ("Rebuild cache(cash) took %.1f seconds") % (time() - stime,)

        if ttid:
            where = f"WHERE t.tourneyTypeId = {ttid}<hero_where>"
        elif self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'tour' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
            else:
                where = "WHERE g.type = 'tour'<hero_where>"
        else:
            where = (
                "where (((    hp.playerId not in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + v_start
                + "')"
                + "   or (    hp.playerId in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + h_start
                + "'))"
                + "   AND hp.tourneysPlayersId >= 0)"
            )
        rebuild_sql_tourney = self.sql.query["rebuildCache"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        rebuild_sql_tourney = rebuild_sql_tourney.replace(
            "<tourney_join_clause>",
            """INNER JOIN Tourneys t ON (t.id = h.tourneyId)""",
        )
        rebuild_sql_tourney = rebuild_sql_tourney.replace("<where_clause>", where)
        rebuild_sql_tourney = self.replace_statscache(
            "tour",
            table,
            rebuild_sql_tourney,
        )
        # print rebuild_sql_tourney
        self.get_cursor().execute(rebuild_sql_tourney)
        self.commit()
        # print ("Rebuild hudcache took %.1f seconds") % (time() - stime,)

    # end def rebuild_cache

    def update_timezone(self, tz_name) -> None:
        select_W = self.sql.query["select_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        select_M = self.sql.query["select_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_W = self.sql.query["insert_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_M = self.sql.query["insert_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        update_WM_S = self.sql.query["update_WM_S"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        c = self.get_cursor()
        c.execute("SELECT id, sessionStart, weekId wid, monthId mid FROM Sessions")
        sessions = self.fetchallDict(c, ["id", "sessionStart", "wid", "mid"])
        for s in sessions:
            utc_start = pytz.utc.localize(s["sessionStart"])
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime("%z")
            offset = timedelta(
                hours=int(loc_tz[:-2]),
                minutes=int(loc_tz[0] + loc_tz[-2:]),
            )
            local = s["sessionStart"] + offset
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day)
            weekStart = weekdate - timedelta(days=weekdate.weekday())
            wid = self.insertOrUpdate("weeks", c, (weekStart,), select_W, insert_W)
            mid = self.insertOrUpdate("months", c, (monthStart,), select_M, insert_M)
            if wid != s["wid"] or mid != s["mid"]:
                row = [wid, mid, s["id"]]
                c.execute(update_WM_S, row)
                self.wmold.add((s["wid"], s["mid"]))
                self.wmnew.add((wid, mid))
        self.commit()
        self.cleanUpWeeksMonths()

    def get_hero_hudcache_start(self):
        """Fetches earliest stylekey from hudcache for one of hero's player ids."""
        try:
            # derive list of program owner's player ids
            self.hero = {}  # name of program owner indexed by site id
            self.hero_ids = {
                "dummy": -53,
                "dummy2": -52,
            }  # playerid of owner indexed by site id
            # make sure at least two values in list
            # so that tuple generation creates doesn't use
            # () or (1,) style
            for site in self.config.get_supported_sites():
                result = self.get_site_id(site)
                if result:
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    for idx, p_id in enumerate(self.get_hero_player_ids(site)):
                        self.hero_ids[f"{site_id}_{idx}"] = int(p_id)

            q = self.sql.query["get_hero_hudcache_start"].replace(
                "<playerid_list>",
                str(tuple(self.hero_ids.values())),
            )
            c = self.get_cursor()
            c.execute(q)
            tmp = c.fetchone()
            if tmp == (None,):
                return self.hero_hudstart_def
            return "20" + tmp[0][1:3] + "-" + tmp[0][3:5] + "-" + tmp[0][5:7]
        except Exception:  # intentional broad catch: hero hudcache start query/parse best-effort, log only
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            log.exception(f"Error rebuilding hudcache: {sys.exc_info()[1]!s}\n{err}")

    # end def get_hero_hudcache_start

    def analyzeDB(self) -> None:
        """Do whatever the DB can offer to update index/table statistics."""
        stime = time()
        if self.backend in (self.MYSQL_INNODB, self.SQLITE):
            try:
                self.get_cursor().execute(self.sql.query["analyze"])
            except Exception:  # intentional broad catch: analyzeDB (MySQL/SQLite) maintenance best-effort
                log.exception(f"Error during analyze: {sys.exc_info()[1]!s}")
        elif self.backend == self.PGSQL:
            self._pg_set_isolation(0)  # allow analyze to work
            try:
                self.get_cursor().execute(self.sql.query["analyze"])
            except Exception:  # intentional broad catch: analyzeDB (PG) maintenance best-effort
                log.exception(f"Error during analyze: {sys.exc_info()[1]!s}")
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()
        atime = time() - stime
        log.info(f"Analyze took {atime:.1f} seconds")

    # end def analyzeDB

    def vacuumDB(self) -> None:
        """Do whatever the DB can offer to update index/table statistics."""
        stime = time()
        if self.backend in (self.MYSQL_INNODB, self.SQLITE):
            try:
                self.get_cursor().execute(self.sql.query["vacuum"])
            except Exception:  # intentional broad catch: vacuumDB (MySQL/SQLite) maintenance best-effort
                log.exception(f"Error during vacuum: {sys.exc_info()[1]!s}")
        elif self.backend == self.PGSQL:
            self._pg_set_isolation(0)  # allow vacuum to work
            try:
                self.get_cursor().execute(self.sql.query["vacuum"])
            except Exception as e:  # intentional broad catch: vacuumDB (PG) maintenance best-effort
                log.exception(f"Error during vacuum: {e!s}")
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()
        atime = time() - stime
        log.debug(f"Vacuum took {atime:.1f} seconds")

    # end def analyzeDB

    # Start of Hand Writing routines. Idea is to provide a mixture of routines to store Hand data
    # however the calling prog requires. Main aims:
    # - existing static routines from fpdb_simple just modified

    def setThreadId(self, threadid) -> None:
        self.threadId = threadid

    def acquireLock(self, wait=True, retry_time=0.01) -> bool:
        while not self._has_lock:
            cursor = self.get_cursor()
            num = cursor.execute(self.sql.query["switchLockOn"], (True, self.threadId))
            self.commit()
            if self.backend == self.MYSQL_INNODB and num == 0:
                if not wait:
                    return False
                sleep(retry_time)
            else:
                self._has_lock = True
                return True
        return False

    def releaseLock(self) -> None:
        if self._has_lock:
            cursor = self.get_cursor()
            cursor.execute(self.sql.query["switchLockOff"], (False, self.threadId))
            self.commit()
            self._has_lock = False

    def lock_for_insert(self) -> None:
        """Lock tables in MySQL to try to speed inserts up."""
        try:
            self.get_cursor().execute(self.sql.query["lockForInsert"])
        except Exception as e:  # intentional broad catch: lock_for_insert (MySQL) best-effort speed-up
            log.debug(f"Error during lock_for_insert: {e!s}")

    # end def lock_for_insert

    def resetBulkCache(self, reconnect=False) -> None:
        self.siteHandNos: list[Any] = []  # cache of siteHandNo
        self.hbulk: list[Any] = []  # Hands bulk inserts
        self.bbulk: list[Any] = []  # Boards bulk inserts
        self.hpbulk: list[Any] = []  # HandsPlayers bulk inserts
        self.habulk: list[Any] = []  # HandsActions bulk inserts
        self.hcbulk: dict[Any, Any] = {}  # HudCache bulk inserts
        self.dcbulk: dict[Any, Any] = {}  # CardsCache bulk inserts
        self.pcbulk: dict[Any, Any] = {}  # PositionsCache bulk inserts
        self.hsbulk: list[Any] = []  # HandsStove bulk inserts
        self.hsdbulk: list[Any] = []  # HandsShowdown bulk inserts
        self.hcobulk: list[Any] = []  # HandsCashout bulk inserts
        self.panbulk: list[Any] = []  # PlayerAutoNotes bulk upserts
        self.htbulk: list[Any] = []  # HandsPots bulk inserts
        self.tbulk: dict[Any, Any] = {}  # Tourneys bulk updates
        self.s: dict[str, Any] = {"bk": []}  # Sessions bulk updates
        self.sc: dict[Any, Any] = {}  # SessionsCache bulk updates
        self.tc: dict[Any, Any] = {}  # TourneysCache bulk updates
        self.hids: list[Any] = []  # hand ids in order of hand bulk inserts
        # self.tids        = []         # tourney ids in order of hp bulk inserts
        if reconnect:
            self.do_connect(self.config)

    def executemany(self, c, q, values) -> None:
        if self.backend == self.PGSQL and self.import_options["hhBulkPath"] != "":
            # COPY much faster under postgres. Requires superuser privileges
            m = re_insert.match(q)
            if m is None:
                raise FpdbError(f"Unable to derive a COPY statement from query: {q}")
            rand = "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(5))
            bulk_file = os.path.join(
                self.import_options["hhBulkPath"],
                m.group("TABLENAME") + "_" + rand,
            )
            with open(bulk_file, "w", encoding="utf-8", newline="") as csvfile:
                writer = csv.writer(
                    csvfile,
                    delimiter="\t",
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                writer.writerows(w for w in values)
            q_insert = (
                "COPY " + m.group("TABLENAME") + m.group("COLUMNS") + " FROM '" + bulk_file + "' DELIMITER '\t' CSV"
            )
            c.execute(q_insert)
            os.remove(bulk_file)
        else:
            batch_size = 20000  # experiment to find optimal batch_size for your data
            while values:  # repeat until all records in values have been inserted ''
                batch, values = (
                    values[:batch_size],
                    values[batch_size:],
                )  # split values into the current batch and the remaining records
                c.executemany(q, batch)  # insert current batch ''

    def storeHand(self, hdata, doinsert=False, printdata=False) -> None:
        if printdata:
            log.debug("######## Hands ##########")
            import pprint

            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(hdata)
            log.debug("###### End Hands ########")

        # Tablename can have odd charachers
        # hdata["tableName"] = Charset.to_db_utf8(hdata["tableName"])[:50]
        table_name = hdata.get("tableName", "")
        table_name_safe = table_name.encode("utf-8", "replace").decode("utf-8")
        hdata["tableName"] = table_name_safe[:50]

        self.hids.append(hdata["id"])
        self.hbulk.append(
            [
                hdata["tableName"],
                hdata["siteHandNo"],
                hdata["tourneyId"],
                hdata["gametypeId"],
                hdata["sessionId"],
                hdata["fileId"],
                hdata["startTime"].replace(tzinfo=None),
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),  # importtime
                hdata["seats"],
                hdata["heroSeat"],
                hdata["maxPosition"],
                hdata["texture"],
                hdata["playersVpi"],
                hdata["boardcard1"],
                hdata["boardcard2"],
                hdata["boardcard3"],
                hdata["boardcard4"],
                hdata["boardcard5"],
                hdata["runItTwice"],
                hdata["playersAtStreet1"],
                hdata["playersAtStreet2"],
                hdata["playersAtStreet3"],
                hdata["playersAtStreet4"],
                hdata["playersAtShowdown"],
                hdata["street0Raises"],
                hdata["street1Raises"],
                hdata["street2Raises"],
                hdata["street3Raises"],
                hdata["street4Raises"],
                hdata["street0Pot"],
                hdata["street1Pot"],
                hdata["street2Pot"],
                hdata["street3Pot"],
                hdata["street4Pot"],
                hdata["finalPot"],
                hdata.get("bombPot", 0),
            ],
        )

        if doinsert:
            self.appendHandsSessionIds()
            self.updateTourneysSessions()
            q = self.sql.query["store_hand"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.executemany(q, self.hbulk)
            self.commit()

    def storeBoards(self, id, boards, doinsert) -> None:
        if boards:
            for b in boards:
                self.bbulk += [[id, *b]]
        if doinsert and self.bbulk:
            q = self.sql.query["store_boards"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.bbulk)  # c.executemany(q, self.bbulk)

    def updateTourneysSessions(self) -> None:
        if self.tbulk:
            q_update_sessions = self.sql.query["updateTourneysSessions"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            c = self.get_cursor()
            for t, sid in list(self.tbulk.items()):
                c.execute(q_update_sessions, (sid, t))
                self.commit()

    def storeHandsPlayers(self, hid, pids, pdata, doinsert=False, printdata=False) -> None:
        log.info(
            f"Entering storeHandsPlayers: hid={hid}, doinsert={doinsert}, printdata={printdata}",
        )

        if printdata:
            import pprint

            pp = pprint.PrettyPrinter(indent=4)
            log.debug("Printing pdata for debugging:")
            pp.pprint(pdata)

        hpbulk = self.hpbulk
        log.debug(f"Initialized hpbulk with current size: {len(hpbulk)}")

        for p, pvalue in pdata.items():
            log.debug(f"Processing player: {p}")
            try:
                bulk_data = [pvalue[key] for key in HANDS_PLAYERS_KEYS]
                bulk_data.append(pids[p])
                bulk_data.append(hid)
                bulk_data.reverse()
                hpbulk.append(bulk_data)
                log.debug(f"Appended data for player {p}: {bulk_data}")
            except KeyError as e:
                log.exception(f"Key error when processing player {p}. Missing key: {e}")
                raise

        log.debug(f"Final hpbulk size after processing: {len(hpbulk)}")

        if doinsert:
            log.info("Performing database insertion for hands_players data.")
            try:
                q = self.sql.query["store_hands_players"]
                q = q.replace("%s", self.sql.query["placeholder"])
                c = self.get_cursor(True)
                self.executemany(c, q, self.hpbulk)
                log.info(
                    f"Successfully inserted {len(self.hpbulk)} rows into hands_players.",
                )
            except Exception as e:  # intentional broad catch: hands_players bulk insert logs then re-raises
                log.exception(f"Error during database insertion in storeHandsPlayers: {e}")
                raise
        else:
            log.info("Skipping database insertion as doinsert=False.")

        log.info("Exiting storeHandsPlayers.")

    def storeHandsPots(self, tdata, doinsert) -> None:
        self.htbulk += tdata
        if doinsert and self.htbulk:
            q = self.sql.query["store_hands_pots"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.htbulk)  # c.executemany(q, self.hsbulk)

    def storeHandsActions(self, hid, pids, adata, doinsert=False, printdata=False) -> None:
        # print "DEBUG: %s %s %s" %(hid, pids, adata)

        # This can be used to generate test data. Currently unused
        # if printdata:
        #    import pprint
        #    pp = pprint.PrettyPrinter(indent=4)
        #    pp.pprint(adata)

        for a in adata:
            self.habulk.append(
                (
                    hid,
                    pids[adata[a]["player"]],
                    adata[a]["street"],
                    adata[a]["actionNo"],
                    adata[a]["streetActionNo"],
                    adata[a]["actionId"],
                    adata[a]["amount"],
                    adata[a]["raiseTo"],
                    adata[a]["amountCalled"],
                    adata[a]["numDiscarded"],
                    adata[a]["cardsDiscarded"],
                    adata[a]["allIn"],
                ),
            )

        if doinsert:
            q = self.sql.query["store_hands_actions"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.habulk)  # c.executemany(q, self.habulk)

    def storeHandsStove(self, sdata, doinsert) -> None:
        self.hsbulk += sdata
        if doinsert and self.hsbulk:
            q = self.sql.query["store_hands_stove"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hsbulk)  # c.executemany(q, self.hsbulk)

    def storeHandsShowdown(self, sdata, doinsert) -> None:
        """Persist parsed showdown combinations (and winning cards) per player."""
        self.hsdbulk += sdata
        if doinsert and self.hsdbulk:
            q = self.sql.query["store_hands_showdown"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hsdbulk)

    def get_hands_showdown(self, hand_id) -> dict:
        """Return {player_name: (combo, cards)} for a hand, or {} if none/absent.

        Tolerates databases created before the HandsShowdown table existed.
        """
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_showdown"], (hand_id,))
            for name, combo, cards in c.fetchall():
                result[name] = (combo, cards)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no showdown info.
            return {}
        return result

    def storeHandsCashout(self, sdata, doinsert) -> None:
        """Persist per-player cashout amounts/fees."""
        self.hcobulk += sdata
        if doinsert and self.hcobulk:
            q = self.sql.query["store_hands_cashout"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hcobulk)

    def get_hands_cashout(self, hand_id) -> dict:
        """Return {player_name: (amount, fee)} for a hand, or {} if none/absent."""
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_cashout"], (hand_id,))
            for name, amount, fee in c.fetchall():
                result[name] = (amount, fee)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no cashout info.
            return {}
        return result

















    def get_id(self, file):
        q = self.sql.query["get_id"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, (file,))
        id = c.fetchone()
        if not id:
            return 0
        return id[0]

    def storeFile(self, fdata):
        q = self.sql.query["store_file"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, fdata)
        return self.get_last_insert_id(c)

    def repair_sequence(self, table: str) -> None:
        """Synchronize a backend identity sequence with the stored row ids."""
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).repair_sequence(self, table)

    def repair_sequences(self) -> None:
        """Synchronize every backend identity sequence after a data migration."""
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).repair_sequences(self)

    def updateFile(self, fdata) -> None:
        q = self.sql.query["update_file"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, fdata)

    def _hero_aliases(self, site_name):
        """Resolve the configured hero aliases for a site, defensively.

        Uses ``Config.get_hero_aliases`` when available, otherwise falls back to
        the single ``screen_name``. Tolerates fake/minimal config objects used in
        tests.
        """
        cfg = self.config
        getter = getattr(cfg, "get_hero_aliases", None)
        if callable(getter):
            return list(getter(site_name) or [])
        site = getattr(cfg, "supported_sites", {}).get(site_name)
        if site is None:
            return []
        screen_name = getattr(site, "screen_name", "")
        return [screen_name] if screen_name else []

    def _resolve_alias_ids(self, site_name, aliases):
        """Resolve exact ``(siteId, name)`` matches for a list of aliases."""
        site_res = self.get_site_id(site_name)
        if not site_res:
            return set()
        site_id = site_res[0][0]
        aliases = [a for a in aliases if a]
        if not aliases:
            return set()
        ph = self.sql.query["placeholder"]
        marks = ",".join(["%s"] * len(aliases))
        q = f"SELECT id FROM Players WHERE siteId=%s AND name IN ({marks})".replace("%s", ph)
        c = self.get_cursor()
        c.execute(q, tuple([site_id, *aliases]))
        return {int(r[0]) for r in c.fetchall()}

    def get_hero_player_ids_for_profile(self, profile):
        """Return hero playerIds for a multiroom :class:`HeroProfile`.

        ``profile`` may be a ``HeroProfile`` instance or a profile name. Each
        ``(site, alias)`` link is matched **exactly** on ``(siteId, name)``;
        results are deduplicated across rooms. Returns ``[]`` if unresolved.
        """
        if isinstance(profile, str):
            getter = getattr(self.config, "get_hero_profiles", None)
            profile = getter().get(profile) if callable(getter) else None
        if profile is None:
            return []
        ids = set()
        for site_name, aliases in profile.aliases_by_site().items():
            ids.update(self._resolve_alias_ids(site_name, aliases))
        return sorted(ids)

    def get_hero_player_ids(self, site_name=None, profile=None):
        """Return every hero playerId for a site (multi-alias aware).

        When ``profile`` is given (a ``HeroProfile`` or its name), resolve the
        multiroom profile across all its rooms instead of a single site.

        Per-site resolution order:
          1. Configured aliases matched **exactly** on ``(siteId, name)`` — no
             cross-site fuzzy fallback, to avoid mis-attributing look-alike names.
          2. If none resolve, fall back to the ``Players.hero`` flag set during
             import (so old imports work without alias config).

        Results are deduplicated. Returns ``[]`` when the site is unknown.
        """
        if profile is not None:
            return self.get_hero_player_ids_for_profile(profile)

        site_res = self.get_site_id(site_name)
        if not site_res:
            return []
        site_id = site_res[0][0]

        ids = self._resolve_alias_ids(site_name, self._hero_aliases(site_name))

        if not ids:
            ph = self.sql.query["placeholder"]
            q = "SELECT id FROM Players WHERE siteId=%s AND hero=%s".replace("%s", ph)
            c = self.get_cursor()
            c.execute(q, (site_id, True))
            ids.update(int(r[0]) for r in c.fetchall())

        return sorted(ids)

    def getHeroIds(self, pids, sitename):
        # Grab playerIds using hero names in HUD_Config.xml
        try:
            # derive list of program owner's player ids
            hero_ids = []
            # make sure at least two values in list
            # so that tuple generation creates doesn't use
            # () or (1,) style
            for site in self.config.get_supported_sites():
                aliases = set(self._hero_aliases(site))
                for n, v in list(pids.items()):
                    if sitename == site and n in aliases:
                        hero_ids.append(v)

        except Exception:  # intentional broad catch: hero-id resolution over config/pids best-effort, log only
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            log.exception("Error acquiring hero ids")
            log.exception(f"traceback: {err}")
        return hero_ids

    def fetchallDict(self, cursor, desc):
        data = cursor.fetchall()
        if not data:
            return []
        results: list[dict[Any, Any]] = [{} for _ in data]
        for i in range(len(data)):
            for n in range(len(desc)):
                results[i][desc[n]] = data[i][n]
        return results

    def nextHandId(self):
        c = self.get_cursor(True)
        c.execute("SELECT max(id) FROM Hands")
        id = c.fetchone()[0]
        if not id:
            id = 0
        id += self.hand_inc
        return id

    def isDuplicate(self, siteId, siteHandNo, heroSeat, publicDB) -> bool:
        q = self.sql.query["isAlreadyInDB"].replace("%s", self.sql.query["placeholder"])
        key: tuple[Any, ...]
        if publicDB:
            key = (siteHandNo, siteId, heroSeat)
            q = q.replace("<heroSeat>", " AND heroSeat=%s").replace(
                "%s",
                self.sql.query["placeholder"],
            )
        else:
            key = (siteHandNo, siteId)
            q = q.replace("<heroSeat>", "")
        if key in self.siteHandNos:
            return True
        c = self.get_cursor()
        c.execute(q, key)
        result = c.fetchall()
        if len(result) > 0:
            return True
        self.siteHandNos.append(key)
        return False

    def getSqlPlayerIDs(self, pnames, siteid, hero):
        result = {}
        if self.pcache is None:
            self.pcache = LambdaDict(
                lambda key: self.insertPlayer(key[0], key[1], key[2]),
            )

        for player in pnames:
            result[player] = self.pcache[(player, siteid, player == hero)]
            # NOTE: Using the LambdaDict does the same thing as:
            # if player in self.pcache:
            #    #print "DEBUG: cachehit"
            #    pass
            # else:
            #    self.pcache[player] = self.insertPlayer(player, siteid)
            # result[player] = self.pcache[player]

        return result

    def insertPlayer(self, name, site_id, hero):
        insert_player = "INSERT INTO Players (name, siteId, hero, chars) VALUES (%s, %s, %s, %s)"
        insert_player = insert_player.replace("%s", self.sql.query["placeholder"])
        _name = name[:32] if name else " "
        if not _name:
            _name = " "
        if re_char.match(_name[0]):
            char = "123"
        elif len(_name) == 1 or re_char.match(_name[1]):
            char = _name[0] + "1"
        else:
            char = _name[:2]

        key = (_name, site_id, hero, char.upper())

        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            # LAST_INSERT_ID(id) makes connection.insert_id() return the
            # existing row id as well as the id of a newly inserted player.
            upsert_player = insert_player + " ON DUPLICATE KEY UPDATE hero=hero OR VALUES(hero), id=LAST_INSERT_ID(id)"
            c.execute(upsert_player, key)
            return self.get_last_insert_id(c)

        q = "SELECT id, name, hero FROM Players WHERE name=%s and siteid=%s"
        q = q.replace("%s", self.sql.query["placeholder"])
        return self.insertOrUpdate("players", c, key, q, insert_player)

    def insertOrUpdate(self, type, cursor, key, select, insert):
        if type == "players":
            cursor.execute(select, key[:2])
        else:
            cursor.execute(select, key)
        tmp = cursor.fetchone()
        if tmp is None:
            cursor.execute(insert, key)
            result = self.get_last_insert_id(cursor)
        else:
            result = tmp[0]
            if type == "players" and not tmp[2] and key[2]:
                q = "UPDATE Players SET hero=%s WHERE name=%s and siteid=%s"
                q = q.replace("%s", self.sql.query["placeholder"])
                cursor.execute(q, (key[2], key[0], key[1]))
        return result

    def getSqlGameTypeId(self, siteid, game, printdata=False):
        if self.gtcache is None:
            self.gtcache = LambdaDict(lambda key: self.insertGameTypes(key[0], key[1]))

        self.gtprintdata = printdata
        hilo = Card.games[game["category"]][2]

        gtinfo = (
            siteid,
            game["type"],
            game["category"],
            game["limitType"],
            game["currency"],
            game["mix"],
            int(Decimal(game["sb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            game["maxSeats"],
            int(game["ante"] * 100),
            game["buyinType"],
            game["fast"],
            game["newToGame"],
            game["homeGame"],
            game["split"],
        )

        gtinsert = (
            siteid,
            game["currency"],
            game["type"],
            game["base"],
            game["category"],
            game["limitType"],
            hilo,
            game["mix"],
            int(Decimal(game["sb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            int(Decimal(game["bb"]) * 200),
            game["maxSeats"],
            int(game["ante"] * 100),
            game["buyinType"],
            game["fast"],
            game["newToGame"],
            game["homeGame"],
            game["split"],
        )

        return self.gtcache[(gtinfo, gtinsert)]
        # NOTE: Using the LambdaDict does the same thing as:
        # if player in self.pcache:
        #    #print "DEBUG: cachehit"
        #    pass
        # else:
        #    self.pcache[player] = self.insertPlayer(player, siteid)
        # result[player] = self.pcache[player]

    def insertGameTypes(self, gtinfo, gtinsert):
        result = None
        c = self.get_cursor()
        q = self.sql.query["getGametypeNL"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, gtinfo)
        tmp = c.fetchone()
        if tmp is None:
            if self.gtprintdata:
                log.debug("######## Gametype ##########")
                import pprint

                pp = pprint.PrettyPrinter(indent=4)
                pp.pprint(gtinsert)
                log.debug("###### End Gametype ########")

            c.execute(
                self.sql.query["insertGameTypes"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                gtinsert,
            )
            result = self.get_last_insert_id(c)
        else:
            result = tmp[0]
        return result


    # end def getTourneyInfo


    # end def getTourneyTypesIds





    def cleanUpWeeksMonths(self) -> None:
        if self.cacheSessions and self.wmold:
            selectWeekId = self.sql.query["selectSessionWithWeekId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            selectMonthId = self.sql.query["selectSessionWithMonthId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            deleteWeekId = self.sql.query["deleteWeekId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            deleteMonthId = self.sql.query["deleteMonthId"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor = self.get_cursor()
            weeks, months, wmids = set(), set(), set()
            for wid, mid in self.wmold:
                for t in ("CardsCache", "PositionsCache"):
                    statement = f"clear{t}WeeksMonths"
                    clear = self.sql.query[statement].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    )
                    cursor.execute(clear, (wid, mid))
                self.commit()
                weeks.add(wid)
                months.add(mid)

            for wid in weeks:
                cursor.execute(selectWeekId, (wid,))
                result = cursor.fetchone()
                if not result:
                    cursor.execute(deleteWeekId, (wid,))
                    self.commit()

            for mid in months:
                cursor.execute(selectMonthId, (mid,))
                result = cursor.fetchone()
                if not result:
                    cursor.execute(deleteMonthId, (mid,))
                    self.commit()

            for wid, mid in self.wmnew:
                for t in ("CardsCache", "PositionsCache"):
                    statement = f"clear{t}WeeksMonths"
                    clear = self.sql.query[statement].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    )
                    cursor.execute(clear, (wid, mid))
                self.commit()

            if self.wmold:
                for t in ("CardsCache", "PositionsCache"):
                    statement = f"fetchNew{t}WeeksMonths"
                    fetch = self.sql.query[statement].replace(
                        "%s",
                        self.sql.query["placeholder"],
                    )
                    cursor.execute(fetch)
                    for wid, mid in cursor.fetchall():
                        wmids.add((wid, mid))
                for wmid in wmids:
                    for t in ("CardsCache", "PositionsCache"):
                        self.rebuild_cache(None, None, t, None, wmid)
            self.commit()

    def rebuild_caches(self) -> None:
        tables: tuple[str, ...] | set[str]
        if self.callHud and self.cacheSessions:
            tables = ("HudCache", "CardsCache", "PositionsCache")
        elif self.callHud:
            tables = ("HudCache",)
        elif self.cacheSessions:
            tables = ("CardsCache", "PositionsCache")
        else:
            tables = set()
        for t in tables:
            self.rebuild_cache(None, None, t)

    def resetClean(self) -> None:
        self.ttold = set()
        self.ttnew = set()
        self.wmold = set()
        self.wmnew = set()

    def cleanRequired(self) -> bool:
        return bool(self.ttold or self.wmold)



    # end def createOrUpdateTourney


    # end def getTourneyPlayerInfo





    def cleanup_connections(self) -> None:
        """Clean up database connections to prevent timeouts and pool exhaustion."""
        cursor = getattr(self, "cursor", None)
        if cursor:
            with contextlib.suppress(Exception):
                cursor.close()
                log.debug("Database cursor closed.")
            self.cursor = None

        try:
            if hasattr(self, "connection") and self.connection:
                self.connection.close()
                self.connection = None
                self.__connected = False
                log.debug("Database connection closed.")
        except Exception as e:  # intentional broad catch: connection cleanup best-effort, log warning
            log.warning(f"Error closing connection: {e}")

    def __del__(self) -> None:
        """Ensure connections are cleaned up when Database object is destroyed."""
        try:
            self.cleanup_connections()
        except Exception:  # intentional broad catch: destructor cleanup ignores errors
            pass  # Ignore errors during cleanup in destructor


# end class Database


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB Database utility")
    parser.add_argument("--test-connection", action="store_true", help="Test database connection")
    parser.add_argument("--rebuild-indexes", action="store_true", help="Drop and recreate all database indexes")
    parser.add_argument("--vacuum", action="store_true", help="Reclaim space and optimize database storage")
    parser.add_argument("--show-stats", action="store_true", help="Show statistics for last hand")
    parser.add_argument("--show-info", action="store_true", help="Show database information")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    Configuration.set_logfile("fpdb-log.txt")

    try:
        c = Configuration.Config()
        sql = SQL.Sql(db_server="sqlite")
        db_connection = Database(c)
    except Exception as e:  # intentional broad catch: CLI top-level DB connect boundary
        print(f"Error connecting to database: {e}")
        return 1

    if args.test_connection:
        print("Database connection successful ✓")
        print(f"Backend: {db_connection.backend}")
        print(f"Connection: {db_connection.connection}")

    if args.show_info:
        print("\n=== Database Information ===")
        print(f"Backend type: {db_connection.backend}")
        print(f"Database name: {db_connection.database}")
        print(f"Host: {db_connection.host}")

    if args.rebuild_indexes:
        print("Rebuilding indexes and foreign keys...")
        db_connection.rebuild_indexes()
        print("Index rebuild complete ✓")

    if args.vacuum:
        print("Vacuuming database...")
        db_connection.vacuumDB()
        print("Database vacuum complete ✓")

    if args.show_stats:
        try:
            h = db_connection.get_last_hand()
            if h:
                print(f"\n=== Statistics for Hand {h} ===")
                t0 = time()
                stat_dict = db_connection.get_stats_from_hand(h, "ring")
                t1 = time()

                for p in sorted(stat_dict.keys()):
                    print(f"  {p}: {stat_dict[p]}")

                print(f"\nQuery took: {t1 - t0:4.3f} seconds")

                cards = db_connection.get_cards("1")
                if cards:
                    print(f"Cards for player 1: {cards}")
            else:
                print("No hands found in database")
        except Exception as e:  # intentional broad catch: CLI top-level show-stats boundary
            print(f"Error retrieving statistics: {e}")

    if args.interactive:
        print("Running original interactive test...")
        log.debug(f"database connection object = {db_connection.connection}")
        db_connection.dropAllIndexes()
        db_connection.createAllIndexes()

        h = db_connection.get_last_hand()
        log.debug(f"last hand = {h}")

        hero = db_connection.get_player_id(c, "PokerStars", "nutOmatic")
        if hero:
            log.debug(f"nutOmatic player_id {hero}")

        if db_connection.backend == 4:
            c = db_connection.get_cursor()
            c.execute("explain query plan " + sql.query["get_table_name"], (h,))
            for row in c.fetchall():
                log.debug(f"Query plan: {row}")

        t0 = time()
        stat_dict = db_connection.get_stats_from_hand(h, "ring")
        t1 = time()
        for p in list(stat_dict.keys()):
            log.debug(f"{p}  {stat_dict[p]}")

        log.debug(f"cards = {db_connection.get_cards('1')}")
        db_connection.close_connection

        log.debug(f"get_stats took: {t1 - t0:4.3f} seconds")

        print("Press ENTER to continue...")
        sys.stdin.readline()

    return 0


if __name__ == "__main__":
    sys.exit(main())
