#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2010-2012, Carl Gherardi
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

########################################################################

#import L10n
#_ = L10n.get_translation()

# This code is based on CarbonToFpdb.py by Matthew Boss
#
# TODO:
#
# -- No support for tournaments (see also the last item below)
# -- Assumes that the currency of ring games is USD
# -- No support for a bring-in or for antes (is the latter in fact unnecessary
#    for hold 'em on Carbon?)
# -- hand.maxseats can only be guessed at
# -- The last hand in a history file will often be incomplete and is therefore
#    rejected
# -- Is behaviour currently correct when someone shows an uncalled hand?
# -- Information may be lost when the hand ID is converted from the native form
#    xxxxxxxx-yyy(y*) to xxxxxxxxyyy(y*) (in principle this should be stored as
#    a string, but the database does not support this). Is there a possibility
#    of collision between hand IDs that ought to be distinct?
# -- Cannot parse tables that run it twice (nor is this likely ever to be
#    possible)
# -- Cannot parse hands in which someone is all in in one of the blinds. Until
#    this is corrected tournaments will be unparseable

import sys
from HandHistoryConverter import *
from decimal_wrapper import Decimal
from TourneySummary import *

class iPoker(HandHistoryConverter):
    """
    A class for converting iPoker hand history files to the PokerTH format.
    """

    sitename = "iPoker"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId   = 14
    copyGameHeader = True   # NOTE: Not sure if this is necessary yet. The file is xml so its likely
    summaryInFile = True

    substitutions = {
        'LS': r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|kr|",  # Used to remove currency symbols from the hand history
        'PLYR': r'(?P<PNAME>[^\"]+)',  # Regex pattern for matching player names
        'NUM': r'(.,\d+)|(\d+)',  # Regex pattern for matching numbers
        'NUM2': r'\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b',  # Regex pattern for matching numbers with spaces

    }

    limits = { 'No limit':'nl', 
              'Pot limit':'pl', 
                  'Limit':'fl',
                     'NL':'nl',
                     'SL':'nl',
                    u'БЛ':'nl',
                     'PL':'pl',
                     'LP':'pl',
                      'L':'fl',
                     'LZ':'nl',
                  }
    games = {              # base, category
                '7 Card Stud' : ('stud','studhi'),
          '7 Card Stud Hi-Lo' : ('stud','studhilo'),
          '7 Card Stud HiLow' : ('stud','studhilo'),
                '5 Card Stud' : ('stud','5_studhi'),
                     'Holdem' : ('hold','holdem'),
            'Six Plus Holdem' : ('hold','6_holdem'),
                      'Omaha' : ('hold','omahahi'),
                'Omaha Hi-Lo' : ('hold','omahahilo'),
                'Omaha HiLow' : ('hold','omahahilo'),
            }

    currencies = { u'€':'EUR', '$':'USD', '':'T$', u'£':'GBP', 'RSD': 'RSD', 'kr': 'SEK'}
    
    # translations from captured groups to fpdb info strings
    Lim_Blinds = {      '0.04': ('0.01', '0.02'),         '0.08': ('0.02', '0.04'),
                        '0.10': ('0.02', '0.05'),         '0.20': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),         '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),         '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),         '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),         '4': ('1.00', '2.00'),
                        '6.00': ('1.00', '3.00'),         '6': ('1.00', '3.00'),
                        '8.00': ('2.00', '4.00'),         '8': ('2.00', '4.00'),
                       '10.00': ('2.00', '5.00'),        '10': ('2.00', '5.00'),
                       '20.00': ('5.00', '10.00'),       '20': ('5.00', '10.00'),
                       '30.00': ('10.00', '15.00'),      '30': ('10.00', '15.00'),
                       '40.00': ('10.00', '20.00'),      '40': ('10.00', '20.00'),
                       '60.00': ('15.00', '30.00'),      '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),      '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),     '100': ('25.00', '50.00'),
                      '150.00': ('50.00', '75.00'),     '150': ('50.00', '75.00'),
                      '200.00': ('50.00', '100.00'),    '200': ('50.00', '100.00'),
                      '400.00': ('100.00', '200.00'),   '400': ('100.00', '200.00'),
                      '800.00': ('200.00', '400.00'),   '800': ('200.00', '400.00'),
                     '1000.00': ('250.00', '500.00'),  '1000': ('250.00', '500.00'),
                     '2000.00': ('500.00', '1000.00'), '2000': ('500.00', '1000.00'),
                  }

    # translations from captured groups to fpdb info strings
    Lim_Blinds = {      '0.04': ('0.01', '0.02'),         '0.08': ('0.02', '0.04'),
                        '0.10': ('0.02', '0.05'),         '0.20': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),         '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),         '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),         '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),         '4': ('1.00', '2.00'),
                        '6.00': ('1.50', '3.00'),         '6': ('1.50', '3.00'),
                        '8.00': ('2.00', '4.00'),         '8': ('2.00', '4.00'),
                       '10.00': ('2.50', '5.00'),        '10': ('2.50', '5.00'),
                       '20.00': ('5.00', '10.00'),       '20': ('5.00', '10.00'),
                       '30.00': ('7.50', '15.00'),       '30': ('7.50', '15.00'),
                       '40.00': ('10.00', '20.00'),      '40': ('10.00', '20.00'),
                       '60.00': ('15.00', '30.00'),      '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),      '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),     '100': ('25.00', '50.00'),
                      '150.00': ('50.00', '75.00'),     '150': ('50.00', '75.00'),
                      '200.00': ('50.00', '100.00'),    '200': ('50.00', '100.00'),
                      '300.00': ('75.00', '150.00'),    '300': ('75.00', '150.00'),
                      '400.00': ('100.00', '200.00'),   '400': ('100.00', '200.00'),
                      '600.00': ('150.00', '300.00'),   '600': ('150.00', '300.00'),
                      '800.00': ('200.00', '400.00'),   '800': ('200.00', '400.00'),
                     '1000.00': ('250.00', '500.00'),  '1000': ('250.00', '500.00'),
                     '2000.00': ('500.00', '1000.00'), '2000': ('500.00', '1000.00'),
                     '4000.00': ('1000.00','2000.00'), '4000': ('1000.00', '2000.00'),
                  }

    months = { 'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6, 'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

    # Static regexes
    re_client = re.compile(r'<client_version>(?P<CLIENT>.*?)</client_version>')
    #re_Identify = re.compile(u"""<\?xml version=\"1\.0\" encoding=\"utf-8\"\?>""")
    re_Identify = re.compile(u"""<game gamecode=\"\d+\">""")
    re_SplitHands = re.compile(r'</game>')
    re_TailSplitHands = re.compile(r'(</game>)')
    re_GameInfo = re.compile(r"""
            <gametype>(?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo|\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo|\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[%(NUM)s]+)(%(LS)s)?/(?P<LBB>[%(NUM)s]+)(%(LS)s)?.+?)
            (\s(%(LS)s)?(?P<SB>[%(NUM)s]+)(%(LS)s)?/(%(LS)s)?(?P<BB>[%(NUM)s]+))?(%(LS)s)?(\sAnte\s(%(LS)s)?(?P<ANTE>[%(NUM)s]+)(%(LS)s)?)?</gametype>\s+?
            <tablename>(?P<TABLE>.+)?</tablename>\s+?
            (<(tablecurrency|tournamentcurrency)>(?P<TABLECURRENCY>.*)</(tablecurrency|tournamentcurrency)>\s+?)?
            (<smallblind>.+</smallblind>\s+?)?
            (<bigblind>.+</bigblind>\s+?)?
            <duration>.+</duration>\s+?
            <gamecount>.+</gamecount>\s+?
            <startdate>.+</startdate>\s+?
            <currency>(?P<CURRENCY>.+)?</currency>\s+?
            <nickname>(?P<HERO>.+)?</nickname>
            """ % substitutions, re.MULTILINE|re.VERBOSE)
    re_GameInfoTrny = re.compile(r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<rewarddrawn>(?P<REWARD>[%(NUM2)s%(LS)s]+)</rewarddrawn>))| 
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)\s\+\s(?P<BIRAKE2>[%(NUM2)s%(LS)s]+)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))|
                        (?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
                        """ % substitutions, re.VERBOSE)
    re_GameInfoTrny2 = re.compile(r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>[%(NUM2)s%(LS)s]+)</totalbuyin>))|
                        (?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
                        """ % substitutions, re.VERBOSE)
    re_Buyin = re.compile(r"""(?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))""" , re.VERBOSE)
    re_TotalBuyin  = re.compile(r"""(?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)\s\+\s(?P<BIRAKE2>[%(NUM2)s%(LS)s]+)</buyin>)""" % substitutions, re.VERBOSE)
    re_HandInfo = re.compile(r'code="(?P<HID>[0-9]+)">\s*?<general>\s*?<startdate>(?P<DATETIME>[\.a-zA-Z-/: 0-9]+)</startdate>', re.MULTILINE)
    re_PlayerInfo = re.compile(r'<player( (seat="(?P<SEAT>[0-9]+)"|name="%(PLYR)s"|chips="(%(LS)s)?(?P<CASH>[%(NUM2)s]+)(%(LS)s)?"|dealer="(?P<BUTTONPOS>(0|1))"|win="(%(LS)s)?(?P<WIN>[%(NUM2)s]+)(%(LS)s)?"|bet="(%(LS)s)?(?P<BET>[^"]+)(%(LS)s)?"|addon="\d*"|rebuy="\d*"|merge="\d*"|reg_code="[\d-]*"))+\s*/>' % substitutions, re.MULTILINE)
    re_Board = re.compile(r'<cards( (type="(?P<STREET>Flop|Turn|River)"|player=""))+>(?P<CARDS>.+?)</cards>', re.MULTILINE)
    re_EndOfHand = re.compile(r'<round id="END_OF_GAME"', re.MULTILINE)
    re_Hero = re.compile(r'<nickname>(?P<HERO>.+)</nickname>', re.MULTILINE)
    re_HeroCards = re.compile(r'<cards( (type="(Pocket|Second\sStreet|Third\sStreet|Fourth\sStreet|Fifth\sStreet|Sixth\sStreet|River)"|player="%(PLYR)s"))+>(?P<CARDS>.+?)</cards>' % substitutions, re.MULTILINE)
    #re_Action = re.compile(r'<action ((no="(?P<ACT>[0-9]+)"|player="%(PLYR)s"|(actiontxt="[^"]+" turntime="[^"]+")|type="(?P<ATYPE>\d+)"|sum="(%(LS)s)(?P<BET>[%(NUM)s]+)"|cards="[^"]*") ?)*/>' % substitutions, re.MULTILINE)
    re_Action = re.compile(r'<action(?:\s+player=\"%(PLYR)s\"|\s+type=\"(?P<ATYPE>\d+)\"|\s+no=\"(?P<ACT>[0-9]+)\"|\s+sum=\"(?P<BET>[%(NUM)s]+)(%(LS)s)\")+/>' % substitutions, re.MULTILINE)
    re_SitsOut = re.compile(r'<event sequence="[0-9]+" type="SIT_OUT" player="(?P<PSEAT>[0-9])"/>', re.MULTILINE)
    re_DateTime1 = re.compile("""(?P<D>[0-9]{2})\-(?P<M>[a-zA-Z]{3})\-(?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""", re.MULTILINE)
    re_DateTime2 = re.compile("""(?P<D>[0-9]{2})[\/\.](?P<M>[0-9]{2})[\/\.](?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""", re.MULTILINE)
    re_DateTime3 = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""", re.MULTILINE)
    re_MaxSeats = re.compile(r'<tablesize>(?P<SEATS>[0-9]+)</tablesize>', re.MULTILINE)
    re_tablenamemtt = re.compile(r'<tablename>(?P<TABLET>.+?)</tablename>', re.MULTILINE)
    re_TourNo = re.compile(r'(?P<TOURNO>\d+)$', re.MULTILINE)
    re_non_decimal = re.compile(r'[^\d.,]+')
    re_Partial = re.compile('<startdate>', re.MULTILINE)
    re_UncalledBets = re.compile('<uncalled_bet_enabled>true<\/uncalled_bet_enabled>')
    re_ClientVersion = re.compile('<client_version>(?P<VERSION>[.\d]+)</client_version>')
    re_FPP = re.compile(r'Pts\s')
    
    def compilePlayerRegexs(self, hand):
        pass

    def playerNameFromSeatNo(self, seatNo, hand):
        """
        Returns the name of the player from the given seat number.

        This special function is required because Carbon Poker records actions by seat number, not by the player's name.

        Args:
            seatNo (int): The seat number of the player.
            hand (Hand): The hand instance containing the players information.

        Returns:
            str: The name of the player from the given seat number.
        """
        for p in hand.players:
            if p[0] == int(seatNo):
                return p[1]


    def readSupportedGames(self):
        """
        Return a list of supported games, where each game is a list of strings.
        The first element of each game list is either "ring" or "tour".
        The second element of each game list is either "stud" or "hold".
        The third element of each game list is either "nl", "pl", or "fl".
        """
        return [
            ["ring", "stud", "fl"],  # ring game with stud format and fixed limit
            ["ring", "hold", "nl"],  # ring game with hold format and no limit
            ["ring", "hold", "pl"],  # ring game with hold format and pot limit
            ["ring", "hold", "fl"],  # ring game with hold format and fixed limit
            ["tour", "hold", "nl"],  # tournament with hold format and no limit
            ["tour", "hold", "pl"],  # tournament with hold format and pot limit
            ["tour", "hold", "fl"],  # tournament with hold format and fixed limit
            ["tour", "stud", "fl"],  # tournament with stud format and fixed limit
        ]
    
    def parseHeader(self, handText, whole_file):
        """
        Parses the header of a hand history and returns the game type.

        Args:
            hand_text (str): The text containing the header of the hand history.
            whole_file (str): The entire text of the hand history.

        Returns:
            str: The game type, if it can be determined from the header or the whole file.
                None otherwise.

        Raises:
            FpdbParseError: If the hand history is an iPoker hand lacking actions/starttime.
            FpdbHandPartial: If the hand history is an iPoker partial hand history without a start date.
        """
        gametype = self.determineGameType(handText)
        if gametype is None:
            gametype = self.determineGameType(whole_file)
        if gametype is None:
            # Catch iPoker hands lacking actions/starttime and funnel them to partial
            if self.re_Partial.search(whole_file):
                tmp = handText[:200]
                log.error(f"iPokerToFpdb.determineGameType: '{tmp}'")
                raise FpdbParseError
            else:
                message = "No startdate"
                raise FpdbHandPartial(f"iPoker partial hand history: {message}")
        return gametype

    def determineGameType(self, handText):
        """
        Given a hand history, extract information about the type of game being played.
        """
        m = self.re_GameInfo.search(handText)
        if not m: return None
        m2 = self.re_MaxSeats.search(handText)
        m3 = self.re_tablenamemtt.search(handText)
        self.info = {}
        mg = m.groupdict()
        mg2 = m2.groupdict()
        mg3 = m3.groupdict()
        tourney = False
        #print "DEBUG: m.groupdict(): %s" % mg
        if mg['GAME'][:2]=='LH':
            mg['CATEGORY'] = 'Holdem'
            mg['LIMIT'] = 'L'
            mg['BB'] = mg['LBB']
        if 'GAME' in mg:
            if mg['CATEGORY'] is None:
                (self.info['base'], self.info['category']) = ('hold', '5_omahahi') 
            else:
                (self.info['base'], self.info['category']) = self.games[mg['CATEGORY']]
        if 'LIMIT' in mg:
            self.info['limitType'] = self.limits[mg['LIMIT']]
        if 'HERO' in mg:
            self.hero = mg['HERO']
        if 'SB' in mg:
            self.info['sb'] = self.clearMoneyString(mg['SB'])
            if not mg['SB']: tourney = True
        if 'BB' in mg:
            self.info['bb'] = self.clearMoneyString(mg['BB'])
        if 'SEATS' in mg2:
            self.info['seats'] = mg2['SEATS']
            
        if self.re_UncalledBets.search(handText):
            self.uncalledbets = False
        else:
            self.uncalledbets = True
            if mv := self.re_ClientVersion.search(handText):
                major_version = mv.group('VERSION').split('.')[0]
                if int(major_version) >= 20:
                    self.uncalledbets = False

        if tourney:
            self.info['type'] = 'tour'
            self.info['currency'] = 'T$'
            if 'TABLET' in mg3:
                self.info['table_name'] = mg3['TABLET']
                print(mg3['TABLET'])
            # FIXME: The sb/bb isn't listed in the game header. Fixing to 1/2 for now
            self.tinfo = {} # FIXME?: Full tourney info is only at the top of the file. After the
                            #         first hand in a file, there is no way for auto-import to
                            #         gather the info unless it reads the entire file every time.
            mt = self.re_TourNo.search(mg['TABLE'])
            if mt:
                self.tinfo['tourNo'] = mt.group('TOURNO')
            else:
                tourNo = mg['TABLE'].split(',')[-1].strip().split(' ')[0]
                if tourNo.isdigit():
                    self.tinfo['tourNo'] = tourNo

            self.tablename = '1'
            if not mg['CURRENCY'] or mg['CURRENCY']=='fun':
                self.tinfo['buyinCurrency'] = 'play'
            else:
                self.tinfo['buyinCurrency'] = mg['CURRENCY']
            self.tinfo['buyin'] = 0
            self.tinfo['fee'] = 0
            client_match =  self.re_client.search(handText)
            re_client_split = '.'.join(client_match['CLIENT'].split('.')[:2])
            if re_client_split == '23.5':   #betclic fr
                matches = list(self.re_GameInfoTrny.finditer(handText))
                if len(matches) > 0:
                    mg['TOURNO'] = matches[0].group('TOURNO')
                    mg['NAME'] = matches[1].group('NAME') 
                    mg['REWARD'] = matches[2].group('REWARD')
                    mg['PLACE'] = matches[3].group('PLACE') 
                    mg['BIAMT'] = matches[4].group('BIAMT') 
                    mg['BIRAKE'] = matches[4].group('BIRAKE')
                    mg['BIRAKE2'] = matches[4].group('BIRAKE2') 
                    mg['TOTBUYIN'] = matches[5].group('TOTBUYIN') 
                    mg['WIN'] = matches[6].group('WIN') 

            else:
                matches = list(self.re_GameInfoTrny2.finditer(handText))
                if len(matches) > 0:
                    mg['TOURNO'] = matches[0].group('TOURNO')
                    mg['NAME'] = matches[1].group('NAME') 
                    mg['PLACE'] = matches[2].group('PLACE') 
                    mg['BIAMT'] = matches[3].group('BIAMT') 
                    mg['BIRAKE'] = matches[3].group('BIRAKE')
                    mg['TOTBUYIN'] = matches[4].group('TOTBUYIN') 
                    mg['WIN'] = matches[5].group('WIN') 


            if mg['TOURNO']:
                self.tinfo['tour_name'] = mg['NAME']
                self.tinfo['tourNo'] = mg['TOURNO']
            if mg['PLACE'] and mg['PLACE'] != 'N/A':
                self.tinfo['rank'] = int(mg['PLACE'])
                
            if 'winnings' not in self.tinfo:
                self.tinfo['winnings'] = 0  # Initialize 'winnings' if it doesn't exist yet

            if mg['WIN'] and mg['WIN']  != 'N/A':
                self.tinfo['winnings'] += int(100*Decimal(self.clearMoneyString(self.re_non_decimal.sub('',mg['WIN']))))
                    
              
            if not mg['BIRAKE']: #and mg['TOTBUYIN']:
                m3 = self.re_TotalBuyin.search(handText)
                if m3:
                    mg = m3.groupdict()
                elif mg['BIAMT']: mg['BIRAKE'] = '0'


            if mg['BIAMT'] and self.re_FPP.match(mg['BIAMT']):
                self.tinfo['buyinCurrency'] = 'FPP'

            if mg['BIRAKE']:
                    #FIXME: tournament no looks liek it is in the table name
                mg['BIRAKE'] = self.clearMoneyString(self.re_non_decimal.sub('',mg['BIRAKE']))
                mg['BIAMT']  = self.clearMoneyString(self.re_non_decimal.sub('',mg['BIAMT']))
                if re_client_split == '23.5':
                    if mg['BIRAKE2']:
                        self.tinfo['buyin'] += int(100*Decimal(self.clearMoneyString(self.re_non_decimal.sub('',mg['BIRAKE2']))))
                    m4 = self.re_Buyin.search(handText)
                    if m4:
                        
                        self.tinfo['fee']   = int(100*Decimal(self.clearMoneyString(self.re_non_decimal.sub('',mg['BIRAKE']))))
                        self.tinfo['buyin'] = int(100*Decimal(self.clearMoneyString(self.re_non_decimal.sub('',mg['BIRAKE2']))))

                    # FIXME: <place> and <win> not parsed at the moment.
                    #  NOTE: Both place and win can have the value N/A
            if self.tinfo['buyin'] == 0:
                self.tinfo['buyinCurrency'] = 'FREE'
            if self.tinfo.get('tourNo') is None:
                log.error(("iPokerToFpdb.determineGameType: Could Not Parse tourNo"))
                raise FpdbParseError
        else:
            self.info['type'] = 'ring'
            self.tablename = mg['TABLE']
            if not mg['TABLECURRENCY'] and not mg['CURRENCY']:
                self.info['currency'] = 'play'
            elif not mg['TABLECURRENCY']:
                self.info['currency'] = mg['CURRENCY']
            else:
                self.info['currency'] = mg['TABLECURRENCY']

            if self.info['limitType'] == 'fl' and self.info['bb'] is not None:
                try:
                    self.info['sb'] = self.Lim_Blinds[self.clearMoneyString(mg['BB'])][0]
                    self.info['bb'] = self.Lim_Blinds[self.clearMoneyString(mg['BB'])][1]
                except KeyError as e:
                    tmp = handText[:200]
                    log.error(
                        f"iPokerToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'"
                    )
                    raise FpdbParseError from e
        
        return self.info

    def readHandInfo(self, hand):
        """
        Parses the hand text and extracts relevant information about the hand.

        Args:
            hand: An instance of the Hand class that represents the hand being parsed.

        Raises:
            FpdbParseError: If the hand text cannot be parsed.

        Returns:
            None
        """
        # Search for the relevant information in the hand text
        m = self.re_HandInfo.search(hand.handText)
        if m is None:
            # If the information cannot be found, log an error and raise an exception
            tmp = hand.handText[:200]
            log.error(f"iPokerToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError
        
        # Extract the relevant information from the match object
        mg = m.groupdict()
        

        # Set the table name and maximum number of seats for the hand
        hand.tablename = self.tablename
        if self.info['seats']:
            hand.maxseats = int(self.info['seats'])


        # Set the hand ID for the hand
        hand.handid = m.group('HID')

        # Parse the start time for the hand
        if m2 := self.re_DateTime1.search(m.group('DATETIME')):
            # If the datetime string matches the first format, parse it accordingly
            month = self.months[m2.group('M')]
            sec = m2.group('S')
            if m2.group('S') is None:
                sec = '00'
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
        else:
            # If the datetime string does not match the first format, try the second format
            try:
                hand.startTime = datetime.datetime.strptime(m.group('DATETIME'), '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                # If the datetime string cannot be parsed, try the third format
                if date_match := self.re_DateTime2.search(m.group('DATETIME')):
                    datestr = '%d/%m/%Y %H:%M:%S' if '/' in m.group('DATETIME') else '%d.%m.%Y %H:%M:%S'
                    if date_match.group('S') is None:
                        datestr = '%d/%m/%Y %H:%M'
                else:
                    date_match1 = self.re_DateTime3.search(m.group('DATETIME'))
                    datestr = '%Y/%m/%d %H:%M:%S'
                    if date_match1 is None:
                        # If the datetime string cannot be parsed in any format, log an error and raise an exception
                        log.error(
                            f"iPokerToFpdb.readHandInfo Could not read datetime: '{hand.handid}'"
                        )
                        raise FpdbParseError from e
                    if date_match1.group('S') is None:
                        datestr = '%Y/%m/%d %H:%M'
                hand.startTime = datetime.datetime.strptime(m.group('DATETIME'), datestr)

        # If the hand is a tournament hand, set additional information
        if self.info['type'] == 'tour':
            hand.tourNo = self.tinfo['tourNo']
            hand.buyinCurrency = self.tinfo['buyinCurrency']
            hand.buyin = self.tinfo['buyin']
            hand.fee = self.tinfo['fee']
            hand.tablename = f"{self.info['table_name']}"


    def readPlayerStacks(self, hand):
        """
        Extracts player information from the hand text and populates the Hand object with
        player stacks and winnings.

        Args:
            hand (Hand): Hand object to populate with player information.

        Raises:
            FpdbParseError: If there are fewer than 2 players in the hand.

        Returns:
            None
        """
        # Initialize dictionaries and regex pattern
        self.playerWinnings, plist = {}, {}
        m = self.re_PlayerInfo.finditer(hand.handText)

        # Extract player information from regex matches
        for a in m:
            ag = a.groupdict()
            # Create a dictionary entry for the player with their seat, stack, winnings,
            # and sitout status
            plist[a.group('PNAME')] = [int(a.group('SEAT')), self.clearMoneyString(a.group('CASH')), 
                                        self.clearMoneyString(a.group('WIN')), False]
            # If the player is the button, set the button position in the Hand object
            if a.group('BUTTONPOS') == '1':
                hand.buttonpos = int(a.group('SEAT'))

        # Ensure there are at least 2 players in the hand
        if len(plist)<=1:
            # Hand cancelled
            log.error(f"iPokerToFpdb.readPlayerStacks: '{hand.handid}'")
            raise FpdbParseError

        # Add remaining players to the Hand object and playerWinnings dictionary if they won
        for pname in plist:
            seat, stack, win, sitout = plist[pname]
            hand.addPlayer(seat, pname, stack, None, sitout)
            if Decimal(win) != 0:
                self.playerWinnings[pname] = win

        # Set the maxseats attribute in the Hand object if it is not already set
        if hand.maxseats is None:
            if self.info['type'] == 'tour' and self.maxseats==0:
                hand.maxseats = self.guessMaxSeats(hand)
                self.maxseats = hand.maxseats
            elif self.info['type'] == 'tour':
                hand.maxseats = self.maxseats
            else:
                hand.maxseats = None


    def markStreets(self, hand):
        """
        Extracts the rounds of a hand and adds them to the Hand object

        Args:
            hand (Hand): the Hand object to which the rounds will be added
        """
        if hand.gametype['base'] in ('hold'):
            # Extract rounds for hold'em game
            m = re.search(
                r'(?P<PREFLOP>.+(?=<round no="2">)|.+)'  # Preflop round
                r'(<round no="2">(?P<FLOP>.+(?=<round no="3">)|.+))?'  # Flop round
                r'(<round no="3">(?P<TURN>.+(?=<round no="4">)|.+))?'  # Turn round
                r'(<round no="4">(?P<RIVER>.+))?',  # River round
                hand.handText, re.DOTALL
            )
        elif hand.gametype['base'] in ('stud'):
            # Extract rounds for stud game
            if hand.gametype['category'] == '5_studhi':
                # Extract rounds for 5-card stud high game
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<SECOND>.+(?=<round no="3">)|.+))?'  # Second round
                    r'(<round no="3">(?P<THIRD>.+(?=<round no="4">)|.+))?'  # Third round
                    r'(<round no="4">(?P<FOURTH>.+(?=<round no="5">)|.+))?'  # Fourth round
                    r'(<round no="5">(?P<FIFTH>.+))?',  # Fifth round
                    hand.handText, re.DOTALL
                )
            else:
                # Extract rounds for 7-card stud high/low game
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<THIRD>.+(?=<round no="3">)|.+))?'  # Third round
                    r'(<round no="3">(?P<FOURTH>.+(?=<round no="4">)|.+))?'  # Fourth round
                    r'(<round no="4">(?P<FIFTH>.+(?=<round no="5">)|.+))?'  # Fifth round
                    r'(<round no="5">(?P<SIXTH>.+(?=<round no="6">)|.+))?'  # Sixth round
                    r'(<round no="6">(?P<SEVENTH>.+))?',  # Seventh round
                    hand.handText, re.DOTALL
                )
        hand.addStreets(m)


    def readCommunityCards(self, hand, street):
        """
        Parse the community cards for the given street and set them in the hand object.

        Args:
            hand (Hand): The hand object.
            street (str): The street to parse the community cards for.

        Raises:
            FpdbParseError: If the community cards could not be parsed.

        Returns:
            None
        """
        cards = []
        # Search for the board cards in the hand's streets
        if m := self.re_Board.search(hand.streets[street]):
            # Split the card string into a list of cards
            cards = m.group('CARDS').strip().split(' ')
            # Format the cards
            cards = [c[1:].replace('10', 'T') + c[0].lower() for c in cards]
            # Set the community cards in the hand object
            hand.setCommunityCards(street, cards)
        else:
            # Log an error if the board cards could not be found
            log.error(f"iPokerToFpdb.readCommunityCards: '{hand.handid}'")
            # Raise an exception
            raise FpdbParseError


    def readAntes(self, hand):
        """
        Reads the antes for each player in the given hand.

        Args:
            hand (Hand): The hand to read the antes from.

        Returns:
            None
        """
        # Find all the antes in the hand text using a regular expression
        m = self.re_Action.finditer(hand.handText)

        # Loop through each ante found
        for a in m:
            # If the ante is of type 15, add it to the hand
            if a.group('ATYPE') == '15':
                hand.addAnte(a.group('PNAME'), self.clearMoneyString(a.group('BET')))


    def readBringIn(self, hand):
        """
        Reads the bring-in for a hand and sets the small blind (sb) and big blind (bb) values if they are not already set.

        Args:
            hand (Hand): The hand object for which to read the bring-in.

        Returns:
            None
        """
        # If sb and bb are not already set, set them to default values
        if hand.gametype['sb'] is None and hand.gametype['bb'] is None:
            hand.gametype['sb'] = "1"  # default small blind value
            hand.gametype['bb'] = "2"  # default big blind value


    def readBlinds(self, hand):
        """
        Parses hand history to extract blind information for each player in the hand.

        :param hand: Hand object containing the hand history.
        :type hand: Hand
        """
        # Find all actions in the preflop street
        for a in self.re_Action.finditer(hand.streets['PREFLOP']):
            if a.group('ATYPE') == '1':
                # If the action is a small blind, add it to the hand object
                hand.addBlind(a.group('PNAME'), 'small blind', self.clearMoneyString(a.group('BET')))
                # If the small blind amount is not already set, set it
                if not hand.gametype['sb']:
                    hand.gametype['sb'] = self.clearMoneyString(a.group('BET'))

        # Find all actions in the preflop street
        m = self.re_Action.finditer(hand.streets['PREFLOP'])
        # Create a dictionary to store big blind information for each player
        blinds = {
            int(a.group('ACT')): a.groupdict()
            for a in m
            if a.group('ATYPE') == '2'
        }
        # Iterate over the big blind information and add it to the hand object
        for b in sorted(list(blinds.keys())):
            type = 'big blind'
            blind = blinds[b]
            # If the big blind amount is not already set, set it
            if not hand.gametype['bb']:
                hand.gametype['bb'] = self.clearMoneyString(blind['BET'])
            # If the small blind amount is set, check if the amount is bigger than the small blind amount
            elif hand.gametype['sb']:
                bb = Decimal(hand.gametype['bb'])
                amount = Decimal(self.clearMoneyString(blind['BET']))
                if amount > bb:
                    type = 'both'
            # Add the big blind to the hand object
            hand.addBlind(blind['PNAME'], type, self.clearMoneyString(blind['BET']))
        # Fix tournament blinds if necessary
        self.fixTourBlinds(hand)


    def fixTourBlinds(self, hand):
        """
        Fix tournament blinds if small blind is missing or sb/bb is all-in.

        :param hand: A dictionary containing the game type information.
        :return: None
        """
        # FIXME
        # The following should only trigger when a small blind is missing in a tournament, or the sb/bb is ALL_IN
        # see http://sourceforge.net/apps/mantisbt/fpdb/view.php?id=115
        if hand.gametype['type'] != 'tour':
            return
        if hand.gametype['sb'] is None and hand.gametype['bb'] is None:
            hand.gametype['sb'] = "1"
            hand.gametype['bb'] = "2"
        elif hand.gametype['sb'] is None:
            hand.gametype['sb'] = str(int(old_div(Decimal(hand.gametype['bb']),2)))
        elif hand.gametype['bb'] is None:
            hand.gametype['bb'] = str(int(Decimal(hand.gametype['sb']))*2)
        if int(old_div(Decimal(hand.gametype['bb']),2)) != int(Decimal(hand.gametype['sb'])):
            if int(old_div(Decimal(hand.gametype['bb']),2)) < int(Decimal(hand.gametype['sb'])):
                hand.gametype['bb'] = str(int(Decimal(hand.gametype['sb']))*2)
            else:
                hand.gametype['sb'] = str(int((Decimal(hand.gametype['bb']))//2))


    def readButton(self, hand):
        # Found in re_Player
        pass

    def readHoleCards(self, hand):
        """
        Parses a Hand object to extract hole card information for each player on each street. 
        Adds the hole card information to the Hand object.

        Args:
            hand: Hand object to extract hole card information from

        Returns:
            None
        """

        # streets PREFLOP, PREDRAW, and THIRD are special cases beacause we need to grab hero's cards
        for street in ('PREFLOP', 'DEAL'):
            if street in hand.streets.keys():
                # Find all instances of hero's cards in the street and add them to the Hand object
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    player = found.group('PNAME')
                    cards = found.group('CARDS').split(' ')
                    cards = [c[1:].replace('10', 'T') + c[0].lower().replace('x', '') for c in cards]
                    if player == self.hero and cards[0]:
                        hand.hero = player
                    hand.addHoleCards(street, player, closed=cards, shown=True, mucked=False, dealt=True)

        # Go through each street in the Hand object and add hole card information for each player
        for street, text in list(hand.streets.items()):
            if not text or street in ('PREFLOP', 'DEAL'): 
                continue  # already done these
            m = self.re_HeroCards.finditer(hand.streets[street])
            for found in m:
                player = found.group('PNAME')
                if player is not None:
                    cards = found.group('CARDS').split(' ')

                    # Handle special case where hero is not the player and it's the seventh street in a stud game
                    if street == 'SEVENTH' and self.hero != player:
                        newcards = []
                        oldcards = [c[1:].replace('10', 'T') + c[0].lower() for c in cards if c[0].lower()!='x']
                    else:
                        newcards = [c[1:].replace('10', 'T') + c[0].lower() for c in cards if c[0].lower()!='x']
                        oldcards = []

                    # Handle special case where hero is the player and it's the third street in a stud game
                    if street == 'THIRD' and len(newcards) == 3 and self.hero == player: 
                        hand.hero = player
                        hand.dealt.add(player) 
                        hand.addHoleCards(
                            street,
                            player,
                            closed=newcards[:2],
                            open=[newcards[2]],
                            shown=True,
                            mucked=False,
                            dealt=False,
                        )

                    # Handle special case where hero is the player and it's the second street in a stud game
                    elif street == 'SECOND' and len(newcards) == 2 and self.hero == player: 
                        hand.hero = player
                        hand.dealt.add(player)
                        hand.addHoleCards(street, player, closed=[newcards[0]], open=[newcards[1]], shown=True, mucked=False, dealt=False)

                    # Handle all other cases where hole card information needs to be added to the Hand object
                    else:
                        hand.addHoleCards(street, player, open=newcards, closed=oldcards, shown=True, mucked=False, dealt=False)


    def readAction(self, hand, street):
        """
        Extracts actions from a hand and adds them to the corresponding street in a Hand object.

        Args:
            hand (Hand): Hand object to which the actions will be added.
            street (int): Number of the street in the hand (0 for preflop, 1 for flop, etc.).

        Returns:
            None
        """
        # HH format doesn't actually print the actions in order!
        m = self.re_Action.finditer(hand.streets[street])
        actions = {int(a.group('ACT')): a.groupdict() for a in m}

        # Add each action to the corresponding method of the Hand object.
        # atype is the action type (0 for fold, 4 for check, etc.).
        for a in sorted(list(actions.keys())):
            action = actions[a]
            atype = action['ATYPE']
            player = action['PNAME']
            bet = self.clearMoneyString(action['BET'])

            if atype == '0':
                hand.addFold(street, player)
            elif atype == '4':
                hand.addCheck(street, player)
            elif atype == '3':
                hand.addCall(street, player, bet)
            elif atype == '23': # Raise to
                hand.addRaiseTo(street, player, bet)
            elif atype == '6': # Raise by
                # This is only a guess
                hand.addRaiseBy(street, player, bet)
            elif atype == '5':
                hand.addBet(street, player, bet)
            elif atype == '16': # BringIn
                hand.addBringIn(player, bet)
            elif atype == '7':
                hand.addAllIn(street, player, bet)
            elif atype == '15': # Ante
                pass # Antes dealt with in readAntes
            elif atype in ['1', '2', '8']: # sb/bb/no action this hand (joined table)
                pass
            elif atype == '9': # FIXME: Sitting out
                hand.addFold(street, player)
            else:
                log.error(
                    # Log an error for unimplemented actions
                    ("DEBUG:")
                    + " "
                    + f"Unimplemented readAction: '{action['PNAME']}' '{action['ATYPE']}'"
                )


    def readShowdownActions(self, hand):
        # Cards lines contain cards
        pass

    def readCollectPot(self, hand):
        """
        Sets the uncalled bets for the given hand and adds collect pot actions for each player with non-zero winnings.

        Args:
            hand: The Hand object to update with the collect pot actions.
        """
        hand.setUncalledBets(self.uncalledbets)
        for pname, pot in list(self.playerWinnings.items()):
            hand.addCollectPot(player=pname, pot=self.clearMoneyString(pot))
            # add collect pot action for player with non-zero winnings


    def readShownCards(self, hand):
        # Cards lines contain cards
        pass

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """
        Generate a regular expression pattern for table title.

        Args:
        - type: A string value.
        - table_name: A string value representing the table name.
        - tournament: A string value representing the tournament.
        - table_number: An integer value representing the table number.

        Returns:
        - A string value representing the regular expression pattern for table title.
        """
        # Log the input parameters
        log.info(
            f"iPoker getTableTitleRe: table_name='{table_name}' tournament='{tournament}' table_number='{table_number}'"
        )

        # Generate the regex pattern based on the input parameters
        regex = f"{table_name}"
        
        if type == "tour":
            regex = f"([^\(]+)\s{table_number}"

            
            print(regex)
            
            return regex
        elif table_name.find('(No DP),') != -1:
            regex = table_name.split('(No DP),')[0]
        elif table_name.find(',') != -1:
            regex = table_name.split(',')[0]
        else:
            regex = table_name.split(' ')[0]

        # Log the generated regex pattern and return it
        log.info(f"iPoker getTableTitleRe: returns: '{regex}'")
        return regex

