#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2008-2011, Carl Gherardi
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

from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

from HandHistoryConverter import *
from decimal_wrapper import Decimal


class Cake(HandHistoryConverter):
    """
    A class for converting Cake hand histories to FPDB format.

    Inherits from HandHistoryConverter.

    Class Variables:
        sitename (str): The name of the site.
        filetype (str): The file type of the hand history.
        codepage (tuple): The supported code pages for the hand history.
        siteId (int): The ID of the site.
        sym (dict): A dictionary mapping currencies to their symbols.
        substitutions (dict): A dictionary mapping shorthand codes to regular expressions for parsing hand histories.
    """

    # Class Variables

    sitename = "Cake"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId   = 17
    sym = {'USD': "\$", 'CAD': "\$", 'T$': "", "EUR": "€", "GBP": "\xa3", "play": ""}
    substitutions = {
                        'LEGAL_ISO' : "USD|EUR|GBP|CAD|FPP",      # legal ISO currency codes
                                'LS' : r"\$|€|", # legal currency symbols - Euro(cp1252, utf-8)
                            'PLYR': r'(?P<PNAME>.+?)',
                                'CUR': r"(\$|€|)",
                                'NUM' :r".(,|\s)\d\xa0",
                                'NUM2': r'\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b',  # Regex pattern for matching numbers with spaces
                        }

                    
    # translations from captured groups to fpdb info strings
    Lim_Blinds = {      '0.04': ('0.01', '0.02'),    '0.08': ('0.02', '0.04'),
                        '0.10': ('0.02', '0.05'),    '0.20': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),    '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),       '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),       '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),       '4': ('1.00', '2.00'),
                        '6.00': ('1.50', '3.00'),       '6': ('1.50', '3.00'),
                        '8.00': ('2.00', '4.00'),       '8': ('2.00', '4.00'),
                       '10.00': ('2.50', '5.00'),      '10': ('2.50', '5.00'),
                       '12.00': ('3.00', '6.00'),      '12': ('3.00', '6.00'),
                       '20.00': ('5.00', '10.00'),     '20': ('5.00', '10.00'),
                       '30.00': ('7.50', '15.00'),     '30': ('7.50', '15.00'),
                       '40.00': ('10.00', '20.00'),    '40': ('10.00', '20.00'),
                       '60.00': ('15.00', '30.00'),    '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),    '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),   '100': ('25.00', '50.00'),
                      '200.00': ('50.00', '100.00'),  '200': ('50.00', '100.00'),
                      '400.00': ('100.00', '200.00'), '400': ('100.00', '200.00'),
                      '800.00': ('200.00', '400.00'), '800': ('200.00', '400.00'),
                     '1000.00': ('250.00', '500.00'),'1000': ('250.00', '500.00')
                  }

    limits = { 'NL':'nl', 'PL':'pl', 'FL':'fl' }
    games = {                          # base, category
                              "Hold'em" : ('hold','holdem'), 
                                'Omaha' : ('hold','omahahi'),
                          'Omaha Hi/Lo' : ('hold','omahahilo'),
                            'OmahaHiLo' : ('hold','omahahilo'),
               }
    currencies = { u'€':'EUR', '$':'USD', '':'T$' }

    # Static regexes
    re_GameInfo     = re.compile(r"""
          Hand\#(?P<HID>[A-Z0-9]+)\s+\-\s+(?P<TABLE>(?P<BUYIN1>(?P<BIAMT1>(%(LS)s)[%(NUM)s]+)\sNLH\s(?P<MAX1>\d+)\smax)?.+?)\s(\((Turbo,\s)?(?P<MAX>\d+)\-+[Mm]ax\)\s)?((?P<TOURNO>T\d+)|\d+)\s(\-\-\s(TICKET|CASH|TICKETCASH|FREEROLL)\s\-\-\s(?P<BUYIN>(?P<BIAMT>\$\d+)\s\+\s(?P<BIRAKE>\$\d+))\s\-\-\s(?P<TMAX>\d+)\sMax\s)?(\-\-\sTable\s(?P<TABLENO>\d+)\s)?\-\-\s(?P<CURRENCY>%(LS)s|)?(?P<ANTESB>(\-)?\d+)/(%(LS)s)?(?P<SBBB>\d+)(/(%(LS)s)?(?P<BB>\d+))?\s(?P<LIMIT>NL|FL||PL)\s(?P<GAME>Hold\'em|Omaha|Omaha\sHi/Lo|OmahaHiLo)\s-\-\s(?P<DATETIME>.*$)
          
          """ % substitutions, re.MULTILINE|re.VERBOSE)

    re_PlayerInfo   = re.compile(r"""
            ^Seat\s(?P<SEAT>[0-9]+):\s
            (?P<PNAME>.+?)\s
            \((%(LS)s)?(?P<CASH>[%(NUM2)s]+)\sin\schips\)
            (\s\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?""" % substitutions, 
            re.MULTILINE|re.VERBOSE)

    re_Trim         = re.compile("(Hand\#)")
    re_Identify     = re.compile(u'Hand\#[A-Z0-9]+\s\-\s')
    re_SplitHands   = re.compile('\n\n+')
    re_Button       = re.compile('Dealer: Seat (?P<BUTTON>\d+)', re.MULTILINE)
    re_Board        = re.compile(r"\[(?P<CARDS>.+)\]")

    re_DateTime     = re.compile("""(?P<Y>[0-9]{4})[\/\-\.](?P<M>[0-9]{2})[\/\-\.](?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""", re.MULTILINE)
    re_PostSB       = re.compile(r"^%(PLYR)s: posts small blind %(CUR)s(?P<SB>[%(NUM)s]+)(\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?$" %  substitutions, re.MULTILINE)
    re_PostBB       = re.compile(r"^%(PLYR)s: posts big blind %(CUR)s(?P<BB>[%(NUM)s]+)(\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?$" %  substitutions, re.MULTILINE)
    re_Antes        = re.compile(r"^%(PLYR)s: posts ante of %(CUR)s(?P<ANTE>[%(NUM)s]+)(\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?" % substitutions, re.MULTILINE)
    re_BringIn      = re.compile(r"^%(PLYR)s: brings[- ]in( low|) for %(CUR)s(?P<BRINGIN>[%(NUM)s]+)(\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?" % substitutions, re.MULTILINE)
    re_PostBoth     = re.compile(r"^%(PLYR)s:posts dead blind %(CUR)s(\-)?(?P<SB>[%(NUM)s]+) and big blind %(CUR)s(?P<BB>[%(NUM)s]+)" %  substitutions, re.MULTILINE)
    re_HeroCards    = re.compile(r"^Dealt to %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % substitutions, re.MULTILINE)
    re_Action       = re.compile(r"""
                        ^%(PLYR)s:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sis\sall\sin)
                        (\s(to\s)?(%(CUR)s)?(?P<BET>[%(NUM)s]+))?(\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?$
                        """
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    re_sitsOut          = re.compile("^%s sits out" %  substitutions['PLYR'], re.MULTILINE)
    re_ShownCards       = re.compile(r"^%s: (?P<SHOWED>shows|mucks) \[(?P<CARDS>.*)\] ?(\((?P<STRING>.*)\))?" % substitutions['PLYR'], re.MULTILINE)
    re_CollectPot       = re.compile(r"^%(PLYR)s:? wins (low pot |high pot )?%(CUR)s(?P<POT>[%(NUM)s]+)((\swith.+?)?\s+\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?" %  substitutions, re.MULTILINE)
    re_Finished         = re.compile(r"%(PLYR)s:? finished \d+ out of \d+ players" %  substitutions, re.MULTILINE)
    re_Dealer           = re.compile(r"Dealer:") #Some Cake hands just omit the game line so we can just discard them as partial
    re_CoinFlip         = re.compile(r"Coin\sFlip\sT\d+", re.MULTILINE)
    re_ReturnBet        = re.compile(r"returns\suncalled\sbet", re.MULTILINE)
    re_ShowDown         = re.compile(r"\*\*\*SHOW DOWN\*\*\*")
    re_ShowDownLeft     = re.compile(r"\*\*\*SHOW\sDOWN\*\*\*\nPlayer\sleft\sthe\stable$", re.MULTILINE)

    def compilePlayerRegexs(self, hand):
        """
        Compiles regular expressions representing the cards in a player's hand.

        Args:
            hand (list[str]): The cards in the player's hand.

        Returns:
            list[re.Pattern]: A list of compiled regular expressions, one for each card in the player's hand.
        """
        pass  # TODO: Implement this function.


    def readSupportedGames(self):
        """
        Returns a list of supported games.

        Each supported game is represented as a list of game modes.
        """
        return [
            ["ring", "hold", "nl"],  # Ring game, hold mode, no limit
            ["ring", "hold", "pl"],  # Ring game, hold mode, pot limit
            ["ring", "hold", "fl"],  # Ring game, hold mode, fixed limit
            ["tour", "hold", "nl"],  # Tournament, hold mode, no limit
            ["tour", "hold", "pl"],  # Tournament, hold mode, pot limit
            ["tour", "hold", "fl"],  # Tournament, hold mode, fixed limit
        ]

    def determineGameType(self, handText):
        """
        Determine the type of game from the given hand text.

        Args:
            handText (str): The text of the hand.

        Returns:
            dict: A dictionary containing information about the game type.
        """
        # Initialize dictionary to store game type info
        info = {}

        # Search for game info in hand text
        m = self.re_GameInfo.search(handText)

        # If no game info found, raise appropriate error
        if not m:
            if self.re_Finished.search(handText):
                raise FpdbHandPartial
            if self.re_Dealer.match(handText):
                raise FpdbHandPartial
            tmp = handText[:200]
            log.error(f"CakeToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        # If no ShowDown or ShowDownLeft found, raise appropriate error
        if not self.re_ShowDown.search(handText) or self.re_ShowDownLeft.search(handText):
            raise FpdbHandPartial

        # Extract game info from match object's group dictionary
        mg = m.groupdict()

        # Determine limit type and store in info dictionary
        if 'LIMIT' in mg:
            info['limitType'] = self.limits[mg['LIMIT']]

        # Determine game category and base type and store in info dictionary
        if 'GAME' in mg:
            (info['base'], info['category']) = self.games[mg['GAME']]

        # Determine big blind and store in info dictionary
        if 'BB' in mg:
            if not mg['BB']:
                info['bb'] = self.clearMoneyString(mg['SBBB'])
            else:
                info['bb'] = self.clearMoneyString(mg['BB'])

        # Determine small blind and store in info dictionary
        if 'SBBB' in mg:
            if not mg['BB']:
                info['sb'] = self.clearMoneyString(mg['ANTESB'])
            else:
                info['sb'] = self.clearMoneyString(mg['SBBB'])

        # Determine currency and store in info dictionary
        if 'CURRENCY' in mg:
            info['currency'] = self.currencies[mg['CURRENCY']]

        # Determine mix and store in info dictionary
        if 'MIXED' in mg and mg['MIXED'] is not None:
            info['mix'] = self.mixes[mg['MIXED']]

        # Determine game type and store in info dictionary
        if 'TOURNO' in mg and mg['TOURNO'] is not None:
            info['type'] = 'tour'
        else:
            info['type'] = 'ring'

        # If play money game, set currency to 'play'
        if 'TABLE' in mg and 'Play Money' in mg['TABLE']:
            info['currency'] = 'play'

        # If limit type is 'fl' and big blind is not None 
        if info['limitType'] == 'fl' and info['bb'] is not None:
            # If game type is 'ring'
            if info['type'] == 'ring':
                try:
                    # Determine small blind and big blind and store in info dictionary
                    info['sb'] = self.Lim_Blinds[info['bb']][0]
                    info['bb'] = self.Lim_Blinds[info['bb']][1]
                except KeyError as e:
                    tmp = handText[:200]
                    log.error(
                        f"CakeToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'"
                    )
                    raise FpdbParseError from e
            # If game type is not 'ring'
            else:
                # Calculate small blind and big blind and store in info dictionary
                info['sb'] = str((old_div(Decimal(info['sb']),2)).quantize(Decimal("0.01")))
                info['bb'] = str(Decimal(info['sb']).quantize(Decimal("0.01")))

        return info



    def readHandInfo(self, hand):
        """
        Reads information from a hand history string and updates the corresponding Hand object.

        Parameters:
        hand (Hand): The Hand object to update.

        Returns:
        None
        """

        # trim off malformatted text from partially written hands
        if not self.re_Trim.match(hand.handText):
            hand.handText = "".join(self.re_Trim.split(hand.handText)[1:])

        info = {}
        m = self.re_GameInfo.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"CakeToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError

        info |= m.groupdict()

        for key in info:
            # extract datetime information and convert to UTC timezone
            if key == 'DATETIME':
                m1 = self.re_DateTime.finditer(info[key])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
                hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
                hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")

            # extract hand ID
            elif key == 'HID':
                hand.handid = re.sub('[A-Z]+', '', info[key])

            # extract table name for ring games
            if key == 'TABLE' and hand.gametype['type'] == 'ring':
                hand.tablename = info[key]

            # extract table name for tournament games
            if key == 'TABLENO' and hand.gametype['type'] == 'tour':
                hand.tablename = info[key]

            # extract button position
            if key == 'BUTTON':
                hand.buttonpos = info[key]

            # extract maximum number of seats
            if key == 'MAX' and info[key]:
                hand.maxseats = int(info[key])

            # extract tournament number
            if key == 'TOURNO' and info[key]:
                hand.tourNo = info[key].replace('T', '')

            # extract maximum number of seats for tournament games
            if key == 'TMAX' and info[key]:
                hand.maxseats = int(info[key])
            if key == 'TMAX1' and info[key]:
                hand.maxseats = int(info[key])

            # extract buy-in information
            if key in ['BUYIN', 'BUYIN1'] and info[key] and hand.tourNo!=None:
                if info[key].find("$")!=-1:
                    hand.buyinCurrency="USD"
                elif info[key].find(u"£")!=-1:
                    hand.buyinCurrency="GBP"
                elif info[key].find(u"€")!=-1:
                    hand.buyinCurrency="EUR"
                elif re.match("^[0-9+]*$", info[key]):
                    hand.buyinCurrency="play"
                else:
                    #FIXME: handle other currencies, play money
                    log.error(
                        f"CakeToFpdb.readHandInfo: Failed to detect currency. Hand ID: {hand.handid}: '{info[key]}'"
                    )
                    raise FpdbParseError

                # extract buy-in amount and rake amount
                if key == 'BUYIN1':
                    info['BIAMT1']  = self.clearMoneyString(info['BIAMT1'].strip(u'$€£'))
                    hand.buyin = int(100*Decimal(info['BIAMT1']))
                    hand.fee = 0
                else:
                    info['BIAMT']  = self.clearMoneyString(info['BIAMT'].strip(u'$€£'))
                    info['BIRAKE'] = self.clearMoneyString(info['BIRAKE'].strip(u'$€£'))
                    hand.buyin = int(100*Decimal(info['BIAMT']))
                    hand.fee = int(100*Decimal(info['BIRAKE']))

        if hand.gametype['type'] == 'tour' and not hand.buyin:
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency="NA"



    def readButton(self, hand):
        """
        Parses a hand for the button position and updates the hand object.

        Args:
            hand (Hand): The hand object to update.

        Returns:
            None
        """
        # Search for the button position in the hand text
        if m := self.re_Button.search(hand.handText):
            # If found, update the button position in the hand object
            hand.buttonpos = int(m.group('BUTTON'))
        else:
            # If not found, log an info message
            log.info('readButton: ' + ('not found'))


    def readPlayerStacks(self, hand):
        """
        Reads player stacks from the given `hand` object and adds them to the `hand` object.

        Args:
            hand (Hand): The `Hand` object to read player stacks from.

        Returns:
            None
        """
        # Find each player's stack information in the hand text
        m = self.re_PlayerInfo.finditer(hand.handText)

        # Check if there was a coinflip in the hand
        coinflip = bool(self.re_CoinFlip.search(hand.handText))

        # Iterate over each player's stack information
        for a in m:
            # Check if the stack information has a EUROVALUE and set the roundPenny flag accordingly
            if a.group('EUROVALUE'):
                hand.roundPenny = True
            cash_value = a.group('CASH')
            cash_value = cash_value.encode("utf-8")
            cash_value = cash_value.replace(b"\xe2\x80\xaf", b"")
            cash_value = cash_value.decode("utf-8")
            print("value:",  cash_value)
            print("type:" , type(cash_value))
            # Add the player's stack information to the `hand` object
            hand.addPlayer(int(a.group('SEAT')), a.group('PNAME'), cash_value)

            # Add the player's stack information to the `hand` object
            #hand.addPlayer(int(a.group('SEAT')), a.group('PNAME'), self.convertMoneyString('CASH', a))

            # If there was a coinflip, add the ante for the player
            if coinflip:
                hand.addAnte(a.group('PNAME'), self.convertMoneyString('CASH', a))


    def markStreets(self, hand):
        """
        Given a Hand object, extract the street information from its handText attribute
        and update the Hand object with the street information.

        Args:
        - hand: a Hand object to extract street information from

        Returns:
        - None
        """

        # The following regex matches the different streets in a hand history and captures the information
        # in named groups: PREFLOP, FLOP, TURN, RIVER.
        # It first matches everything up to the FLOP street, then optionally matches the FLOP street,
        # then optionally matches the TURN street, and finally optionally matches the RIVER street.
        # The information captured in each street is then stored in its respective named group.
        regex = r"(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)" \
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S,\S\S,\S\S\].+(?=\*\*\* TURN \*\*\*)|.+))?" \
                r"(\*\*\* TURN \*\*\* (?P<TURN>\[\S\S\].+(?=\*\*\* RIVER \*\*\*)|.+))?" \
                r"(\*\*\* RIVER \*\*\* (?P<RIVER>\[\S\S\].+))?"

        # Use the regex to search for the street information in the hand's handText attribute
        m = re.search(regex, hand.handText, re.DOTALL)

        # Add the street information to the Hand object
        hand.addStreets(m)


    def readCommunityCards(self, hand, street):
        """
        Reads the community cards for a given street of the current hand and sets them in the hand object.

        Args:
            hand (Hand): The current hand object.
            street (str): The street to read the community cards for.

        Returns:
            None
        """
        if street in ('FLOP','TURN','RIVER'):
            # Parse the community cards from the hand object's streets dictionary
            m = self.re_Board.search(hand.streets[street])
            # Set the community cards in the hand object
            hand.setCommunityCards(street, m.group('CARDS').split(',')) 


    def readAntes(self, hand):
        """
        Reads the antes from the hand and adds them to the Hand object.

        Args:
            hand: The Hand object to add the antes to.

        Returns:
            None
        """
        log.debug(("reading antes"))
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            # Uncomment the following line to enable logging
            # logging.debug("hand.addAnte(%s,%s)" %(player.group('PNAME'), player.group('ANTE')))
            hand.addAnte(player.group('PNAME'), self.convertMoneyString('ANTE', player))

    
    def readBringIn(self, hand):
        """
        Reads the BringIn information from the hand's handText and adds it to the hand object.

        Args:
            hand (Hand): The Hand object to add the BringIn information to.

        Returns:
            None
        """
        if m := self.re_BringIn.search(hand.handText, re.DOTALL):
            # The BringIn information was found, add it to the hand object.
            # logging.debug("readBringIn: %s for %s" %(m.group('PNAME'),  m.group('BRINGIN')))
            hand.addBringIn(m.group('PNAME'),  self.convertMoneyString('BRINGIN', m))

        
    def readBlinds(self, hand):
        """
        Parses the hand text and extracts the blinds information.

        Args:
            hand: An instance of the Hand class representing the hand being parsed.

        Returns:
            None
        """

        # Flag to keep track of whether the small blind is still live.
        liveBlind = True

        # If no bets were returned, set the uncalled bets flag to True.
        if not self.re_ReturnBet.search(hand.handText):
            hand.setUncalledBets(True)

        # Find all instances of the small blind and add them to the Hand object.
        for a in self.re_PostSB.finditer(hand.handText):
            if liveBlind:
                hand.addBlind(a.group('PNAME'), 'small blind', self.convertMoneyString('SB',a))
                liveBlind = False
            else:
                # Post dead blinds as ante
                hand.addBlind(a.group('PNAME'), 'secondsb', self.convertMoneyString('SB', a))

        # Find all instances of the big blind and add them to the Hand object.
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'big blind', self.convertMoneyString('BB', a))

        # Find all instances of both blinds being posted and add them to the Hand object.
        for a in self.re_PostBoth.finditer(hand.handText):
            sb = Decimal(self.clearMoneyString(a.group('SB')))
            bb = Decimal(self.clearMoneyString(a.group('BB')))
            sbbb = sb + bb
            hand.addBlind(a.group('PNAME'), 'both', str(sbbb))



    def readHoleCards(self, hand):
        """
        Reads the hero's hole cards from the given hand object and adds them to the corresponding streets.

        Args:
            hand (Hand): The hand object containing the streets and player information.

        Returns:
            None
        """
        # Iterate through the streets where hole cards can be found
        for street in ('PREFLOP', 'DEAL'):
            # Check if the street is present in the hand object
            if street in list(hand.streets.keys()):
                # Use regex to find hero's cards in the street
                m = self.re_HeroCards.finditer(hand.streets[street])
                # Iterate through each match found
                for found in m:
                    # Save the hero's name
                    hand.hero = found.group('PNAME')
                    # Split the hole cards string into individual cards
                    newcards = found.group('NEWCARDS').split(',')
                    # Add the hole cards to the corresponding street
                    hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)


    def readAction(self, hand, street):
        """
        Given a Hand object and a street string, reads the actions from the hand 
        and updates the Hand object with the appropriate information.

        Args:
        - hand: Hand object representing the current state of the hand
        - street: string representing the current betting round of the hand

        Returns:
        None
        """
        # Find all the actions in the current street of the hand
        m = self.re_Action.finditer(hand.streets[street])

        # Loop through each action and update the Hand object accordingly
        for action in m:
            acts = action.groupdict()
            #print "DEBUG: acts: %s" %acts
            bet = self.convertMoneyString('BET', action)
            actionType = action.group('ATYPE')

            # If the current action is a fold and not in preflop, add a fold to the Hand object
            if street != 'PREFLOP' or actionType != ' folds':
                hand.setUncalledBets(False)
            if actionType == ' folds':
                hand.addFold(street, action.group('PNAME'))

            # If the current action is a check, add a check to the Hand object
            elif actionType == ' checks':
                hand.addCheck(street, action.group('PNAME'))

            # If the current action is a call, add a call to the Hand object
            elif actionType == ' calls':
                hand.addCall(street, action.group('PNAME'), bet)

            # If the current action is a raise, add a raise to the Hand object
            elif actionType == ' raises':
                hand.setUncalledBets(None)
                hand.addRaiseTo(street, action.group('PNAME'), bet)

            # If the current action is a bet, add a bet to the Hand object
            elif actionType == ' bets':
                hand.addBet(street, action.group('PNAME'), bet)

            # If the current action is an all-in, add an all-in to the Hand object
            elif actionType == ' is all in':
                hand.addAllIn(street, action.group('PNAME'), bet)

            # If the current action is not one of the above types, log an error
            else:
                log.error(
                    ("DEBUG:")
                    + " "
                    + f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'"
                )


    def readShowdownActions(self, hand):
        """
        Parses a hand of cards and returns the best possible action to take in a game of poker.

        Args:
            hand (list): A list of cards in the hand.

        Returns:
            str: The best possible action to take.
        """
        pass


    def readCollectPot(self,hand):
        """
        Finds the collect pot for a given hand and adds it to the Hand object.

        Args:
            hand (Hand): The Hand object to which the collect pot will be added.

        Returns:
            None
        """
        # Find all instances of the collect pot in the hand text.
        for m in self.re_CollectPot.finditer(hand.handText):
            # Only consider the collect pot if it is not part of a tournament hand.
            if not re.search('Tournament:\s', m.group('PNAME')):
                # Add the collect pot to the Hand object.
                hand.addCollectPot(player=m.group('PNAME'),pot=self.convertMoneyString('POT', m))


    def readShownCards(self, hand):
        """
        Finds shown cards in a hand text and adds them to the Hand object.

        Args:
            hand: The Hand object to which shown cards will be added.

        Returns:
            None
        """

        # Find shown cards using regular expression.
        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group('CARDS') is not None:
                cards = m.group('CARDS')
                string = m.group('STRING')

                # Check if player showed or mucked cards.
                (shown, mucked) = (False, False)
                if m.group('SHOWED') == "shows":
                    shown = True
                    # Split cards into a list.
                    cards = cards.split(' ')
                elif m.group('SHOWED') == "mucks":
                    mucked = True
                    # Split cards into a list and remove any leading/trailing whitespace.
                    cards = [c.strip() for c in cards.split(',')]

                # Try to add shown cards to the hand.
                try:
                    hand.checkPlayerExists(m.group('PNAME'))
                    player = m.group('PNAME')
                except FpdbParseError:
                    # If the player doesn't exist, replace underscores with spaces in the player name.
                    player = m.group('PNAME').replace('_', ' ')

                # Add shown cards to the hand.
                hand.addShownCards(cards=cards, player=player, shown=shown, mucked=mucked, string=string)

                
    def convertMoneyString(self, type, match):
        """
        Converts a string of money to a float value.

        Args:
        - type: string type of currency (e.g. "USD", "GBP", etc.)
        - match: string to be converted

        Returns:
        - float value of the money string or None if no match found
        """

        if match.group('EUROVALUE'):
            # if the match is in EUROVALUE format, return the cleared money string
            return self.clearMoneyString(match.group('EUROVALUE'))
        elif match.group(type):
            # if the match is in the specified currency format, return the cleared money string
            return self.clearMoneyString(match.group(type))
        else:
            # if no match found, return None
            return None    

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament = None, table_number=None):
        log.info(
            f"cake.getTableTitleRe: table_name='{table_name}' tournament='{tournament}' table_number='{table_number}'"
        )
        regex = f""
        print("regex get table cash title:", regex)
        if tournament:
            
            regex = f"Tournament:\s{tournament}\sBuy\-In\s\w+\s:\sTable\s{table_number}"
            #Tournament: 17106061 Buy-In Freeroll : Table 10 - No Limit Holdem - 15/30
            print("regex get mtt sng expresso cash title:", regex)
        log.info(f"Seals.getTableTitleRe: returns: '{regex}'")
        return regex