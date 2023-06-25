#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2008-2012, Chaz Littlejohn
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

# TODO: straighten out discards for draw games

import sys, copy
from HandHistoryConverter import *
import Card
from decimal_wrapper import Decimal

# Bovada HH Format

class Bovada(HandHistoryConverter):

    # Class Variables

    sitename = "Bovada"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId   = 21 # Needs to match id entry in Sites database
    summaryInFile = True
    copyGameHeader = True
    sym = {'USD': "\$", 'T$': "", "play": ""}         # ADD Euro, Sterling, etc HERE
    substitutions = {
                     'LEGAL_ISO' : "USD",      # legal ISO currency codes
                            'LS' : u"\$|", # legal currency symbols - Euro(cp1252, utf-8)
                           'PLYR': r'(?P<PNAME>.+?)',
                            'CUR': u"(\$|)",
                            'NUM' :u".,\d",
                    }
                    
    # translations from captured groups to fpdb info strings
    Lim_Blinds = {      '0.04': ('0.01', '0.02'),        
                        '0.08': ('0.02', '0.04'),         '0.10': ('0.02', '0.05'),
                        '0.20': ('0.05', '0.10'),         '0.25': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),         '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),         '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),         '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),         '4': ('1.00', '2.00'),
                        '6.00': ('1.50', '3.00'),         '6': ('1.50', '3.00'),
                        '8.00': ('2.00', '4.00'),         '8': ('2.00', '4.00'),
                       '10.00': ('2.50', '5.00'),        '10': ('2.50', '5.00'),
                       '16.00': ('4.00', '8.00'),        '16': ('4.00', '8.00'),
                       '20.00': ('5.00', '10.00'),       '20': ('5.00', '10.00'),
                       '30.00': ('7.50', '15.00'),       '30': ('7.50', '15.00'),
                       '40.00': ('10.00', '20.00'),      '40': ('10.00', '20.00'),
                       '60.00': ('15.00', '30.00'),      '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),      '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),     '100': ('25.00', '50.00'),
                  }

    limits = { 'No Limit':'nl', 'Pot Limit':'pl', 'Fixed Limit':'fl', 'Turbo': 'nl'}
    games = {                          # base, category
                               "HOLDEM" : ('hold','holdem'),
                                'OMAHA' : ('hold','omahahi'),
                           'OMAHA HiLo' : ('hold','omahahilo'),
                             'OMAHA_HL' : ('hold','omahahilo'),
                                '7CARD' : ('stud','studhi'),
                           '7CARD HiLo' : ('stud','studhilo'),
                             '7CARD_HL' : ('hold','studhilo'),
                      'HOLDEMZonePoker' : ('hold','holdem'),
                       'OMAHAZonePoker' : ('hold','omahahi'),
                  'OMAHA HiLoZonePoker' : ('hold','omahahilo'),
                      
               }
    currencies = {'$':'USD', '':'T$'}

    # Static regexes
    re_GameInfo     = re.compile(u"""
          (Ignition|Bovada|Bodog(\.com|\.eu|\sUK|\sCanada|88)?)\sHand\s\#C?(?P<HID>[0-9]+):?\s+
          ((?P<ZONE>Zone\sPoker\sID|TBL)\#(?P<TABLE>.+?)\s)?
          (?P<GAME>HOLDEM|OMAHA|OMAHA_HL|7CARD|7CARD\sHiLo|OMAHA\sHiLo|7CARD_HL|HOLDEMZonePoker|OMAHAZonePoker|OMAHA\sHiLoZonePoker)\s+
          (Tournament\s\#(M\-)?                # open paren of tournament info Tournament #2194767 TBL#1, 
          (?P<TOURNO>\d+)\sTBL\#(?P<TABLENO>\d+),
          \s)?
          (?P<HU>1\son\s1\s)? 
          (?P<LIMIT>No\sLimit|Fixed\sLimit|Pot\sLimit|Turbo)?
          (\s?Normal\s?)?
          (-\sLevel\s\d+?\s
          \(?                            # open paren of the stakes
          (?P<CURRENCY>%(LS)s|)?
          (?P<SB>[,.0-9]+)/(%(LS)s)?
          (?P<BB>[,.0-9]+)
          \s?(?P<ISO>%(LEGAL_ISO)s)?
          \))?
          (\s\[(?P<VERSION>MVS)\])?
          \s-\s
          (?P<DATETIME>.*$)
        """ % substitutions, re.MULTILINE|re.VERBOSE)

    re_PlayerInfo   = re.compile(u"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          %(PLYR)s\s(?P<HERO>\[ME\]\s)?
          \((%(LS)s)?(?P<CASH>[%(NUM)s]+)\sin\schips\)""" % substitutions, 
          re.MULTILINE|re.VERBOSE)
    
    re_PlayerInfoStud   = re.compile(u"""
         ^(?P<PNAME>Seat\+(?P<SEAT>[0-9]+))
         (?P<HERO>\s\[ME\])?:\s
         (%(LS)s)?(?P<CASH>[%(NUM)s]+)\sin\schips""" % substitutions, 
         re.MULTILINE|re.VERBOSE)
    
    re_PlayerSeat = re.compile(u"^Seat\+(?P<SEAT>[0-9]+)", re.MULTILINE|re.VERBOSE)
    re_Identify     = re.compile(u'(Ignition|Bovada|Bodog(\.com|\.eu|\sUK|\sCanada|88)?)\sHand')
    re_SplitHands   = re.compile('\n\n+')
    re_TailSplitHands   = re.compile('(\n\n\n+)')
    re_Button       = re.compile('Dealer : Set dealer\/Bring in spot \[(?P<BUTTON>\d+)\]', re.MULTILINE)
    re_Board1       = re.compile(r"Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s+?(?P<TURN>\S\S\S?)?\s+?(?P<RIVER>\S\S\S?)?\]")
    re_Board2       = {
        "FLOP": re.compile(r"\*\*\* FLOP \*\*\* \[(?P<CARDS>\S\S \S\S \S\S)\]"),
        "TURN": re.compile(r"\*\*\* TURN \*\*\* \[\S\S \S\S \S\S\] \[(?P<CARDS>\S\S)\]"),
        "RIVER": re.compile(r"\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S\] \[(?P<CARDS>\S\S)\]")
    } 
    re_DateTime     = re.compile("""(?P<Y>[0-9]{4})\-(?P<M>[0-9]{2})\-(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""", re.MULTILINE)
    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB           = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: (Ante\/Small (B|b)lind|Posts chip|Small (B|b)lind) (?P<CURRENCY>%(CUR)s)(?P<SB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_PostBB           = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: (Big (B|b)lind\/Bring in|Big (B|b)lind) (?P<CURRENCY>%(CUR)s)(?P<BB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_Antes            = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: Ante chip %(CUR)s(?P<ANTE>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_BringIn          = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: (Bring_in chip|Big (B|b)lind\/Bring in|Bring in)\s?(\(timeout\) )?%(CUR)s(?P<BRINGIN>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_PostBoth         = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: Posts dead chip %(CUR)s(?P<SBBB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_HeroCards        = re.compile(r"^%(PLYR)s  ?\[ME\] : Card dealt to a spot \[(?P<NEWCARDS>.+?)\]" % substitutions, re.MULTILINE)
    re_Action           = re.compile(r"""(?P<ACTION>
                        ^%(PLYR)s\s(\s?\[ME\]\s)?:(\sD)?(?P<ATYPE>\s(B|b)ets|\sDouble\sbets|\sChecks|\s(R|r)aises|\sCalls?|\sFold|\sBring_in\schip|\sBig\sblind\/Bring\sin|\sAll\-in(\((raise|raise\-timeout)\))?|\sCard\sdealt\sto\sa\sspot)
                        (\schip\sinfo)?(\(timeout\))?(\s%(CUR)s(?P<BET>[%(NUM)s]+)(\sto\s%(CUR)s(?P<BETTO>[%(NUM)s]+))?|\s\[(?P<NEWCARDS>.+?)\])?)"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    re_ShowdownAction   = re.compile(r"^%(PLYR)s (?P<HERO>\s?\[ME\]\s)?: Card dealt to a spot \[(?P<CARDS>.*)\]" % substitutions, re.MULTILINE)
    #re_ShownCards       = re.compile("^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and won \([.\d]+\) with (?P<STRING>.*))?" % substitutions, re.MULTILINE)
    re_CollectPot1      = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: Hand (R|r)esult(\-Side (P|p)ot)? %(CUR)s(?P<POT1>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_Bounty           = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: BOUNTY PRIZE \[%(CUR)s(?P<BOUNTY>[%(NUM)s]+)\]" %  substitutions, re.MULTILINE)
    re_Dealt            = re.compile(r"^%(PLYR)s (\s?\[ME\]\s)?: Card dealt to a spot" % substitutions, re.MULTILINE)
    re_Buyin            = re.compile(r"(\s-\s\d+\s-\s(?P<TOURNAME>.+?))?\s-\s(?P<BUYIN>(?P<TICKET>TT)?(?P<BIAMT>[%(LS)s\d\.,]+)-(?P<BIRAKE>[%(LS)s\d\.,]+)?)\s-\s" % substitutions)
    re_Knockout         = re.compile(r"\s\((?P<BOUNTY>[%(LS)s\d\.,]+)\sKnockout" % substitutions)
    re_Stakes           = re.compile(r"(RING|ZONE)\s-\s(?P<CURRENCY>%(LS)s|)?(?P<SB>[%(NUM)s]+)-(%(LS)s)?(?P<BB>[%(NUM)s]+)" % substitutions)
    re_Summary          = re.compile(r"\*\*\*\sSUMMARY\s\*\*\*")
    re_Hole_Third       = re.compile(r"\*\*\*\s(3RD\sSTREET|HOLE\sCARDS)\s\*\*\*")
    re_ReturnBet        = re.compile(r"Return\suncalled\sportion", re.MULTILINE)
    #Small Blind : Hand result $19
    

    def compilePlayerRegexs(self, hand):
        """
        Compiles regex patterns for players and pot collection.

        Args:
        - hand: the hand to be compiled.

        Returns:
        None
        """
        # Set up substitution values
        subst = self.substitutions

        # Get the set of players and check if it's already compiled
        players = set(self.playersMap.keys())
        if not players <= self.compiledPlayers: # x <= y means 'x is subset of y'

            # If not, set the compiled players to the current set
            self.compiledPlayers = players

            # Compile the player regex pattern
            subst['PLYR'] = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"

            # Compile the pot collection regex pattern
            self.re_CollectPot2  = re.compile(u"""
                Seat[\+ ](?P<SEAT>[0-9]+):\s?%(PLYR)s
                (\sHI)?\s(%(LS)s)?(?P<POT1>[%(NUM)s]+)?
                (?P<STRING>[a-zA-Z ]+)
                (?P<CARDS1>\[[-a-zA-Z0-9 ]+\])
                (\sLOW?\s(%(LS)s)?(?P<POT2>[%(NUM)s]+))?
                """ % subst, re.MULTILINE|re.VERBOSE)


    def readSupportedGames(self):
        """
        Returns a list of supported games.

        Each game is represented as a list containing its attributes.
        The attributes are, in order: game type, game mode, and game variant.
        """
        return [
            # Ring games
            ["ring", "hold", "nl"],  # No Limit Hold'em
            ["ring", "hold", "pl"],  # Pot Limit Hold'em
            ["ring", "hold", "fl"],  # Fixed Limit Hold'em
            ["ring", "stud", "fl"],  # Fixed Limit Stud

            # Tournament games
            ["tour", "hold", "nl"],  # No Limit Hold'em
            ["tour", "hold", "pl"],  # Pot Limit Hold'em
            ["tour", "hold", "fl"],  # Fixed Limit Hold'em
            ["tour", "stud", "fl"],  # Fixed Limit Stud
        ]

    def parseHeader(self, handText, whole_file):
        """
        Parses the header of a poker hand history and returns the game type.

        Args:
            handText (str): The text of the header.
            whole_file (str): The entire hand history file.

        Returns:
            dict: A dictionary containing the game type information.
        """
        gametype = self.determineGameType(handText)

        # If the game type is a tournament, split the file into hands and find the player seat numbers
        if gametype['type'] == 'tour':
            handlist = re.split(self.re_SplitHands,  whole_file)
            result = re.findall(self.re_PlayerSeat, handlist[0])
            #gametype['maxSeats'] = len(result)

        return gametype


    def determineGameType(self, handText):
        """
        Analyzes handText to determine the game type and relevant information.

        Args:
            handText (str): The raw text of the hand history.

        Returns:
            dict: A dictionary containing information about the game type, stakes, and currency.
        """
        info = {}

        # Search for game information
        m = self.re_GameInfo.search(handText)
        if not m:
            # If game information is not found, raise an error
            tmp = handText[:200]
            log.error(f"BovadaToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        # Search for dealt cards, summary of the hand, and hole cards for the third street
        m1 = self.re_Dealt.search(handText)
        m2 = self.re_Summary.split(handText)
        m3 = self.re_Hole_Third.split(handText)

        # If any of the above searches fail, raise a partial hand history error
        if not m1 or len(m2) != 2 or len(m3) > 3:
            raise FpdbHandPartial("BovadaToFpdb.determineGameType: " + ("Partial hand history"))

        # Extract game information from the regular expression match
        mg = m.groupdict()

        # Search for stakes information in the file path
        if m := self.re_Stakes.search(self.in_path):
            mg.update(m.groupdict())

        # Determine limit type (no limit, fixed limit, or pot limit)
        if 'LIMIT' in mg:
            info['limitType'] = self.limits[mg['LIMIT']] if mg['LIMIT'] else 'nl'

        # Determine the game type and category (hold'em, omaha, etc.)
        if 'GAME' in mg:
            (info['base'], info['category']) = self.games[mg['GAME']]

        # Determine the small blind amount (if applicable)
        if 'SB' in mg:
            info['sb'] = self.clearMoneyString(mg['SB'])

        # Determine the big blind amount (if applicable)
        if 'BB' in mg:
            info['bb'] = self.clearMoneyString(mg['BB'])

        # Determine the game type (ring or tournament) and currency
        if 'TOURNO' in mg and mg['TOURNO'] is not None:
            info['type'] = 'tour'
            info['currency'] = 'T$'
        else:
            info['type'] = 'ring'
            info['currency'] = 'USD'

        # Determine the currency (if applicable)
        if 'CURRENCY' in mg and mg['CURRENCY'] is not None:
            info['currency'] = self.currencies[mg['CURRENCY']]

        # Determine if the game is a fast-fold variant (e.g. Zone Poker)
        if 'Zone' in mg['GAME']:
            info['fast'] = True
        else:
            info['fast'] = False

        # If the game is fixed limit and a big blind amount is specified, adjust the small and big blind amounts
        if info['limitType'] == 'fl' and info['bb'] is not None:
            if info['type'] == 'ring':
                # Adjust small and big blind amounts based on the specified big blind amount
                try:
                    info['sb'] = self.Lim_Blinds[info['bb']][0]
                    info['bb'] = self.Lim_Blinds[info['bb']][1]
                except KeyError as e:
                    tmp = handText[:200]
                    log.error(
                        f"BovadaToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'"
                    )
                    raise FpdbParseError from e
            else:
                info['sb'] = str((Decimal(info['sb'])/2).quantize(Decimal("0.01")))
                info['bb'] = str(Decimal(info['sb']).quantize(Decimal("0.01")))   

        return info

    def readHandInfo(self, hand):
        """
        Read hand information from a given hand object.

        Args:
            hand: Hand object to read information from.

        Returns:
            Dictionary containing parsed information from the hand object.

        Raises:
            FpdbParseError: If hand information could not be parsed.
        """
        # Create empty dictionary to store parsed information
        info = {}

        # Parse game information
        m = self.re_GameInfo.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"BovadaToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError
        info |= m.groupdict()

        # Parse buy-in information
        if m := self.re_Buyin.search(self.in_path):
            info.update(m.groupdict())

        # Set allInBlind flag to False
        hand.allInBlind = False

        # Parse knockout information
        if m2 := self.re_Knockout.search(self.in_path):
            info.update(m2.groupdict())

        # Set speed based on path
        if "Hyper Turbo" in self.in_path:
            hand.speed = "Hyper"
        elif  "Turbo" in self.in_path:
            hand.speed = "Turbo"

        # Parse remaining information from info dictionary
        for key, value in info.items():
            if key == 'BUYIN':
                # Parse buy-in amount and currency
                if info['TOURNO']!=None:
                    # Handle freerolls
                    if value == 'Freeroll':
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "FREE"
                    else:
                        # Handle other buy-in amounts and currencies
                        if info[key].find("$")!=-1:
                            hand.buyinCurrency="USD"
                        elif re.match("^[0-9+]*$", info[key]):
                            hand.buyinCurrency="play"
                        else:
                            #FIXME: handle other currencies, play money
                            log.error(
                                f"BovadaToFpdb.readHandInfo: Failed to detect currency. Hand ID: {hand.handid}: '{info[key]}'"
                            )
                            raise FpdbParseError

                        # Parse knockout bounty information
                        if info.get('BOUNTY') != None:
                            info['BOUNTY'] = self.clearMoneyString(info['BOUNTY'].strip(u'$'))
                            hand.koBounty = int(100*Decimal(info['BOUNTY']))
                            hand.isKO = True
                        else:
                            hand.isKO = False

                        # Parse buy-in amount and rake
                        info['BIAMT'] = self.clearMoneyString(info['BIAMT'].strip(u'$'))

                        info['BIRAKE'] = (
                            self.clearMoneyString(info['BIRAKE'].strip(u'$'))
                            if info['BIRAKE']
                            else '0'
                        )

                        # Parse buy-in and fee or ticket
                        if info['TICKET'] is None:
                            hand.buyin = int(100*Decimal(info['BIAMT']))
                            hand.fee = int(100*Decimal(info['BIRAKE']))
                        else:
                            hand.buyin = 0
                            hand.fee = 0
            elif key == 'DATETIME':
                # Parse date and time information
                m1 = self.re_DateTime.finditer(info[key])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
                                #tz = a.group('TZ')  # just assume ET??
                                #print "   tz = ", tz, " datetime =", datetimestr
                hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S") # also timezone at end, e.g. " ET"
                hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")
            elif key == 'HID':
                hand.handid = info[key]
            elif key == 'TABLE':
                if info.get('TABLENO'):
                    hand.tablename = info.get('TABLENO')
                elif info['ZONE'] and 'Zone' in info['ZONE']:
                    hand.tablename = info['ZONE'] + ' ' +info[key]
                else:
                    hand.tablename = info[key]
            elif key == 'TOURNO':
                hand.tourNo = info[key]
            if key == 'MAX' and info[key] != None:
                hand.maxseats = int(info[key])
            if key == 'HU' and info[key] != None:
                hand.maxseats = 2
            if key == 'VERSION':
                hand.version = info[key]

        if not hand.maxseats:
            hand.maxseats = 9

        if not hand.version:
            hand.version = 'LEGACY'
    
    def readButton(self, hand):
        """
        Parses the hand text to extract the button position and updates the hand object with it.

        Args:
            self: The current object instance.
            hand: The Hand object to update.
        """
        # Search for the button position using the regex pattern.
        if m := self.re_Button.search(hand.handText):
            # If a match is found, update the button position in the hand object.
            hand.buttonpos = int(m.group('BUTTON'))


    def readPlayerStacks(self, hand):
        """
        Reads player stacks from the hand history text and populates the playersMap and hand object.

        Args:
            hand: Hand object containing hand history text.

        Returns:
            None
        """
        # Initialize playersMap and seatNo
        self.playersMap, seatNo = {}, 1

        # Find player info using appropriate regex
        if hand.gametype['base'] in ("stud"):
            m = self.re_PlayerInfoStud.finditer(hand.handText)
        else:
            m = self.re_PlayerInfo.finditer(hand.handText)

        # Iterate over regex matches and populate playersMap and hand object
        for a in m:
            # Check if card is dealt to a spot or version is MVS
            if re.search(r"%s (\s?\[ME\]\s)?: Card dealt to a spot" % re.escape(a.group('PNAME')), hand.handText) or hand.version == 'MVS':
                # Check if current player is the dealer
                if not hand.buttonpos and a.group('PNAME')=='Dealer':
                    hand.buttonpos = int(a.group('SEAT'))
                # Check if current player is the hero
                if a.group('HERO'):
                    self.playersMap[a.group('PNAME')] = 'Hero'
                else:
                    self.playersMap[a.group('PNAME')] = f"Seat {a.group('SEAT')}"
                # Add player to hand object
                hand.addPlayer(seatNo, self.playersMap[a.group('PNAME')], self.clearMoneyString(a.group('CASH')))
            seatNo += 1

        # Check if any players were added to the hand object
        if len(hand.players)==0:
            tmp = hand.handText[:200]
            log.error(f"BovadaToFpdb.readPlayerStacks: '{tmp}'")
            raise FpdbParseError
        # Set maxseats to 10 if 10 players were added to the hand object
        elif len(hand.players)==10:
            hand.maxseats = 10

        
    def playerSeatFromPosition(self, source, handid, position):
        """
        Given a position, returns the player object sitting in that position.

        Args:
            source (str): The source of the hand.
            handid (str): The ID of the hand.
            position (int): The position of the player.

        Returns:
            Player: The player object sitting in the given position.

        Raises:
            FpdbParseError: If no player is found in the given position.
        """
        # Get the player object from the players map.
        player = self.playersMap.get(position)
        # If no player is found, log an error and raise an exception.
        if player is None:
            log.error(
                f"Hand.{source}: '{handid}' unknown player seat from position: '{position}'"
            )
            raise FpdbParseError
        # Return the player object.
        return player
          

    def markStreets(self, hand):
        """
        Mark the streets of the hand with the corresponding actions.

        Args:
            hand (Hand): The hand to mark the streets for.

        Returns:
            None
        """
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        if hand.gametype['base'] == "hold":
            street, firststreet = 'PREFLOP', 'PREFLOP'
        else:
            street, firststreet = 'THIRD', 'THIRD'

        # Count the number of players who were dealt in and the number of players who went all-in blind
        m = self.re_Action.finditer(self.re_Hole_Third.split(hand.handText)[0])
        allinblind = sum(action.group('ATYPE') == ' All-in' for action in m)
        m = self.re_Action.finditer(self.re_Hole_Third.split(hand.handText)[-1])
        dealtIn = len(hand.players) - allinblind

        # Initialize variables
        streetactions, streetno, players, i, contenders, bets, acts = 0, 1, dealtIn, 0, dealtIn, 0, None

        # Iterate through each action in the hand and process it accordingly
        for action in m:
            if action.groupdict()!=acts or streetactions == 0:
                acts = action.groupdict()

                # Determine the player who performed the action
                player = self.playerSeatFromPosition('BovadaToFpdb.markStreets', hand.handid, action.group('PNAME'))

                # Update the number of contenders based on the current action
                if action.group('ATYPE') == ' Fold':
                    contenders -= 1
                elif action.group('ATYPE') in (' Raises', ' raises'):
                    if streetno==1: bets = 1
                    streetactions, players = 0, contenders
                elif action.group('ATYPE') in (' Bets', ' bets', ' Double bets'):
                    streetactions, players, bets = 0, contenders, 1
                elif action.group('ATYPE') in (' All-in(raise)', 'All-in(raise-timeout)'):
                    streetactions, players = 0, contenders
                    contenders -= 1
                elif action.group('ATYPE') == ' All-in':
                    if bets == 0 and streetno>1:
                        streetactions, players, bets = 0, contenders, 1
                    contenders -= 1

                # Update the number of actions for the current street and add the action to the hand's streets
                if action.group('ATYPE') != ' Card dealt to a spot' and (action.group('ATYPE')!=' Big blind/Bring in' or hand.gametype['base'] == 'stud'):
                    streetactions += 1
                hand.streets[street] += action.group('ACTION') + '\n'

                # Update the street number and street name if all players have acted
                if streetactions == players:
                    streetno += 1
                    if streetno < len(hand.actionStreets):
                        street = hand.actionStreets[streetno]
                    streetactions, players, bets = 0, contenders, 0

        # If the first street is missing, add the entire hand text to it
        if not hand.streets.get(firststreet):
            hand.streets[firststreet] = hand.handText

        # If the base game is hold'em and the board is not fully known, add the board cards to the corresponding streets
        if hand.gametype['base'] == "hold":
            if True: #hand.gametype['fast']:
                for street in ('FLOP', 'TURN', 'RIVER'):
                    m1 = self.re_Board2[street].search(hand.handText)
                    if m1 and m1.group('CARDS') and not hand.streets.get(street):
                        hand.streets[street] = m1.group('CARDS')
            else:
                m1 = self.re_Board1.search(hand.handText)
                for street in ('FLOP', 'TURN', 'RIVER'):
                    if m1 and m1.group(street) and not hand.streets.get(street):
                        hand.streets[street] = m1.group(street)
            

    def readCommunityCards(self, hand, street):
        """
        Read community cards from the hand text for the given street and update the hand object with the cards.

        Args:
        hand: A Hand object representing the current hand being played.
        street: A string representing the current street being dealt (e.g. 'FLOP', 'TURN', 'RIVER').

        Returns:
        None
        """
        # If the game is fast, use a regex to match the community cards for the given street and update the hand object.
        if True: #hand.gametype['fast']:
            m = self.re_Board2[street].search(hand.handText)
            if m and m.group('CARDS'):
                hand.setCommunityCards(street, m.group('CARDS').split(' '))
        # If the game is not fast and the street is one that gets dealt community cards, use a regex to match the community
        # cards for the given street and update the hand object.
        elif street in ('FLOP','TURN','RIVER'):   # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_Board1.search(hand.handText)
            if m and m.group(street):
                cards = m.group(street).split(' ')
                hand.setCommunityCards(street, cards)


    def readAntes(self, hand):
        """
        Extracts the antes from a hand text and adds them to the corresponding players in the Hand object.

        Args:
            hand (Hand): The Hand object to add the antes to.

        Returns:
            None
        """

        # Initialize variables
        antes = None
        m = self.re_Antes.finditer(hand.handText)

        # Iterate over the matches and add the antes to the corresponding players
        for a in m:
            # Check if the antes have already been added for this player
            if a.groupdict() != antes:
                # Update the value of antes
                antes = a.groupdict()
                # Get the player seat from their position
                player = self.playerSeatFromPosition('BovadaToFpdb.readAntes', hand.handid, antes['PNAME'])
                # Add the ante to the player's stack
                hand.addAnte(player, self.clearMoneyString(antes['ANTE']))

    def readBringIn(self, hand):
        """
        This function reads the BringIn value from a poker hand and adds it to the corresponding player's hand.

        Args:
        - self: instance of the class
        - hand: instance of the Hand class

        Returns: None
        """
        if m := self.re_BringIn.search(hand.handText, re.DOTALL):
            # If there is a match with the BringIn pattern, add the value to the corresponding player's hand
            player = self.playerSeatFromPosition('BovadaToFpdb.readBringIn', hand.handid, m.group('PNAME'))
            hand.addBringIn(player,  self.clearMoneyString(m.group('BRINGIN')))            

        # If the small blind and big blind values are not defined, set them to default values
        if hand.gametype['sb'] is None and hand.gametype['bb'] is None:
            hand.gametype['sb'] = "1"
            hand.gametype['bb'] = "2"

        
    def readBlinds(self, hand):
        """Reads blinds from hand history text and updates the hand object with the blinds information.

        Args:
            hand (Hand): A Hand object representing the current hand.

        Returns:
            None
        """
        # Initialize variables to keep track of small blind, big blind, and other actions
        sb, bb, acts, postsb, postbb, both = None, None, None, None, None, None

        # Check if there are any uncalled bets in the hand, set the flag in the hand object if there are none
        if not self.re_ReturnBet.search(hand.handText):
            hand.setUncalledBets(True)

        # Find all instances of small blind posts and update the hand object with the small blind information
        for a in self.re_PostSB.finditer(hand.handText):
            if postsb != a.groupdict():
                postsb = a.groupdict()
                # Get the player's seat number from their position at the table
                player = self.playerSeatFromPosition('BovadaToFpdb.readBlinds.postSB', hand.handid, postsb['PNAME'])
                # Add the small blind bet to the hand object for the player
                hand.addBlind(player, 'small blind', self.clearMoneyString(postsb['SB']))
                # If the small blind is not set in the game type information, update it with the small blind amount
                if not hand.gametype['sb']:
                    hand.gametype['sb'] = self.clearMoneyString(postsb['SB'])
            # Update the small blind variable with the current amount
            sb = self.clearMoneyString(postsb['SB'])
            # Check if the player is all-in with their blind bet
            self.allInBlind(hand, 'PREFLOP', a, 'small blind')

        # Find all instances of big blind posts and update the hand object with the big blind information
        for a in self.re_PostBB.finditer(hand.handText):
            if postbb != a.groupdict():
                postbb = a.groupdict()
                # Get the player's seat number from their position at the table
                player = self.playerSeatFromPosition('BovadaToFpdb.readBlinds.postBB', hand.handid, 'Big Blind')
                # Add the big blind bet to the hand object for the player
                hand.addBlind(player, 'big blind', self.clearMoneyString(postbb['BB']))
                # Check if the player is all-in with their blind bet
                self.allInBlind(hand, 'PREFLOP', a, 'big blind')
                # If the big blind is not set in the game type information, update it with the big blind amount
                if not hand.gametype['bb']:
                    hand.gametype['bb'] = self.clearMoneyString(postbb['BB'])
                # Update the big blind variable with the current amount
                bb = self.clearMoneyString(postbb['BB'])
                # If the currency is not set in the game type information, update it based on the big blind amount
                if not hand.gametype['currency']:
                    if postbb['CURRENCY'].find("$") != -1:
                        hand.gametype['currency'] = "USD"
                    elif re.match("^[0-9+]*$", postbb['CURRENCY']):
                        hand.gametype['currency'] = "play"

        # Find all instances of actions before the flop and update the hand object with the relevant information
        for a in self.re_Action.finditer(self.re_Hole_Third.split(hand.handText)[0]):
            if acts != a.groupdict():
                acts = a.groupdict()
                # Check if the action is an all-in bet
                if acts['ATYPE'] == ' All-in':
                    # Create a regular expression to match the player's ante bet if applicable
                    re_Ante_Plyr = re.compile(r"^" + re.escape(acts['PNAME']) + " (\s?\[ME\]\s)?: Ante chip %(CUR)s(?P<ANTE>[%(NUM)s]+)" % self.substitutions, re.MULTILINE)
                    # Search for all instances of antes in the hand history text
                    m = self.re_Antes.search(hand.handText)
                    # Search for the player's ante bet if applicable
                    m1 = re_Ante_Plyr.search(hand.handText)
                    # If there are no instances of antes or the player's ante bet is found, update the hand object with the relevant information
                    if (not m or m1):
                        # Get the player's seat number from their position at the table
                        player = self.playerSeatFromPosition('BovadaToFpdb.readBlinds.postBB', hand.handid, acts['PNAME'])
                        # If the action is a big blind bet, add the big blind bet to the hand object for the player
                        if acts['PNAME'] == 'Big Blind':
                            hand.addBlind(player, 'big blind', self.clearMoneyString(acts['BET']))
                            # Check if the player is all-in with their big blind bet
                            self.allInBlind(hand, 'PREFLOP', a, 'big blind')
                        # If the action is a small blind bet or the dealer is the only other player, add the small blind bet to the hand object for the player
                        elif acts['PNAME'] == 'Small Blind' or (acts['PNAME'] == 'Dealer' and len(hand.players) == 2):
                            hand.addBlind(player, 'small blind', self.clearMoneyString(acts['BET']))
                            # Check if the player is all-in with their small blind bet
                            self.allInBlind(hand, 'PREFLOP', a, 'small blind')
                    # If there are instances of antes and the player's ante bet is not found, update the hand object with the player's ante bet
                    else:
                        # Get the player's seat number from their position at the table
                        player = self.playerSeatFromPosition('BovadaToFpdb.readAntes', hand.handid, acts['PNAME'])
                        # Add the ante bet to the hand object for the player
                        hand.addAnte(player, self.clearMoneyString(acts['BET']))
                        # Check if the player is all-in with their ante bet
                        self.allInBlind(hand, 'PREFLOP', a, 'antes')

        # Fix any issues with the blind information in the hand object
        self.fixBlinds(hand)

        # Find all instances of both players posting a blind and update the hand object with the relevant information
        for a in self.re_PostBoth.finditer(hand.handText):
            if both != a.groupdict():
                both = a.groupdict()
                # Get the player's seat number from their position at the table
                player = self.playerSeatFromPosition('BovadaToFpdb.readBlinds.postBoth', hand.handid, both['PNAME'])
                # Add the both blind bet to the hand object for the player
                hand.addBlind(player, 'both', self.clearMoneyString(both['SBBB']))
                # Check if the player is all-in with their both blind bet
                self.allInBlind(hand, 'PREFLOP', a, 'both')


    def fixBlinds(self, hand):
        """
        Fixes blinds for the given poker hand.

        Args:
            hand (Hand): The poker hand to fix blinds for.

        Raises:
            FpdbParseError: If failed to fix blinds.
        """
        # If small blind is missing and big blind is present.
        if hand.gametype['sb'] is None and hand.gametype['bb'] != None:
            BB = str(Decimal(hand.gametype['bb']) * 2)
            # If the doubled big blind value exists in the Lim_Blinds dictionary.
            if self.Lim_Blinds.get(BB) != None:
                # Set the small blind value to the first value of the Lim_Blinds dictionary.
                hand.gametype['sb'] = self.Lim_Blinds.get(BB)[0]

        # If big blind is missing and small blind is present.
        elif hand.gametype['bb'] is None and hand.gametype['sb'] != None:
            # Loop through the Lim_Blinds dictionary.
            for k, v in list(self.Lim_Blinds.items()):
                # If the small blind value matches the first value of the Lim_Blinds dictionary.
                if hand.gametype['sb'] == v[0]:
                    # Set the big blind value to the second value of the Lim_Blinds dictionary.
                    hand.gametype['bb'] = v[1]

        # If either small blind or big blind is missing.
        if hand.gametype['sb'] is None or hand.gametype['bb'] is None:
            # Log an error and raise an exception.
            log.error(
                f"BovadaToFpdb.fixBlinds: Failed to fix blinds Hand ID: {hand.handid}"
            )
            raise FpdbParseError

        # Set the small blind and big blind values of the hand.
        hand.sb = hand.gametype['sb']
        hand.bb = hand.gametype['bb']


    def readHoleCards(self, hand):
        """
        Reads the hole cards for each street in the hand and adds them to the Hand object.

        Args:
        - hand (Hand): A Hand object to which hole cards will be added.

        Returns:
        - None
        """
        # Streets PREFLOP, PREDRAW, and THIRD are special cases because we need to grab hero's cards.
        for street in ('PREFLOP', 'DEAL'):
            if street in hand.streets.keys():
                foundDict = None
                m = self.re_HeroCards.finditer(hand.handText)
                for found in m:
                    if found.groupdict()!=foundDict:
                        foundDict = found.groupdict()
                        hand.hero = 'Hero'
                        newcards = found.group('NEWCARDS').split(' ')
                        hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)

        for street, text in list(hand.streets.items()):
            if not text or street in ('PREFLOP', 'DEAL'):
                continue  # already done these
            m = self.re_ShowdownAction.finditer(hand.streets[street])
            foundDict = None
            for found in m:
                if foundDict!=found.groupdict():
                    foundDict = found.groupdict()
                    player = self.playerSeatFromPosition('BovadaToFpdb.readHoleCards', hand.handid, found.group('PNAME'))
                    if street != 'SEVENTH' or found.group('HERO'):
                        newcards = found.group('CARDS').split(' ')
                        oldcards = []
                    else:
                        oldcards = found.group('CARDS').split(' ')
                        newcards = []

                    if street == 'THIRD' and found.group('HERO'): # hero in stud game
                        hand.hero = 'Hero'
                        hand.dealt.add(player) # need this for stud??
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
        Reads the actions of the hand and populates the corresponding attributes of the hand object.

        Args:
        - hand: Hand object representing the current hand being played.
        - street: String representing the current betting round.

        Returns:
        - None
        """

        acts = None
        m = self.re_Action.finditer(hand.streets[street])

        for action in m:
            if acts != action.groupdict():
                acts = action.groupdict()
                player = self.playerSeatFromPosition('BovadaToFpdb.readAction', hand.handid, action.group('PNAME'))

                # If action is not a check, fold, card dealt to a spot, or big blind/bring in, update uncalled bets
                if action.group('ATYPE') not in (' Checks', ' Fold', ' Card dealt to a spot', ' Big blind/Bring in') and not hand.allInBlind:
                    hand.setUncalledBets(False)

                # Update hand object based on the type of action
                if action.group('ATYPE') == ' Fold':
                    hand.addFold(street, player)
                elif action.group('ATYPE') == ' Checks':
                    hand.addCheck(street, player)
                elif action.group('ATYPE') in [' Calls', ' Call']:
                    if not action.group('BET'):
                        log.error(f"BovadaToFpdb.readAction: Amount not found in Call {hand.handid}")
                        raise FpdbParseError
                    hand.addCall(street, player, self.clearMoneyString(action.group('BET')))
                elif action.group('ATYPE') in (' Raises', ' raises', ' All-in(raise)', ' All-in(raise-timeout)'):
                    if action.group('BETTO'):
                        bet = self.clearMoneyString(action.group('BETTO'))
                    elif action.group('BET'):
                        bet = self.clearMoneyString(action.group('BET'))
                    else:
                        log.error(f"BovadaToFpdb.readAction: Amount not found in Raise {hand.handid}")
                        raise FpdbParseError
                    hand.addRaiseTo(street, player, bet)
                elif action.group('ATYPE') in (' Bets', ' bets', ' Double bets'):
                    if not action.group('BET'):
                        log.error(f"BovadaToFpdb.readAction: Amount not found in Bet {hand.handid}")
                        raise FpdbParseError
                    hand.addBet(street, player, self.clearMoneyString(action.group('BET')))
                elif action.group('ATYPE') == ' All-in':
                    if not action.group('BET'):
                        log.error(f"BovadaToFpdb.readAction: Amount not found in All-in {hand.handid}")
                        raise FpdbParseError
                    hand.addAllIn(street, player, self.clearMoneyString(action.group('BET')))
                    self.allInBlind(hand, street, action, action.group('ATYPE'))
                elif action.group('ATYPE') == ' Bring_in chip':
                    pass
                elif action.group('ATYPE') not in (' Card dealt to a spot', ' Big blind/Bring in'):
                    log.debug(
                        ("DEBUG:")
                        + " "
                        + f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'"
                    )

                
    def allInBlind(self, hand, street, action, actiontype):
        """
        Sets the "all-in blind" flag for a hand if a player goes all-in with a blind bet.
        Args:
            hand (Hand): the current hand being played
            street (str): the current betting round
            action (str): the action taken by the player
            actiontype (str): the type of action taken by the player
        """
        # Check if the current street is preflop or deal
        if street in ('PREFLOP', 'DEAL'):
            # Get the player who made the all-in blind bet
            player = self.playerSeatFromPosition('BovadaToFpdb.allInBlind', hand.handid, action.group('PNAME'))
            # Check if the player's stack is 0 and if they did not return any bet
            if hand.stacks[player]==0 and not self.re_ReturnBet.search(hand.handText):
                # Set the uncalled bets flag to True and set the all-in blind flag to True
                hand.setUncalledBets(True)
                hand.allInBlind = True


    def readShowdownActions(self, hand):
        """
        Parses the handText and adds the shown cards to the corresponding player's hand.

        Args:
            hand (Hand): The hand object representing the current hand being parsed.

        Returns:
            None
        """
        # TODO: pick up mucks also??
        if hand.gametype['base'] in ("hold"):
            for shows in self.re_ShowdownAction.finditer(hand.handText):
                cards = shows.group('CARDS').split(' ')
                player = self.playerSeatFromPosition('BovadaToFpdb.readShowdownActions', hand.handid, shows.group('PNAME'))
                hand.addShownCards(cards, player)

    def readCollectPot(self, hand):
        """Parses hand text to extract pot information and adds it to the hand object.

        Args:
            hand: A Hand object containing the hand text to be parsed.

        Returns:
            None
        """
        # Determine which pattern to use for parsing based on hand version
        if self.re_CollectPot2.search(hand.handText):
            re_CollectPot = self.re_CollectPot2
        else:
            re_CollectPot = self.re_CollectPot1

        # Search for pot information using the selected pattern
        for m in re_CollectPot.finditer(hand.handText.replace(" [ME]", "") if hand.version == 'MVS' else hand.handText):# [ME]
            collect, pot = m.groupdict(), 0
            if 'POT1' in collect and collect['POT1'] != None:
                pot += Decimal(self.clearMoneyString(collect['POT1']))
            if 'POT2' in collect and collect['POT2'] != None:
                pot += Decimal(self.clearMoneyString(collect['POT2']))

            # If pot information was found, add it to the hand object
            if pot > 0: 
                player = self.playerSeatFromPosition('BovadaToFpdb.readCollectPot', hand.handid, collect['PNAME'])
                hand.addCollectPot(player=player, pot=str(pot))


    def readShownCards(self,hand):
        """
        Reads and returns the cards shown by the dealer.

        Args:
            hand (list): A list of cards shown by the dealer.

        Returns:
            list: A list of cards shown by the dealer.
        """
        # TODO: Implement the logic for reading shown cards
        pass
    

    def readTourneyResults(self, hand):
        """
        Reads knockout bounties and adds them to the koCounts dict.

        Args:
            hand (Hand): The hand object to read knockout bounties from.

        Returns:
            None
        """

        # Find all the knockout bounties in the hand text
        for a in self.re_Bounty.finditer(hand.handText):
            # Get the player seat from their position
            player = self.playerSeatFromPosition('BovadaToFpdb.readCollectPot', hand.handid, a.group('PNAME'))

            # Add the player to the koCounts dict if they are not already in it
            if player not in hand.koCounts:
                hand.koCounts[player] = 0

            # Increment the player's knockout count
            hand.koCounts[player] += 1
 
        