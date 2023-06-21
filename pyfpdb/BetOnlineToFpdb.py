#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2008-2011, Chaz Littlejohn
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

from __future__ import division
from L10n import set_locale_translation
from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

# TODO: straighten out discards for draw games

import sys
from HandHistoryConverter import *
from decimal_wrapper import Decimal

# BetOnline HH Format
set_locale_translation()
class BetOnline(HandHistoryConverter):
    """
    A class for converting hand histories from BetOnline format to a standardized format.
    """

    # Class Variables

    sitename = "BetOnline"
    skin = "BetOnline"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId = 19  # Needs to match id entry in Sites database
    sym = {'USD': "\$", 'CAD': "\$", 'T$': "", "EUR": "€", "GBP": "\xa3", "play": ""}  # ADD Euro, Sterling, etc HERE

    substitutions = {
        'LS': u"\$|€|",  # legal currency symbols - Euro(cp1252, utf-8)
        'PLYR': r'(?P<PNAME>.+?)',
        'NUM': u".,\d",
    }
                    
    # translations from captured groups to fpdb info strings
    Lim_Blinds = {  '0.04': ('0.01', '0.02'),        '0.08': ('0.02', '0.04'),
                        '0.10': ('0.02', '0.05'),    '0.20': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),    '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),       '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),       '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),       '4': ('1.00', '2.00'),
                        '6.00': ('1.00', '3.00'),       '6': ('1.00', '3.00'),
                        '8.00': ('2.00', '4.00'),       '8': ('2.00', '4.00'),
                       '10.00': ('2.00', '5.00'),      '10': ('2.00', '5.00'),
                       '20.00': ('5.00', '10.00'),     '20': ('5.00', '10.00'),
                       '30.00': ('10.00', '15.00'),    '30': ('10.00', '15.00'),
                       '40.00': ('10.00', '20.00'),    '40': ('10.00', '20.00'),
                       '60.00': ('15.00', '30.00'),    '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),    '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),   '100': ('25.00', '50.00'),
                      '200.00': ('50.00', '100.00'),  '200': ('50.00', '100.00'),
                      '400.00': ('100.00', '200.00'), '400': ('100.00', '200.00'),
                      '800.00': ('200.00', '400.00'), '800': ('200.00', '400.00'),
                     '1000.00': ('250.00', '500.00'),'1000': ('250.00', '500.00')
                  }

    limits = { 'No Limit':'nl', 'Pot Limit':'pl', 'Limit':'fl', 'LIMIT':'fl' }
    games = {                          # base, category
                              "Hold'em" : ('hold','holdem'), 
                                'Omaha' : ('hold','omahahi'),
                          'Omaha Hi/Lo' : ('hold','omahahilo'),
                                 'Razz' : ('stud','razz'), 
                          '7 Card Stud' : ('stud','studhi'),
                    '7 Card Stud Hi/Lo' : ('stud','studhilo'),
                               'Badugi' : ('draw','badugi'),
              'Triple Draw 2-7 Lowball' : ('draw','27_3draw'),
              'Single Draw 2-7 Lowball' : ('draw','27_1draw'),
                          '5 Card Draw' : ('draw','fivedraw')
               }
    mixes = {
                                 'HORSE': 'horse',
                                '8-Game': '8game',
                                  'HOSE': 'hose',
                         'Mixed PLH/PLO': 'plh_plo',
                       'Mixed Omaha H/L': 'plo_lo',
                        'Mixed Hold\'em': 'mholdem',
                           'Triple Stud': '3stud'
               } # Legal mixed games
    currencies = { u'€':'EUR', '$':'USD', '':'T$' }
    
    skins = {
                       'BetOnline Poker': 'BetOnline',
                             'PayNoRake': 'PayNoRake',
                       'ActionPoker.com': 'ActionPoker',
                            'Gear Poker': 'GearPoker',
                'SportsBetting.ag Poker': 'SportsBetting.ag',
                          'Tiger Gaming': 'Tiger Gaming'
               } # Legal mixed games

    # Static regexes
    re_GameInfo     = re.compile(u"""
          (?P<SKIN>BetOnline\sPoker|PayNoRake|ActionPoker\.com|Gear\sPoker|SportsBetting\.ag\sPoker|Tiger\sGaming)\sGame\s\#(?P<HID>[0-9]+):\s+
          (\{.*\}\s+)?(Tournament\s\#                # open paren of tournament info
          (?P<TOURNO>\d+):\s?
          # here's how I plan to use LS
          (?P<BUYIN>(?P<BIAMT>(%(LS)s)[%(NUM)s]+)?\+?(?P<BIRAKE>(%(LS)s)[%(NUM)s]+)?\+?(?P<BOUNTY>(%(LS)s)[%(NUM)s]+)?\s?|Freeroll|)\s+)?
          # close paren of tournament info
          (?P<GAME>Hold\'em|Razz|7\sCard\sStud|7\sCard\sStud\sHi/Lo|Omaha|Omaha\sHi/Lo|Badugi|Triple\sDraw\s2\-7\sLowball|Single\sDraw\s2\-7\sLowball|5\sCard\sDraw)\s
          (?P<LIMIT>No\sLimit|Limit|LIMIT|Pot\sLimit)?,?\s?
          (
              \(?                            # open paren of the stakes
              (?P<CURRENCY>%(LS)s|)?
              (?P<SB>[%(NUM)s]+)/(%(LS)s)?
              (?P<BB>[%(NUM)s]+)
              \)?                        # close paren of the stakes
          )?
          \s?-\s
          (?P<DATETIME>.*$)
        """ % substitutions, re.MULTILINE|re.VERBOSE)

    re_PlayerInfo   = re.compile(u"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.*)\s
          \((%(LS)s)?(?P<CASH>[%(NUM)s]+)\sin\s[cC]hips\)""" % substitutions, 
          re.MULTILINE|re.VERBOSE)

    re_HandInfo1     = re.compile("""
          ^Table\s\'(?P<TABLE>[\/,\.\-\ &%\$\#a-zA-Z\d\'\(\)]+)\'\s
          ((?P<MAX>\d+)-max\s)?
          (?P<MONEY>\((Play\sMoney|Real\sMoney)\)\s)?
          (Seat\s\#(?P<BUTTON>\d+)\sis\sthe\sbutton)?""", 
          re.MULTILINE|re.VERBOSE)
    
    re_HandInfo2     = re.compile("""
          ^Table\s(?P<TABLE>[\/,\.\-\ &%\$\#a-zA-Z\d\']+)\s
          (?P<MONEY>\((Play\sMoney|Real\sMoney)\)\s)?
          (Seat\s\#(?P<BUTTON>\d+)\sis\sthe\sbutton)?""", 
          re.MULTILINE|re.VERBOSE)

    re_Identify     = re.compile(u'(BetOnline\sPoker|PayNoRake|ActionPoker\.com|Gear\sPoker|SportsBetting\.ag\sPoker|Tiger\sGaming)\sGame\s\#\d+')
    re_SplitHands   = re.compile('\n\n\n+')
    re_TailSplitHands   = re.compile('(\n\n\n+)')
    re_Button       = re.compile('Seat #(?P<BUTTON>\d+) is the button', re.MULTILINE)
    re_Board1        = re.compile(r"Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\]")
    re_Board2        = re.compile(r"\[(?P<CARDS>.+)\]")
    re_Hole          = re.compile(r"\*\*\*\sHOLE\sCARDS\s\*\*\*")


    re_DateTime1     = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?\s(?P<TZ>.*$)""", re.MULTILINE)
    re_DateTime2     = re.compile("""(?P<Y>[0-9]{4})\-(?P<M>[0-9]{2})\-(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""", re.MULTILINE)

    re_PostSB           = re.compile(r"^%(PLYR)s: [Pp]osts small blind (%(LS)s)?(?P<SB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_PostBB           = re.compile(r"^%(PLYR)s: ([Pp]osts big blind|[Pp]osts? [Nn]ow)( (%(LS)s)?(?P<BB>[%(NUM)s]+))?" %  substitutions, re.MULTILINE)
    re_Antes            = re.compile(r"^%(PLYR)s: ante processed (%(LS)s)?(?P<ANTE>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_BringIn          = re.compile(r"^%(PLYR)s: brings[- ]in( low|) for (%(LS)s)?(?P<BRINGIN>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_PostBoth         = re.compile(r"^%(PLYR)s: [Pp]ost dead (%(LS)s)?(?P<SBBB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_HeroCards        = re.compile(r"^Dealt [Tt]o %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % substitutions, re.MULTILINE)
    re_Action           = re.compile(r"""
                        ^%(PLYR)s:?(?P<ATYPE>\shas\sleft\sthe\stable|\s[Bb]ets|\s[Cc]hecks|\s[Rr]aises|\s[Cc]alls|\s[Ff]olds|\s[Dd]iscards|\s[Ss]tands\spat|\sReraises)
                        (\s(%(LS)s)?(?P<BET>[%(NUM)s]+))?(\sto\s(%(LS)s)?(?P<BETTO>[%(NUM)s]+))?  # the number discarded goes in <BET>
                        \s*(and\sis\s[Aa]ll.[Ii]n)?
                        (\son|\scards?)?
                        (\s\[(?P<CARDS>.+?)\])?\.?\s*$"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    re_ShowdownAction   = re.compile(r"^%s: shows (?P<CARDS>.*)" % substitutions['PLYR'], re.MULTILINE)
    re_sitsOut          = re.compile("^%s sits out" %  substitutions['PLYR'], re.MULTILINE)
    re_JoinsTable       = re.compile("^.+ joins the table at seat #\d+", re.MULTILINE)
    re_TotalPot         = re.compile(r"^Total pot (?P<POT>[%(NUM)s]+)( \| Rake (?P<RAKE>[%(NUM)s]+))?", re.MULTILINE)
    re_ShownCards       = re.compile(r"Seat (?P<SEAT>[0-9]+): %(PLYR)s (\(.+?\)  )?(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and won \([%(NUM)s]+\))?" %  substitutions, re.MULTILINE)
    re_CollectPot       = re.compile(r"Seat (?P<SEAT>[0-9]+): %(PLYR)s (\(.+?\)  )?(collected|showed \[.*\] and won) \((%(LS)s)?(?P<POT>[%(NUM)s]+)\)" %  substitutions, re.MULTILINE)

    def compilePlayerRegexs(self,  hand):
        pass

    def readSupportedGames(self):
        """
        Returns a list of supported games.
        """
        return [
            ["ring", "hold", "nl"],  # Ring hold'em no-limit
            ["ring", "hold", "pl"],  # Ring hold'em pot-limit
            ["ring", "hold", "fl"],  # Ring hold'em fixed-limit

            # ["ring", "stud", "fl"],

            # ["ring", "draw", "fl"],
            # ["ring", "draw", "pl"],
            # ["ring", "draw", "nl"],

            ["tour", "hold", "nl"],  # Tournament hold'em no-limit
            ["tour", "hold", "pl"],  # Tournament hold'em pot-limit
            ["tour", "hold", "fl"],  # Tournament hold'em fixed-limit

            # ["tour", "stud", "fl"],

            # ["tour", "draw", "fl"],
            # ["tour", "draw", "pl"],
            # ["tour", "draw", "nl"],
        ]

    def determineGameType(self, handText):
        """
        Determine the game type (limit, game variant, etc.) from a BetOnline hand history.

        Args:
            handText (str): The hand history text.

        Returns:
            dict: A dictionary containing the extracted game type information.
        """

        info = {}

        # Search for the game information in the hand history text
        m = self.re_GameInfo.search(handText)

        if not m:
            # If no game information is found, check if it's a partial hand history where a player is joining the table
            if m2 := self.re_JoinsTable.search(handText):
                raise FpdbHandPartial(_("BetOnlineToFpdb.determineGameType: Partial hand history: 'Player joining table'"))

            tmp = handText[:200]
            log.error(f"BetOnlineToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()

        if mg['LIMIT']:
            # Determine the limit type and check if it's a Pot-Limit Omaha game
            info['limitType'] = self.limits[mg['LIMIT']]

            if info['limitType'] == 'pl':
                # Check if it's an Omaha game by looking for hero cards with four cards
                m = self.re_HeroCards.search(handText)

                if m and len(m.group('NEWCARDS').split(' ')) == 4:
                    (info['base'], info['category']) = self.games['Omaha']
        else:
            info['limitType'] = self.limits['No Limit']

        if 'SKIN' in mg:
            # Set the skin based on the extracted value
            self.skin = self.skins[mg['SKIN']]

        if 'GAME' in mg and not info.get('base'):
            # Determine the game variant if it hasn't been determined already
            (info['base'], info['category']) = self.games[mg['GAME']]

        if 'SB' in mg:
            # Extract and store the small blind value
            info['sb'] = self.clearMoneyString(mg['SB'])

        if 'BB' in mg:
            # Extract and store the big blind value
            info['bb'] = self.clearMoneyString(mg['BB'])

        if 'CURRENCY' in mg and mg['CURRENCY'] is not None:
            # Set the currency based on the extracted value
            info['currency'] = self.currencies[mg['CURRENCY']]
        else:
            info['currency'] = 'USD'

        if 'MIXED' in mg and mg['MIXED'] is not None:
            # Set the mix type based on the extracted value
            info['mix'] = self.mixes[mg['MIXED']]

        info['type'] = 'ring' if 'TOURNO' in mg and mg['TOURNO'] is None else 'tour'

        if info['limitType'] == 'fl' and info['bb'] is not None:
            if info['type'] == 'ring':
                try:
                    # Lookup and set the small blind and big blind values based on the big blind value
                    info['sb'] = self.Lim_Blinds[info['BB']][0]
                    info['bb'] = self.Lim_Blinds[info['BB']][1]
                except KeyError as e:
                    tmp = handText[:200]
                    log.error(_(f"BetOnlineToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'"))
                    raise FpdbParseError from e
            else:
                # Calculate the small blind and big blind values for tournament games
                info['sb'] = str((old_div(Decimal(info['SB']), 2)).quantize(Decimal("0.01")))
                info['bb'] = str(Decimal(info['SB']).quantize(Decimal("0.01")))

        return info


    def readHandInfo(self, hand):
        """
        Read the hand information from a BetOnline hand history and update the Hand object.

        Args:
            hand (Hand): The Hand object to update with the extracted information.

        Raises:
            FpdbParseError: If the required information is not found in the hand history.

        Returns:
            None
        """

        info = {}

        # Search for hand information patterns
        if self.skin in ('ActionPoker', 'GearPoker'):
            m = self.re_HandInfo2.search(hand.handText, re.DOTALL)
        else:
            m = self.re_HandInfo1.search(hand.handText, re.DOTALL)

        m2 = self.re_GameInfo.search(hand.handText)

        if m is None or m2 is None:
            tmp = hand.handText[:200]
            log.error(_(f"BetOnlineToFpdb.readHandInfo: '{tmp}'"))
            raise FpdbParseError

        # Extract the information using groupdict()
        info |= m.groupdict()
        info.update(m2.groupdict())

        for key, value in info.items():
            if key == 'DATETIME':
                # Process datetime information
                datetimestr, time_zone = "2000/01/01 00:00:00", 'ET'  # Default values

                if self.skin in ('ActionPoker', 'GearPoker'):
                    m2 = self.re_DateTime2.finditer(info[key])
                    for a in m2:
                        # Extract date and time components from the matched groups
                        datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
                        time_zone = 'ET'
                else:
                    m1 = self.re_DateTime1.finditer(info[key])
                    for a in m1:
                        seconds = '00'
                        if a.group('S'):
                            seconds = a.group('S')
                        datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{seconds}"
                        tz = a.group('TZ')  # Assume ET as the default timezone
                        if tz == 'GMT Standard Time':
                            time_zone = 'GMT'
                        elif tz in ('Pacific Daylight Time', 'Pacific Standard Time'):
                            time_zone = 'PT'
                        else:
                            time_zone = 'ET'

                hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")  # Parse the datetime string
                hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, time_zone, "UTC")  # Convert to UTC
            elif key == 'HID':
                hand.handid = info[key]
            elif key == 'MONEY':
                if value == '(Play Money) ':
                    hand.gametype['currency'] = 'play'
            elif key == 'TOURNO':
                hand.tourNo = info[key]
            elif key == 'BUYIN' and hand.tourNo is not None:
                # Process buy-in information
                if not info[key] or info[key] == 'Freeroll':
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                else:
                    if info[key].find("$") != -1:
                        hand.buyinCurrency = "USD"
                    elif info[key].find(u"€") != -1:
                        hand.buyinCurrency = "EUR"
                    elif re.match("^[0-9+]*$", info[key]):
                        hand.buyinCurrency = "play"
                    else:
                        # FIXME: handle other currencies, play money
                        raise FpdbParseError(_(
                            "BetOnlineToFpdb.readHandInfo: Failed to detect currency. Hand ID: '{hand.handid}': '{info[key]}'"
                        ))

                    info['BIAMT'] = info['BIAMT'].strip(u'$€')
                    if info['BOUNTY'] is not None:
                        # There is a bounty, switch BOUNTY and BIRAKE values
                        tmp = info['BOUNTY']
                        info['BOUNTY'] = info['BIRAKE']
                        info['BIRAKE'] = tmp
                        info['BOUNTY'] = info['BOUNTY'].strip(u'$€')
                        hand.koBounty = int(100 * Decimal(info['BOUNTY']))
                        hand.isKO = True
                    else:
                        hand.isKO = False

                    info['BIRAKE'] = info['BIRAKE'].strip(u'$€')

                    hand.buyin = int(100 * Decimal(info['BIAMT']))
                    hand.fee = int(100 * Decimal(info['BIRAKE']))
            elif key == 'BUTTON':
                hand.buttonpos = info[key]
            elif key == 'LEVEL':
                hand.level = info[key]
            elif key == 'TABLE':
                hand.tablename = re.split("-", info[key])[1] if hand.tourNo is not None else info[key]
            elif key == 'MAX' and info[key] is not None:
                hand.maxseats = int(info[key])

        if not self.re_Board1.search(hand.handText) and self.skin not in ('ActionPoker', 'GearPoker'):
            raise FpdbHandPartial(_("readHandInfo: Partial hand history: '{hand.handid}'"))

    
    def readButton(self, hand):
        """
        Reads the button position from the given hand.

        Args:
            hand (Hand): The hand object containing the hand text.

        Returns:
            None
        """
        # Search for the button position in the hand text using regex
        if m := self.re_Button.search(hand.handText):
            hand.buttonpos = int(m.group('BUTTON'))
        else:
            # If the button position is not found, log an error message
            log.info(_('readButton: not found'))


    def readPlayerStacks(self, hand):
        """Extracts player stacks from the given hand and adds them to the Hand object.

        Args:
            hand (Hand): The hand to extract player stacks from.

        """
        # Find all player information using a regular expression
        m = self.re_PlayerInfo.finditer(hand.handText)

        # Iterate through each match and add the player to the hand
        for a in m:
            # Get the player name and handle unknown names
            pname = self.unknownPlayer(hand, a.group('PNAME'))

            # Add the player to the hand object
            hand.addPlayer(int(a.group('SEAT')), pname, self.clearMoneyString(a.group('CASH')))


    def markStreets(self, hand):
        """
        Mark the streets in the hand text based on the game type and update the Hand object.

        Args:
            hand (Hand): The Hand object to update with the marked streets.

        Returns:
            None
        """

        if hand.gametype['category'] in ('27_1draw', 'fivedraw'):
            # Insert DRAW marker for Stars single draw games
            discard_split = re.split(r"(?:(.+(?: stands pat|: discards).+))", hand.handText, re.DOTALL)
            if len(hand.handText) != len(discard_split[0]):
                discard_split[0] += "*** DRAW ***\r\n"
                hand.handText = "".join(discard_split)

        if hand.gametype['base'] in ("hold"):
            # Mark streets for Hold'em games
            m = re.search(
                r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* \[\S\S\S? \S\S\S? \S\S\S?](?P<TURN>\[\S\S\S?\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* \[\S\S\S? \S\S\S? \S\S\S? \S\S\S?](?P<RIVER>\[\S\S\S?\].+))?",
                hand.handText, re.DOTALL
            )
            m2 = self.re_Board1.search(hand.handText)
            if m and m2:
                if m2.group('FLOP') and not m.group('FLOP'):
                    m = re.search(
                        r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=Board )|.+)"
                        r"(Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
                        hand.handText, re.DOTALL
                    )
                elif m2.group('TURN') and not m.group('TURN'):
                    m = re.search(
                        r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                        r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=Board )|.+))?"
                        r"(Board \[(?P<BFLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
                        hand.handText, re.DOTALL
                    )
                elif m2.group('RIVER') and not m.group('RIVER'):
                    m = re.search(
                        r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                        r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                        r"(\*\*\* TURN \*\*\* \[\S\S\S? \S\S\S? \S\S\S?](?P<TURN>\[\S\S\S?\].+(?=Board )|.+))?"
                        r"(Board \[(?P<BFLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<BTURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
                        hand.handText, re.DOTALL
                    )
        elif hand.gametype['base'] in ("stud"):
            # Mark streets for Stud games
            m = re.search(
                r"(?P<ANTES>.+(?=\*\*\* 3rd STREET \*\*\*)|.+)"
                r"(\*\*\* 3rd STREET \*\*\*(?P<THIRD>.+(?=\*\*\* 4th STREET \*\*\*)|.+))?"
                r"(\*\*\* 4th STREET \*\*\*(?P<FOURTH>.+(?=\*\*\* 5th STREET \*\*\*)|.+))?"
                r"(\*\*\* 5th STREET \*\*\*(?P<FIFTH>.+(?=\*\*\* 6th STREET \*\*\*)|.+))?"
                r"(\*\*\* 6th STREET \*\*\*(?P<SIXTH>.+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\*(?P<SEVENTH>.+))?",
                hand.handText, re.DOTALL
            )
        elif hand.gametype['base'] in ("draw"):
            # Mark streets for Draw games
            if hand.gametype['category'] in ('27_1draw', 'fivedraw'):
                m = re.search(
                    r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
                    r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* DRAW \*\*\*)|.+))?"
                    r"(\*\*\* DRAW \*\*\*(?P<DRAWONE>.+))?",
                    hand.handText, re.DOTALL
                )
            else:
                m = re.search(
                    r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
                    r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* FIRST DRAW \*\*\*)|.+))?"
                    r"(\*\*\* FIRST DRAW \*\*\*(?P<DRAWONE>.+(?=\*\*\* SECOND DRAW \*\*\*)|.+))?"
                    r"(\*\*\* SECOND DRAW \*\*\*(?P<DRAWTWO>.+(?=\*\*\* THIRD DRAW \*\*\*)|.+))?"
                    r"(\*\*\* THIRD DRAW \*\*\*(?P<DRAWTHREE>.+))?",
                    hand.handText, re.DOTALL
                )

        hand.addStreets(m)

        #if m3 and m2:
        #    if m2.group('RIVER') and not m3.group('RIVER'):
        #        print hand.streets

    def readCommunityCards(self, hand, street):
        """
        Reads the community cards for a given street and updates the hand object.

        Args:
            hand (Hand): An instance of the Hand class.
            street (str): The street for which community cards need to be read.

        Returns:
            None
        """
        # Check if the street is a valid street for dealing community cards
        if street in ('FLOP','TURN','RIVER'):
            # Check if the skin is not ActionPoker or GearPoker
            if self.skin not in ('ActionPoker', 'GearPoker'):
                # Search for the community cards using regex
                m = self.re_Board1.search(hand.handText)
                if m and m.group(street):
                    # Split the cards and replace 10 with T
                    cards = m.group(street).split(' ')
                    cards = [c.replace("10", "T") for c in cards]
                    # Update the hand object with the community cards
                    hand.setCommunityCards(street, cards)
            else:
                # Search for the community cards using regex
                m = self.re_Board2.search(hand.streets[street])
                # Split the cards and replace 10 with T and lowercase the suit
                cards = m.group('CARDS').split(' ')
                cards = [c[:-1].replace('10', 'T') + c[-1].lower() for c in cards]
                # Update the hand object with the community cards
                hand.setCommunityCards(street, cards)


    def readAntes(self, hand):
        """
        Reads the antes from a hand and adds it to the corresponding player's stack.

        Args:
        - hand: A Hand object representing the hand being processed.

        Returns:
        - None
        """
        # Find all instances of antes using a regular expression
        m = self.re_Antes.finditer(hand.handText)
        # Iterate over each player's antes and add them to the corresponding player's stack
        for player in m:
            # Ignore players with no antes
            if player.group('ANTE')!='0.00':
                # Use the unknownPlayer function to handle unknown players
                pname = self.unknownPlayer(hand, player.group('PNAME'))
                # Add the ante to the player's stack
                hand.addAnte(pname, self.clearMoneyString(player.group('ANTE')))

    
    def readBringIn(self, hand):
        """
        Reads the bring-in from the hand and adds it to the player's hand.

        Args:
            hand (Hand): The hand to read the bring-in from.
        """
        if m := self.re_BringIn.search(hand.handText, re.DOTALL):
            # Uncomment the following line to enable debug logging
            # logging.debug("readBringIn: %s for %s" %(m.group('PNAME'),  m.group('BRINGIN')))
            hand.addBringIn(m.group('PNAME'),  self.clearMoneyString(m.group('BRINGIN')))

        
    def readBlinds(self, hand):
        """
        Reads blinds information from a hand history string and updates the Hand object with the blind information.

        Args:
            hand (Hand): The Hand object to be updated.

        Returns:
            None.
        """
        liveBlind = True  # Flag to indicate if the small blind is still in play.
        # Find all small blind posts in the hand history.
        for a in self.re_PostSB.finditer(hand.handText):
            pname = self.unknownPlayer(hand, a.group('PNAME'))  # Get the player name.
            sb = self.clearMoneyString(a.group('SB'))  # Get the amount of the small blind.
            if liveBlind:
                hand.addBlind(pname, 'small blind', sb)  # Add the small blind to the Hand object.
                liveBlind = False  # Set the flag to False since the small blind is no longer in play.
            else:
                # Post dead blinds as ante
                hand.addBlind(pname, 'secondsb', sb)  # Add the second small blind to the Hand object.
            # If the sb value is not set in the gametype and the skin is ActionPoker or GearPoker, set the sb value to sb.
            if not hand.gametype['sb'] and self.skin in ('ActionPoker', 'GearPoker'):
                hand.gametype['sb'] = sb
        # Find all big blind posts in the hand history.
        for a in self.re_PostBB.finditer(hand.handText):
            pname = self.unknownPlayer(hand, a.group('PNAME'))  # Get the player name.
            if a.group('BB') is not None:
                bb = self.clearMoneyString(a.group('BB'))  # Get the amount of the big blind.
            elif hand.gametype['bb']:
                bb = hand.gametype['bb']  # If the bb value is set in the gametype, use that value.
            else:
                raise FpdbHandPartial(_("BetOnlineToFpdb.readBlinds: " + ("Partial hand history: 'No blind info'")))
            hand.addBlind(pname, 'big blind', bb)  # Add the big blind to the Hand object.
            # If the bb value is not set in the gametype and the skin is ActionPoker or GearPoker, set the bb value to bb
            if not hand.gametype['bb'] and self.skin in ('ActionPoker', 'GearPoker'):
                hand.gametype['bb'] = bb
        # Find all posts that are both small and big blinds in the hand history.
        for a in self.re_PostBoth.finditer(hand.handText):
            if a.group('SBBB')!='0.00':
                pname = self.unknownPlayer(hand, a.group('PNAME'))  # Get the player name.
                sbbb = self.clearMoneyString(a.group('SBBB'))  # Get the amount of the small and big blinds.
                amount = str(Decimal(sbbb) + old_div(Decimal(sbbb),2))  # Calculate the total amount of the blinds.
                hand.addBlind(pname, 'both', amount)  # Add the total amount of the blinds to the Hand object.
            else:
                pname = self.unknownPlayer(hand, a.group('PNAME'))  # Get the player name.
                hand.addBlind(pname, 'secondsb', hand.gametype['sb'])  # Add the second small blind to the Hand object.
        self.fixBlinds(hand)  # Fix any errors in the Blind objects of the Hand object.
                


    def fixBlinds(self, hand):
        """
        This function fixes blinds if they are missing in an ActionPoker hand or if the sb/bb is ALL_IN.

        Args:
        - self (BetOnline): An instance of the BetOnline class.
        - hand (HandHistory): An instance of the HandHistory class.

        Returns:
        - None
        """
        # FIXME
        # The following should only trigger when a small blind is missing in ActionPoker hands, or the sb/bb is ALL_IN
        # Check if the skin is ActionPoker or GearPoker
        if self.skin not in ('ActionPoker', 'GearPoker'):
            return

        # Check if sb is missing but bb is not missing
        if hand.gametype['sb'] is None and hand.gametype['bb'] != None:
            BB = str(Decimal(hand.gametype['bb']) * 2)
            # Check if BB is in Lim_Blinds dictionary
            if self.Lim_Blinds.get(BB) != None:
                hand.gametype['sb'] = self.Lim_Blinds.get(BB)[0]
        # Check if bb is missing but sb is not missing
        elif hand.gametype['bb'] is None and hand.gametype['sb'] != None:
            for k, v in list(self.Lim_Blinds.items()):
                if hand.gametype['sb'] == v[0]:
                    hand.gametype['bb'] = v[1]
        # If sb or bb is still missing after all checks, raise an exception
        if hand.gametype['sb'] is None or hand.gametype['bb'] is None:
            log.error(f"BetOnline.fixBlinds: Failed to fix blinds Hand ID: {hand.handid}")
            raise FpdbParseError
        hand.sb = hand.gametype['sb']
        hand.bb = hand.gametype['bb']

            
    def unknownPlayer(self, hand, pname):
        """Return the name of an unknown player and add them to the hand if not already present.

        Args:
            hand (Hand): The hand object to add the player to.
            pname (str): The name of the unknown player.

        Returns:
            str: The name of the unknown player.
        """
        # If pname is 'Unknown player' or an empty string
        if pname == 'Unknown player' or not pname:
            # If pname is empty, set it to 'Dead'
            if not pname:
                pname = 'Dead'
            # If pname is not in the list of player names in the hand, add a new player to the hand
            if pname not in (p[1] for p in hand.players):
                hand.addPlayer(-1, pname, '0')
        # Return the name of the unknown player
        return pname

    def readHoleCards(self, hand):
        """
        Reads the hole cards from a given hand object
        and updates the hand object with the hole cards.

        :param hand: Hand object to be updated
        """

        # Iterate over special streets to grab hero's cards
        for street in ('PREFLOP', 'DEAL'):
            if street in list(hand.streets.keys()):
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group('PNAME')
                    newcards = found.group('NEWCARDS').split(' ')
                    newcards = [c[:-1].replace('10', 'T') + c[-1].lower() for c in newcards]
                    hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)

        # Iterate over all streets to grab player's cards
        for street, text in list(hand.streets.items()):
            if not text or street in ('PREFLOP', 'DEAL'):
                continue  # already done these
            m = self.re_HeroCards.finditer(hand.streets[street])
            for found in m:
                player = found.group('PNAME')
                if found.group('NEWCARDS') is None:
                    newcards = []
                else:
                    newcards = found.group('NEWCARDS').split(' ')
                    newcards = [c[:-1].replace('10', 'T') + c[-1].lower() for c in newcards]
                if found.group('OLDCARDS') is None:
                    oldcards = []
                else:
                    oldcards = found.group('OLDCARDS').split(' ')
                    oldcards = [c[:-1].replace('10', 'T') + c[-1].lower() for c in oldcards]
                if street == 'THIRD' and len(newcards) == 3: # hero in stud game
                    hand.hero = player
                    hand.dealt.add(player) # need this for stud?
                    hand.addHoleCards(
                        street,
                        player,
                        closed=newcards[:2],
                        open=[newcards[2]],
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )
                else:
                    hand.addHoleCards(street, player, open=newcards, closed=oldcards, shown=False, mucked=False, dealt=False)


    def readAction(self, hand, street):
        """
        Reads the actions of a hand and updates the hand object accordingly.

        Args:
            hand (Hand): The hand object containing the information about the hand.
            street (str): The name of the street.

        Returns:
            None
        """
        # If the street is preflop, look for actions in the hole cards section of the hand text
        if street == "PREFLOP":
            m0 = self.re_Action.finditer(self.re_Hole.split(hand.handText)[0])
            for action in m0:
                # Get the player name and handle unknown players
                pname = self.unknownPlayer(hand, action.group("PNAME"))
                # If the player has left the table, add a fold for them
                if (
                    action.group("ATYPE") == " has left the table"
                    and pname in (p[1] for p in hand.players)
                ):
                    hand.addFold(street, pname)

        # Look for actions in the current street
        m = self.re_Action.finditer(hand.streets[street])
        for action in m:
            acts = action.groupdict()
            # Get the player name and handle unknown players
            pname = self.unknownPlayer(hand, action.group("PNAME"))
            # Determine the type of action and update the hand object accordingly
            if action.group("ATYPE") in (" folds", " Folds", " has left the table"):
                if pname in (p[1] for p in hand.players):
                    hand.addFold(street, pname)
            elif action.group("ATYPE") in (" checks", " Checks"):
                hand.addCheck(street, pname)
            elif action.group("ATYPE") in (" calls", " Calls"):
                hand.addCall(
                    street, pname, self.clearMoneyString(action.group("BET"))
                )
            elif action.group("ATYPE") in (" raises", " Raises", " Reraises"):
                hand.addCallandRaise(
                    street, pname, self.clearMoneyString(action.group("BET"))
                )
            elif action.group("ATYPE") in (" bets", " Bets"):
                hand.addBet(street, pname, self.clearMoneyString(action.group("BET")))
            elif action.group("ATYPE") == " discards":
                hand.addDiscard(
                    street, pname, action.group("BET"), action.group("CARDS")
                )
            elif action.group("ATYPE") == " stands pat":
                hand.addStandsPat(street, pname, action.group("CARDS"))
            else:
                log.debug(_(f"DEBUG: Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'"
                ))

    def readShowdownActions(self, hand):
        """Reads and processes the showdown actions in the hand's text.

        Args:
            hand (Hand): The hand object containing the text to parse.

        Returns:
            None
        """
        # TODO: pick up mucks also??
        for shows in self.re_ShowdownAction.finditer(hand.handText):            
            cards = shows.group('CARDS').split(' ')
            # Convert card values to standard format (e.g. '10' -> 'T')
            cards = [c[:-1].replace('10', 'T') + c[-1].lower() for c in cards]
            hand.addShownCards(cards, shows.group('PNAME'))


    def readCollectPot(self, hand):
        """
        Sets a flag in the hand object to indicate that it has adjusted the collected pot data,
        then searches for collected pot and total pot data in the hand text and adds it to the hand object.

        Args:
            hand: An object representing a poker hand.

        """
        hand.adjustCollected = True

        # Find and add collected pot data to hand object
        for m in self.re_CollectPot.finditer(hand.handText):
            hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT'))

        # Find and add total pot data to hand object
        for m in self.re_TotalPot.finditer(hand.handText):
            if hand.rakes.get('pot'):
                hand.rakes['pot'] += Decimal(self.clearMoneyString(m.group('POT')))
            else:
                hand.rakes['pot'] = Decimal(self.clearMoneyString(m.group('POT')))


    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """
        Returns a string to search in windows titles.

        Args:
            type (str): The type of table title to return.
            table_name (str, optional): The name of the table. Defaults to None.
            tournament (str, optional): The name of the tournament. Defaults to None.
            table_number (int, optional): The number of the table. Defaults to None.

        Returns:
            str: A string to search in windows titles.
        """
        if type == 'tour':
            return r'\(' + re.escape(str(tournament)) + r'\-' + re.escape(str(table_number)) + r'\)'
        else:
            return re.escape(table_name)

