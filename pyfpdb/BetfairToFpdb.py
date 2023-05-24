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


#import L10n
#_ = L10n.get_translation()

import sys
from HandHistoryConverter import *

# Betfair HH format
class Betfair(HandHistoryConverter):
    """
    A class for converting Betfair hand history files.

    This class inherits from the HandHistoryConverter class and provides methods to convert Betfair hand history files
    into a standardized format.

    Attributes:
        sitename (str): The name of the site, which is 'Betfair'.
        filetype (str): The file type of the hand history files, which is 'text'.
        codepage (str): The code page used for encoding, which is 'cp1252'.
        siteId (int): The site ID used for identifying the site in the Sites database, which is 7.

        re_GameInfo (re.Pattern): A compiled regular expression pattern for extracting game information from the hand history.
        re_Identify (re.Pattern): A compiled regular expression pattern for identifying Betfair hand history files.
        re_SplitHands (re.Pattern): A compiled regular expression pattern for splitting multiple hands in a hand history file.
        re_HandInfo (re.Pattern): A compiled regular expression pattern for extracting hand information from the hand history.
        re_Button (re.Pattern): A compiled regular expression pattern for identifying the button seat in the hand history.
        re_PlayerInfo (re.Pattern): A compiled regular expression pattern for extracting player information from the hand history.
        re_Board (re.Pattern): A compiled regular expression pattern for extracting board cards from the hand history.

    """

    sitename = 'Betfair'
    filetype = "text"
    codepage = "cp1252"
    siteId = 7  # Needs to match id entry in Sites database

    # Static regexes
    re_GameInfo = re.compile("^(?P<LIMIT>NL|PL|) (?P<CURRENCY>\$|)?(?P<SB>[.0-9]+)/\$?(?P<BB>[.0-9]+) (?P<GAME>(Texas Hold\'em|Omaha Hi|Omaha|Razz))", re.MULTILINE)
    re_Identify = re.compile(u'\*{5}\sBetfair\sPoker\sHand\sHistory\sfor\sGame\s\d+\s')
    re_SplitHands = re.compile(r'\n\n+')
    re_HandInfo = re.compile("\*\*\*\*\* Betfair Poker Hand History for Game (?P<HID>[0-9]+) \*\*\*\*\*\n(?P<LIMIT>NL|PL|) (?P<CURRENCY>\$|)?(?P<SB>[.0-9]+)/\$?(?P<BB>[.0-9]+) (?P<GAMETYPE>(Texas Hold\'em|Omaha|Razz)) - (?P<DATETIME>[a-zA-Z]+, [a-zA-Z]+ \d+, \d\d:\d\d:\d\d GMT \d\d\d\d)\nTable (?P<TABLE>[ a-zA-Z0-9]+) \d-max \(Real Money\)\nSeat (?P<BUTTON>[0-9]+)", re.MULTILINE)
    re_Button = re.compile(r"^Seat (?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_PlayerInfo = re.compile("Seat (?P<SEAT>[0-9]+): (?P<PNAME>.*)\s\(\s(\$(?P<CASH>[.0-9]+)) \)")
    re_Board = re.compile(r"\[ (?P<CARDS>.+) \]")



    def compilePlayerRegexs(self, hand):
        """
        Compile player-related regular expressions based on the players in the hand.

        This method takes a hand object and compiles regular expressions specific to the players involved in the hand.
        The compiled regular expressions are stored as attributes of the class for later use.

        Args:
            hand (Hand): The hand object containing player information.

        """

        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            # We need to recompile the player regexs.
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            log.debug(f"player_re: {player_re}")
            self.re_PostSB = re.compile(
                "^%s posts small blind \[\$?(?P<SB>[.0-9]+)" % player_re, re.MULTILINE
            )
            self.re_PostBB = re.compile(
                "^%s posts big blind \[\$?(?P<BB>[.0-9]+)" % player_re, re.MULTILINE
            )
            self.re_Antes = re.compile(
                f"^{player_re} antes asdf sadf sadf", re.MULTILINE
            )
            self.re_BringIn = re.compile(
                f"^{player_re} antes asdf sadf sadf", re.MULTILINE
            )
            self.re_PostBoth = re.compile(
                "^%s posts small \& big blinds \[\$?(?P<SBBB>[.0-9]+)" % player_re, re.MULTILINE
            )
            self.re_HeroCards = re.compile(
                "^Dealt to %s \[ (?P<CARDS>.*) \]" % player_re, re.MULTILINE
            )
            self.re_Action = re.compile(
                "^%s (?P<ATYPE>bets|checks|raises to|raises|calls|folds)(\s\[\$(?P<BET>[.\d]+)\])?" % player_re,
                re.MULTILINE,
            )
            self.re_ShowdownAction = re.compile(
                "^%s shows \[ (?P<CARDS>.*) \]" % player_re, re.MULTILINE
            )
            self.re_CollectPot = re.compile(
                "^%s wins \$(?P<POT>[.\d]+) (.*?\[ (?P<CARDS>.*?) \])?" % player_re,
                re.MULTILINE,
            )
            self.re_SitsOut = re.compile(f"^{player_re} sits out", re.MULTILINE)
            self.re_ShownCards = re.compile(
                f"{player_re} (?P<SEAT>[0-9]+) (?P<CARDS>adsfasdf)", re.MULTILINE
            )


    def readSupportedGames(self):
        """
        Reads the supported games.

        Args:
            None

        Returns:
            List of lists containing supported games.
        """
        # Games currently supported by the system
        return [["ring", "hold", "nl"],
                ["ring", "hold", "pl"]
               ]

    def determineGameType(self, handText):
        """
        Determines the game type from a given hand text.

        Args:
            handText (str): The hand text to parse.

        Returns:
            dict: A dictionary with the following keys:
                - 'type': The type of the game.
                - 'limitType': The limit type of the game.
                - 'base': The base of the game.
                - 'category': The category of the game.
                - 'sb': The small blind amount.
                - 'bb': The big blind amount.
                - 'currency': The currency of the game.
        """

        # Initialize the info dictionary with default values
        info = {'type': 'ring'}

        # Search for game info in hand text
        m = self.re_GameInfo.search(handText)
        if not m:
            # If no game info is found, log an error and raise an exception
            tmp = handText[:200]
            log.error(f"BetfairToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        # Get the dictionary of named capturing groups from the regex match
        mg = m.groupdict()

        # Parse game info from the regex groups
        if 'LIMIT' in mg:
            # If the 'LIMIT' group is present, map its value to a limit type string
            limits = {'NL': 'nl', 'PL': 'pl', 'Limit': 'fl'}
            info['limitType'] = limits[mg['LIMIT']]
        if 'GAME' in mg:
            # If the 'GAME' group is present, map its value to a base and category tuple
            games = {
                "Texas Hold'em": ('hold', 'holdem'),
                'Omaha Hi': ('hold', 'omahahi'),
                'Omaha': ('hold', 'omahahi'),
                'Razz': ('stud', 'razz'),
                '7 Card Stud': ('stud', 'studhi')
            }
            (info['base'], info['category']) = games[mg['GAME']]
        if 'SB' in mg:
            # If the 'SB' group is present, set its value as the small blind amount
            info['sb'] = mg['SB']
        if 'BB' in mg:
            # If the 'BB' group is present, set its value as the big blind amount
            info['bb'] = mg['BB']
        if 'CURRENCY' in mg:
            # If the 'CURRENCY' group is present, map its value to a currency string
            currencies = {u' €': 'EUR', '$': 'USD', '': 'T$'}
            info['currency'] = currencies[mg['CURRENCY']]


        return info


    def readHandInfo(self, hand):
        """
        Reads hand information from the given hand and extracts relevant details.

        Args:
            hand (Hand): The hand to read information from.

        Raises:
            FpdbParseError: If the hand information cannot be parsed.

        Returns:
            None
        """
        # Search for hand information
        m = self.re_HandInfo.search(hand.handText)

        # If hand information not found, raise error
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"BetfairToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError

        # Extract relevant details from the hand information
        log.debug(f"HID {m.group('HID')}, Table {m.group('TABLE')}")
        hand.handid = m.group('HID')
        hand.tablename = m.group('TABLE')
        hand.startTime = datetime.datetime.strptime(m.group('DATETIME'), "%A, %B %d, %H:%M:%S GMT %Y")
        # hand.buttonpos = int(m.group('BUTTON'))  # Not used in this version


    def readPlayerStacks(self, hand):
        """
        Reads player stacks from the hand object.

        Args:
            hand: Hand object containing the handText to be parsed.

        Returns:
            None
        """
        # Find players in handText and add them to the hand object.
        m = self.re_PlayerInfo.finditer(hand.handText)
        for a in m:
            hand.addPlayer(int(a.group('SEAT')), a.group('PNAME'), a.group('CASH'))

        # Check if there are less than two players in the hand.
        # This shouldn't happen, so log a warning if it does.
        if len(hand.players) < 2:
            log.warning(f"Less than 2 players found in hand {hand.handid}.")



    def markStreets(self, hand):
        """
        Marks the streets in the given `hand`.

        Args:
            hand (Hand): The hand to mark the streets in.

        Returns:
            None
        """
        # Search for the streets using regular expressions
        m = re.search(
            r"\*\* Dealing down cards \*\*"
            r"(?P<PREFLOP>.+(?=\*\* Dealing Flop \*\*)|.+)"
            r"(\*\* Dealing Flop \*\*(?P<FLOP> \[ \S\S, \S\S, \S\S \].+(?=\*\* Dealing Turn \*\*)|.+))?"
            r"(\*\* Dealing Turn \*\*(?P<TURN> \[ \S\S \].+(?=\*\* Dealing River \*\*)|.+))?"
            r"(\*\* Dealing River \*\*(?P<RIVER> \[ \S\S \].+))?",
            hand.handText,
            re.DOTALL,
        )

        # Add the streets to the hand
        hand.addStreets(m)

            

    def readCommunityCards(self, hand, street):
        """
        Reads the community cards of a given street and adds them to the hand object.

        Args:
        - hand: the hand object to which the community cards will be added
        - street: the current street of the hand

        Returns:
        - None
        """

        # Check if the current street has community cards
        if street in ('FLOP','TURN','RIVER'):

            # Find the community cards using regex
            m = self.re_Board.search(hand.streets[street])

            # Split the cards into a list and add them to the hand object
            hand.setCommunityCards(street, m.group('CARDS').split(', '))

    def readBlinds(self, hand):
        """
        Reads the blinds from the given hand and adds them to the Hand object.

        :param hand: Hand object to add the blinds to.
        """
        try:
            m = self.re_PostSB.search(hand.handText)
            hand.addBlind(m.group('PNAME'), 'small blind', m.group('SB'))
        except Exception:
            hand.addBlind(None, None, None)
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'big blind', a.group('BB'))
        for a in self.re_PostBoth.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'small & big blinds', a.group('SBBB'))


    def readAntes(self, hand):
        """
        Read the antes from the given hand and add them to the hand.

        Args:
        hand (Hand): the hand to read the antes from.

        """
        # Find all the antes in the hand text and iterate through them
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            # Add the ante for the player to the hand
            log.debug(f"hand.addAnte({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(player.group('PNAME'), player.group('ANTE'))


    def readAntes(self, hand):
        """
        Read the antes from the given hand and add them to the hand.

        Args:
        hand (Hand): the hand to read the antes from.

        """
        # Find all the antes in the hand text and iterate through them
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            # Add the ante for the player to the hand
            log.debug(f"hand.addAnte({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(player.group('PNAME'), player.group('ANTE'))


    def readButton(self, hand):
        """
        Reads the button position from the hand text using a regular expression and sets it in the hand object.

        Args:
            hand (Hand): The hand object to set the button position in.

        Returns:
            None
        """
        hand.buttonpos = int(self.re_Button.search(hand.handText).group('BUTTON'))


    def readHoleCards(self, hand):
        """
        Extracts the hole cards from the hand object for each street.

        Args:
            hand (Hand): Hand object to extract hole cards.

        Returns:
            None
        """
        # Streets PREFLOP, PREDRAW, and THIRD are special cases because
        # we need to grab hero's cards
        for street in ('PREFLOP', 'DEAL'):
            if street in list(hand.streets.keys()):
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group('PNAME')
                    newcards = [c.strip() for c in found.group('CARDS').split(',')]
                    hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)

    def readStudPlayerCards(self, hand, street):
        """Reads the cards of a player in a Stud poker game.

        Args:
            hand (list): The current hand of the player.
            street (str): The current street of the game.

        Returns:
            None
        """
        # Read the cards of the player and add them to their hand
        # ...
        pass


    def readAction(self, hand, street):
        """
        Reads the actions taken on a given street and updates the hand accordingly.

        Args:
            hand (Hand): The hand object to update.
            street (int): The current street being read.

        Returns:
            None
        """
        # Find all actions in the current street
        m = self.re_Action.finditer(hand.streets[street])

        # Iterate over each action found
        for action in m:
            # Check the type of action and update the hand accordingly
            if action.group('ATYPE') == 'folds':
                hand.addFold(street, action.group('PNAME'))
            elif action.group('ATYPE') == 'checks':
                hand.addCheck(street, action.group('PNAME'))
            elif action.group('ATYPE') == 'calls':
                hand.addCall(street, action.group('PNAME'), action.group('BET'))
            elif action.group('ATYPE') == 'bets':
                hand.addBet(street, action.group('PNAME'), action.group('BET'))
            elif action.group('ATYPE') == 'raises to':
                hand.addRaiseTo(street, action.group('PNAME'), action.group('BET'))
            else:
                # If the action type is not recognized, log a debug message
                log.debug(
                    ("DEBUG:") +
                    " " +
                    f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'"
                )


    def readShowdownActions(self, hand):
        """
        Reads the showdown actions from the hand text and adds the shown cards to the hand object.

        Args:
            hand (Hand): The hand object to add the shown cards to.
        """
        # Find all the showdown actions in the hand text using a regular expression
        for shows in self.re_ShowdownAction.finditer(hand.handText):
            # Extract the cards and player name from the regex match
            cards = shows.group('CARDS')
            playerName = shows.group('PNAME')

            # Split the cards string into a list of individual cards
            cards = cards.split(', ')

            # Add the shown cards to the hand object
            hand.addShownCards(cards, playerName)

    def readCollectPot(self, hand):
        """
        Reads the collect pot information from the given hand text and adds it to the hand object.

        Args:
            hand (Hand): The hand object to which the collect pot information should be added.

        Returns:
            None
        """
        # Find all instances of collect pot information in the hand text.
        for m in self.re_CollectPot.finditer(hand.handText):
            # Add the collect pot information to the hand object.
            hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT'))


    def readShownCards(self, hand):
        """
        Reads the shown cards from the hand's text and adds them to the hand's shown cards list.

        Args:
            self: The Game object.
            hand: The Hand object.

        Returns:
            None.
        """
        # Find all shown cards in the hand's text.
        for m in self.re_ShownCards.finditer(hand.handText):
            # If shown cards are found.
            if m.group('CARDS') is not None:
                # Split the cards into a list.
                cards = m.group('CARDS')
                cards = cards.split(', ')
                # Add the shown cards to the hand object.
                hand.addShownCards(cards=None, player=m.group('PNAME'), holeandboard=cards)

