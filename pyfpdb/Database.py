#!/usr/bin/env python
# -*- coding: utf-8 -*-
# #    Copyright 2008-2011, Ray E. Barker
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
"""Database.py

Create and manage the database objects.
"""

from __future__ import print_function
from __future__ import division
import future

from past.utils import old_div

# #import L10n
# #_ = L10n.get_translation()

########################################################################

# TODO:  - rebuild indexes / vacuum option
#        - check speed of get_stats_from_hand() - add log info
#        - check size of db, seems big? (mysql)
######### investigate size of mysql db (200K for just 7K hands? 2GB for 140K hands?)

# postmaster -D /var/lib/pgsql/data

#    Standard Library modules
import os
import sys
import traceback
from datetime import datetime, date, time, timedelta, timezone
from time import time, strftime, sleep
from decimal_wrapper import Decimal
import string
import re


import math
import pytz
import csv
import logging
import random


re_char = re.compile('[^a-zA-Z]')
re_insert = re.compile(r"insert\sinto\s(?P<TABLENAME>[A-Za-z]+)\s(?P<COLUMNS>\(.+?\))\s+values", re.DOTALL)

#    FreePokerTools modules
import SQL
import Card
import Charset
from Exceptions import *
import Configuration

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("db")

#    Other library modules
try:
    import sqlalchemy.pool as pool
    use_pool = True
except ImportError:
    log.info(("Not using sqlalchemy connection pool."))
    use_pool = False

try:
    from numpy import var
    use_numpy = True
except ImportError:
    log.info(("Not using numpy to define variance in sqlite."))
    use_numpy = False


DB_VERSION = 216

# Variance created as sqlite has a bunch of undefined aggregate functions.


class VARIANCE(object):
    def __init__(self):
        """
        Initializes an instance of the VARIANCE class.
        """
        self.store = []       # list to store values for calculating variance

    def step(self, value):
        """
        Adds a value to the list of values.
        """
        self.store.append(value)

    def finalize(self):
        """
        Calculates the variance of the values in the list.
        """
        return float(var(self.store))

class sqlitemath(object):
    def mod(self, a, b):
        """
        Returns the remainder of dividing a by b.
        """
        return a % b

    
    
def adapt_decimal(d):
    """
    Converts a decimal to a string representation.

    Args:
        d (decimal): The decimal to be converted.

    Returns:
        str: The string representation of the decimal.
    """
    return str(d)  # convert the decimal to a string


def convert_decimal(s):
    """
    Convert a string representation of a decimal number to a Decimal object.

    Args:
        s (str): A string representation of a decimal number.

    Returns:
        decimal.Decimal: A Decimal object representing the input string.

    Raises:
        UnicodeDecodeError: If the input string cannot be decoded.
    """
    # Print debug information
    print('convertvalue')
    print(s)

    # Decode input string
    s = s.decode()

    # Return Decimal object
    return Decimal(s)

    
    
# These are for appendStats. Insert new stats at the right place, because
# SQL needs strict order.
# Keys used to index into player data in storeHandsPlayers.
HANDS_PLAYERS_KEYS = [
    'startCash',
    'effStack',
    'startBounty',
    'endBounty',
    'seatNo',
    'sitout',
    'card1',
    'card2',
    'card3',
    'card4',
    'card5',
    'card6',
    'card7',
    'card8',
    'card9',
    'card10',
    'card11',
    'card12',
    'card13',
    'card14',
    'card15',
    'card16',
    'card17',
    'card18',
    'card19',
    'card20',
    'common',
    'committed',
    'winnings',
    'rake',
    'rakeDealt',
    'rakeContributed',
    'rakeWeighted',
    'totalProfit',
    'allInEV',
    'street0VPIChance',
    'street0VPI',
    'street1Seen',
    'street2Seen',
    'street3Seen',
    'street4Seen',
    'sawShowdown',
    'showed',
    'street0AllIn',
    'street1AllIn',
    'street2AllIn',
    'street3AllIn',
    'street4AllIn',
    'wentAllIn',
    'street0AggrChance',
    'street0Aggr',
    'street1Aggr',
    'street2Aggr',
    'street3Aggr',
    'street4Aggr',
    'street1CBChance',
    'street2CBChance',
    'street3CBChance',
    'street4CBChance',
    'street1CBDone',
    'street2CBDone',
    'street3CBDone',
    'street4CBDone',
    'wonWhenSeenStreet1',
    'wonWhenSeenStreet2',
    'wonWhenSeenStreet3',
    'wonWhenSeenStreet4',
    'wonAtSD',
    'position',
    'street0InPosition',
    'street1InPosition',
    'street2InPosition',
    'street3InPosition',
    'street4InPosition',
    'street0FirstToAct',
    'street1FirstToAct',
    'street2FirstToAct',
    'street3FirstToAct',
    'street4FirstToAct',
    'tourneysPlayersId',
    'startCards',
    'street0CalledRaiseChance',
    'street0CalledRaiseDone',
    'street0_2BChance',
    'street0_2BDone',
    'street0_3BChance',
    'street0_3BDone',
    'street0_4BChance',
    'street0_4BDone',
    'street0_C4BChance',
    'street0_C4BDone',
    'street0_FoldTo2BChance',
    'street0_FoldTo2BDone',
    'street0_FoldTo3BChance',
    'street0_FoldTo3BDone',
    'street0_FoldTo4BChance',
    'street0_FoldTo4BDone',
    'street0_SqueezeChance',
    'street0_SqueezeDone',
    'raiseToStealChance',
    'raiseToStealDone',
    'stealChance',
    'stealDone',
    'success_Steal',
    'otherRaisedStreet0',
    'otherRaisedStreet1',
    'otherRaisedStreet2',
    'otherRaisedStreet3',
    'otherRaisedStreet4',
    'foldToOtherRaisedStreet0',
    'foldToOtherRaisedStreet1',
    'foldToOtherRaisedStreet2',
    'foldToOtherRaisedStreet3',
    'foldToOtherRaisedStreet4',
    'raiseFirstInChance',
    'raisedFirstIn',
    'foldBbToStealChance',
    'foldedBbToSteal',
    'foldSbToStealChance',
    'foldedSbToSteal',
    'foldToStreet1CBChance',
    'foldToStreet1CBDone',
    'foldToStreet2CBChance',
    'foldToStreet2CBDone',
    'foldToStreet3CBChance',
    'foldToStreet3CBDone',
    'foldToStreet4CBChance',
    'foldToStreet4CBDone',
    'street1CheckCallRaiseChance',
    'street1CheckCallDone',
    'street1CheckRaiseDone',
    'street2CheckCallRaiseChance',
    'street2CheckCallDone',
    'street2CheckRaiseDone',
    'street3CheckCallRaiseChance',
    'street3CheckCallDone',
    'street3CheckRaiseDone',
    'street4CheckCallRaiseChance',
    'street4CheckCallDone',
    'street4CheckRaiseDone',
    'street0Calls',
    'street1Calls',
    'street2Calls',
    'street3Calls',
    'street4Calls',
    'street0Bets',
    'street1Bets',
    'street2Bets',
    'street3Bets',
    'street4Bets',
    'street0Raises',
    'street1Raises',
    'street2Raises',
    'street3Raises',
    'street4Raises',
    'street1Discards',
    'street2Discards',
    'street3Discards',
    'handString'
]

# Just like STATS_KEYS, this lets us efficiently add data at the
# "beginning" later.
HANDS_PLAYERS_KEYS.reverse()


CACHE_KEYS = [
    'n',
    'street0VPIChance',
    'street0VPI',
    'street0AggrChance',
    'street0Aggr',
    'street0CalledRaiseChance',
    'street0CalledRaiseDone',
    'street0_2BChance',
    'street0_2BDone',
    'street0_3BChance',
    'street0_3BDone',
    'street0_4BChance',
    'street0_4BDone',
    'street0_C4BChance',
    'street0_C4BDone',
    'street0_FoldTo2BChance',
    'street0_FoldTo2BDone',
    'street0_FoldTo3BChance',
    'street0_FoldTo3BDone',
    'street0_FoldTo4BChance',
    'street0_FoldTo4BDone',
    'street0_SqueezeChance',
    'street0_SqueezeDone',
    'raiseToStealChance',
    'raiseToStealDone',
    'stealChance',
    'stealDone',
    'success_Steal',
    'street1Seen',
    'street2Seen',
    'street3Seen',
    'street4Seen',
    'sawShowdown',
    'street1Aggr',
    'street2Aggr',
    'street3Aggr',
    'street4Aggr',
    'otherRaisedStreet0',
    'otherRaisedStreet1',
    'otherRaisedStreet2',
    'otherRaisedStreet3',
    'otherRaisedStreet4',
    'foldToOtherRaisedStreet0',
    'foldToOtherRaisedStreet1',
    'foldToOtherRaisedStreet2',
    'foldToOtherRaisedStreet3',
    'foldToOtherRaisedStreet4',
    'wonWhenSeenStreet1',
    'wonWhenSeenStreet2',
    'wonWhenSeenStreet3',
    'wonWhenSeenStreet4',
    'wonAtSD',
    'raiseFirstInChance',
    'raisedFirstIn',
    'foldBbToStealChance',
    'foldedBbToSteal',
    'foldSbToStealChance',
    'foldedSbToSteal',
    'street1CBChance',
    'street1CBDone',
    'street2CBChance',
    'street2CBDone',
    'street3CBChance',
    'street3CBDone',
    'street4CBChance',
    'street4CBDone',
    'foldToStreet1CBChance',
    'foldToStreet1CBDone',
    'foldToStreet2CBChance',
    'foldToStreet2CBDone',
    'foldToStreet3CBChance',
    'foldToStreet3CBDone',
    'foldToStreet4CBChance',
    'foldToStreet4CBDone',
    'common',
    'committed',
    'winnings',
    'rake',
    'rakeDealt',
    'rakeContributed',
    'rakeWeighted',
    'totalProfit',
    'allInEV',
    'showdownWinnings',
    'nonShowdownWinnings',
    'street1CheckCallRaiseChance',
    'street1CheckCallDone',
    'street1CheckRaiseDone',
    'street2CheckCallRaiseChance',
    'street2CheckCallDone',
    'street2CheckRaiseDone',
    'street3CheckCallRaiseChance',
    'street3CheckCallDone',
    'street3CheckRaiseDone',
    'street4CheckCallRaiseChance',
    'street4CheckCallDone',
    'street4CheckRaiseDone',
    'street0Calls',
    'street1Calls',
    'street2Calls',
    'street3Calls',
    'street4Calls',
    'street0Bets',
    'street1Bets',
    'street2Bets',
    'street3Bets',
    'street4Bets',
    'street0Raises',
    'street1Raises',
    'street2Raises',
    'street3Raises',
    'street4Raises',
    'street1Discards',
    'street2Discards',
    'street3Discards'
    ]


class Database(object):

    MYSQL_INNODB = 2
    PGSQL = 3
    SQLITE = 4

    hero_hudstart_def = '1999-12-31'      # default for length of Hero's stats in HUD
    villain_hudstart_def = '1999-12-31'   # default for length of Villain's stats in HUD

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
                [ ] # no db with index 0
              , [ ] # no db with index 1
              , [ # indexes for mysql (list index 2) (foreign keys not here, in next data structure)
                #  {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
                #  {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
                #, {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
                ]
              , [ # indexes for postgres (list index 3)
                  {'tab':'Gametypes',       'col':'siteId',            'drop':0}
                , {'tab':'Hands',           'col':'tourneyId',         'drop':0} # mct 22/3/09
                , {'tab':'Hands',           'col':'gametypeId',        'drop':0} # mct 22/3/09
                , {'tab':'Hands',           'col':'sessionId',         'drop':0} # mct 22/3/09
                , {'tab':'Hands',           'col':'fileId',            'drop':0} # mct 22/3/09
                #, {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
                , {'tab':'HandsActions',    'col':'handId',            'drop':1}
                , {'tab':'HandsActions',    'col':'playerId',          'drop':1}
                , {'tab':'HandsActions',    'col':'actionId',          'drop':1}
                , {'tab':'HandsStove',      'col':'handId',            'drop':1}
                , {'tab':'HandsStove',      'col':'playerId',          'drop':1}
                , {'tab':'HandsStove',      'col':'hiLo',              'drop':1}
                , {'tab':'HandsPots',       'col':'handId',            'drop':1}
                , {'tab':'HandsPots',       'col':'playerId',          'drop':1}
                , {'tab':'Boards',          'col':'handId',            'drop':1}
                , {'tab':'HandsPlayers',    'col':'handId',            'drop':1}
                , {'tab':'HandsPlayers',    'col':'playerId',          'drop':1}
                , {'tab':'HandsPlayers',    'col':'tourneysPlayersId', 'drop':0}
                , {'tab':'HandsPlayers',    'col':'startCards',        'drop':1}
                , {'tab':'HudCache',        'col':'gametypeId',        'drop':1}
                , {'tab':'HudCache',        'col':'playerId',          'drop':0}
                , {'tab':'HudCache',        'col':'tourneyTypeId',     'drop':0}
                , {'tab':'Sessions',        'col':'weekId',            'drop':1}
                , {'tab':'Sessions',        'col':'monthId',           'drop':1}
                , {'tab':'SessionsCache',   'col':'sessionId',         'drop':1}
                , {'tab':'SessionsCache',   'col':'gametypeId',        'drop':1}
                , {'tab':'SessionsCache',   'col':'playerId',          'drop':0}
                , {'tab':'TourneysCache',   'col':'sessionId',         'drop':1}
                , {'tab':'TourneysCache',   'col':'tourneyId',         'drop':1}
                , {'tab':'TourneysCache',   'col':'playerId',          'drop':0}
                , {'tab':'Players',         'col':'siteId',            'drop':1}
                #, {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
                , {'tab':'Tourneys',        'col':'tourneyTypeId',     'drop':1}
                , {'tab':'Tourneys',        'col':'sessionId',         'drop':1}
                #, {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
                , {'tab':'TourneysPlayers', 'col':'playerId',          'drop':0}
                #, {'tab':'TourneysPlayers', 'col':'tourneyId',         'drop':0}  unique indexes not dropped
                , {'tab':'TourneyTypes',    'col':'siteId',            'drop':0}
                , {'tab':'Backings',        'col':'tourneysPlayersId', 'drop':0}
                , {'tab':'Backings',        'col':'playerId',          'drop':0}
                , {'tab':'RawHands',        'col':'id',                'drop':0}
                , {'tab':'RawTourneys',     'col':'id',                'drop':0}
                ]
              , [ # indexes for sqlite (list index 4)
                  {'tab':'Hands',           'col':'tourneyId',         'drop':0}
                , {'tab':'Hands',           'col':'gametypeId',        'drop':0}
                , {'tab':'Hands',           'col':'sessionId',         'drop':0}
                , {'tab':'Hands',           'col':'fileId',            'drop':0}
                , {'tab':'Boards',          'col':'handId',            'drop':0}
                , {'tab':'Gametypes',       'col':'siteId',            'drop':0}
                , {'tab':'HandsPlayers',    'col':'handId',            'drop':0}
                , {'tab':'HandsPlayers',    'col':'playerId',          'drop':0}
                , {'tab':'HandsPlayers',    'col':'tourneysPlayersId', 'drop':0}
                , {'tab':'HandsActions',    'col':'handId',            'drop':0}
                , {'tab':'HandsActions',    'col':'playerId',          'drop':0}
                , {'tab':'HandsActions',    'col':'actionId',          'drop':1}
                , {'tab':'HandsStove',      'col':'handId',            'drop':0}
                , {'tab':'HandsStove',      'col':'playerId',          'drop':0}
                , {'tab':'HandsPots',       'col':'handId',            'drop':0}
                , {'tab':'HandsPots',       'col':'playerId',          'drop':0}
                , {'tab':'HudCache',        'col':'gametypeId',        'drop':1}
                , {'tab':'HudCache',        'col':'playerId',          'drop':0}
                , {'tab':'HudCache',        'col':'tourneyTypeId',     'drop':0}
                , {'tab':'Sessions',        'col':'weekId',            'drop':1}
                , {'tab':'Sessions',        'col':'monthId',           'drop':1}
                , {'tab':'SessionsCache',   'col':'sessionId',         'drop':1}
                , {'tab':'SessionsCache',   'col':'gametypeId',        'drop':1}
                , {'tab':'SessionsCache',   'col':'playerId',          'drop':0}
                , {'tab':'TourneysCache',   'col':'sessionId',         'drop':1}
                , {'tab':'TourneysCache',   'col':'tourneyId',         'drop':1}
                , {'tab':'TourneysCache',   'col':'playerId',          'drop':0}
                , {'tab':'Players',         'col':'siteId',            'drop':1}
                , {'tab':'Tourneys',        'col':'tourneyTypeId',     'drop':1}
                , {'tab':'Tourneys',        'col':'sessionId',         'drop':1}
                , {'tab':'TourneysPlayers', 'col':'playerId',          'drop':0}
                , {'tab':'TourneyTypes',    'col':'siteId',            'drop':0}
                , {'tab':'Backings',        'col':'tourneysPlayersId', 'drop':0}
                , {'tab':'Backings',        'col':'playerId',          'drop':0}
                , {'tab':'RawHands',        'col':'id',                'drop':0}
                , {'tab':'RawTourneys',     'col':'id',                'drop':0}
                ]
              ]
              
    
    foreignKeys = [
                    [ ] # no db with index 0
                  , [ ] # no db with index 1
                  , [ # foreign keys for mysql (index 2)
                      {'fktab':'Hands',         'fkcol':'tourneyId',     'rtab':'Tourneys',      'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'fileId',        'rtab':'Files',         'rcol':'id', 'drop':1}
                    , {'fktab':'Boards',        'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'tourneysPlayersId','rtab':'TourneysPlayers','rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'startCards',    'rtab':'StartCards',    'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'actionId',      'rtab':'Actions',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'rankId',        'rtab':'Rank',          'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPots',     'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPots',     'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HudCache',      'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'HudCache',      'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'HudCache',      'fkcol':'tourneyTypeId', 'rtab':'TourneyTypes',  'rcol':'id', 'drop':1}
                    , {'fktab':'Sessions',      'fkcol':'weekId',        'rtab':'Weeks',         'rcol':'id', 'drop':1}
                    , {'fktab':'Sessions',      'fkcol':'monthId',       'rtab':'Months',        'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'TourneysCache', 'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'TourneysCache', 'fkcol':'tourneyId',     'rtab':'Tourneys',      'rcol':'id', 'drop':1}
                    , {'fktab':'TourneysCache', 'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'Tourneys',      'fkcol':'tourneyTypeId', 'rtab':'TourneyTypes',  'rcol':'id', 'drop':1}
                    , {'fktab':'Tourneys',      'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    ]
                  , [ # foreign keys for postgres (index 3)
                      {'fktab':'Hands',         'fkcol':'tourneyId',     'rtab':'Tourneys',      'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'Hands',         'fkcol':'fileId',        'rtab':'Files',         'rcol':'id', 'drop':1}
                    , {'fktab':'Boards',        'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'tourneysPlayersId','rtab':'TourneysPlayers','rcol':'id', 'drop':1}
                    , {'fktab':'HandsPlayers',  'fkcol':'startCards',    'rtab':'StartCards',    'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsActions',  'fkcol':'actionId',      'rtab':'Actions',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HandsStove',    'fkcol':'rankId',        'rtab':'Rank',          'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPots',     'fkcol':'handId',        'rtab':'Hands',         'rcol':'id', 'drop':1}
                    , {'fktab':'HandsPots',     'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':1}
                    , {'fktab':'HudCache',      'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'HudCache',      'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'HudCache',      'fkcol':'tourneyTypeId', 'rtab':'TourneyTypes',  'rcol':'id', 'drop':1}
                    , {'fktab':'Sessions',      'fkcol':'weekId',        'rtab':'Weeks',         'rcol':'id', 'drop':1}
                    , {'fktab':'Sessions',      'fkcol':'monthId',       'rtab':'Months',        'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'gametypeId',    'rtab':'Gametypes',     'rcol':'id', 'drop':1}
                    , {'fktab':'SessionsCache', 'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'TourneysCache', 'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    , {'fktab':'TourneysCache', 'fkcol':'tourneyId',     'rtab':'Tourneys',      'rcol':'id', 'drop':1}
                    , {'fktab':'TourneysCache', 'fkcol':'playerId',      'rtab':'Players',       'rcol':'id', 'drop':0}
                    , {'fktab':'Tourneys',      'fkcol':'tourneyTypeId', 'rtab':'TourneyTypes',  'rcol':'id', 'drop':1}
                    , {'fktab':'Tourneys',      'fkcol':'sessionId',     'rtab':'Sessions',      'rcol':'id', 'drop':1}
                    ]
                  , [ # no foreign keys in sqlite (index 4)
                    ]
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


    def __init__(self, c, sql=None, autoconnect=True):
        """
        Class constructor for DatabaseManager.

        :param c: Configuration object.
        :param sql: SQL instance.
        :param autoconnect: Whether to automatically connect to the database.
        """
        self.config = c
        self.__connected = False
        self.settings = {'os': "linuxmac" if os.name != "nt" else "windows"}
        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params['db-backend']
        self.db_server = db_params['db-server']
        self.database = db_params['db-databaseName']
        self.host = db_params['db-host']
        self.port = db_params['db-port']
        self.db_path = ''
        gen = c.get_general_params()
        self.day_start = 0
        self._hero = None
        self._has_lock = False
        self.printdata = False
        self.resetCache()
        self.resetBulkCache()

        if 'day_start' in gen:
            self.day_start = float(gen['day_start'])

        self.sessionTimeout = float(self.import_options['sessionTimeout'])
        self.publicDB = self.import_options['publicDB']

        # where possible avoid creating new SQL instance by using the global one passed in
        self.sql = SQL.Sql(db_server=self.db_server) if sql is None else sql
        if autoconnect:
            # connect to db
            self.do_connect(c)

            # Set isolation levels for Postgres
            if self.backend == self.PGSQL:
                from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, ISOLATION_LEVEL_READ_COMMITTED, ISOLATION_LEVEL_SERIALIZABLE
                #ISOLATION_LEVEL_AUTOCOMMIT     = 0
                #ISOLATION_LEVEL_READ_COMMITTED = 1
                #ISOLATION_LEVEL_SERIALIZABLE   = 2

            # Recreate tables if necessary
            if self.backend == self.SQLITE and self.database == ':memory:' and self.wrongDbVersion and self.is_connected():
                log.info("sqlite/:memory: - creating")
                self.recreate_tables()
                self.wrongDbVersion = False

            # Initialize caches
            self.gtcache = None  # GameTypeId cache
            self.tcache = None  # TourneyId cache
            self.pcache = None  # PlayerId cache
            self.tpcache = None  # TourneysPlayersId cache

            # Set options for building hudcache
            self.build_full_hudcache = not self.import_options['fastStoreHudCache']
            self.cacheSessions = self.import_options['cacheSessions']
            self.callHud = self.import_options['callFpdbHud']

            # vars for hand ids or dates fetched according to above config:
            self.hand_1day_ago = 0  # max hand id more than 24 hrs earlier than now
            self.date_ndays_ago = 'd000000'  # date N days ago ('d' + YYMMDD)
            self.h_date_ndays_ago = 'd000000'  # date N days ago ('d' + YYMMDD) for hero
            self.date_nhands_ago = {}  # dates N hands ago per player - not used yet

            # Save actions if enabled
            self.saveActions = self.import_options['saveActions'] != False

            # Get sites if connected and version is correct
            if self.is_connected():
                if not self.wrongDbVersion:
                    self.get_sites()

                self.connection.rollback()  # make sure any locks taken so far are released
    #end def __init__

    def dumpDatabase(self):
        """
        Dumps the database into a string.

        Returns:
            str: A string representation of the database dump.
        """
        # Initialize the result with the database name and version.
        result = ["fpdb database dump", f"DB version={DB_VERSION}\n"]

        # Get a list of all tables in the database.
        tables = [table[0] for table in self.cursor.execute(self.sql.query['list_tables'])]

        # Loop through each table and add its contents to the result.
        for table in tables:
            # Add a header for the table.
            result.append(f"###################\nTable {table}\n###################\n")

            # Get all rows for the table.
            if rows := self.cursor.execute(
                self.sql.query.get(f'get{table}', f'SELECT * FROM {table}')
            ).fetchall():
                # Get the column names for the table.
                columnNames = self.cursor.description

                # Loop through each row and add its columns to the result.
                for row in rows:
                    for columnNumber in range(len(columnNames)):
                        # Add a special message for certain columns.
                        if columnNames[columnNumber][0] in [
                            "importTime",
                            "styleKey",
                        ]:
                            result.append(f"  {columnNames[columnNumber][0]}=ignore\n")
                        else:
                            result.append(f"  {columnNames[columnNumber][0]}={row[columnNumber]}\n")
                    result.append("\n")
            else:
                # Add a message for empty tables.
                result.append("empty table\n")
            result.append("\n")

        # Join all elements of the result into a single string.
        return "".join(result)


    #end def dumpDatabase

    # could be used by hud to change hud style
    def set_hud_style(self, style):
        """
        Sets the style of the HUD.

        Args:
            style (str): The style to set the HUD to.
        """
        # Set the HUD style to the given style.
        self.hud_style = style


    def do_connect(self, c):
        """
        Connect to the database using the provided configuration.

        Args:
            c (object): Configuration object containing database parameters.

        Raises:
            FpdbError: If configuration is not defined.
            Exception: If error occurs during connect.

        Returns:
            None
        """
        # Check if configuration is defined
        if c is None:
            raise FpdbError('Configuration not defined')

        # Get database parameters from configuration
        db = c.get_db_parameters()

        try:
            # Connect to the database
            self.connect(backend=db['db-backend'],
                         host=db['db-host'],
                         port=db['db-port'],
                         database=db['db-databaseName'],
                         user=db['db-user'],
                         password=db['db-password'])
        except:
            # error during connect
            self.__connected = False
            raise

        # Set class variables
        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params['db-backend']
        self.db_server = db_params['db-server']
        self.database = db_params['db-databaseName']
        self.host = db_params['db-host']
        self.port = db_params['db-port']


    def connect(self, backend=None, host=None, database=None,
                user=None, password=None, create=False, port="default_value"):
        """
        Connects a database with the given parameters.

        Parameters:
        backend (str): the database backend, must be one of 'MYSQL_INNODB', 'PGSQL', or 'SQLITE'
        host (str): the database host
        database (str): the name of the database
        user (str): the username for the database
        password (str): the password for the database
        create (bool): whether to create the database if it doesn't exist

        Raises:
        FpdbError: If the backend is not defined or is unrecognized.

        Returns:
        None
        """
        # Check that backend is defined
        if backend is None:
            raise FpdbError('Database backend not defined')

        # Set up database parameters
        self.backend = backend
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        self.cursor     = None
        self.hand_inc   = 1

        # Connect to MySQL database backend
        if backend == Database.MYSQL_INNODB:
            #####not working mysql connector on py3.9####
            import MySQLdb
            if use_pool:
                MySQLdb = pool.manage(MySQLdb, pool_size=5)
            try:
                # Connect to the MySQL database with the given parameters
                self.connection = MySQLdb.connect(host=host
                                                ,user=user
                                                ,passwd=password
                                                ,db=database
                                                ,charset='utf8'
                                                ,use_unicode=True)
                self.__connected = True
            except MySQLdb.Error as ex:
                # Handle known exceptions
                if ex.args[0] == 1045:
                    raise FpdbMySQLAccessDenied(ex.args[0], ex.args[1]) from ex
                elif ex.args[0] == 2002 or ex.args[0] == 2003: # 2002 is no unix socket, 2003 is no tcp socket
                    raise FpdbMySQLNoDatabase(ex.args[0], ex.args[1]) from ex
                else:
                    print(("*** WARNING UNKNOWN MYSQL ERROR:"), ex)

            # Set hand_inc value
            c = self.get_cursor()
            c.execute("show variables like 'auto_increment_increment'")
            self.hand_inc = int(c.fetchone()[1])


        elif backend == Database.PGSQL:
            # Connect to a PostgreSQL database using the given parameters
            import psycopg2
            import psycopg2.extensions
            if use_pool:
                psycopg2 = pool.manage(psycopg2, pool_size=5)
            psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
            psycopg2.extensions.register_adapter(Decimal, psycopg2._psycopg.Decimal)

            # If DB connection is made over TCP, then the variables
            # host, user and password are required
            # For local domain-socket connections, only DB name is
            # needed, and everything else is in fact undefined and/or
            # flat out wrong
            # sqlcoder: This database only connect failed in my windows setup??
            # Modifed it to try the 4 parameter style if the first connect fails - does this work everywhere?
            self.__connected = False
            if self.host == "localhost" or self.host == "127.0.0.1":
                try:
                    self.connection = psycopg2.connect(database = database)
                    self.__connected = True
                except Exception:
                    # direct connection failed so try user/pass/... version
                    pass

            # If still not connected, try with host, user, password, and database parameters
            if not self.is_connected():
                try:
                    self.connection = psycopg2.connect(host = host,
                                                    user = user,
                                                    password = password,
                                                    database = database)
                    self.__connected = True
                except Exception as ex:
                    # Handle known exceptions
                    if 'Connection refused' in ex.args[0] or ('database "' in ex.args[0] and '" does not exist' in ex.args[0]):
                        # meaning eg. db not running
                        raise FpdbPostgresqlNoDatabase(errmsg = ex.args[0])
                    elif 'password authentication' in ex.args[0]:
                        raise FpdbPostgresqlAccessDenied(errmsg = ex.args[0])
                    elif 'role "' in ex.args[0] and '" does not exist' in ex.args[0]: #role "fpdb" does not exist
                        raise FpdbPostgresqlAccessDenied(errmsg = ex.args[0])
                    else:
                        msg = ex.args[0]
                    log.error(msg)
                    raise FpdbError(msg)

                
        elif backend == Database.SQLITE:
            create = True
            import sqlite3
            if use_pool:
                sqlite3 = pool.manage(sqlite3, pool_size=1)
            #else:
            #    log.warning("SQLite won't work well without 'sqlalchemy' installed.")

            # Create a SQLite database if it does not exist
            if database != ":memory:":
                if not os.path.isdir(self.config.dir_database) and create:
                    log.info(("Creating directory: '%s'") % (self.config.dir_database))
                    os.makedirs(self.config.dir_database)
                database = os.path.join(self.config.dir_database, database).replace("\\","/")
            self.db_path = database
            log.info(("Connecting to SQLite: %s") % self.db_path)
            if os.path.exists(database) or create:
                # Connect to the existing or newly created SQLite database
                self.connection = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES )
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
                    log.warning(("Some database functions will not work without NumPy support"))
                self.cursor = self.connection.cursor()
                self.cursor.execute('PRAGMA temp_store=2')  # use memory for temp tables/indexes
                self.cursor.execute('PRAGMA journal_mode=WAL')  # use memory for temp tables/indexes
                self.cursor.execute('PRAGMA synchronous=0') # don't wait for file writes to finish
            else:
                # Raise an exception if the SQLite database does not exist
                raise FpdbError("sqlite database "+database+" does not exist")

        else:
            raise FpdbError("unrecognised database backend:"+str(backend))

        if self.is_connected():
            self.cursor = self.connection.cursor()
            self.cursor.execute(self.sql.query['set tx level'])
            self.check_version(database=database, create=create)

    def get_sites(self):
        """
        Retrieves the names and IDs of all sites from the database and sets them in the config object.
        """
        # Execute the SQL query to select the site names and IDs
        self.cursor.execute("SELECT name,id FROM Sites")
        # Fetch all the results from the query
        sites = self.cursor.fetchall()
        # Set the site IDs in the config object
        self.config.set_site_ids(sites)


    def check_version(self, database, create):
        """Checks database version and recreates tables if necessary.

        Args:
            database (str): name of the database.
            create (bool): whether to create tables if they don't exist.
        """
        # Set the flag to False.
        self.wrongDbVersion = False

        try:
            # Try to read the "Settings" table.
            self.cursor.execute("SELECT * FROM Settings")
            settings = self.cursor.fetchone()

            # If the database version is not equal to DB_VERSION, log an error and set the flag to True.
            if settings[0] != DB_VERSION:
                log.error(
                    f"Outdated or too new database version ({settings[0]}). Please recreate tables."
                )
                self.wrongDbVersion = True
        except Exception:
            # If reading the "Settings" table fails and the database is in memory, set the flag to True.
            if database == ":memory:":
                self.wrongDbVersion = True

            # If "create" is True, recreate the tables and call check_version with create=False.
            elif create:
                log.info(("Failed to read settings table.") + " - " + ("Recreating tables."))
                self.recreate_tables()
                self.check_version(database=database, create=False)

            # If "create" is False, log an error and set the flag to True.
            else:
                log.info(("Failed to read settings table.") + " - " + ("Please recreate tables."))
                self.wrongDbVersion = True

    #end def connect

    def commit(self):
        """
        Commits the current transaction on the database connection.
        If the backend is not SQLite, the connection is simply committed.
        If the backend is SQLite, the connection is retried up to 5 times
        in case a shared lock on the database caused the commit to fail.
        """
        if self.backend != self.SQLITE:
            self.connection.commit()
        else:
            # SQLite commits can fail because of shared locks on the database (SQLITE_BUSY).
            # Retry commit if it fails in case this happened.
            maxtimes = 5  # Maximum number of retries.
            pause = 1  # Number of seconds to sleep between retries.
            ok = False  # Whether the commit was successful.
            for i in range(maxtimes):
                try:
                    ret = self.connection.commit()
                    # log.debug(("commit finished ok, i = ")+str(i))
                    ok = True
                except:
                    log.debug(
                        f"commit {str(i)} failed: info={str(sys.exc_info())} value={str(sys.exc_info()[1])}"
                    )
                    sleep(pause)
                if ok:
                    break
            if not ok:
                log.debug(("commit failed"))
                raise FpdbError('sqlite commit failed')


    def rollback(self):
        """
        Roll back the current transaction.
        """
        self.connection.rollback()  # Roll back the transaction


    def connected(self):
        """Return the value of the __connected attribute.

        This method is now deprecated, use is_connected() instead.
        """
        return self.__connected


    def is_connected(self):
        """
        Check if the connection is currently established.

        :return: True if the connection is established, False otherwise.
        """
        return self.__connected

    def get_cursor(self, connect=False):
        """Returns a cursor object for the database connection.

        Args:
            connect (bool): Whether to establish a new database connection or not.

        Returns:
            cursor: A cursor object for the database connection.
        """
        # Check if the backend is MySQL InnoDB and the operating system is Windows.
        if self.backend == Database.MYSQL_INNODB and os.name == 'nt':
            # Ping the connection to keep it alive.
            self.connection.ping(True)
        # Return a cursor object for the database connection.
        return self.connection.cursor()


    def close_connection(self):
        """Closes the connection to the database."""
        self.connection.close()  # Close the connection
        self.__connected = False  # Set the 'connected' attribute to False



    def disconnect(self, due_to_error=False):
        """
        Disconnect from the database.

        Args:
            due_to_error (bool): If True, roll back any uncommitted changes before disconnecting.
                Otherwise, commit any changes and then disconnect.
        """
        if due_to_error:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.cursor.close()
        self.connection.close()
        self.__connected = False



    def reconnect(self, due_to_error=False):
        """
        Reconnect to the database.

        Args:
            due_to_error (bool): Whether the function is being called due to an error.
        """
        # Disconnect from the database.
        self.disconnect(due_to_error)

        # Connect to the database with the given parameters.
        self.connect(
            self.backend,
            self.host,
            self.database,
            self.user,
            self.password,
        )


    def get_backend_name(self):
        """
        Returns the name of the currently used backend.

        Args:
            self: An instance of the class.

        Returns:
            str: The name of the backend currently being used.

        Raises:
            FpdbError: If an invalid backend value is encountered.
        """
        if self.backend == 2:
            return "MySQL InnoDB"
        elif self.backend == 3:
            return "PostgreSQL"
        elif self.backend == 4:
            return "SQLite"
        else:
            raise FpdbError("invalid backend")

    def get_db_info(self):
        """Returns a tuple containing database connection information."""
        # Extract connection information from the object attributes.
        return (self.host, self.database, self.user, self.password)


    def get_table_name(self, hand_id):
        """
        Retrieves the name of the table associated with the given hand_id.

        Args:
            hand_id (int): The ID of the hand to retrieve the table name for.

        Returns:
            str: The name of the table associated with the given hand_id.
        """
        # Create a cursor object using the connection obtained from the parent class
        c = self.connection.cursor()

        # Execute the query to retrieve the table name using the given hand_id
        c.execute(self.sql.query['get_table_name'], (hand_id, ))

        # Return the first row from the query result
        return c.fetchone()



    def get_table_info(self, hand_id):
        """Get information about a poker table based on the given hand ID.

        Args:
            hand_id (int): The ID of the hand to get information for.

        Returns:
            list: A list containing information about the table, including the
            table name, game type (ring or tournament), tournament number (if
            applicable), and table number (if applicable).
        """
        # Create cursor to execute query
        c = self.connection.cursor()

        # Execute query to get table name and game type
        c.execute(self.sql.query['get_table_name'], (hand_id, ))

        # Fetch one row from the query result
        row = c.fetchone()

        # Convert row to list for easier manipulation
        l = list(row)

        # If the game type is a cash game, add None values for tournament number and table number
        if row[3] == "ring":
            l.extend((None, None))
        else:
            # If the game type is a tournament, extract the tournament number and table number from the table name
            tour_no, tab_no = re.split(" ", row[0], 1)
            l.append(tour_no)
            l.append(tab_no)

        # Return the list containing table information
        return l



    def get_last_hand(self):
        """
        Returns the last hand from the database.

        Args:
            self: The instance of the class.

        Returns:
            The last hand from the database.
        """
        # Create a cursor object from the connection
        c = self.connection.cursor()

        # Execute the SQL query to get the last hand from the database
        c.execute(self.sql.query['get_last_hand'])

        # Get the first row of the result set
        row = c.fetchone()

        # Return the first column of the first row
        return row[0]



    def get_xml(self, hand_id):
        """
        Retrieves XML data from the database for a given hand ID.

        Args:
            hand_id (int): The ID of the hand for which to retrieve XML data.

        Returns:
            str: The XML data for the specified hand.
        """
        # Create a cursor object
        c = self.connection.cursor()

        # Execute the SQL query to retrieve the XML data for the specified hand ID
        c.execute(self.sql.query['get_xml'], (hand_id))

        # Fetch the first row of the query results
        row = c.fetchone()

        # Return the XML data from the first column of the row
        return row[0]


    def get_recent_hands(self, last_hand):
        """
        Retrieve recent hands from the database

        Args:
            last_hand (int): the ID of the last hand to retrieve

        Returns:
            list of tuples: each tuple represents a row in the database result set
        """
        # create a cursor object
        c = self.connection.cursor()
        # execute the query with the provided parameter
        c.execute(self.sql.query['get_recent_hands'], {'last_hand': last_hand})
        # fetch all the resulting rows
        return c.fetchall()


    def get_gameinfo_from_hid(self, hand_id):
        """Returns a gameinfo (gametype) dictionary suitable for passing to Hand.hand_factory.

        Args:
            hand_id (int): The id of the hand.

        Returns:
            dict: A dictionary with the gameinfo.
        """
        # Get a cursor and prepare the query
        c = self.connection.cursor()
        q = self.sql.query['get_gameinfo_from_hid']
        q = q.replace('%s', self.sql.query['placeholder'])

        # Execute the query and fetch the results
        c.execute(q, (hand_id, ))
        row = c.fetchone()

        # Create and return the gameinfo dictionary
        return {
            'sitename': row[0], # Name of the site where the game was played
            'category': row[1], # Category of the game (e.g. Texas Holdem)
            'base': row[2], # Base amount of the game
            'type': row[3], # Type of game (e.g. No Limit)
            'limitType': row[4], # Limit type (e.g. Pot Limit)
            'hilo': row[5], # High/Low
            'sb': row[6], # Small blind
            'bb': row[7], # Big blind
            'sbet': row[8], # Small bet
            'bbet': row[9], # Big bet
            'currency': row[10], # Currency used in the game
            'gametypeId': row[11], # Game type id
            'split': row[12], # Split game
        }

        
#   Query 'get_hand_info' does not exist, so it seems
#    def get_hand_info(self, new_hand_id):
#        c = self.connection.cursor()
#        c.execute(self.sql.query['get_hand_info'], new_hand_id)
#        return c.fetchall()      

    def getHandCount(self):
        """Returns the number of hands in the database.

        Returns:
            int: The number of hands in the database.
        """
        c = self.connection.cursor()
        # Execute the SQL query to get the hand count.
        c.execute(self.sql.query['getHandCount'])
        # Return the result of the query (the hand count).
        return c.fetchone()[0]
    #end def getHandCount

    def getTourneyCount(self):
        """
        Retrieves the count of tournaments from the database.

        Returns:
            int: The count of tournaments.
        """
        # Create a cursor object to execute the query.
        c = self.connection.cursor()

        # Execute the query to retrieve the count of tournaments.
        c.execute(self.sql.query['getTourneyCount'])

        # Return the first row of the results, which is the count of tournaments.
        return c.fetchone()[0]

    def getTourneyTypeCount(self):
        """
        Retrieves the count of tournament types using a database cursor.

        Returns:
            int: The count of tournament types.
        """
        # Create a cursor object
        c = self.connection.cursor()

        # Execute the SQL query to retrieve the count of tournament types
        c.execute(self.sql.query['getTourneyTypeCount'])
        # Return the count of tournament types
        return c.fetchone()[0]
    #end def getTourneyCount

    def getSiteTourneyNos(self, site):
        """
        Returns a list of tournament numbers for a given site.

        Args:
            site (str): The name of the site.

        Returns:
            list: A list of tournament numbers.
        """
        # Create a cursor object for the database connection
        c = self.connection.cursor()

        # Get the site ID for the given site
        q = self.sql.query['getSiteId']
        q = q.replace('%s', self.sql.query['placeholder'])
        c.execute(q, (site,))
        siteid = c.fetchone()[0]

        # Get the tournament numbers for the given site ID
        q = self.sql.query['getSiteTourneyNos']
        q = q.replace('%s', self.sql.query['placeholder'])
        c.execute(q, (siteid,))

        # Add each tournament number to a list and return the list
        alist = []
        for row in c.fetchall():
            alist.append(row)
        return alist


    def get_actual_seat(self, hand_id, name):
        """
        Returns the actual seat of the player with the given hand_id and name.

        Args:
            hand_id (int): The hand ID of the player.
            name (str): The name of the player.

        Returns:
            int: The actual seat of the player.
        """
        # Create a cursor object
        c = self.connection.cursor()

        # Execute the SQL query to get the actual seat of the player
        c.execute(self.sql.query['get_actual_seat'], (hand_id, name))

        # Fetch the result
        row = c.fetchone()

        # Return the actual seat of the player
        return row[0]


    def get_cards(self, hand):
        """
        Get and return the cards for each player in the hand.

        Args:
            hand (int): The id of the hand to get the cards for.

        Returns:
            dict: A dictionary of player ids and their corresponding cards.
        """
        # Create a cursor to execute SQL queries
        c = self.connection.cursor()

        # Execute the 'get_cards' query with the given hand id
        c.execute(self.sql.query['get_cards'], [hand])

        # Fetch all the results and convert them into a dictionary of player ids and their corresponding cards
        return {row[0]: row[1:] for row in c.fetchall()}


    def get_common_cards(self, hand):
        """Get and return the community cards for the specified hand.

        Args:
            hand (int): The ID of the hand to retrieve community cards for.

        Returns:
            dict: A dictionary containing the community cards for the specified hand.
        """
        # Create a cursor object to interact with the database
        c = self.connection.cursor()

        # Execute a SQL query to retrieve the common cards for the specified hand
        c.execute(
            self.sql.query['get_common_cards'], 
            [hand]
        )

        return {'common': c.fetchone()}


    def get_action_from_hand(self, hand_no):
        """
        Given a hand number, retrieves the action taken in each street
        and returns a list of actions for each street.

        Args:
        - hand_no (int): the number of the hand

        Returns:
        - action (list): a list of actions for each street, 
                        where each action is a list of tuples.
        """
        action = [ [], [], [], [], [] ] # a list of actions for each street
        c = self.connection.cursor() # create a cursor object
        c.execute(self.sql.query['get_action_from_hand'], (hand_no,)) # execute query
        for row in c.fetchall(): # loop over each row in the result set
            street = row[0]
            act = row[1:]
            action[street].append(act) # add the action to the corresponding street
        return action # return the list of actions


    def get_winners_from_hand(self, hand):
        """Returns a hash of winners:amount won, given a hand number.

        Args:
            hand (int): The number of the hand to get winners from.

        Returns:
            dict: A dictionary containing the winners and their respective amounts won.
        """
        # Get cursor
        c = self.connection.cursor()
        # Execute query to get winners from hand
        c.execute(self.sql.query['get_winners_from_hand'], (hand,))
        # Fetch all rows and create dictionary of winners and their amounts won
        return {row[0]: row[1] for row in c.fetchall()}


    def set_printdata(self, val):
        """
        Setter function for self.printdata. Sets the value of self.printdata to the given value.

        Args:
            val: The value to set self.printdata to.
        """
        # Set the value of self.printdata to the given value
        self.printdata = val

    def init_hud_stat_vars(self, hud_days, h_hud_days):
        """Initialise variables used by Hud to fetch stats:
        self.hand_1day_ago     handId of latest hand played more than a day ago
        self.date_ndays_ago    date n days ago
        self.h_date_ndays_ago  date n days ago for hero (different n)
        """
        self.hand_1day_ago = 1

        # Get the cursor
        c = self.get_cursor()

        # Execute the query to get the hand played more than a day ago
        c.execute(self.sql.query['get_hand_1day_ago'])

        # Fetch the first row
        row = c.fetchone()

        # If the row exists and the first element is not null, update the hand_1day_ago variable
        if row and row[0]:
            self.hand_1day_ago = int(row[0])

        # Get the timezone offset
        tz = datetime.now(timezone.utc) - datetime.now(timezone.utc)
        tz_offset = old_div(tz.seconds, 3600)

        # Calculate the timezone offset at the start of the day
        tz_day_start_offset = self.day_start + tz_offset

        # Calculate the date n days ago
        d = timedelta(days=hud_days, hours=tz_day_start_offset)
        now = datetime.now(timezone.utc) - d
        self.date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)

        # Calculate the date n days ago for hero
        d = timedelta(days=h_hud_days, hours=tz_day_start_offset)
        now = datetime.now(timezone.utc) - d
        self.h_date_ndays_ago = "d%02d%02d%02d" % (now.year - 2000, now.month, now.day)


    # is get_stats_from_hand slow?
    # Gimick - yes  - reason being that the gametypeid join on hands
    # increases exec time on SQLite and postgres by a factor of 6 to 10
    # method below changed to lookup hand.gametypeid and pass that as
    # a constant to the underlying query.
    
    def get_stats_from_hand(self, hand, type, hud_params=None, hero_id=-1, num_seats=6):
        """Get statistics from a hand.

        Args:
        - hand: string representing the hand id.
        - type: string representing the type of statistic desired.
        - hud_params: dictionary containing HUD parameters.
        - hero_id: integer representing the hero's id.
        - num_seats: integer representing the number of seats.

        Returns:
        Dictionary containing the statistics for each player.

        """
        # Set default values for HUD parameters if not provided.
        if hud_params is None:
            hud_params = {
                'stat_range': 'A',
                'agg_bb_mult': 1000,
                'seats_style': 'A',
                'seats_cust_nums_low': 1,
                'seats_cust_nums_high': 10,
                'h_stat_range': 'S',
                'h_agg_bb_mult': 1000,
                'h_seats_style': 'A',
                'h_seats_cust_nums_low': 1,
                'h_seats_cust_nums_high': 10,
            }

        # Extract HUD parameters into individual variables for easier access.
        stat_range = hud_params['stat_range']
        agg_bb_mult = hud_params['agg_bb_mult']
        seats_style = hud_params['seats_style']
        seats_cust_nums_low = hud_params['seats_cust_nums_low']
        seats_cust_nums_high = hud_params['seats_cust_nums_high']
        h_stat_range = hud_params['h_stat_range']
        h_agg_bb_mult = hud_params['h_agg_bb_mult']
        h_seats_style = hud_params['h_seats_style']
        h_seats_cust_nums_low = hud_params['h_seats_cust_nums_low']
        h_seats_cust_nums_high = hud_params['h_seats_cust_nums_high']

        # Initialize the dictionary that will hold the statistics.
        stat_dict = {}

        # Determine the range of seats to include in the statistics.
        if seats_style == 'A':
            seats_min, seats_max = 0, 10
        elif seats_style == 'C':
            seats_min, seats_max = seats_cust_nums_low, seats_cust_nums_high
        elif seats_style == 'E':
            seats_min, seats_max = num_seats, num_seats
        else:
            seats_min, seats_max = 0, 10
            log.warning(f"bad seats_style value: {seats_style}")

        # Determine the range of seats for the villain to include in the statistics.
        if h_seats_style == 'A':
            h_seats_min, h_seats_max = 0, 10
        elif h_seats_style == 'C':
            h_seats_min, h_seats_max = h_seats_cust_nums_low, h_seats_cust_nums_high
        elif h_seats_style == 'E':
            h_seats_min, h_seats_max = num_seats, num_seats
        else:
            h_seats_min, h_seats_max = 0, 10
            log.warning(f"bad h_seats_style value: {h_seats_style}")

        # Get the statistics for the session if necessary.
        if stat_range == 'S' or h_stat_range == 'S':
            self.get_stats_from_hand_session(hand, stat_dict, hero_id
                                            ,stat_range, seats_min, seats_max
                                            ,h_stat_range, h_seats_min, h_seats_max)

        # If both stat ranges are session, return the statistics dictionary.
        if stat_range == 'S' and h_stat_range == 'S':
            return stat_dict

        # Determine the style key for the hero's statistics.                        
        if stat_range == 'T':
            stylekey = self.date_ndays_ago
        elif stat_range == 'A':
            stylekey = '0000000'  # all stylekey values should be higher than this
        elif stat_range == 'S':
            stylekey = 'zzzzzzz'  # all stylekey values should be lower than this
        else:
            stylekey = '0000000'
            log.info(f'stat_range: {stat_range}')

        #elif stat_range == 'H':
        #    stylekey = date_nhands_ago  needs array by player here ...

        if h_stat_range == 'T':
            h_stylekey = self.h_date_ndays_ago
        elif h_stat_range == 'A':
            h_stylekey = '0000000'  # all stylekey values should be higher than this
        elif h_stat_range == 'S':
            h_stylekey = 'zzzzzzz'  # all stylekey values should be lower than this
        else:
            h_stylekey = '00000000'
            log.info(f'h_stat_range: {h_stat_range}')

        #elif h_stat_range == 'H':
        #    h_stylekey = date_nhands_ago  needs array by player here ...

        # lookup gametypeId from hand
        handinfo = self.get_gameinfo_from_hid(hand)
        gametypeId = handinfo["gametypeId"]

        query = 'get_stats_from_hand_aggregated'
        subs = (hand
               ,hero_id, stylekey, agg_bb_mult, agg_bb_mult, gametypeId, seats_min, seats_max  # hero params
               ,hero_id, h_stylekey, h_agg_bb_mult, h_agg_bb_mult, gametypeId, h_seats_min, h_seats_max)    # villain params

        stime = time()
        c = self.connection.cursor()

        # Now get the stats
        c.execute(self.sql.query[query], subs)
        ptime = time() - stime
        log.info("HudCache query get_stats_from_hand_aggregated took %.3f seconds" % ptime)
        colnames = [desc[0] for desc in c.description]
        for row in c.fetchall():
            playerid = row[0]
            if (playerid == hero_id and h_stat_range != 'S') or (playerid != hero_id and stat_range != 'S'):
                t_dict = {name.lower(): val for name, val in zip(colnames, row)}
                stat_dict[t_dict['player_id']] = t_dict

        return stat_dict

    # uses query on handsplayers instead of hudcache to get stats on just this session
    def get_stats_from_hand_session(self, hand, stat_dict, hero_id, stat_range, seats_min, seats_max, h_stat_range, h_seats_min, h_seats_max):
        """
        Get stats for just this session (currently defined as any play in the last 24 hours - to be improved at some point ...)

        Args:
            hand (int): the hand ID
            stat_dict (dict): a dictionary of statistics
            hero_id (int): the player ID of the hero
            stat_range (str): 'S' or 'N', indicating which stats to get
            seats_min (int): minimum number of seats
            seats_max (int): maximum number of seats
            h_stat_range (str): 'S' or 'N', indicating whether to get stats for hero and/or others
            h_seats_min (int): minimum number of seats for hero
            h_seats_max (int): maximum number of seats for hero

        Returns:
            dict: a dictionary of statistics for the given session
        """

        # get the SQL query string
        query = self.sql.query['get_stats_from_hand_session']
        if self.db_server == 'mysql':
            query = query.replace("<signed>", 'signed ')
        else:
            query = query.replace("<signed>", '')

        # substitute the parameters into the query
        subs = (self.hand_1day_ago, hand, hero_id, seats_min, seats_max, hero_id, h_seats_min, h_seats_max)

        # get the cursor and execute the query
        c = self.get_cursor()
        c.execute(query, subs)

        # get the column names
        colnames = [desc[0] for desc in c.description]

        # initialize the row counter
        n = 0

        # get the first row
        row = c.fetchone()

        # check if the first column is player_id
        if colnames[0].lower() == 'player_id':

            # loop through the rows and add the stats to the appropriate stat_dict
            while row:
                playerid = row[0]
                seats = row[1]
                if (playerid == hero_id and h_stat_range == 'S') or (playerid != hero_id and stat_range == 'S'):
                    for name, val in zip(colnames, row):
                        if playerid not in stat_dict:
                            stat_dict[playerid] = {name.lower(): val}
                        elif name.lower() not in stat_dict[playerid]:
                            stat_dict[playerid][name.lower()] = val
                        elif name.lower() not in ('hand_id', 'player_id', 'seat', 'screen_name', 'seats'):
                            stat_dict[playerid][name.lower()] += val
                    n += 1
                    if n >= 10000: break  # todo: don't think this is needed so set nice and high
                                                    # prevents infinite loop so leave for now - comment out or remove?
                row = c.fetchone()
        else:
            log.error(
                f"ERROR: query {query} result does not have player_id as first column"
            )
        log.debug(f"   {n} rows fetched, len(stat_dict) = {len(stat_dict)}")

        # return the stat_dict
        return stat_dict


        #print "   %d rows fetched, len(stat_dict) = %d" % (n, len(stat_dict))

        #print "session stat_dict =", stat_dict
        #return stat_dict

    def get_player_id(self, config, siteName, playerName):
        """
        Given a site name and player name, return the player id from the database.

        Args:
            config (dict): A dictionary containing database configuration parameters.
            siteName (str): The name of the player's site.
            playerName (str): The name of the player.

        Returns:
            int or None: The player id from the database, or None if no record was found.
        """
        # Create a cursor object for executing SQL queries.
        c = self.connection.cursor()

        # Convert site name to UTF-8 encoding.
        siteNameUtf = Charset.to_utf8(siteName)

        # Convert player name to string.
        playerNameUtf = str(playerName)

        # Execute the SQL query to get the player id.
        c.execute(self.sql.query['get_player_id'], (playerNameUtf, siteNameUtf))

        # Fetch the first row of the result set.
        row = c.fetchone()

        # Return the player id if a row was found, else return None.
        return row[0] if (row := c.fetchone()) else None


    def get_player_names(self, config, site_id=None, like_player_name="%"):
        """
        Fetch player names from players table. Use site_id and like_player_name if provided.

        Args:
            config: configuration object.
            site_id: site id.
            like_player_name: pattern to match player name.

        Returns:
            List of tuples containing player names.
        """

        # Set default value for site_id if not provided.
        if site_id is None:
            site_id = -1

        # Get database cursor.
        c = self.get_cursor()

        # Convert like_player_name to utf-8.
        p_name = Charset.to_utf8(like_player_name)

        # Execute SQL query to get player names.
        c.execute(self.sql.query['get_player_names'], (p_name, site_id, site_id))

        # Return list of tuples containing player names.
        return c.fetchall()


    def get_site_id(self, site):
        """
        Retrieve the site ID for a given site name from the database.

        Args:
            site (str): The name of the site to retrieve the ID for.

        Returns:
            list: A list of tuples containing the site ID(s) for the given site name.
        """
        c = self.get_cursor()
        c.execute(self.sql.query['getSiteId'], (site,))

        return c.fetchall()


    def resetCache(self):
        """
        Resets the cache by setting all cached values to their initial states.

        Parameters:
        self (object): The object to reset the cache for.

        Returns:
        None
        """
        self.ttold = set()  # Set of old TourneyTypes
        self.ttnew = set()  # Set of new TourneyTypes
        self.wmold = set()  # Set of old WeeksMonths
        self.wmnew = set()  # Set of new WeeksMonths
        self.gtcache = None  # Cached GameTypeId
        self.tcache = None  # Cached TourneyId
        self.pcache = None  # Cached PlayerId
        self.tpcache = None  # Cached TourneysPlayersId

    def get_last_insert_id(self, cursor=None):
        """
        A function that returns the last inserted ID from a database connection.

        Args:
            cursor: An optional cursor object. Defaults to None.

        Returns:
            The last inserted ID from the database connection or -1 if there was an error.

        Raises:
            Any exception raised during the function execution.
        """

        # Initialize the return value to None
        ret = None

        try:
            # If the database backend is MySQL with InnoDB storage engine
            if self.backend == self.MYSQL_INNODB:
                # Get the last inserted ID from the connection
                ret = self.connection.insert_id()
                # If the retrieved ID is out of bounds
                if ret < 1 or ret > 999999999:
                    # Log a warning message
                    log.warning(("getLastInsertId(): problem fetching insert_id? ret=%d") % ret)
                    # Set the return value to a default value of -1
                    ret = -1

            # If the database backend is PostgreSQL
            elif self.backend == self.PGSQL:
                # Get a cursor object
                c = self.get_cursor()
                # Execute a SELECT statement to retrieve the last inserted ID
                ret = c.execute ("SELECT lastval()")
                # If a result is returned
                if row := c.fetchone():
                    # Set the return value to the retrieved ID
                    ret = row[0]
                # If no result is returned
                else:
                    # Log a warning message
                    log.warning(("getLastInsertId(%s): problem fetching lastval? row=%d") % (seq, row))
                    # Set the return value to a default value of -1
                    ret = -1

            # If the database backend is SQLite
            elif self.backend == self.SQLITE:
                # Get the last inserted ID from the cursor
                ret = cursor.lastrowid

            # If the database backend is unknown
            else:
                # Log an error message
                log.error(("getLastInsertId(): unknown backend: %d") % self.backend)
                # Set the return value to a default value of -1
                ret = -1

        # If an exception occurs
        except:
            # Set the return value to a default value of -1
            ret = -1
            # Log the error message and traceback
            err = traceback.extract_tb(sys.exc_info()[2])
            log.error(f"*** Database get_last_insert_id error: {str(sys.exc_info()[1])}")
            log.error("\n".join([f'{e[0]}:{str(e[1])} {e[2]}' for e in err]))
            # Raise the exception
            raise

        # Return the last inserted ID or -1 if there was an error
        return ret

    
    def prepareBulkImport(self):
        """Drop some indexes/foreign keys to prepare for bulk import.
           Currently keeping the standalone indexes as needed to import quickly"""
        stime = time()
        c = self.get_cursor()
        # sc: don't think autocommit=0 is needed, should already be in that mode
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=0")
            c.execute("SET autocommit=0")
            return
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)   # allow table/index operations to work
        for fk in self.foreignKeys[self.backend]:
            if fk['drop'] == 1:
                if self.backend == self.MYSQL_INNODB:
                    c.execute("SELECT constraint_name " +
                              "FROM information_schema.KEY_COLUMN_USAGE " +
                              #"WHERE REFERENCED_TABLE_SCHEMA = 'fpdb'
                              "WHERE 1=1 " +
                              "AND table_name = %s AND column_name = %s " +
                              "AND referenced_table_name = %s " +
                              "AND referenced_column_name = %s ",
                              (fk['fktab'], fk['fkcol'], fk['rtab'], fk['rcol']) )
                    if cons := c.fetchone():
                        print("dropping mysql fk", cons[0], fk['fktab'], fk['fkcol'])
                        try:
                            c.execute("alter table " + fk['fktab'] + " drop foreign key " + cons[0])
                        except Exception:
                            print(f"    drop failed: {str(sys.exc_info())}")
                elif self.backend == self.PGSQL:
    #    DON'T FORGET TO RECREATE THEM!!
                    print("dropping pg fk", fk['fktab'], fk['fkcol'])
                    try:
                        # try to lock table to see if index drop will work:
                        # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                        # then drop still hangs :-(  does work in some tests though??
                        # will leave code here for now pending further tests/enhancement ...
                        c.execute("BEGIN TRANSACTION")
                        c.execute(f"lock table {fk['fktab']} in exclusive mode nowait")
                        #print "after lock, status:", c.statusmessage
                        #print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                        try:
                            c.execute(
                                f"alter table {fk['fktab']} drop constraint {fk['fktab']}_{fk['fkcol']}_fkey"
                            )
                            print(f"dropped pg fk pg fk {fk['fktab']}_{fk['fkcol']}_fkey, continuing ...")
                        except Exception:
                            if "does not exist" not in str(sys.exc_info()[1]):
                                print(("warning: drop pg fk %s_%s_fkey failed: %s, continuing ...") \
                                                                          % (fk['fktab'], fk['fkcol'], str(sys.exc_info()[1]).rstrip('\n') ))
                        c.execute("END TRANSACTION")
                    except Exception:
                        print(("warning: constraint %s_%s_fkey not dropped: %s, continuing ...") \
                                                                  % (fk['fktab'],fk['fkcol'], str(sys.exc_info()[1]).rstrip('\n')))
                else:
                    return -1

        for idx in self.indexes[self.backend]:
            if idx['drop'] == 1:
                if self.backend == self.MYSQL_INNODB:
                    print(("dropping mysql index "), idx['tab'], idx['col'])
                    try:
                        # apparently nowait is not implemented in mysql so this just hangs if there are locks
                        # preventing the index drop :-(
                        c.execute( "alter table %s drop index %s;", (idx['tab'],idx['col']) )
                    except Exception:
                        print(f"    drop index failed: {str(sys.exc_info())}")
                elif self.backend == self.PGSQL:
    #    DON'T FORGET TO RECREATE THEM!!
                    print(("dropping pg index "), idx['tab'], idx['col'])
                    try:
                        # try to lock table to see if index drop will work:
                        c.execute("BEGIN TRANSACTION")
                        c.execute(f"lock table {idx['tab']} in exclusive mode nowait")
                        #print "after lock, status:", c.statusmessage
                        try:
                            # table locked ok so index drop should work:
                            #print "drop index %s_%s_idx" % (idx['tab'],idx['col'])
                            c.execute(f"drop index if exists {idx['tab']}_{idx['col']}_idx")
                        except Exception:
                            if "does not exist" not in str(sys.exc_info()[1]):
                                print(("warning: drop index %s_%s_idx failed: %s, continuing ...") \
                                                                          % (idx['tab'],idx['col'], str(sys.exc_info()[1]).rstrip('\n')))
                        c.execute("END TRANSACTION")
                    except Exception:
                        print(("warning: index %s_%s_idx not dropped %s, continuing ...") \
                                                                  % (idx['tab'],idx['col'], str(sys.exc_info()[1]).rstrip('\n')))
                else:
                    return -1

        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(1)   # go back to normal isolation level
        self.commit() # seems to clear up errors if there were any in postgres
        ptime = time() - stime
        print(f"prepare import took {ptime} seconds")
    #end def prepareBulkImport

    def afterBulkImport(self):
        """
        Re-create any dropped indexes/foreign keys after bulk import.
        """
        stime = time()

        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=1")
            c.execute("SET autocommit=1")
            return

        # For Postgres, allow table/index operations to work
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)   # allow table/index operations to work

        # Recreate any dropped foreign keys
        for fk in self.foreignKeys[self.backend]:
            if fk['drop'] == 1:
                # Get the constraint name if it exists
                if self.backend == self.MYSQL_INNODB:
                    c.execute("SELECT constraint_name " +
                              "FROM information_schema.KEY_COLUMN_USAGE " +
                              #"WHERE REFERENCED_TABLE_SCHEMA = 'fpdb'
                              "WHERE 1=1 " +
                              "AND table_name = %s AND column_name = %s " +
                              "AND referenced_table_name = %s " +
                              "AND referenced_column_name = %s ",
                              (fk['fktab'], fk['fkcol'], fk['rtab'], fk['rcol']) )
                    cons = c.fetchone()
                    # If the constraint does not exist, create the foreign key
                    if not cons:
                        print(("Creating foreign key "), fk['fktab'], fk['fkcol'], "->", fk['rtab'], fk['rcol'])
                        try:
                            c.execute("alter table " + fk['fktab'] + " add foreign key ("
                                      + fk['fkcol'] + ") references " + fk['rtab'] + "("
                                      + fk['rcol'] + ")")
                        except Exception:
                            print(f"Create foreign key failed: {str(sys.exc_info())}")
                elif self.backend == self.PGSQL:
                    print(("Creating foreign key "), fk['fktab'], fk['fkcol'], "->", fk['rtab'], fk['rcol'])
                    try:
                        c.execute("alter table " + fk['fktab'] + " add constraint "
                                  + fk['fktab'] + '_' + fk['fkcol'] + '_fkey'
                                  + " foreign key (" + fk['fkcol']
                                  + ") references " + fk['rtab'] + "(" + fk['rcol'] + ")")
                    except Exception:
                        print(f"Create foreign key failed: {str(sys.exc_info())}")
                else:
                    return -1
        # Recreate any dropped indexes
        for idx in self.indexes[self.backend]:
            if idx['drop'] == 1:
                if self.backend == self.MYSQL_INNODB:
                    print(f"Creating MySQL index {idx['tab']} {idx['col']}")
                    try:
                        s = f"alter table {idx['tab']} add index {idx['col']}({idx['col']})"
                        c.execute(s)
                    except Exception:
                        print(f"Create foreign key failed: {str(sys.exc_info())}")
                elif self.backend == self.PGSQL:
    #                pass
                    # mod to use tab_col for index name?
                    print(("Creating PostgreSQL index "), idx['tab'], idx['col'])
                    try:
                        s = f"create index {idx['tab']}_{idx['col']}_idx on {idx['tab']}({idx['col']})"
                        c.execute(s)
                    except Exception:
                        print(f"Create index failed: {str(sys.exc_info())}")
                else:
                    return -1

        # For Postgres, go back to normal isolation level
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(1)   # go back to normal isolation level
        # Commit the changes and print the time taken
        self.commit()   # seems to clear up errors if there were any in postgres
        atime = time() - stime
        print(f"After import took {atime} seconds")
    #end def afterBulkImport

    def drop_referential_integrity(self):
        """
        Update all tables to remove foreign keys.
        """
        # Get cursor
        c = self.get_cursor()

        # Get all tables
        c.execute(self.sql.query['list_tables'])
        result = c.fetchall()

        # Loop through tables
        for i in range(len(result)):
            # Get table's CREATE TABLE parameters
            c.execute(f"SHOW CREATE TABLE {result[i][0]}")
            inner = c.fetchall()

            # Loop through CREATE TABLE parameters to find foreign key constraints
            for j in range(len(inner)):
                # result[i][0] - Table name
                # result[i][1] - CREATE TABLE parameters
                # Searching for CONSTRAINT `tablename_ibfk_1`
                for m in re.finditer('(ibfk_[0-9]+)', inner[j][1]):
                    # Drop foreign key constraint
                    key = f"`{inner[j][0]}_{m.group()}`"
                    c.execute(f"ALTER TABLE {inner[j][0]} DROP FOREIGN KEY {key}")
                # Commit changes after each foreign key constraint is dropped
                self.commit()

    #end drop_referential_inegrity

    def recreate_tables(self):
        """(Re-)creates the tables of the current DB"""
        # Delete existing tables
        self.drop_tables()
        # Reset cache and bulk cache
        self.resetCache()
        self.resetBulkCache()
        # Create new tables
        self.create_tables()
        # Create indexes for new tables
        self.createAllIndexes()
        # Commit changes to the database
        self.commit()
        # Get all sites in the database
        self.get_sites()
        # Log that table recreation is finished
        log.info(("Finished recreating tables"))

    #end def recreate_tables

    def create_tables(self):
        """
        Creates all necessary tables for the database and adds unique indexes to them.
        """
        log.debug(self.sql.query['createSettingsTable'])
        c = self.get_cursor()
        c.execute(self.sql.query['createSettingsTable'])

        log.debug("Creating tables")
        c.execute(self.sql.query['createActionsTable'])
        c.execute(self.sql.query['createRankTable'])
        c.execute(self.sql.query['createStartCardsTable'])
        c.execute(self.sql.query['createSitesTable'])
        c.execute(self.sql.query['createGametypesTable'])
        c.execute(self.sql.query['createFilesTable'])
        c.execute(self.sql.query['createPlayersTable'])
        c.execute(self.sql.query['createAutoratesTable'])
        c.execute(self.sql.query['createWeeksTable'])
        c.execute(self.sql.query['createMonthsTable'])
        c.execute(self.sql.query['createSessionsTable'])
        c.execute(self.sql.query['createTourneyTypesTable'])
        c.execute(self.sql.query['createTourneysTable'])
        c.execute(self.sql.query['createTourneysPlayersTable'])
        c.execute(self.sql.query['createSessionsCacheTable'])
        c.execute(self.sql.query['createTourneysCacheTable'])
        c.execute(self.sql.query['createHandsTable'])
        c.execute(self.sql.query['createHandsPlayersTable'])
        c.execute(self.sql.query['createHandsActionsTable'])
        c.execute(self.sql.query['createHandsStoveTable'])
        c.execute(self.sql.query['createHandsPotsTable'])
        c.execute(self.sql.query['createHudCacheTable'])
        c.execute(self.sql.query['createCardsCacheTable'])
        c.execute(self.sql.query['createPositionsCacheTable'])
        c.execute(self.sql.query['createBoardsTable'])
        c.execute(self.sql.query['createBackingsTable'])
        c.execute(self.sql.query['createRawHands'])
        c.execute(self.sql.query['createRawTourneys'])

        # Create unique indexes:
        log.debug("Creating unique indexes")
        c.execute(self.sql.query['addTourneyIndex'])
        c.execute(self.sql.query['addHandsIndex'].replace('<heroseat>', ', heroSeat' if self.publicDB else ''))
        c.execute(self.sql.query['addPlayersIndex'])
        c.execute(self.sql.query['addTPlayersIndex'])
        c.execute(self.sql.query['addPlayersSeat'])
        c.execute(self.sql.query['addHeroSeat'])
        c.execute(self.sql.query['addStartCardsIndex'])
        c.execute(self.sql.query['addSeatsIndex'])
        c.execute(self.sql.query['addPositionIndex'])
        c.execute(self.sql.query['addFilesIndex'])
        c.execute(self.sql.query['addTableNameIndex'])
        c.execute(self.sql.query['addPlayerNameIndex'])
        c.execute(self.sql.query['addPlayerHeroesIndex'])
        c.execute(self.sql.query['addStartCashIndex'])
        c.execute(self.sql.query['addEffStackIndex'])
        c.execute(self.sql.query['addTotalProfitIndex'])
        c.execute(self.sql.query['addWinningsIndex'])
        c.execute(self.sql.query['addFinalPotIndex'])
        c.execute(self.sql.query['addStreetIndex'])
        c.execute(self.sql.query['addSessionsCacheCompundIndex'])
        c.execute(self.sql.query['addTourneysCacheCompundIndex'])
        c.execute(self.sql.query['addHudCacheCompundIndex'])
        c.execute(self.sql.query['addCardsCacheCompundIndex'])
        c.execute(self.sql.query['addPositionsCacheCompundIndex'])

        self.fillDefaultData()
        self.commit()

    def drop_tables(self):
        """
        Drops the fpdb tables from the current db based on the backend used.

        Args:
            self: The instance of the class.

        Returns:
            None.

        Raises:
            None.
        """

        # Get the cursor for the current db.
        c = self.get_cursor()

        # Get the name of the backend used.
        backend = self.get_backend_name()

        # If backend is MySQL InnoDB.
        if backend == 'MySQL InnoDB':
            try:
                # Needed to drop tables with foreign keys.
                self.drop_referential_integrity()

                # Get list of tables.
                c.execute(self.sql.query['list_tables'])
                tables = c.fetchall()

                # Drop each table.
                for table in tables:
                    c.execute(self.sql.query['drop_table'] + table[0])

                # Enable foreign key checks.
                c.execute('SET FOREIGN_KEY_CHECKS=1')

            except Exception:
                # Print error message.
                err = traceback.extract_tb(sys.exc_info()[2])[-1]
                print(f"***Error dropping tables: {err[2]}({err[1]}): {sys.exc_info()[1]}")

                # Rollback changes if there's an error.
                self.rollback()

        # If backend is PostgreSQL.
        elif backend == 'PostgreSQL':
            try:
                # Commit changes before dropping tables.
                self.commit()

                # Get list of tables.
                c.execute(self.sql.query['list_tables'])
                tables = c.fetchall()

                # Drop each table.
                for table in tables:
                    c.execute(self.sql.query['drop_table'] + table[0] + ' cascade')

            except Exception:
                # Print error message.
                err = traceback.extract_tb(sys.exc_info()[2])[-1]
                print(
                    "***Error dropping tables:",
                    f"{err[2]}({str(err[1])}): {str(sys.exc_info()[1])}",
                )
                # Rollback changes if there's an error.
                self.rollback()

        # If backend is SQLite.
        elif backend == 'SQLite':
            # Get list of tables.
            c.execute(self.sql.query['list_tables'])

            # Drop each table except sqlite_stat1.
            for table in c.fetchall():
                if table[0] != 'sqlite_stat1':
                    log.info(f"{self.sql.query['drop_table']} '{table[0]}'")
                    c.execute(self.sql.query['drop_table'] + table[0])

        # Commit the changes to the db.
        self.commit() 


    #end def drop_tables

    def createAllIndexes(self):
        """Create new indexes."""

        # Allow table/index operations to work if using PostgreSQL
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)

        c = self.get_cursor()

        # Iterate through indexes and create them
        for idx in self.indexes[self.backend]:
            log.info(f"Creating index {idx['tab']} {idx['col']}")

            # If using MySQL InnoDB, use this syntax
            if self.backend == self.MYSQL_INNODB:
                s = f"CREATE INDEX {idx['col']} ON {idx['tab']}({idx['col']})"
                c.execute(s)

            # If using PostgreSQL or SQLite, use this syntax
            elif self.backend in [self.PGSQL, self.SQLITE]:
                s = f"CREATE INDEX {idx['tab']}_{idx['col']}_idx ON {idx['tab']}({idx['col']})"
                c.execute(s)

        # Set isolation level back to normal if using PostgreSQL
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(1)
        #end def createAllIndexes

    def dropAllIndexes(self):
        """
        Drop all standalone indexes (i.e. not including primary keys or foreign keys)
        using list of indexes in indexes data structure.
        """
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)   # allow table/index operations to work
        for idx in self.indexes[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                # print which index is being dropped
                print((("Dropping index:"), idx['tab'], idx['col']))
                try:
                    # drop the index
                    self.get_cursor().execute( "alter table %s drop index %s"
                                            , (idx['tab'], idx['col']) )
                except Exception:
                    # print error message if index cannot be dropped
                    print("Drop index failed:", sys.exc_info())
            elif self.backend == self.PGSQL:
                # print which index is being dropped
                print((("Dropping index:"), idx['tab'], idx['col']))
                # mod to use tab_col for index name?
                try:
                    # drop the index
                    self.get_cursor().execute(f"drop index {idx['tab']}_{idx['col']}_idx")
                except Exception:
                    # print error message if index cannot be dropped
                    print((("Drop index failed:"), str(sys.exc_info())))
            elif self.backend == self.SQLITE:
                # print which index is being dropped
                print((("Dropping index:"), idx['tab'], idx['col']))
                try:
                    # drop the index
                    self.get_cursor().execute(f"drop index {idx['tab']}_{idx['col']}_idx")
                except Exception:
                    # print error message if index cannot be dropped
                    print("Drop index failed:", sys.exc_info())
            else:
                return -1
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(1)   # go back to normal isolation level

    #end def dropAllIndexes

    def createAllForeignKeys(self):
        """
        Create foreign keys.
        """
        try:
            if self.backend == self.PGSQL:
                # Allow table/index operations to work.
                self.connection.set_isolation_level(0)
            c = self.get_cursor()
        except Exception:
            print("set_isolation_level failed:", sys.exc_info())

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                # Select constraint_name from information_schema.KEY_COLUMN_USAGE.
                c.execute("SELECT constraint_name "
                        "FROM information_schema.KEY_COLUMN_USAGE "
                        #"WHERE REFERENCED_TABLE_SCHEMA = 'fpdb'
                        "WHERE 1=1 "
                        "AND table_name = %s AND column_name = %s "
                        "AND referenced_table_name = %s "
                        "AND referenced_column_name = %s ",
                        (fk['fktab'], fk['fkcol'], fk['rtab'], fk['rcol']))
                cons = c.fetchone()
                # print("afterbulk: cons=", cons)
                if not cons:
                    print("Creating foreign key:", fk['fktab'], fk['fkcol'], "->", fk['rtab'], fk['rcol'])
                    try:
                        c.execute("alter table " + fk['fktab'] + " add foreign key ("
                                + fk['fkcol'] + ") references " + fk['rtab'] + "("
                                + fk['rcol'] + ")")
                    except Exception:
                        print("Create foreign key failed:", sys.exc_info())
            elif self.backend == self.PGSQL:
                print("Creating foreign key:", fk['fktab'], fk['fkcol'], "->", fk['rtab'], fk['rcol'])
                try:
                    c.execute("alter table " + fk['fktab'] + " add constraint "
                            + fk['fktab'] + '_' + fk['fkcol'] + '_fkey'
                            + " foreign key (" + fk['fkcol']
                            + ") references " + fk['rtab'] + "(" + fk['rcol'] + ")")
                except Exception:
                    print("Create foreign key failed:", sys.exc_info())
        try:
            if self.backend == self.PGSQL:
                # Go back to normal isolation level.
                self.connection.set_isolation_level(1)
        except Exception:
            print("set_isolation_level failed:", sys.exc_info())

    #end def createAllForeignKeys

    def dropAllForeignKeys(self):
        """Drop all standalone indexes (i.e. not including primary keys or foreign keys)
           using list of indexes in indexes data structure"""
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)   # allow table/index operations to work
        c = self.get_cursor()

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                c.execute("SELECT constraint_name " +
                          "FROM information_schema.KEY_COLUMN_USAGE " +
                          #"WHERE REFERENCED_TABLE_SHEMA = 'fpdb'
                          "WHERE 1=1 " +
                          "AND table_name = %s AND column_name = %s " +
                          "AND referenced_table_name = %s " +
                          "AND referenced_column_name = %s ",
                          (fk['fktab'], fk['fkcol'], fk['rtab'], fk['rcol']) )
                if cons := c.fetchone():
                    print(("Dropping foreign key:"), cons[0], fk['fktab'], fk['fkcol'])
                    try:
                        # Drop foreign key constraint.
                        c.execute("alter table " + fk['fktab'] + " drop foreign key " + cons[0])
                    except Exception:
                        print(("Warning:"), ("Drop foreign key %s_%s_fkey failed: %s, continuing ...") \
                                                      % (fk['fktab'], fk['fkcol'], str(sys.exc_info()[1]).rstrip('\n') ))
            elif self.backend == self.PGSQL:
#    DON'T FORGET TO RECREATE THEM!!
                # Print message to inform user that foreign key is being dropped.
                print(("Dropping foreign key:"), fk['fktab'], fk['fkcol'])
                try:
                    # try to lock table to see if index drop will work:
                    # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                    # then drop still hangs :-(  does work in some tests though??
                    # will leave code here for now pending further tests/enhancement ...
                    c.execute("BEGIN TRANSACTION")
                    c.execute(f"lock table {fk['fktab']} in exclusive mode nowait")
                    #print "after lock, status:", c.statusmessage
                    #print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                    try:
                        # Drop foreign key constraint.
                        c.execute(
                            f"alter table {fk['fktab']} drop constraint {fk['fktab']}_{fk['fkcol']}_fkey"
                        )
                        print(f"dropped foreign key {fk['fktab']}_{fk['fkcol']}_fkey, continuing ...")
                    except Exception:
                        if "does not exist" not in str(sys.exc_info()[1]):
                            print(("Warning:"), ("Drop foreign key %s_%s_fkey failed: %s, continuing ...") \
                                                      % (fk['fktab'], fk['fkcol'], str(sys.exc_info()[1]).rstrip('\n') ))
                    c.execute("END TRANSACTION")
                except Exception:
                    print(("Warning:"), ("constraint %s_%s_fkey not dropped: %s, continuing ...") \
                                              % (fk['fktab'],fk['fkcol'], str(sys.exc_info()[1]).rstrip('\n')))
            else:
                #print ("Only MySQL and Postgres supported so far")
                pass

        if self.backend == self.PGSQL:
            self.connection.set_isolation_level(1)   # go back to normal isolation level
    #end def dropAllForeignKeys


    def fillDefaultData(self):
        """
        Fills the database with default data.
        """
        c = self.get_cursor()

        # Insert database version
        c.execute(f"INSERT INTO Settings (version) VALUES ({DB_VERSION});")

        # Fill Sites table with default data
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('1', 'Full Tilt Poker', 'FT')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('2', 'PokerStars', 'PS')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('3', 'Everleaf', 'EV')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('4', 'Boss', 'BM')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('5', 'OnGame', 'OG')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('6', 'UltimateBet', 'UB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('7', 'Betfair', 'BF')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('8', 'Absolute', 'AB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('9', 'PartyPoker', 'PP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('10', 'PacificPoker', 'P8')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('11', 'Partouche', 'PA')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('12', 'Merge', 'MN')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('13', 'PKR', 'PK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('14', 'iPoker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('15', 'Winamax', 'WM')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('16', 'Everest', 'EP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('17', 'Cake', 'CK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('18', 'Entraction', 'TR')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('19', 'BetOnline', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('20', 'Microgaming', 'MG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('21', 'Bovada', 'BV')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('22', 'Enet', 'EN')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('23', 'SealsWithClubs', 'SW')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('24', 'WinningPoker', 'WP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('25', 'PokerMaster', 'PM')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('26', 'Run It Once Poker', 'RO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('27', 'GGPoker', 'GG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('28', 'KingsClub', 'KC')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('29', 'PokerBros', 'PB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('30', 'Unibet', 'UN')")
        #c.execute("INSERT INTO Sites (id,name,code) VALUES ('31', 'PMU Poker', 'PM')")

        #Fill Actions
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('1', 'ante', 'A')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('2', 'small blind', 'SB')")
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
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('16', 'button blind', 'BUB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('17', 'cashout', 'CO')")

        #Fill Rank
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

        #Fill StartCards
        sql = "INSERT INTO StartCards (category, name, rank, combinations) VALUES (%s, %s, %s, %s)".replace('%s', self.sql.query['placeholder'])
        for i in range(170):
            (name, rank, combinations) = Card.StartCardRank(i)
            c.execute(sql,  ('holdem', name, rank, combinations))
        for idx in range(-13,1184):
            name = Card.decodeRazzStartHand(idx)
            c.execute(sql, ('razz', name, idx, 0))        

    #end def fillDefaultData

    def rebuild_indexes(self, start=None):
        """
        Rebuilds all indexes and foreign keys for the table.

        Args:
            start (Optional[any]): The starting point for the index rebuild.
        """
        # Drop all existing indexes
        self.dropAllIndexes()

        # Create new indexes
        self.createAllIndexes()

        # Drop all foreign keys
        self.dropAllForeignKeys()

        # Create new foreign keys
        self.createAllForeignKeys()
    #end def rebuild_indexes
    
    def replace_statscache(self, type, table, query):
        """
        Replaces stats cache with query to generate stats table

        :param type: string representing type of game (e.g. "tour")
        :param table: string representing name of table to replace
        :param query: string representing query to generate stats table
        :return: string representing modified query
        """
        if table == 'HudCache':
            # Define columns to insert
            insert = """HudCache
                (gametypeId
                ,playerId
                ,seats
                ,position
                <tourney_insert_clause>
                ,styleKey"""

            # Define columns to select
            select = """h.gametypeId
                    ,hp.playerId
                    ,h.seats as seat_num
                    <hc_position>
                    <tourney_select_clause>
                    <styleKey>"""

            # Define columns to group by
            group = """h.gametypeId
                        ,hp.playerId
                        ,seat_num
                        ,hc_position
                        <tourney_group_clause>
                        <styleKeyGroup>"""

            # Replace placeholders in query with actual values
            query = query.replace('<insert>', insert)
            query = query.replace('<select>', select)
            query = query.replace('<group>', group)
            query = query.replace('<sessions_join_clause>', "")

            if self.build_full_hudcache:
                # Build query for full hudcache
                query = query.replace('<hc_position>', """,case when hp.position = 'B' then 'B'
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
                    end                                            as hc_position""")
                if self.backend == self.PGSQL:
                    query = query.replace('<styleKey>', ",'d' || to_char(h.startTime, 'YYMMDD')")
                    query = query.replace('<styleKeyGroup>', ",to_char(h.startTime, 'YYMMDD')")
                elif self.backend == self.SQLITE:
                    query = query.replace('<styleKey>', ",'d' || substr(strftime('%Y%m%d', h.startTime),3,7)")
                    query = query.replace('<styleKeyGroup>', ",substr(strftime('%Y%m%d', h.startTime),3,7)")
                elif self.backend == self.MYSQL_INNODB:
                    query = query.replace('<styleKey>', ",date_format(h.startTime, 'd%y%m%d')")
                    query = query.replace('<styleKeyGroup>', ",date_format(h.startTime, 'd%y%m%d')")
            else:
                # Build query for partial hudcache
                query = query.replace('<hc_position>', ",'0' as hc_position")
                query = query.replace('<styleKey>', ",'A000000' as styleKey")
                query = query.replace('<styleKeyGroup>', ',styleKey')

            # Handle tournament queries
            if type == 'tour':
                query = query.replace('<tourney_insert_clause>', ",tourneyTypeId")
                query = query.replace('<tourney_select_clause>', ",t.tourneyTypeId")
                query = query.replace('<tourney_group_clause>', ",t.tourneyTypeId")
            else:
                query = query.replace('<tourney_insert_clause>', "")
                query = query.replace('<tourney_select_clause>',"")
                query = query.replace('<tourney_group_clause>', "")
                
        elif table == 'PositionsCache':
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
                        
            query = query.replace('<insert>', insert)
            query = query.replace('<select>', select)
            query = query.replace('<group>', group)
            query = query.replace('<hero_join>', '')
            query = query.replace('<sessions_join_clause>', """INNER JOIN Sessions s ON (s.id = h.sessionId)
                INNER JOIN Players p ON (hp.playerId = p.id)""")
            query = query.replace('<hero_where>', "")
            
            if type == 'tour':
                query = query.replace('<tourney_insert_clause>', ",tourneyTypeId")
                query = query.replace('<tourney_select_clause>', ",t.tourneyTypeId")
                query = query.replace('<tourney_group_clause>', ",t.tourneyTypeId")
            else:
                query = query.replace('<tourney_insert_clause>', "")
                query = query.replace('<tourney_select_clause>', "")
                query = query.replace('<tourney_group_clause>', "")
                
        return query

    def rebuild_cache(self, h_start=None, v_start=None, table = 'HudCache', ttid = None, wmid = None):
        """
        Clears hudcache and rebuilds from the individual handsplayers records.

        Args:
            h_start (str): The start time for hero hand records.
            v_start (str): The start time for villain hand records.
            table (str): The name of the table to rebuild.
            ttid (int): The ID of the tourney to rebuild from.
            wmid (tuple): The week and month IDs to rebuild from.

        Returns:
            None

        """
        stime = time()
        # derive list of program owner's player ids
        self.hero = {}                               # name of program owner indexed by site id
        self.hero_ids = {'dummy':-53, 'dummy2':-52}  # playerid of owner indexed by site id
        if h_start or v_start:
            for site in self.config.get_supported_sites():
                if result := self.get_site_id(site):
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    if p_id := self.get_player_id(
                        self.config, site, self.hero[site_id]
                    ):
                        self.hero_ids[site_id] = int(p_id)

            if not h_start:
                h_start = self.hero_hudstart_def
            if not v_start:
                v_start = self.villain_hudstart_def

        else:
            self.hero_ids = None
        if not ttid and not wmid:
            self.get_cursor().execute(self.sql.query[f'clear{table}'])
            self.commit()

        if not ttid:
            if self.hero_ids is None:
                if wmid:
                    where = "WHERE g.type = 'ring' AND weekId = %s and monthId = %s<hero_where>" % wmid
                else:
                    where = "WHERE g.type = 'ring'<hero_where>"
            else:
                where = f"where (((hp.playerId not in {tuple(self.hero_ids.values())}" \
                                    f"       and h.startTime > '{v_start}')" \
                                    f"   or (hp.playerId in {tuple(self.hero_ids.values())}" \
                                    f"       and h.startTime > '{h_start}'))" \
                                    f"   AND hp.tourneysPlayersId IS NULL)"

            rebuild_sql_cash = self.sql.query['rebuildCache'].replace('%s', self.sql.query['placeholder'])
            rebuild_sql_cash = rebuild_sql_cash.replace('<tourney_join_clause>', "")
            rebuild_sql_cash = rebuild_sql_cash.replace('<where_clause>', where)
            rebuild_sql_cash = self.replace_statscache('ring', table, rebuild_sql_cash)
            #print rebuild_sql_cash 
            self.get_cursor().execute(rebuild_sql_cash)
            self.commit()
            #print ("Rebuild cache(cash) took %.1f seconds") % (time() - stime,)

        if ttid:
            where = f"WHERE t.tourneyTypeId = {ttid}<hero_where>"
        elif self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'tour' AND weekId = %s and monthId = %s<hero_where>" % wmid
            else:
                where = "WHERE g.type = 'tour'<hero_where>"
        else:
            where = f"where (((hp.playerId not in {tuple(self.hero_ids.values())}" \
                                f"       and h.startTime > '{v_start}')" \
                                f"   or (hp.playerId in {tuple(self.hero_ids.values())}" \
                                f"       and h.startTime > '{h_start}'))" \
                                f"   AND hp.tourneysPlayersId >= 0)"

        rebuild_sql_tourney = self.sql.query['rebuildCache'].replace('%s', self.sql.query['placeholder'])
        rebuild_sql_tourney = rebuild_sql_tourney.replace('<tourney_join_clause>', """INNER JOIN Tourneys t ON (t.id = h.tourneyId)""")
        rebuild_sql_tourney = rebuild_sql_tourney.replace('<where_clause>', where)
        rebuild_sql_tourney = self.replace_statscache('tour', table, rebuild_sql_tourney)
        #print rebuild_sql_tourney
        self.get_cursor().execute(rebuild_sql_tourney)
        self.commit()
        #print ("Rebuild hudcache took %.1f seconds") % (time() - stime,)
    #end def rebuild_cache
    
    def update_timezone(self, tz_name):
        """
        This function updates all session times to a given timezone.
        :param tz_name: string name of the timezone to convert to.
        """
        # Get the SQL queries to execute
        select_W = self.sql.query['select_W'].replace('%s', self.sql.query['placeholder'])
        select_M = self.sql.query['select_M'].replace('%s', self.sql.query['placeholder'])
        insert_W = self.sql.query['insert_W'].replace('%s', self.sql.query['placeholder'])
        insert_M = self.sql.query['insert_M'].replace('%s', self.sql.query['placeholder'])
        update_WM_S = self.sql.query['update_WM_S'].replace('%s', self.sql.query['placeholder'])

        # Get all sessions and update their times
        c = self.get_cursor()
        c.execute("SELECT id, sessionStart, weekId wid, monthId mid FROM Sessions")
        sessions = self.fetchallDict(c,['id','sessionStart','wid', 'mid'])
        for s in sessions:
            # Change the timezone of the session start time
            utc_start = pytz.utc.localize(s['sessionStart'])
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime('%z')
            offset = timedelta(hours=int(loc_tz[:-2]), minutes=int(loc_tz[0]+loc_tz[-2:]))
            local = s['sessionStart'] + offset

            # Get the start of the month and the start of the week for the session
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day) 
            weekStart = weekdate - timedelta(days=weekdate.weekday())

            # Insert or update the month and week in the database
            wid = self.insertOrUpdate('weeks', c, (weekStart,), select_W, insert_W)
            mid = self.insertOrUpdate('months', c, (monthStart,), select_M, insert_M)

            # Update the session with the new month and week
            if wid != s['wid'] or mid != s['mid']:
                row = [wid, mid, s['id']]
                c.execute(update_WM_S, row)
                self.wmold.add((s['wid'], s['mid']))
                self.wmnew.add((wid, mid))

        # Commit the changes to the database and clean up old weeks and months
        self.commit()
        self.cleanUpWeeksMonths()

    def get_hero_hudcache_start(self):
        """fetches earliest stylekey from hudcache for one of hero's player ids"""

        self.hero_ids = {'dummy':-53, 'dummy2':-52}  # playerid of owner indexed by site id
        # get all player ids in one query
        q = self.sql.query['get_player_ids'].replace("<playerid_list>", str(tuple(self.hero_ids.values())))
        c = self.get_cursor()
        c.execute(q)
        for (player_id,) in c.fetchall():
            site_id = next((site_id for site_id, id_ in self.hero_ids.items() if id_ == player_id), None)
            if site_id is not None:
                self.hero_ids[site_id] = player_id

        # get earliest stylekey
        q = self.sql.query['get_hero_hudcache_start'].replace("<playerid_list>", str(tuple(self.hero_ids.values())))
        with self.get_cursor() as c:
            c.execute(q)
            tmp = c.fetchone()
            if tmp == (None,):
                return self.hero_hudstart_def
            else:
                return f"20{tmp[0][1:3]}-{tmp[0][3:5]}-{tmp[0][5:7]}"

    #end def get_hero_hudcache_start


    def analyzeDB(self):
        """Do whatever the DB can offer to update index/table statistics"""

        # Start time to measure performance
        stime = time()

        # Analyze database statistics for supported backends
        if self.backend in [self.MYSQL_INNODB, self.SQLITE]:
            try:
                self.get_cursor().execute(self.sql.query['analyze'])
            except Exception:
                # If there's an error, print it to the console
                print("Error during analyze:", sys.exc_info()[1])
        elif self.backend == self.PGSQL:
            # Set isolation level to 0 to allow analyze to work
            self.connection.set_isolation_level(0)
            try:
                self.get_cursor().execute(self.sql.query['analyze'])
            except Exception:
                # If there's an error, print it to the console
                print("Error during analyze:", sys.exc_info()[1])
            # Set isolation level back to 1 to return to normal
            self.connection.set_isolation_level(1)

        # Commit changes to the database
        self.commit()

        # Measure time elapsed and log it
        atime = time() - stime
        log.info(("Analyze took %.1f seconds") % (atime,))

    #end def analyzeDB

    def vacuumDB(self):
        """
        Do whatever the DB can offer to update index/table statistics
        """
        stime = time() # record start time
        # execute vacuum command based on backend type
        if self.backend in [self.MYSQL_INNODB, self.SQLITE]:
            try:
                self.get_cursor().execute(self.sql.query['vacuum'])
            except Exception:
                print("Error during vacuum:", sys.exc_info()[1])
        elif self.backend == self.PGSQL:
            self.connection.set_isolation_level(0)   # allow vacuum to work
            try:
                self.get_cursor().execute(self.sql.query['vacuum'])
            except Exception:
                print("Error during vacuum:", sys.exc_info()[1])
            self.connection.set_isolation_level(1)   # go back to normal isolation level
        self.commit() # commit changes to database
        atime = time() - stime # calculate elapsed time
        print(("Vacuum took %.1f seconds") % (atime,))

    #end def analyzeDB

# Start of Hand Writing routines. Idea is to provide a mixture of routines to store Hand data
# however the calling prog requires. Main aims:
# - existing static routines from fpdb_simple just modified

    def setThreadId(self, threadid):
        """
        Sets the thread ID for this object.

        Args:
            threadid (int): The ID of the thread to set.
        """
        # Set the thread ID.
        self.threadId = threadid

                
    def acquireLock(self, wait=True, retry_time=.01):
        """
        Acquires a lock on the table.

        Args:
            wait (bool): If True, wait until lock is available.
            retry_time (float): Time to wait between retries.

        Returns:
            bool: True if lock is acquired, False otherwise.
        """
        while not self._has_lock:
            cursor = self.get_cursor()
            num = cursor.execute(self.sql.query['switchLockOn'], (True, self.threadId))
            self.commit()
            if (self.backend == self.MYSQL_INNODB and num == 0):
                # If MySQL InnoDB is used and lock cannot be acquired, wait for retry_time seconds
                if not wait:
                    return False
                sleep(retry_time)
            else:
                # Lock has been acquired
                self._has_lock = True
                return True

    

    def releaseLock(self):
        """
        Release the lock.
        """
        if self._has_lock:
            # Get cursor and execute query to switch off lock
            cursor = self.get_cursor()
            num = cursor.execute(self.sql.query['switchLockOff'], (False, self.threadId))
            # Commit changes and update class variable
            self.commit()
            self._has_lock = False

    def lock_for_insert(self):
        """Lock tables in MySQL to try to speed inserts up"""
        try:
            self.get_cursor().execute(self.sql.query['lockForInsert'])
        except Exception:
            print("Error during lock_for_insert:", sys.exc_info()[1])
    #end def lock_for_insert
    
    def resetBulkCache(self, reconnect=False):
        """
        Resets all bulk cache attributes to empty lists or dictionaries, and reconnects to the database if
        the `reconnect` parameter is set to True.

        :param reconnect: A boolean indicating whether to reconnect to the database.
        """
        self.siteHandNos = []         # cache of siteHandNo
        self.hbulk       = []         # Hands bulk inserts
        self.bbulk       = []         # Boards bulk inserts
        self.hpbulk      = []         # HandsPlayers bulk inserts
        self.habulk      = []         # HandsActions bulk inserts
        self.hcbulk      = {}         # HudCache bulk inserts
        self.dcbulk      = {}         # CardsCache bulk inserts
        self.pcbulk      = {}         # PositionsCache bulk inserts
        self.hsbulk      = []         # HandsStove bulk inserts
        self.htbulk      = []         # HandsPots bulk inserts
        self.tbulk       = {}         # Tourneys bulk updates
        self.s          = {'bk': []} # Sessions bulk updates
        self.sc          = {}         # SessionsCache bulk updates
        self.tc          = {}         # TourneysCache bulk updates
        self.hids        = []         # hand ids in order of hand bulk inserts
        #self.tids        = []         # tourney ids in order of hp bulk inserts
        if reconnect: self.do_connect(self.config)
        
    def executemany(self, c, q, values):
        """
        Execute a database query with multiple sets of parameters.

        Args:
        c: cursor object.
        q: SQL query to execute.
        values: Iterable containing the parameters for the query.
        Returns:
        None
        """
        if self.backend == self.PGSQL and self.import_options['hhBulkPath'] != "":
            # COPY much faster under postgres. Requires superuser privileges
            m = re_insert.match(q)
            rand = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(5))
            bulk_file = os.path.join(self.import_options['hhBulkPath'], m.group("TABLENAME") + '_' + rand)
            with open(bulk_file, 'wb') as csvfile:
                writer = csv.writer(csvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerows(w for w in values)
            q_insert = "COPY " + m.group("TABLENAME") + m.group("COLUMNS") + " FROM '" + bulk_file + "' DELIMITER '\t' CSV"
            c.execute(q_insert)
            os.remove(bulk_file)
        else:            
            batch_size=20000 #experiment to find optimal batch_size for your data
            while values: # repeat until all records in values have been inserted ''
                batch, values = values[:batch_size], values[batch_size:] #split values into the current batch and the remaining records
                c.executemany(q, batch ) #insert current batch ''

    def storeHand(self, hdata, doinsert=False, printdata=False):
        """
        Store a hand data to the database.

        Args:
        - hdata: dict, data of the hand to be stored
        - doinsert: bool, whether to insert the data to the database or not
        - printdata: bool, whether to print the hand data or not

        Returns:
        - None
        """

        # Print hand data if requested
        if printdata:
            print("######## Hands ##########")
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(hdata)
            print("###### End Hands ########")

        # Truncate table name to 50 characters
        hdata["tableName"] = Charset.to_db_utf8(hdata["tableName"])[:50]

        # Add hand id to the list of hand ids
        self.hids.append(hdata["id"])

        # Append hand data to the list of bulk data
        self.hbulk.append(
            [
                hdata["tableName"],
                hdata["siteHandNo"],
                hdata["tourneyId"],
                hdata["gametypeId"],
                hdata["sessionId"],
                hdata["fileId"],
                hdata["startTime"].replace(tzinfo=None),
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
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
            ]
        )

        # Insert hand data to the database if requested
        if doinsert:
            self.appendHandsSessionIds()
            self.updateTourneysSessions()
            q = self.sql.query["store_hand"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.executemany(q, self.hbulk)
            self.commit()

    
    def storeBoards(self, id, boards, doinsert):
        """
        Stores boards in bulk for a given ID.

        Args:
            id (int): The ID to associate with the boards.
            boards (list): A list of board objects.
            doinsert (bool): Indicates if the boards should be inserted into the database.

        Returns:
            None
        """
        # If there are any boards, add them to the bulk list
        if boards: 
            for b in boards:
                self.bbulk += [[id] + b]

        # If we're supposed to insert and we have boards to insert, do so
        if doinsert and self.bbulk:
            q = self.sql.query['store_boards']
            q = q.replace('%s', self.sql.query['placeholder'])
            c = self.get_cursor()
            self.executemany(c, q, self.bbulk) #c.executemany(q, self.bbulk)

    
    def updateTourneysSessions(self):
        """
        Update tournament sessions in the database.
        """
        # Check if there are any tournaments to update
        if self.tbulk:
            # Prepare the query for updating tournament sessions
            q_update_sessions = self.sql.query['updateTourneysSessions'].replace('%s', self.sql.query['placeholder'])
            # Get a cursor object
            c = self.get_cursor()
            # Loop through each tournament and its session ID in the bulk
            for t, sid in list(self.tbulk.items()):
                # Execute the update query with the session ID and tournament ID as parameters
                c.execute(q_update_sessions,  (sid, t))
                # Commit the update to the database
                self.commit()


    def storeHandsPlayers(self, hid, pids, pdata, doinsert = False, printdata = False):
        """
        Stores information about hands and players in the database.

        Args:
            hid (int): Hand ID.
            pids (dict): Dictionary with player IDs.
            pdata (dict): Dictionary with player data.
            do_insert (bool, optional): If True, the data is inserted into the database. Defaults to False.
            print_data (bool, optional): If True, the data is printed. Defaults to False.
        """
        # Print the data if required
        if printdata:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(pdata)

        hpbulk = self.hpbulk
        for p, pvalue in list(pdata.items()):
            # Add (hid, pids[p]) + all the values in pvalue at the
            # keys in HANDS_PLAYERS_KEYS to hpbulk.
            bulk_data = [pvalue[key] for key in HANDS_PLAYERS_KEYS]
            bulk_data.extend((pids[p], hid))
            bulk_data.reverse()
            hpbulk.append(bulk_data)

        # If required, insert the data into the database
        if doinsert:
            q = self.sql.query['store_hands_players']
            q = q.replace('%s', self.sql.query['placeholder'])
            c = self.get_cursor(True)
            self.executemany(c, q, self.hpbulk) #c.executemany(q, self.hpbulk)
            
    def storeHandsPots(self, tdata, doinsert):
        """
        Store hands and pots in the database.

        Args:
            tdata (list): List of tuples, each tuple contains the data for a single hand.
            doinsert (bool): Whether or not to insert the data into the database.

        Returns:
            None
        """
        # Add new data to bulk data list
        self.htbulk += tdata

        # If doinsert is True and there is bulk data to insert
        if doinsert and self.htbulk:
            # Get the SQL query
            q = self.sql.query['store_hands_pots']
            q = q.replace('%s', self.sql.query['placeholder'])

            # Get the database cursor
            c = self.get_cursor()

            # Execute the SQL query with the bulk data
            self.executemany(c, q, self.htbulk)


    def storeHandsActions(self, hid, pids, adata, doinsert=False, printdata=False):
        """
        Store hands actions in the habulk list and if doinsert is True,
        write the list to the database.

        Args:
        hid (int): hand id
        pids (List[int]): list of player ids
        adata (Dict): dictionary containing action data
        doinsert (bool): flag to determine if data should be written to database
        printdata (bool): flag to print adata dictionary

        Returns:
        None
        """
        #print "DEBUG: %s %s %s" %(hid, pids, adata)

        # This can be used to generate test data. Currently unused
        #if printdata:
        #    import pprint
        #    pp = pprint.PrettyPrinter(indent=4)
        #    pp.pprint(adata)

        for a in adata:
            self.habulk.append(
                (hid,
                pids[adata[a]['player']],
                adata[a]['street'],
                adata[a]['actionNo'],
                adata[a]['streetActionNo'],
                adata[a]['actionId'],
                adata[a]['amount'],
                adata[a]['raiseTo'],
                adata[a]['amountCalled'],
                adata[a]['numDiscarded'],
                adata[a]['cardsDiscarded'],
                adata[a]['allIn']
                )
            )

        if doinsert:
            q = self.sql.query['store_hands_actions']
            q = q.replace('%s', self.sql.query['placeholder'])
            c = self.get_cursor()
            self.executemany(c, q, self.habulk) #c.executemany(q, self.habulk)

    
    def storeHandsStove(self, sdata, doinsert):
        """
        Store hand stove data in bulk into a database.

        Args:
            sdata (list): List of tuples containing hand stove data.
            doinsert (bool): If True, data is inserted into the database.

        Returns:
            None
        """
        # Append sdata to hsbulk
        self.hsbulk += sdata

        # If doinsert is True and hsbulk is not empty
        if doinsert and self.hsbulk:
            # Get the store hands stove query and replace %s with placeholder
            q = self.sql.query['store_hands_stove']
            q = q.replace('%s', self.sql.query['placeholder'])

            # Get cursor and execute the query
            c = self.get_cursor()
            self.executemany(c, q, self.hsbulk)

            
    def storeHudCache(self, gid, gametype, pids, starttime, pdata, doinsert=False):
        """
        Update cached statistics. If update fails because no record exists, do an insert.
        :param gid: int
        :param gametype: str
        :param pids: dict
        :param starttime: datetime
        :param pdata: dict
        :param doinsert: bool
        """
        if pdata:   
            # Get timezone offset
            tz = datetime.now(timezone.utc) - datetime.now(timezone.utc)
            tz_offset = old_div(tz.seconds,3600)
            tz_day_start_offset = self.day_start + tz_offset

            d = timedelta(hours=tz_day_start_offset)
            starttime_offset = starttime - d
            styleKey = datetime.strftime(starttime_offset, 'd%y%m%d')
            seats = len(pids)

        # Map position to shorthand
        pos = {'B':'B', 'S':'S', 0:'D', 1:'C', 2:'M', 3:'M', 4:'M', 5:'E', 6:'E', 7:'E', 8:'E', 9:'E' }

        for p in pdata:
            player_stats = pdata.get(p)
            garbageTourneyTypes = player_stats['tourneyTypeId'] in self.ttnew or player_stats['tourneyTypeId'] in self.ttold
            if self.import_options['hhBulkPath'] == "" or not garbageTourneyTypes:
                position = pos[player_stats['position']]
                k =   (gid
                    ,pids[p]
                    ,seats
                    ,position if self.build_full_hudcache else '0'
                    ,player_stats['tourneyTypeId']
                    ,styleKey if self.build_full_hudcache else 'A000000'
                    )
                player_stats['n'] = 1
                line = [int(player_stats[s]) if isinstance(player_stats[s],bool) else player_stats[s] for s in CACHE_KEYS]

                hud = self.hcbulk.get(k)
                # Add line to the old line in the hudcache.
                if hud is not None:
                    for idx,val in enumerate(line):
                        hud[idx] += val
                else:
                    self.hcbulk[k] = line

        if doinsert:
            update_hudcache = self.sql.query['update_hudcache']
            update_hudcache = update_hudcache.replace('%s', self.sql.query['placeholder'])
            insert_hudcache = self.sql.query['insert_hudcache']
            insert_hudcache = insert_hudcache.replace('%s', self.sql.query['placeholder'])

            select_hudcache_ring = self.sql.query['select_hudcache_ring']
            select_hudcache_ring = select_hudcache_ring.replace('%s', self.sql.query['placeholder'])
            select_hudcache_tour = self.sql.query['select_hudcache_tour']
            select_hudcache_tour = select_hudcache_tour.replace('%s', self.sql.query['placeholder'])
            inserts = []
            c = self.get_cursor()
            for k, item in list(self.hcbulk.items()):

                if not k[4]:
                    q = select_hudcache_ring
                    row = list(k[:4]) + [k[-1]]
                else:
                    q = select_hudcache_tour
                    row = list(k)

                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = item + [id]
                    c.execute(update_hudcache, update)

                else:
                    inserts.append(list(k) + item)

            if inserts:
                self.executemany(c, insert_hudcache, inserts)
            self.commit()

            
    def storeSessions(self, hid, pids, startTime, tid, heroes, tz_name, doinsert=False):
        """
        Update cached sessions. If no record exists, do an insert.

        Args:
            hid: Session id.
            pids: A dictionary of player ids.
            startTime: Start time of the session.
            tid: Tournament id.
            heroes: A list of heroes.
            tz_name: Timezone name.
            doinsert: A boolean flag indicating whether to insert new records.

        Returns:
            None.
        """

        # Set the threshold for the session timeout.
        THRESHOLD = timedelta(seconds=int(self.sessionTimeout * 60))

        # Handle timezone information.
        if tz_name in pytz.common_timezones:
            # Convert start time to UTC and then to the local timezone.
            naive = startTime.replace(tzinfo=None)
            utc_start = pytz.utc.localize(naive)
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime('%z')
            offset = timedelta(hours=int(loc_tz[:-2]), minutes=int(loc_tz[0]+loc_tz[-2:]))
            local = naive + offset

            # Calculate the start of the month and week.
            monthStart = datetime(local.year, local.month, 1)
            weekdate   = datetime(local.year, local.month, local.day)
            weekStart  = weekdate - timedelta(days=weekdate.weekday())
        else:
            if strftime('%Z') == 'UTC':
                local = startTime
                loc_tz = '0'
            else:
                tz_dt = datetime.today() - datetime.utcnow()
                loc_tz = old_div(tz_dt.seconds,3600) - 24
                offset = timedelta(hours=int(loc_tz))
                local = startTime + offset

            # Calculate the start of the month and week.
            monthStart = datetime(local.year, local.month, 1)
            weekdate   = datetime(local.year, local.month, local.day)
            weekStart  = weekdate - timedelta(days=weekdate.weekday())

        j, hand = None, {}

        # Create a dictionary of session information.
        for p, id in list(pids.items()):
            if id in heroes:
                hand['startTime']  = startTime.replace(tzinfo=None)
                hand['weekStart']  = weekStart
                hand['monthStart'] = monthStart
                hand['ids'] = [hid]
                hand['tourneys'] = set()

        id = []
        if hand:
            lower = hand['startTime']-THRESHOLD
            upper = hand['startTime']+THRESHOLD

            # Iterate over the cached sessions.
            for i in range(len(self.s['bk'])):
                if (((lower  <= self.s['bk'][i]['sessionEnd'])
                and  (upper  >= self.s['bk'][i]['sessionStart']))
                or   (tid in self.s['bk'][i]['tourneys'])):
                    if ((hand['startTime'] <= self.s['bk'][i]['sessionEnd']) 
                    and (hand['startTime'] >= self.s['bk'][i]['sessionStart'])):
                         id.append(i)
                    elif hand['startTime'] < self.s['bk'][i]['sessionStart']:
                         self.s['bk'][i]['sessionStart'] = hand['startTime']
                         self.s['bk'][i]['weekStart']    = hand['weekStart']
                         self.s['bk'][i]['monthStart']   = hand['monthStart']
                         id.append(i)
                    elif hand['startTime'] > self.s['bk'][i]['sessionEnd']:
                         self.s['bk'][i]['sessionEnd'] = hand['startTime']
                         id.append(i)
            if len(id) == 1:
                j = id[0]
                self.s['bk'][j]['ids'] += [hid]
                if tid: self.s['bk'][j]['tourneys'].add(tid)
            elif len(id) > 1:
                merged = {}
                merged['ids'] = [hid]
                merged['tourneys'] = set()
                if tid: merged['tourneys'].add(tid) 
                for n in id:
                    h = self.s['bk'][n]
                    if not merged.get('sessionStart') or merged.get('sessionStart') > h['sessionStart']:
                        merged['sessionStart'] = h['sessionStart']
                        merged['weekStart'] = h['weekStart']
                        merged['monthStart'] = h['monthStart']
                    if not merged.get('sessionEnd') or merged.get('sessionEnd') < h['sessionEnd']:
                        merged['sessionEnd'] = h['sessionEnd']
                    merged['ids'] += h['ids']
                    merged['tourneys'].union(h['tourneys'])
                    self.s['bk'][n]['delete'] = True
                    
                self.s['bk'] = [item for item in self.s['bk'] if not item.get('delete')]
                self.s['bk'].append(merged)
            elif len(id) == 0:
                j = len(self.s['bk'])
                hand['id'] = None
                hand['sessionStart'] = hand['startTime']
                hand['sessionEnd']   = hand['startTime']
                if tid: hand['tourneys'].add(tid)
                self.s['bk'].append(hand)
        
        if doinsert:
            select_S     = self.sql.query['select_S'].replace('%s', self.sql.query['placeholder'])
            select_W     = self.sql.query['select_W'].replace('%s', self.sql.query['placeholder'])
            select_M     = self.sql.query['select_M'].replace('%s', self.sql.query['placeholder'])
            update_S     = self.sql.query['update_S'].replace('%s', self.sql.query['placeholder'])
            insert_W     = self.sql.query['insert_W'].replace('%s', self.sql.query['placeholder'])
            insert_M     = self.sql.query['insert_M'].replace('%s', self.sql.query['placeholder'])
            insert_S     = self.sql.query['insert_S'].replace('%s', self.sql.query['placeholder'])
            update_S_SC  = self.sql.query['update_S_SC'].replace('%s', self.sql.query['placeholder'])
            update_S_TC  = self.sql.query['update_S_TC'].replace('%s', self.sql.query['placeholder'])
            update_S_T   = self.sql.query['update_S_T'].replace('%s', self.sql.query['placeholder'])
            update_S_H   = self.sql.query['update_S_H'].replace('%s', self.sql.query['placeholder'])
            delete_S     = self.sql.query['delete_S'].replace('%s', self.sql.query['placeholder'])
            c = self.get_cursor()
            for i in range(len(self.s['bk'])):                
                lower = self.s['bk'][i]['sessionStart'] - THRESHOLD
                upper = self.s['bk'][i]['sessionEnd']   + THRESHOLD
                tourneys = self.s['bk'][i]['tourneys']
                if (self.s['bk'][i]['tourneys']):
                    toursql = 'OR SC.id in (SELECT DISTINCT sessionId FROM Tourneys T WHERE T.id in (%s))' % ', '.join(str(t) for t in tourneys)
                    q = select_S.replace('<TOURSELECT>', toursql)
                else:
                    q = select_S.replace('<TOURSELECT>', '')
                c.execute(q, (lower, upper))
                r = self.fetchallDict(c,['id', 'sessionStart', 'sessionEnd', 'weekStart', 'monthStart', 'weekId', 'monthId'])
                num = len(r)              
                if (num == 1):
                    start, end  = r[0]['sessionStart'], r[0]['sessionEnd']
                    week, month = r[0]['weekStart'],    r[0]['monthStart']
                    wid, mid    = r[0]['weekId'],       r[0]['monthId']
                    update, updateW, updateM = False, False, False
                    if self.s['bk'][i]['sessionStart'] < start:
                        start, update = self.s['bk'][i]['sessionStart'], True
                        if self.s['bk'][i]['weekStart'] != week:
                            week, updateW = self.s['bk'][i]['weekStart'], True
                        if self.s['bk'][i]['monthStart'] != month:
                            month, updateM = self.s['bk'][i]['monthStart'], True
                        if (updateW or updateM):
                            self.wmold.add((wid, mid))
                    if self.s['bk'][i]['sessionEnd'] > end:
                        end, update = self.s['bk'][i]['sessionEnd'], True
                    if updateW:  wid = self.insertOrUpdate('weeks', c, (week,), select_W, insert_W)
                    if updateM:  mid = self.insertOrUpdate('months', c, (month,), select_M, insert_M)
                    if (updateW or updateM):
                        self.wmnew.add((wid, mid))
                    if update: 
                        c.execute(update_S, [wid, mid, start, end, r[0]['id']])
                    for h in  self.s['bk'][i]['ids']:
                        self.s[h] = {'id': r[0]['id'], 'wid': wid, 'mid': mid}
                elif (num > 1):
                    start, end, wmold, merge = None, None, set(), []
                    for n in r: merge.append(n['id'])
                    merge.sort()
                    r.append(self.s['bk'][i])
                    for n in r:
                        if 'weekId' in n:
                            wmold.add((n['weekId'],  n['monthId']))    
                        if start: 
                            if  start > n['sessionStart']: 
                                start = n['sessionStart']
                                week  = n['weekStart']
                                month = n['monthStart']
                        else: 
                            start = n['sessionStart']
                            week  = n['weekStart']
                            month = n['monthStart']
                        if end: 
                            if  end < n['sessionEnd']: 
                                end = n['sessionEnd']
                        else:
                            end = n['sessionEnd']
                    wid = self.insertOrUpdate('weeks', c, (week,), select_W, insert_W)
                    mid = self.insertOrUpdate('months', c, (month,), select_M, insert_M)
                    wmold.discard((wid, mid))
                    if len(wmold)>0:
                        self.wmold = self.wmold.union(wmold)
                        self.wmnew.add((wid, mid))
                    row = [wid, mid, start, end]
                    c.execute(insert_S, row)
                    sid = self.get_last_insert_id(c)
                    for h in self.s['bk'][i]['ids']:
                        self.s[h] = {'id': sid, 'wid': wid, 'mid': mid}
                    for m in merge:
                        for h, n in list(self.s.items()):
                            if h!='bk' and n['id'] == m:
                                self.s[h] = {'id': sid, 'wid': wid, 'mid': mid}
                        c.execute(update_S_TC,(sid, m))
                        c.execute(update_S_SC,(sid, m))
                        c.execute(update_S_T, (sid, m))
                        c.execute(update_S_H, (sid, m))
                        c.execute(delete_S, (m,))
                elif (num == 0):
                    start   =  self.s['bk'][i]['sessionStart']
                    end     =  self.s['bk'][i]['sessionEnd']
                    week    =  self.s['bk'][i]['weekStart']
                    month   =  self.s['bk'][i]['monthStart']
                    wid = self.insertOrUpdate('weeks', c, (week,), select_W, insert_W)
                    mid = self.insertOrUpdate('months', c, (month,), select_M, insert_M)
                    row = [wid, mid, start, end]
                    c.execute(insert_S, row)
                    sid = self.get_last_insert_id(c)
                    for h in self.s['bk'][i]['ids']:
                        self.s[h] = {'id': sid, 'wid': wid, 'mid': mid}
            self.commit()
    
    def storeSessionsCache(self, hid, pids, startTime, gametypeId, gametype, pdata, heroes, doinsert = False):
        """
        Update cached cash sessions. If no record exists, do an insert.
        Args:
            hid (int): some integer value.
            pids (dict): a dictionary of some sort.
            startTime (datetime): a datetime object representing the start time.
            gametypeId (int): some integer value.
            gametype (str): a string.
            pdata (dict): a dictionary of some sort.
            heroes (list): a list of some sort.
            doinsert (bool): a boolean value that determines whether to insert or not.
        """  
        THRESHOLD    = timedelta(seconds=int(self.sessionTimeout * 60))
        if pdata: #gametype['type']=='ring' and 
            for p, pid in list(pids.items()):
                hp = {}
                k = (gametypeId, pid)
                hp['startTime'] = startTime.replace(tzinfo=None)
                hp['hid']           = hid
                hp['ids']           = []
                pdata[p]['n']   = 1
                hp['line'] = [int(pdata[p][s]) if isinstance(pdata[p][s],bool) else pdata[p][s] for s in CACHE_KEYS]
                id = []
                sessionplayer = self.sc.get(k)
                if sessionplayer is not None:        
                    lower = hp['startTime']-THRESHOLD
                    upper = hp['startTime']+THRESHOLD
                    for i in range(len(sessionplayer)):
                        if lower <= sessionplayer[i]['endTime'] and upper >= sessionplayer[i]['startTime']:
                            if len(id)==0:
                                for idx,val in enumerate(hp['line']):
                                    sessionplayer[i]['line'][idx] += val
                            if ((hp['startTime'] <= sessionplayer[i]['endTime']) 
                            and (hp['startTime'] >= sessionplayer[i]['startTime'])):
                                id.append(i)
                            elif hp['startTime']  <  sessionplayer[i]['startTime']:
                                sessionplayer[i]['startTime'] = hp['startTime']
                                id.append(i)
                            elif hp['startTime']  >  sessionplayer[i]['endTime']:
                                sessionplayer[i]['endTime'] = hp['startTime']
                                id.append(i)
                if len(id) == 1:
                    i = id[0]
                    if pids[p]==heroes[0]:
                        self.sc[k][i]['ids'].append(hid)
                elif len(id) == 2:
                    i, j = id[0], id[1]
                    if    sessionplayer[i]['startTime'] < sessionplayer[j]['startTime']:
                          sessionplayer[i]['endTime']   = sessionplayer[j]['endTime']
                    else: sessionplayer[i]['startTime'] = sessionplayer[j]['startTime']
                    for idx,val in enumerate(sessionplayer[j]['line']):
                        sessionplayer[i]['line'][idx] += val
                    g = sessionplayer.pop(j)
                    if pids[p]==heroes[0]:
                        self.sc[k][i]['ids'].append(hid)
                        self.sc[k][i]['ids'] += g['ids']
                elif len(id) == 0:
                    if sessionplayer is None:
                        self.sc[k] = []
                    hp['endTime'] = hp['startTime']
                    if pids[p]==heroes[0]: hp['ids'].append(hid)
                    self.sc[k].append(hp)
        
        if doinsert:
            select_SC    = self.sql.query['select_SC'].replace('%s', self.sql.query['placeholder'])
            update_SC    = self.sql.query['update_SC'].replace('%s', self.sql.query['placeholder'])
            insert_SC    = self.sql.query['insert_SC'].replace('%s', self.sql.query['placeholder'])
            delete_SC    = self.sql.query['delete_SC'].replace('%s', self.sql.query['placeholder'])
            c = self.get_cursor()
            for k, sessionplayer in list(self.sc.items()):
                for session in sessionplayer:
                    hid = session['hid']
                    sid = self.s.get(hid)['id']
                    lower = session['startTime'] - THRESHOLD
                    upper = session['endTime']   + THRESHOLD
                    row = [lower, upper] + list(k[:2])
                    c.execute(select_SC, row)
                    r = self.fetchallDict(c, ['id', 'sessionId', 'startTime', 'endTime'] + CACHE_KEYS)
                    num = len(r)
                    d = [0]*num
                    for z in range(num):
                        d[z] = {}
                        d[z]['line'] = [int(r[z][s]) if isinstance(r[z][s],bool) else r[z][s] for s in CACHE_KEYS]
                        d[z]['id']   = r[z]['id']
                        d[z]['sessionId'] = r[z]['sessionId']
                        d[z]['startTime'] = r[z]['startTime']
                        d[z]['endTime']   = r[z]['endTime']
                    if (num == 1):
                        start, end, id = r[0]['startTime'], r[0]['endTime'], r[0]['id']
                        if session['startTime'] < start:
                            start = session['startTime']
                        if session['endTime']   > end:
                            end = session['endTime']
                        row = [start, end] + session['line'] + [id]
                        c.execute(update_SC, row)
                    elif (num > 1):
                        start, end, merge, line = None, None, [], [0]*len(CACHE_KEYS)
                        for n in r: merge.append(n['id'])
                        merge.sort()
                        r = d
                        r.append(session)
                        for n in r:
                            if start:
                                if  start > n['startTime']: 
                                    start = n['startTime']
                            else:   start = n['startTime']
                            if end: 
                                if  end < n['endTime']: 
                                    end = n['endTime']
                            else:   end = n['endTime']
                            for idx in range(len(CACHE_KEYS)):
                                line[idx] += int(n['line'][idx]) if isinstance(n['line'][idx],bool) else n['line'][idx]
                        row = [sid, start, end] + list(k[:2]) + line 
                        c.execute(insert_SC, row)
                        id = self.get_last_insert_id(c)
                        for m in merge:
                            c.execute(delete_SC, (m,))
                            self.commit()
                    elif (num == 0):
                        start               = session['startTime']
                        end                 = session['endTime']
                        row = [sid, start, end] + list(k[:2]) + session['line'] 
                        c.execute(insert_SC, row)
                        id = self.get_last_insert_id(c)              
            self.commit()
            
    def storeTourneysCache(self, hid, pids, startTime, tid, gametype, pdata, heroes, doinsert = False):
        """Update cached tour sessions. If no record exists, do an insert"""   
        if gametype['type']=='tour' and pdata:
            for p in pdata:
                k = (tid
                    ,pids[p]
                    )
                pdata[p]['n'] = 1
                line = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
                tourplayer = self.tc.get(k)
                # Add line to the old line in the tourcache.
                if tourplayer is not None:
                    for idx,val in enumerate(line):
                        tourplayer['line'][idx] += val
                    if pids[p]==heroes[0]:
                        tourplayer['ids'].append(hid)
                else:
                    self.tc[k] = {'startTime' : None,
                                    'endTime' : None,
                                        'hid' : hid,
                                        'ids' : []}
                    self.tc[k]['line'] = line
                    if pids[p]==heroes[0]:
                        self.tc[k]['ids'].append(hid)

                if not self.tc[k]['startTime'] or startTime < self.tc[k]['startTime']:
                    self.tc[k]['startTime']  = startTime
                    self.tc[k]['hid'] = hid
                if not self.tc[k]['endTime'] or startTime > self.tc[k]['endTime']:
                    self.tc[k]['endTime']    = startTime
                
        if doinsert:
            update_TC = self.sql.query['update_TC'].replace('%s', self.sql.query['placeholder'])
            insert_TC = self.sql.query['insert_TC'].replace('%s', self.sql.query['placeholder'])
            select_TC = self.sql.query['select_TC'].replace('%s', self.sql.query['placeholder'])
            
            inserts = []
            c = self.get_cursor()
            for k, tc in list(self.tc.items()):
                sc = self.s.get(tc['hid'])
                tc['startTime'] = tc['startTime'].replace(tzinfo=None)
                tc['endTime']   = tc['endTime'].replace(tzinfo=None)
                c.execute(select_TC, k)
                r = self.fetchallDict(c, ['id', 'startTime', 'endTime'])
                num = len(r)
                if (num == 1):
                    update = not r[0]['startTime'] or not r[0]['endTime']
                    if (update or (tc['startTime']<r[0]['startTime'] and tc['endTime']>r[0]['endTime'])):
                        q = update_TC.replace('<UPDATE>', 'startTime=%s, endTime=%s,')
                        row = [tc['startTime'], tc['endTime']] + tc['line'] + list(k[:2])
                    elif tc['startTime']<r[0]['startTime']:
                        q = update_TC.replace('<UPDATE>', 'startTime=%s, ')
                        row = [tc['startTime']] + tc['line'] + list(k[:2])
                    elif tc['endTime']>r[0]['endTime']:
                        q = update_TC.replace('<UPDATE>', 'endTime=%s, ')
                        row = [tc['endTime']] + tc['line'] + list(k[:2])
                    else:
                        q = update_TC.replace('<UPDATE>', '')
                        row = tc['line'] + list(k[:2])
                    c.execute(q, row)
                elif (num == 0):
                    row = [sc['id'], tc['startTime'], tc['endTime']] + list(k[:2]) + tc['line']
                    #append to the bulk inserts
                    inserts.append(row)
                
            if inserts:
                self.executemany(c, insert_TC, inserts)
            self.commit()
    
    def storeCardsCache(self, hid, pids, startTime, gametypeId, tourneyTypeId, pdata, heroes, tz_name, doinsert):
        """
        Update cached cash sessions. If no record exists, do an insert.
        Args:
            hid (int): some integer value.
            pids (dict): a dictionary of some sort.
            startTime (datetime): a datetime object representing the start time.
            gametypeId (int): some integer value.
            gametype (str): a string.
            pdata (dict): a dictionary of some sort.
            heroes (list): a list of some sort.
            doinsert (bool): a boolean value that determines whether to insert or not.
        """

        for p in pdata:
            k =   (hid
                  ,gametypeId
                  ,tourneyTypeId
                  ,pids[p]
                  ,pdata[p]['startCards']
                  )
            pdata[p]['n'] = 1
            line = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
            self.dcbulk[k] = line
                
        if doinsert:
            update_cardscache = self.sql.query['update_cardscache']
            update_cardscache = update_cardscache.replace('%s', self.sql.query['placeholder'])
            insert_cardscache = self.sql.query['insert_cardscache']
            insert_cardscache = insert_cardscache.replace('%s', self.sql.query['placeholder'])
            select_cardscache_ring = self.sql.query['select_cardscache_ring']
            select_cardscache_ring = select_cardscache_ring.replace('%s', self.sql.query['placeholder'])
            select_cardscache_tour = self.sql.query['select_cardscache_tour']
            select_cardscache_tour = select_cardscache_tour.replace('%s', self.sql.query['placeholder'])
            
            select_W     = self.sql.query['select_W'].replace('%s', self.sql.query['placeholder'])
            select_M     = self.sql.query['select_M'].replace('%s', self.sql.query['placeholder'])
            insert_W     = self.sql.query['insert_W'].replace('%s', self.sql.query['placeholder'])
            insert_M     = self.sql.query['insert_M'].replace('%s', self.sql.query['placeholder'])
            
            dccache, inserts = {}, []
            for k, l in list(self.dcbulk.items()):
                sc = self.s.get(k[0])
                if sc != None:                    
                    garbageWeekMonths = (sc['wid'], sc['mid']) in self.wmnew or (sc['wid'], sc['mid']) in self.wmold
                    garbageTourneyTypes = k[2] in self.ttnew or k[2] in self.ttold
                    if self.import_options['hhBulkPath'] == "" or (not garbageWeekMonths and not garbageTourneyTypes):
                        n = (sc['wid'], sc['mid'], k[1], k[2], k[3], k[4])
                        startCards = dccache.get(n)
                        # Add line to the old line in the hudcache.
                        if startCards is not None:
                            for idx,val in enumerate(l):
                                dccache[n][idx] += val
                        else:
                            dccache[n] = l

            c = self.get_cursor()
            for k, item in list(dccache.items()):
                if k[3]:
                    q = select_cardscache_tour
                    row = list(k)
                else:
                    q = select_cardscache_ring
                    row = list(k[:3]) + list(k[-2:])
                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = item + [id]
                    c.execute(update_cardscache, update)                 
                else:
                    insert = list(k) + item
                    inserts.append(insert)
                
            if inserts:
                self.executemany(c, insert_cardscache, inserts)
                self.commit()
            
    def storePositionsCache(self, hid, pids, startTime, gametypeId, tourneyTypeId, pdata, hdata, heroes, tz_name, doinsert):
        """
        Update cached position statistics. If update fails because no record exists, do an insert.

        Args:
        hid (int): hero id
        pids (list): list of player ids
        startTime (int): the start time of the match
        gametypeId (int): game type id
        tourneyTypeId (int): tourney type id
        pdata (dict): position data
        hdata (dict): hero data
        heroes (dict): hero information
        tz_name (str): timezone name
        doinsert (bool): flag to insert data

        """

        for p in pdata:
            position = str(pdata[p]['position'])
            k =   (hid
                  ,gametypeId
                  ,tourneyTypeId
                  ,pids[p]
                  ,len(pids)
                  ,hdata['maxPosition']
                  ,position
                  )
            pdata[p]['n'] = 1
            line = [int(pdata[p][s]) if isinstance(pdata[p][s],bool) else pdata[p][s] for s in CACHE_KEYS]
            self.pcbulk[k] = line
                
        if doinsert:
            update_positionscache = self.sql.query['update_positionscache']
            update_positionscache = update_positionscache.replace('%s', self.sql.query['placeholder'])
            insert_positionscache = self.sql.query['insert_positionscache']
            insert_positionscache = insert_positionscache.replace('%s', self.sql.query['placeholder'])
            
            select_positionscache_ring = self.sql.query['select_positionscache_ring']
            select_positionscache_ring = select_positionscache_ring.replace('%s', self.sql.query['placeholder'])
            select_positionscache_tour = self.sql.query['select_positionscache_tour']
            select_positionscache_tour = select_positionscache_tour.replace('%s', self.sql.query['placeholder'])
            
            select_W     = self.sql.query['select_W'].replace('%s', self.sql.query['placeholder'])
            select_M     = self.sql.query['select_M'].replace('%s', self.sql.query['placeholder'])
            insert_W     = self.sql.query['insert_W'].replace('%s', self.sql.query['placeholder'])
            insert_M     = self.sql.query['insert_M'].replace('%s', self.sql.query['placeholder'])
                
            pccache, inserts = {}, []
            for k, l in list(self.pcbulk.items()):
                sc = self.s.get(k[0])
                if sc != None:
                    garbageWeekMonths = (sc['wid'], sc['mid']) in self.wmnew or (sc['wid'], sc['mid']) in self.wmold
                    garbageTourneyTypes = k[2] in self.ttnew or k[2] in self.ttold
                    if self.import_options['hhBulkPath'] == "" or (not garbageWeekMonths and not garbageTourneyTypes):
                        n = (sc['wid'], sc['mid'], k[1], k[2], k[3], k[4], k[5], k[6])         
                        positions = pccache.get(n)
                        # Add line to the old line in the hudcache.
                        if positions is not None:
                            for idx,val in enumerate(l):
                                pccache[n][idx] += val
                        else:
                            pccache[n] = l
            
            c = self.get_cursor()
            for k, item in list(pccache.items()):
                if k[3]:
                    q = select_positionscache_tour
                    row = list(k)
                else:
                    q = select_positionscache_ring
                    row = list(k[:3]) + list(k[-4:])
                
                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = item + [id]
                    c.execute(update_positionscache, update)
                else:
                    insert = list(k) + item
                    inserts.append(insert)
                
            if inserts:
                self.executemany(c, insert_positionscache, inserts)
                self.commit()
    
    def appendHandsSessionIds(self):
        """
        Append session IDs to hands.
        """
        for i in range(len(self.hbulk)):
            # Get the hand ID and tournament ID.
            hid = self.hids[i]
            tid = self.hbulk[i][2]

            # Get the session information.
            sc = self.s.get(hid)

            # If session information is available, append the session ID to the hand.
            if sc is not None:
                self.hbulk[i][4] = sc['id']

                # If tournament information is available, update the tournament information with the session ID.
                if tid:
                    self.tbulk[tid] = sc['id']

                
    def get_id(self, file):
        """
        Gets the ID associated with the given file from the database.

        Args:
            file (str): The name of the file.

        Returns:
            int: The ID associated with the file, or 0 if no ID is found.
        """
        # Get the SQL query to use from the query dictionary.
        q = self.sql.query['get_id']

        # Replace any placeholder in the query with the actual placeholder string.
        q = q.replace('%s', self.sql.query['placeholder'])

        # Get a cursor for the database and execute the query.
        c = self.get_cursor()
        c.execute(q, (file,))

        # Get the ID from the first result, if there is one.
        id = c.fetchone()

        # If no ID is found, return 0.
        if not id:
            return 0

        # Otherwise, return the ID.
        return id[0]


    def storeFile(self, fdata):
        """
        Stores file data in the database and returns the id of the newly inserted row.

        Args:
            fdata: A tuple containing the data to be inserted.

        Returns:
            The id of the newly inserted row.
        """
        # Get the query template from the sql query dictionary and replace placeholders with actual placeholders
        q = self.sql.query['store_file']
        q = q.replace('%s', self.sql.query['placeholder'])

        # Get the database cursor and execute the query
        c = self.get_cursor()
        c.execute(q, fdata)

        # Get the id of the last inserted row and return it
        id = self.get_last_insert_id(c)
        return id

        
    def updateFile(self, fdata):
        """
        Updates a file in the database with the provided data.

        Args:
            fdata: A dictionary containing the new data for the file.

        Returns:
            None
        """
        # Get the SQL query for updating a file and replace the placeholder with the actual values
        q = self.sql.query['update_file']
        q = q.replace('%s', self.sql.query['placeholder'])

        # Get a cursor and execute the query with the provided data
        c = self.get_cursor()
        c.execute(q, fdata)


    def getHeroIds(self, pids, sitename):
        """
        Given a dictionary of player IDs and a site name, return a list of player IDs
        corresponding to the heroes for that site as defined in the HUD_Config.xml file.

        Args:
            pids (dict): A dictionary of player IDs indexed by player name.
            sitename (str): The name of the site for which to retrieve hero IDs.

        Returns:
            list: A list of player IDs corresponding to the heroes for the given site.
        """

        # Grab playerIds using hero names in HUD_Config.xml
        try:
            hero_ids = []
            for site in self.config.get_supported_sites():
                hero_name = self.config.supported_sites[site].screen_name
                for name, pid in pids.items():
                    if name == hero_name and sitename == site:
                        hero_ids.append(pid)
        except:
            # Print error traceback if exception occurs.
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            #print("Error acquiring hero ids:"), str(sys.exc_value)

        return hero_ids
    
    def fetchallDict(self, cursor, desc):
        """
        Fetches all rows from a cursor as dictionaries.

        Args:
            cursor: The cursor to fetch data from.
            desc: A tuple of column descriptions.

        Returns:
            A list of dictionaries mapping column names to row values.
            If no rows were fetched, an empty list is returned.
        """
        data = cursor.fetchall()
        if not data:
            return []
        results = [0] * len(data)
        for i in range(len(data)):
            results[i] = {}
            for n in range(len(desc)):
                results[i][desc[n]] = data[i][n]
        return results

    
    def nextHandId(self):
        """Gets the next unique hand ID."""
        c = self.get_cursor(True)  # Gets cursor
        c.execute("SELECT max(id) FROM Hands")  # Executes query to get max hand ID
        id = c.fetchone()[0] or 0  # Gets max hand ID or sets it to 0 if it doesn't exist
        id += self.hand_inc  # Increments ID
        return id  # Returns new ID


    def isDuplicate(self, siteId, siteHandNo, heroSeat, publicDB):
        """
        Checks if a hand is a duplicate based on its site ID, hand number, hero seat, and whether it's in the public DB.

        Args:
            siteId (int): The ID of the site the hand was played on.
            siteHandNo (int): The hand number assigned by the site.
            heroSeat (int): The seat number of the hero.
            publicDB (bool): A boolean indicating whether the hand is stored in the public database.

        Returns:
            bool: True if the hand is a duplicate, False otherwise.
        """
        # Generate the SQL query based on whether the hand is in the public DB and whether the hero seat is known.
        q = self.sql.query['isAlreadyInDB'].replace('%s', self.sql.query['placeholder'])
        if publicDB:
            key = (siteHandNo, siteId, heroSeat)
            q = q.replace('<heroSeat>', ' AND heroSeat=%s').replace('%s', self.sql.query['placeholder'])
        else:
            key = (siteHandNo, siteId)
            q = q.replace('<heroSeat>', '')

        # Check if the hand has already been seen.
        if key in self.siteHandNos:
            return True

        # Execute the SQL query and check if there are any results.
        c = self.get_cursor()
        c.execute(q, key)
        result = c.fetchall()
        if len(result) > 0:
            return True

        # Add the hand to the list of seen hands and return False.
        self.siteHandNos.append(key)
        return False

    def getSqlPlayerIDs(self, pnames, siteid, hero):
        """
        Given a list of player names `pnames`, a site id `siteid`, and a hero name `hero`, returns a dictionary where:
        - The keys are the player names
        - The values are the IDs of the players in the SQL database.

        If there is no player in the database with the given name, a new player is inserted.

        Args:
            pnames (list): List of strings with the player names.
            siteid (int): The id of the site where the players play.
            hero (str): The name of the hero.

        Returns:
            dict: A dictionary where the keys are the player names and the values are the IDs of the players in the SQL database.
        """
        result = {}

        # If the player cache is empty, create it as a LambdaDict that inserts a new player if it doesn't exist.
        if(self.pcache == None):
            self.pcache = LambdaDict(lambda  key:self.insertPlayer(key[0], key[1], key[2]))

        # For each player name, get the player id from the cache or insert a new player in the database.
        for player in pnames:
            result[player] = self.pcache[(player,siteid,player==hero)]
            # NOTE: Using the LambdaDict does the same thing as:
            #if player in self.pcache:
            #    #print "DEBUG: cachehit"
            #    pass
            #else:
            #    self.pcache[player] = self.insertPlayer(player, siteid)
            #result[player] = self.pcache[player]

        return result

    
    def insertPlayer(self, name, site_id, hero):
        """
        Inserts a player into the Players table in the database.

        Args:
            name (str): Name of the player.
            site_id (int): ID of the site the player is registered on.
            hero (str): Name of the player's hero.

        Returns:
            int: ID of the inserted player.
        """
        # Construct the SQL query.
        insert_player = "INSERT INTO Players (name, siteId, hero, chars) VALUES (%s, %s, %s, %s)"
        insert_player = insert_player.replace('%s', self.sql.query['placeholder'])

        # Get the character abbreviation for the player's name.
        _name = name[:32]
        if re_char.match(_name[0]):
            char = '123'
        elif len(_name)==1 or re_char.match(_name[1]):
            char = _name[0] + '1'
        else:
            char = _name[:2]

        # Create a tuple with the player's information.
        key = (_name, site_id, hero, char.upper())

        # FIXME: MySQL has ON DUPLICATE KEY UPDATE
        # Usage:
        #        INSERT INTO `tags` (`tag`, `count`)
        #         VALUES ($tag, 1)
        #           ON DUPLICATE KEY UPDATE `count`=`count`+1;

        # Insert or update the player in the database.
        result = None
        c = self.get_cursor()
        q = "SELECT id, name, hero FROM Players WHERE name=%s and siteid=%s"
        q = q.replace('%s', self.sql.query['placeholder'])
        result = self.insertOrUpdate('players', c, key, q, insert_player)

        # Return the ID of the inserted player.
        return result

    
    def insertOrUpdate(self, type, cursor, key, select, insert):
        """
        Inserts a new record or updates an existing one in the specified table.

        Args:
            type (str): The name of the table to insert/update records in.
            cursor: The cursor object to execute the SQL queries with.
            key: The values to use as the primary key for the record.
            select (str): The SQL SELECT query to use to check if the record already exists.
            insert (str): The SQL INSERT query to use to insert a new record.

        Returns:
            int: The ID of the newly inserted record or the existing record that was updated.
        """
        if type == 'players':
            cursor.execute(select, key[:2])
        else:
            cursor.execute(select, key)

        tmp = cursor.fetchone()

        if tmp is None:
            cursor.execute(insert, key)
            result = self.get_last_insert_id(cursor)
        else:
            result = tmp[0]

            if type == 'players' and (not tmp[2] and key[2]):
                q = "UPDATE Players SET hero=%s WHERE name=%s and siteid=%s"
                q = q.replace('%s', self.sql.query['placeholder'])
                cursor.execute(q, (key[2], key[0], key[1]))

        return result

    
    def getSqlGameTypeId(self, siteid, game, printdata=False):
        """
        Get GameTypeID from the database cache.

        Args:
            siteid (int): the site id
            game (dict): the game dictionary
            printdata (bool): whether or not to print data

        Returns:
            int: the game type id
        """
        # Check if game types cache is None and create a new cache if it is.
        if(self.gtcache is None):
            self.gtcache = LambdaDict(lambda key: self.insertGameTypes(key[0], key[1]))

        self.gtprintdata = printdata
        hilo = Card.games[game['category']][2]

        # Create game type information tuple.
        gtinfo = (siteid, game['type'], game['category'], game['limitType'], game['currency'],
                game['mix'], int(Decimal(game['sb']) * 100), int(Decimal(game['bb']) * 100),
                game['maxSeats'], int(game['ante'] * 100), game['buyinType'], game['fast'],
                game['newToGame'], game['homeGame'], game['split'])

        # Create game type insertion tuple.
        gtinsert = (siteid, game['currency'], game['type'], game['base'], game['category'],
                    game['limitType'], hilo, game['mix'], int(Decimal(game['sb']) * 100),
                    int(Decimal(game['bb']) * 100), int(Decimal(game['bb']) * 100),
                    int(Decimal(game['bb']) * 200), game['maxSeats'], int(game['ante'] * 100),
                    game['buyinType'], game['fast'], game['newToGame'], game['homeGame'], game['split'])

        # Get the result from the game types cache.
        result = self.gtcache[(gtinfo, gtinsert)]
        # NOTE: Using the LambdaDict does the same thing as:
        #if player in self.pcache:
        #    #print "DEBUG: cachehit"
        #    pass
        #else:
        #    self.pcache[player] = self.insertPlayer(player, siteid)
        #result[player] = self.pcache[player]

        return result

    def insertGameTypes(self, gtinfo, gtinsert):
        """
        Inserts game types into the database.

        Args:
            gtinfo (tuple): Information needed to retrieve the gametype from the database.
            gtinsert (tuple): Information needed to insert the gametype into the database.

        Returns:
            int: The ID of the inserted gametype.
        """
        result = None
        c = self.get_cursor()

        # Retrieve the gametype from the database if it exists
        q = self.sql.query['getGametypeNL']
        q = q.replace('%s', self.sql.query['placeholder'])
        c.execute(q, gtinfo)
        tmp = c.fetchone()

        # If the gametype does not exist, insert it into the database
        if (tmp == None):
            # Optionally print the gametype information
            if self.gtprintdata:
                print ("######## Gametype ##########")
                import pprint
                pp = pprint.PrettyPrinter(indent=4)
                pp.pprint(gtinsert)
                print ("###### End Gametype ########")

            # Insert the gametype into the database
            c.execute(self.sql.query['insertGameTypes'].replace('%s', self.sql.query['placeholder']), gtinsert)
            result = self.get_last_insert_id(c)
        else:
            # The gametype already exists, return its ID
            result = tmp[0]
        return result

    
    def getTourneyInfo(self, siteName, tourneyNo):
        """
        Retrieves tournament information from the database.

        Args:
            siteName (str): The name of the site where the tournament was hosted.
            tourneyNo (int): The tournament number.

        Returns:
            tuple: A tuple containing two elements: a list of column names and a tuple of data.
        """

        # Get a cursor to execute queries
        c = self.get_cursor()

        # Get the SQL query from the query dictionary and replace placeholders with %s
        q = self.sql.query['getTourneyInfo'].replace('%s', self.sql.query['placeholder'])

        # Execute the query with siteName and tourneyNo as parameters
        c.execute(q, (siteName, tourneyNo))

        # Get the column names of the result set
        columnNames = c.description

        # Extract the names of the columns from the columnNames list
        names = []
        for column in columnNames:
            names.append(column[0])

        # Get the first row of the result set
        data = c.fetchone()

        # Return the column names and data as a tuple
        return (names, data)

    #end def getTourneyInfo

    def getTourneyTypesIds(self):
        """
        Retrieves the IDs of all tourney types from the database.

        Returns:
            A list of tuples representing the tourney type IDs.
        """
        # Create a cursor object to execute SQL queries
        c = self.connection.cursor()
        # Execute the query to retrieve tourney type IDs
        c.execute(self.sql.query['getTourneyTypesIds'])
        # Fetch all the rows returned by the query
        result = c.fetchall()
        # Return the list of tourney type IDs
        return result
    #end def getTourneyTypesIds
    
    def getSqlTourneyTypeIDs(self, hand):
        """
        Get the tournament type IDs for a given hand.

        Args:
            hand: Hand data.

        Returns:
            The tournament type IDs for the given hand.
        """
        #if(self.ttcache == None):
        #    self.ttcache = LambdaDict(lambda  key:self.insertTourneyType(key[0], key[1], key[2]))

        #tourneydata =   (hand.siteId, hand.buyinCurrency, hand.buyin, hand.fee, hand.gametype['category'],
        #                 hand.gametype['limitType'], hand.maxseats, hand.isSng, hand.isKO, hand.koBounty, hand.isProgressive,
        #                 hand.isRebuy, hand.rebuyCost, hand.isAddOn, hand.addOnCost, hand.speed, hand.isShootout, hand.isMatrix)

        result = self.createOrUpdateTourneyType(hand) #self.ttcache[(hand.tourNo, hand.siteId, tourneydata)]

        return result

    
    def defaultTourneyTypeValue(self, value1, value2, field):
        """
        This function checks if the given values meet certain criteria based on the field.

        Args:
            value1 (any): The first value to check.
            value2 (any): The second value to check.
            field (str): The field to check against.

        Returns:
            bool: True if the values meet the criteria, False otherwise.
        """
        # Check if value1 is falsy
        if ((not value1) or 
            # Check if field is 'maxseats' and value1 is greater than value2
            (field=='maxseats' and value1>value2) or 
            # Check if field is 'limitType' and value2 is 'mx'
            (field=='limitType' and value2=='mx') or 
            # Check if field is 'buyinCurrency' and value1 is 'NA'
            ((field,value1)==('buyinCurrency','NA')) or 
            # Check if field is 'stack' and value1 is 'Regular'
            ((field,value1)==('stack','Regular')) or
            # Check if field is 'speed' and value1 is 'Normal'
            ((field,value1)==('speed','Normal')) or
            # Check if field is 'koBounty' and value1 is truthy
            (field=='koBounty' and value1)
        ):
            return True
        # Otherwise, return False
        return False

    
    def createOrUpdateTourneyType(self, obj):
        """
        Creates a new tournament type or updates an existing tournament type with the given object.

        Args:
            obj: An object containing the details of the tournament.

        Returns:
            The ID of the tournament type.
        """
        ttid, _ttid, updateDb = None, None, False
        setattr(obj, 'limitType', obj.gametype['limitType'])

        # Get the cursor and query the database for the tournament type ID.
        cursor = self.get_cursor()
        q = self.sql.query['getTourneyTypeIdByTourneyNo'].replace('%s', self.sql.query['placeholder'])
        cursor.execute(q, (obj.tourNo, obj.siteId))
        result = cursor.fetchone()

        # If the result exists, update the object with data from the database.
        if result != None:
            columnNames=[desc[0].lower() for desc in cursor.description]
            expectedValues = (('buyin', 'buyin'), ('fee', 'fee'), ('buyinCurrency', 'currency'), ('limitType', 'limittype'), ('isSng', 'sng'), ('maxseats', 'maxseats')
                            , ('isKO', 'knockout'), ('koBounty', 'kobounty'), ('isProgressive', 'progressive'), ('isRebuy', 'rebuy'), ('rebuyCost', 'rebuycost')
                            , ('isAddOn', 'addon'), ('addOnCost','addoncost'), ('speed', 'speed'), ('isShootout', 'shootout')
                            , ('isMatrix', 'matrix'), ('isFast', 'fast'), ('stack', 'stack'), ('isStep', 'step'), ('stepNo', 'stepno')
                            , ('isChance', 'chance'), ('chanceCount', 'chancecount'), ('isMultiEntry', 'multientry'), ('isReEntry', 'reentry')
                            , ('isHomeGame', 'homegame'), ('isNewToGame', 'newtogame'), ('isSplit', 'split'), ('isFifty50', 'fifty50'), ('isTime', 'time')
                            , ('timeAmt', 'timeamt'), ('isSatellite', 'satellite'), ('isDoubleOrNothing', 'doubleornothing'), ('isCashOut', 'cashout')
                            , ('isOnDemand', 'ondemand'), ('isFlighted', 'flighted'), ('isGuarantee', 'guarantee'), ('guaranteeAmt', 'guaranteeamt'))
            resultDict = dict(list(zip(columnNames, result)))
            ttid = resultDict["id"]

            # Check each attribute against the expected values and update if necessary.
            for ev in expectedValues:
                objField, dbField = ev
                objVal, dbVal = getattr(obj, objField), resultDict[dbField]
                if self.defaultTourneyTypeValue(objVal, dbVal, objField) and dbVal: #DB has this value but object doesnt, so update object
                    setattr(obj, objField, dbVal)
                elif self.defaultTourneyTypeValue(dbVal, objVal, objField) and objVal: #object has this value but DB doesnt, so update DB
                    updateDb = True
                    oldttid = ttid

        # If the result does not exist or an update is necessary, insert a new tournament type.
        if not result or updateDb:
            if obj.gametype['mix']!='none':
                category, limitType = obj.gametype['mix'], 'mx'
            elif result != None and resultDict['limittype']=='mx':
                category, limitType = resultDict['category'], 'mx'
            else:
                category, limitType = obj.gametype['category'], obj.gametype['limitType']
            row = (obj.siteId, obj.buyinCurrency, obj.buyin, obj.fee, category,
                   limitType, obj.maxseats, obj.isSng, obj.isKO, obj.koBounty, obj.isProgressive,
                   obj.isRebuy, obj.rebuyCost, obj.isAddOn, obj.addOnCost, obj.speed, obj.isShootout, 
                   obj.isMatrix, obj.isFast, obj.stack, obj.isStep, obj.stepNo, obj.isChance, obj.chanceCount,
                   obj.isMultiEntry, obj.isReEntry, obj.isHomeGame, obj.isNewToGame, obj.isSplit, obj.isFifty50, obj.isTime,
                   obj.timeAmt, obj.isSatellite, obj.isDoubleOrNothing, obj.isCashOut, obj.isOnDemand, obj.isFlighted, 
                   obj.isGuarantee, obj.guaranteeAmt)
            cursor.execute (self.sql.query['getTourneyTypeId'].replace('%s', self.sql.query['placeholder']), row)
            tmp=cursor.fetchone()
            try:
                ttid = tmp[0]
            except TypeError: #this means we need to create a new entry
                if self.printdata:
                    print ("######## Tourneys ##########")
                    import pprint
                    pp = pprint.PrettyPrinter(indent=4)
                    pp.pprint(row)
                    print ("###### End Tourneys ########")
                cursor.execute (self.sql.query['insertTourneyType'].replace('%s', self.sql.query['placeholder']), row)
                ttid = self.get_last_insert_id(cursor)
            if updateDb:
                #print 'DEBUG createOrUpdateTourneyType:', 'old', oldttid, 'new', ttid, row
                q = self.sql.query['updateTourneyTypeId'].replace('%s', self.sql.query['placeholder'])
                cursor.execute(q, (ttid, obj.siteId, obj.tourNo))
                self.ttold.add(oldttid)
                self.ttnew.add(ttid)
        return ttid
    
    def cleanUpTourneyTypes(self):
        """
        Deletes tourney types that are no longer in use from the database.

        If a tourney type is not used in any sessions or huds and is not in ttnew, it is deleted from the database.

        Args:
            self: the instance of the class calling the method

        Returns:
            None
        """
        # Determine which tables to clear based on whether callHud and cacheSessions are True or False
        if self.ttold:
            if self.callHud and self.cacheSessions:
                tables = ('HudCache','CardsCache', 'PositionsCache')
            elif self.callHud:
                tables = ('HudCache',)
            elif self.cacheSessions:
                tables = ('CardsCache', 'PositionsCache')
            else:
                tables = set([])

            # Get the SQL queries from the instance's sql attribute
            select = self.sql.query['selectTourneyWithTypeId'].replace('%s', self.sql.query['placeholder'])
            delete = self.sql.query['deleteTourneyTypeId'].replace('%s', self.sql.query['placeholder'])
            cursor = self.get_cursor()

            # Iterate through the old tourney types
            for ttid in self.ttold:
                # Clear the tourney type from each table
                for t in tables:
                    statement = 'clear%sTourneyType' % t
                    clear  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                    cursor.execute(clear, (ttid,))
                self.commit()

                # Check if the tourney type is used in any sessions or huds
                cursor.execute(select, (ttid,))
                result=cursor.fetchone()
                if not result:
                    # If the tourney type is not used, delete it from the database
                    cursor.execute(delete, (ttid,))
                    self.commit()

            # Iterate through the new tourney types
            for ttid in self.ttnew:
                # Clear the tourney type from each table
                for t in tables:
                    statement = 'clear%sTourneyType' % t
                    clear  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                    cursor.execute(clear, (ttid,))
                self.commit()

            # Fetch new tourney type ids and rebuild the cache for each one
            for t in tables:
                statement = 'fetchNew%sTourneyTypeIds' % t
                fetch  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                cursor.execute(fetch)
                for id in cursor.fetchall():
                    self.rebuild_cache(None, None, t, id[0])
        else:
            # If there are no tourney types, return None
            return None

                
                    
    def cleanUpWeeksMonths(self):
        """
        Cleans up old data from the "weeks" and "months" tables in the database
        """
        # Prepare SQL statements to select and delete data
        selectWeekId = self.sql.query['selectSessionWithWeekId'].replace('%s', self.sql.query['placeholder'])
        selectMonthId = self.sql.query['selectSessionWithMonthId'].replace('%s', self.sql.query['placeholder'])
        deleteWeekId = self.sql.query['deleteWeekId'].replace('%s', self.sql.query['placeholder'])
        deleteMonthId = self.sql.query['deleteMonthId'].replace('%s', self.sql.query['placeholder'])

        # Get a cursor to execute SQL statements
        cursor = self.get_cursor()

        # Initialize sets to keep track of which weeks/months have been processed
        weeks, months, wmids = set(), set(), set()

        # Process old week/month data
        if self.cacheSessions and self.wmold:
            for (wid, mid) in self.wmold:
                # Clear cache for each week/month
                for t in ('CardsCache', 'PositionsCache'):
                    statement = 'clear%sWeeksMonths' % t
                    clear  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                    cursor.execute(clear, (wid, mid))
                self.commit()

                # Add each week/month to the respective set
                weeks.add(wid)
                months.add(mid)

            # Delete old weeks/months that have no associated sessions
            for wid in weeks:
                cursor.execute(selectWeekId, (wid,))
                result=cursor.fetchone()
                if not result:
                    cursor.execute(deleteWeekId, (wid,))
                    self.commit()

            for mid in months:
                cursor.execute(selectMonthId, (mid,))
                result=cursor.fetchone()
                if not result:
                    cursor.execute(deleteMonthId, (mid,))
                    self.commit()

        # Process new week/month data
        for (wid, mid) in self.wmnew:
            # Clear cache for each week/month
            for t in ('CardsCache', 'PositionsCache'):
                statement = 'clear%sWeeksMonths' % t
                clear  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                cursor.execute(clear, (wid, mid))
            self.commit()

        # Rebuild cache for each new week/month that has associated sessions
        if self.wmold:
            for t in ('CardsCache', 'PositionsCache'):
                statement = 'fetchNew%sWeeksMonths' % t
                fetch  = self.sql.query[statement].replace('%s', self.sql.query['placeholder'])
                cursor.execute(fetch)
                for (wid, mid) in cursor.fetchall():
                    wmids.add((wid, mid))         
            for wmid in wmids:
                for t in ('CardsCache', 'PositionsCache'):
                    self.rebuild_cache(None, None, t, None, wmid)
            self.commit()
     
    def rebuild_caches(self):
        """
        Rebuilds the cache of tables based on whether or not the callHud and cacheSessions variables are set.
        """
        # Determine which tables to rebuild caches for
        if self.callHud and self.cacheSessions:
            tables = ('HudCache','CardsCache', 'PositionsCache')
        elif self.callHud:
            tables = ('HudCache',)
        elif self.cacheSessions:
            tables = ('CardsCache', 'PositionsCache')
        else:
            tables = set([])

        # Rebuild the cache for each table
        for t in tables:
            self.rebuild_cache(None, None, t)

                
    def resetClean(self):
        """
        Resets the instance variables to empty sets.
        """
        self.ttold = set()
        self.ttnew = set()
        self.wmold = set()
        self.wmnew = set()
        
    def cleanRequired(self):
        """
        Check if self.ttold or self.wmold is True.

        Returns:
            bool: True if either self.ttold or self.wmold is True, False otherwise.
        """
        if self.ttold or self.wmold:
            return True
        return False
    
    def getSqlTourneyIDs(self, hand):
        """
        Executes a SQL query to get a tournament ID from a given hand. If the tournament does not exist, it is created.
        Returns the ID of the tournament.
        """
        result = None
        c = self.get_cursor()  # get a cursor object
        q = self.sql.query['getTourneyByTourneyNo']  # get the SQL query string
        q = q.replace('%s', self.sql.query['placeholder'])  # replace the query parameter placeholder
        t = hand.startTime.replace(tzinfo=None)  # get the start time of the hand
        c.execute(q, (hand.siteId, hand.tourNo))  # execute the query with the hand's site ID and tourney number

        tmp = c.fetchone()  # fetch the first row of the result
        if (tmp == None):  # if no rows are returned, insert a new tournament into the database
            c.execute(self.sql.query['insertTourney'].replace('%s', self.sql.query['placeholder']),
                    (hand.tourneyTypeId, None, hand.tourNo, None, None,
                    t, t, hand.tourneyName, None, None, None, None, None, None))
            result = self.get_last_insert_id(c)  # get the ID of the last inserted row
        else:  # if a row is returned, update the start or end time of the tournament if necessary
            result = tmp[0]
            columnNames = [desc[0] for desc in c.description]
            resultDict = dict(list(zip(columnNames, tmp)))
            if self.backend == self.PGSQL:
                startTime, endTime = resultDict['starttime'], resultDict['endtime']
            else:
                startTime, endTime = resultDict['startTime'], resultDict['endTime']

            if (startTime == None or t < startTime):
                q = self.sql.query['updateTourneyStart'].replace('%s', self.sql.query['placeholder'])
                c.execute(q, (t, result))
            elif (endTime == None or t > endTime):
                q = self.sql.query['updateTourneyEnd'].replace('%s', self.sql.query['placeholder'])
                c.execute(q, (t, result))

        return result

    
    def createOrUpdateTourney(self, summary):
        """
        Creates or updates a tournament based on the summary provided.

        Args:
            summary (Summary): The summary to create/update the tournament with.

        Returns:
            int: The ID of the created/updated tournament.
        """
        cursor = self.get_cursor()

        # Get tournament by tourney number
        q = self.sql.query['getTourneyByTourneyNo'].replace('%s', self.sql.query['placeholder'])
        cursor.execute(q, (summary.siteId, summary.tourNo))

        # Get column names and result
        columnNames = [desc[0] for desc in cursor.description]
        result = cursor.fetchone()

        # Check if tournament already exists
        if result != None:

            # Check expected values for current backend
            if self.backend == self.PGSQL:
                expectedValues = (
                    ('comment', 'comment'), 
                    ('tourneyName', 'tourneyname'),
                    ('totalRebuyCount', 'totalrebuycount'), 
                    ('totalAddOnCount', 'totaladdoncount'),
                    ('prizepool', 'prizepool'), 
                    ('startTime', 'starttime'), 
                    ('entries', 'entries'),
                    ('commentTs', 'commentts'), 
                    ('endTime', 'endtime'),
                    ('added', 'added'), 
                    ('addedCurrency', 'addedcurrency')
                )
            else:
                expectedValues = (
                    ('comment', 'comment'), 
                    ('tourneyName', 'tourneyName'),
                    ('totalRebuyCount', 'totalRebuyCount'), 
                    ('totalAddOnCount', 'totalAddOnCount'),
                    ('prizepool', 'prizepool'), 
                    ('startTime', 'startTime'), 
                    ('entries', 'entries'),
                    ('commentTs', 'commentTs'), 
                    ('endTime', 'endTime'),
                    ('added', 'added'), 
                    ('addedCurrency', 'addedCurrency')
                )

            updateDb = False
            resultDict = dict(list(zip(columnNames, result)))
            tourneyId = resultDict["id"]

            # Check expected values against summary
            for ev in expectedValues:
                if getattr(summary, ev[0]) == None and resultDict[ev[1]] != None:
                    # DB has this value but object doesn't, so update object
                    setattr(summary, ev[0], resultDict[ev[1]])
                elif getattr(summary, ev[0]) != None and not resultDict[ev[1]]:
                    # Object has this value but DB doesn't, so update DB
                    updateDb = True

            
                #elif ev=="startTime":
                #    if (resultDict[ev] < summary.startTime):
                #        summary.startTime=resultDict[ev]
            # Update DB if necessary
            if updateDb:
                q = self.sql.query['updateTourney'].replace('%s', self.sql.query['placeholder'])
                startTime, endTime = None, None
                if (summary.startTime!=None): startTime = summary.startTime.replace(tzinfo=None)
                if (summary.endTime!=None): endTime = summary.endTime.replace(tzinfo=None)
                row = (summary.entries, summary.prizepool, startTime, endTime, summary.tourneyName,
                       summary.totalRebuyCount, summary.totalAddOnCount, summary.comment, summary.commentTs, 
                       summary.added, summary.addedCurrency, tourneyId
                      )
                cursor.execute(q, row)
        else:
            startTime, endTime = None, None
            if (summary.startTime!=None): startTime = summary.startTime.replace(tzinfo=None)
            if (summary.endTime!=None): endTime = summary.endTime.replace(tzinfo=None)
            row = (summary.tourneyTypeId, None, summary.tourNo, summary.entries, summary.prizepool, startTime,
                   endTime, summary.tourneyName, summary.totalRebuyCount, summary.totalAddOnCount,
                   summary.comment, summary.commentTs, summary.added, summary.addedCurrency)
            if self.printdata:
                print ("######## Tourneys ##########")
                import pprint
                pp = pprint.PrettyPrinter(indent=4)
                pp.pprint(row)
                print ("###### End Tourneys ########")
            cursor.execute (self.sql.query['insertTourney'].replace('%s', self.sql.query['placeholder']), row)
            tourneyId = self.get_last_insert_id(cursor)
        return tourneyId
    #end def createOrUpdateTourney

    def getTourneyPlayerInfo(self, siteName, tourneyNo, playerName):
        """
        Returns player information for a specific tournament and site.

        Args:
            siteName (str): The name of the site where the tournament took place.
            tourneyNo (int): The tournament number.
            playerName (str): The name of the player.

        Returns:
            A tuple containing a list of column names and a tuple of player information.
        """
        # Get cursor
        c = self.get_cursor()

        # Execute query
        c.execute(self.sql.query['getTourneyPlayerInfo'], (siteName, tourneyNo, playerName))

        # Get column names
        columnNames = c.description
        names = []
        for column in columnNames:
            names.append(column[0])

        # Get player information
        data = c.fetchone()

        return (names, data)

    #end def getTourneyPlayerInfo  
    
    def getSqlTourneysPlayersIDs(self, hand):
        """
        Returns a dictionary mapping player IDs to their corresponding tournament player IDs for a given hand.

        Args:
            hand: The hand object for which to retrieve player IDs.

        Returns:
            A dictionary mapping player IDs to their corresponding tournament player IDs.
        """
        result = {}

        # Initialize the tournament player cache if it hasn't been already
        if self.tpcache is None:
            self.tpcache = LambdaDict(lambda key: self.insertTourneysPlayers(key[0], key[1], key[2]))

        # Iterate over each player in the hand and retrieve their tournament player ID
        for player in hand.players:
            playerId = hand.dbid_pids[player[1]]
            result[player[1]] = self.tpcache[(playerId, hand.tourneyId, hand.entryId)]

        return result

    
    def insertTourneysPlayers(self, playerId, tourneyId, entryId):
        """
        Inserts a new row in the TourneysPlayers table or returns the existing id.
        :param playerId: int - the id of the player
        :param tourneyId: int - the id of the tournament
        :param entryId: int - the id of the entry
        :return: int - the id of the TourneysPlayers row
        """
        result = None  # initialize result variable
        c = self.get_cursor()  # get a cursor
        q = self.sql.query['getTourneysPlayersByIds']  # get the query from the sql dictionary
        q = q.replace('%s', self.sql.query['placeholder'])  # replace the placeholder

        c.execute(q, (tourneyId, playerId, entryId))  # execute the query

        tmp = c.fetchone()  # get the first row from the result
        if (tmp == None):  # if there's no row, insert a new one
            c.execute(self.sql.query['insertTourneysPlayer'].replace('%s', self.sql.query['placeholder'])
                    ,(tourneyId, playerId, entryId, None, None, None, None, None, None))
            # Get last id might be faster here.
            # c.execute("SELECT id FROM Players WHERE name=%s", (name,))
            result = self.get_last_insert_id(c)  # get the last insert id
        else:  # if there's already a row, return its id
            result = tmp[0]
        return result  # return the result

    
    def updateTourneyPlayerBounties(self, hand):
        """
        Update the bounties for players in a tournament hand.

        Args:
            hand: A Hand object representing the tournament hand.

        Returns:
            None.
        """
        updateDb = False
        cursor = self.get_cursor()

        # Replace placeholders in the SQL query with actual values
        q = self.sql.query['updateTourneysPlayerBounties'].replace('%s', self.sql.query['placeholder'])

        # Iterate over players in the hand and update their bounties if they were knocked out
        for player, tourneysPlayersId in list(hand.tourneysPlayersIds.items()):
            if player in hand.koCounts:
                # Execute the SQL query with the appropriate values
                cursor.execute(q, (
                    hand.koCounts[player],
                    hand.koCounts[player],
                    tourneysPlayersId
                ))
                updateDb = True

        # Commit changes to the database if there were any updates
        if updateDb:
            self.commit()

    
    def createOrUpdateTourneysPlayers(self, summary):
        """
        Given a summary object, update the tourneys players table in the database
        with new records or update existing ones.

        :param summary: Summary object that contains information about the players, their entries and their performance
        """
        # initialize variables
        tourneysPlayersIds, tplayers, inserts = {}, [], []
        cursor = self.get_cursor()

        # fetch existing tourney players for the given tourney id
        cursor.execute(self.sql.query['getTourneysPlayersByTourney'].replace('%s', self.sql.query['placeholder']),
                    (summary.tourneyId,))
        result = cursor.fetchall()

        # if existing tourney players are found, add them to tplayers list
        if result:
            tplayers += [i for i in result]

        # iterate through each player and their entries
        for player, entries in list(summary.players.items()):
            playerId = summary.dbid_pids[player]
            for entryIdx in range(len(entries)):
                entryId = entries[entryIdx]

                # check if player and entry exists in tourney players table
                if (playerId, entryId) in tplayers:

                    # if exists, get record from db and compare with summary object
                    cursor.execute(self.sql.query['getTourneysPlayersByIds'].replace('%s', self.sql.query['placeholder']),
                                    (summary.tourneyId, playerId, entryId))
                    columnNames = [desc[0] for desc in cursor.description]
                    result = cursor.fetchone()

                    # define expected values, based on backend
                    if self.backend == self.PGSQL:
                        expectedValues = (('rank', 'rank'), ('winnings', 'winnings')
                                        , ('winningsCurrency', 'winningscurrency'), ('rebuyCount', 'rebuycount')
                                        , ('addOnCount', 'addoncount'), ('koCount', 'kocount'))
                    else:
                        expectedValues = (('rank', 'rank'), ('winnings', 'winnings')
                                        , ('winningsCurrency', 'winningsCurrency'), ('rebuyCount', 'rebuyCount')
                                        , ('addOnCount', 'addOnCount'), ('koCount', 'koCount'))

                    updateDb = False
                    resultDict = dict(list(zip(columnNames, result)))
                    tourneysPlayersIds[(player, entryId)] = result[0]

                    # iterate through expectedValues and check if they match in the db and summary object
                    for ev in expectedValues:
                        summaryAttribute = ev[0]
                        if ev[0] != "winnings" and ev[0] != "winningsCurrency":
                            summaryAttribute += "s"
                        summaryDict = getattr(summary, summaryAttribute)

                        # if db has the value but summary object doesn't, update summary object
                        if summaryDict[player][entryIdx] is None and resultDict[ev[1]] is not None:
                            summaryDict[player][entryIdx] = resultDict[ev[1]]
                            setattr(summary, summaryAttribute, summaryDict)

                        # if summary object has the value but db doesn't, update db
                        elif summaryDict[player][entryIdx] is not None and not resultDict[ev[1]]:
                            updateDb = True

                    # if db needs to be updated, execute update query
                    if updateDb:
                        q = self.sql.query['updateTourneysPlayer'].replace('%s', self.sql.query['placeholder'])
                        inputs = (summary.ranks[player][entryIdx],
                                  summary.winnings[player][entryIdx],
                                  summary.winningsCurrency[player][entryIdx],
                                  summary.rebuyCounts[player][entryIdx],
                                  summary.addOnCounts[player][entryIdx],
                                  summary.koCounts[player][entryIdx],
                                  tourneysPlayersIds[(player,entryId)]
                                 )
                        #print q
                        #pp = pprint.PrettyPrinter(indent=4)
                        #pp.pprint(inputs)
                        cursor.execute(q, inputs)
                else:
                    inserts.append((
                        summary.tourneyId, 
                        playerId,
                        entryId, 
                        summary.ranks[player][entryIdx], 
                        summary.winnings[player][entryIdx], 
                        summary.winningsCurrency[player][entryIdx],
                        summary.rebuyCounts[player][entryIdx],
                        summary.addOnCounts[player][entryIdx],
                        summary.koCounts[player][entryIdx]
                    ))
        if inserts:
            self.executemany(cursor, self.sql.query['insertTourneysPlayer'].replace('%s', self.sql.query['placeholder']), inserts)
            
    
#end class Database

if __name__=="__main__":
    # create a configuration object
    c = Configuration.Config()

    # create a SQL object with the db_server argument set to 'sqlite'
    sql = SQL.Sql(db_server = 'sqlite')

    # create a database connection object
    db_connection = Database(c)

    # print the connection object
    print("database connection object = ", db_connection.connection)

    # drop all indexes on the tables in the database
    db_connection.dropAllIndexes()

    # create all indexes on the tables in the database
    db_connection.createAllIndexes()

    # get the last hand played and print it
    h = db_connection.get_last_hand()
    print("last hand = ", h)

    # get the player ID for a given player name and print it
    hero = db_connection.get_player_id(c, 'PokerStars', 'nutOmatic')
    if hero:
        print("nutOmatic player_id", hero)

    # print the query plan for a sqlite backend (not applicable to other backends)
    if db_connection.backend == 4:
        print()
        c = db_connection.get_cursor()
        c.execute('explain query plan '+sql.query['get_table_name'], (h, ))
        for row in c.fetchall():
            print("Query plan:", row)
        print()

    # get the stats for a given hand and display them
    t0 = time()
    stat_dict = db_connection.get_stats_from_hand(h, "ring")
    t1 = time()
    for p in list(stat_dict.keys()):
        print(p, "  ", stat_dict[p])

    # get the cards for a given hand ID and print them
    print(("cards ="), db_connection.get_cards(u'1'))

    # close the database connection
    db_connection.close_connection

    # print the time taken to get the stats for the given hand
    print(("get_stats took: %4.3f seconds") % (t1-t0))

    # wait for user input before exiting
    print(("Press ENTER to continue."))
    sys.stdin.readline()


#Code borrowed from http://push.cx/2008/caching-dictionaries-in-python-vs-ruby
class LambdaDict(dict):
    """
    A dictionary that creates a new value using a lambda function if the key does not exist.

    :param l: A lambda function that takes a key as an argument and returns a new value
    """
    def __init__(self, l):
        super(LambdaDict, self).__init__()
        self.l = l

    def __getitem__(self, key):
        """
        Get the value for a given key. If the key does not exist, create a new value using the lambda function.

        :param key: Key to search for
        :return: Value for the given key
        """
        if key in self:
            return self.get(key)
        else:
            self.__setitem__(key, self.l(key))
            return self.get(key)

