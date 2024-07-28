#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2008-2013, Carl Gherardi
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
import re
import datetime
import logging
from HandHistoryConverter import *
from decimal_wrapper import Decimal

# Set up debug logging
logging.basicConfig(level=logging.DEBUG)

# SealsWithClubs HH Format

class SealsWithClubs(HandHistoryConverter):

    # Class Variables

    sitename = "SealsWithClubs"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId   = 23 # Needs to match id entry in Sites database
    substitutions = {
                           'PLYR': r'(?P<PNAME>\w+)',
                          'BRKTS': r'(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\) )?',
                    }

    limits = { "NL":'nl',"No Limit":'nl', 'PL': 'pl', 'Limit':'fl', 'Fixed Limit':'fl', 'Pot Limit':'pl' }
    games = {                          # base, category
                              "Hold'em" : ('hold','holdem'),
                                'Omaha' : ('hold','omahahi'),
                          'Omaha Hi-Lo' : ('hold','omahahilo'),
                          "Short Deck Hold'em" : ('hold','6_holdem'),
                          'Omaha 5 Cards' : ('hold','5_omahahi')
               }

    # Static regexes
    re_GameInfo = re.compile(r"""SwCPoker\sHand\s*\#(?P<HID>\d+):\s((Tournament|Cashgame|sitngo)\s\(((?P<TABLE2>.*?))\)\#(?P<TOURNO>\d+),\s(?P<BUYIN>(?P<BIAMT>\d+(\.\d+)?))\+(?P<BIRAKE>\d+(\.\d+)?)\s|\s)(?P<GAME>(Hold\'em|Omaha|Omaha\s5\sCards|Short\sDeck\sHold\'em))\s(?P<LIMIT>(NL|Fixed\sLimit|PL|Limit|Pot\sLimit|No\sLimit))\s((-\sLevel\s\w+\s)|)\((?P<SB>\d+(\.\d+)?(\,\d+)?)/(?P<BB>\d+(\.\d+)?(\,\d+)?)\)\s-\s(?P<DATETIME>.*)""",re.VERBOSE)

    re_PlayerInfo   = re.compile(r"""^Seat\s+(?P<SEAT>\d+):\s+(?P<PNAME>\w+)\s+\((?P<CASH>\d{1,3}(,\d{3})*(\.\d+)?)\sin\schips\)""" , re.MULTILINE|re.VERBOSE)

    re_HandInfo = re.compile(r"""^Table\s'(?P<TABLE>.*?)'\(\d+\)\s(?P<MAX>\d+)-max\s(?:\(Real Money\)\s)?Seat\s\#\d+\sis\sthe\sbutton""",re.MULTILINE)

    re_Identify     = re.compile(r"SwCPoker\sHand\s")
    re_SplitHands   = re.compile('(?:\s?\n){2,}')
    re_ButtonName   = re.compile(r"""^(?P<BUTTONNAME>.*) has the dealer button""",re.MULTILINE)
    re_ButtonPos   = re.compile(r"""Seat\s+\#(?P<BUTTON>\d+)\sis\sthe\sbutton""",re.MULTILINE)
    re_Board        = re.compile(r"\[(?P<CARDS>.+)\]")
    re_DateTime     = re.compile(r"""(?P<Y>\d{4})-(?P<M>\d{2})-(?P<D>\d{2})[\-\s]+(?P<H>\d+):(?P<MIN>\d+):(?P<S>\d+)""", re.MULTILINE)

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB           = re.compile(r"^%(PLYR)s: posts small blind (?P<SB>[.0-9]+)" %  substitutions, re.MULTILINE)
    re_PostBB           = re.compile(r"^%(PLYR)s: posts big blind (?P<BB>[.0-9]+)" %  substitutions, re.MULTILINE)
    re_Antes            = re.compile(r"^%(PLYR)s: posts the ante (?P<ANTE>[.0-9]+)" % substitutions, re.MULTILINE)
    re_PostBoth         = re.compile(r"^%(PLYR)s: posts small \& big blind (?P<SBBB>[.0-9]+)" %  substitutions, re.MULTILINE)
    re_HeroCards        = re.compile(r"^Dealt to %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % substitutions, re.MULTILINE)
    re_Action = re.compile(r"""^%(PLYR)s:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat)(?:\s(?P<BET>\d{1,3}(,\d{3})*(\.\d+)?))?(?:\sto\s(?P<POT>\d{1,3}(,\d{3})*(\.\d+)?))?\s*$""" % substitutions, re.MULTILINE|re.VERBOSE)

    re_ShowdownAction   = re.compile(r"^(?P<PNAME>\w+): (shows \[(?P<CARDS>.*)\]\s\((?P<FHAND>.*?)\)|doesn't show hand|mucks hand)", re.MULTILINE)
    re_CollectPot       = re.compile(r"^Seat (?P<SEAT>[0-9]+): %(PLYR)s ((%(BRKTS)s(((((?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \((?P<POT>[.\d]+)\)) with (?P<STRING>.+?)(\s\sand\s(won\s\([.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$)|collected\s\((?P<POT2>[.\d]+)\)))|folded ((on the (Flop|Turn|River))|before Flop)))|folded before Flop \(didn't bet\))" %  substitutions, re.MULTILINE)
    re_Cancelled        = re.compile('Hand\scancelled', re.MULTILINE)
    re_Uncalled         = re.compile('Uncalled bet \((?P<BET>[,.\d]+)\) returned to %(PLYR)s'  %  substitutions, re.MULTILINE)    
    re_Flop             = re.compile('\*\*\* FLOP \*\*\*')
    re_Turn             = re.compile('\*\*\* TURN \*\*\*')
    re_River            = re.compile('\*\*\* RIVER \*\*\*')
    re_rake = re.compile('Total pot (?P<TOTALPOT>\\d{1,3}(,\\d{3})*(\\.\\d+)?)\\s\\|\\sRake\\s(?P<RAKE>\\d{1,3}(,\\d{3})*(\\.\\d+)?)', re.MULTILINE)
    re_Mucked           = re.compile("^%(PLYR)s: mucks hand" %  substitutions, re.MULTILINE)

    def compilePlayerRegexs(self, hand):
        """
        Compiles regular expressions to match player names and cards shown in a poker hand.

        Args:
        - self: instance of the class containing the method
        - hand: a Hand object representing the poker hand

        Returns: None
        """
        logging.debug("Compiling player regexes")
        # Get a set of player names in the hand
        players = {player[1] for player in hand.players}

        # Check if the set of players is a subset of compiledPlayers
        if not players <= self.compiledPlayers:
            # If not, update compiledPlayers
            self.compiledPlayers = players

            # Compile a regular expression to match the player's name
            # The regular expression is of the form "(?P<PNAME>player1|player2|player3)"
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"

            # Define substitutions for the regular expressions
            subst = {
                'PLYR': player_re,
                'BRKTS': r'(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\) )?',
                'CUR': u"(\$|\xe2\x82\xac|\u20ac||\£|)"
            }

            # Compile a regular expression to match the cards dealt to the player
            # The regular expression is of the form "^Dealt to %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])"
            self.re_HeroCards = re.compile(r"^Dealt to %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % subst, re.MULTILINE)

            # Compile a regular expression to match the cards shown by the player
            # The regular expression is of the form "^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \(%(CUR)s(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$"
            self.re_ShownCards = re.compile("^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \(%(CUR)s(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$" % subst, re.MULTILINE)

    def readSupportedGames(self):
        logging.debug("Reading supported games")
        return [
                ["ring", "hold", "fl"],
                ["ring", "hold", "nl"],
                ["ring", "hold", "pl"],

                ["ring", "stud", "fl"],

                ["ring", "draw", "fl"],
                ["ring", "draw", "pl"],
                ["ring", "draw", "nl"],
                
                ["tour", "hold", "fl"],
                ["tour", "hold", "nl"],
                ["tour", "hold", "pl"],   
                             
                ["tour", "stud", "fl"],
                
                ["tour", "draw", "fl"],
                ["tour", "draw", "pl"],
                ["tour", "draw", "nl"],
                ["tour", "hold", "6_holdem"],
               ]

    def determineGameType(self, handText):
        logging.debug("Determining game type")
        info = {}
        m = self.re_GameInfo.search(handText)
        if not m:
            tmp = handText[:200]
            logging.error(f"SealsWithClubsToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        logging.debug(f"Matched groups: {mg}")
        if 'LIMIT' in mg:
            info['limitType'] = self.limits[mg['LIMIT']]
        if 'GAME' in mg:
            (info['base'], info['category']) = self.games[mg['GAME']]
        if 'SB' in mg:
            if ',' in mg['SB']:
                mg['SB'] = mg['SB'].replace(',', '')
            info['sb'] = mg['SB']
        if 'BB' in mg:
            if ',' in mg['BB']:
                mg['BB'] = mg['BB'].replace(',', '')
            info['bb'] = mg['BB']
        if 'CURRENCY' in mg and mg['CURRENCY'] is not None:
            info['currency'] = self.currencies[mg['CURRENCY']]

        info['type'] = 'ring' if 'TOURNO' in mg and mg['TOURNO'] is None else 'tour'
        if info['type'] == 'ring':
            info['currency'] = 'mBTC'
        else:
            info['currency'] = 'mBTC'

        if info['limitType'] == 'fl' and info['bb'] is not None:
            info['sb'] = str((Decimal(mg['SB'])/2).quantize(Decimal("0.01")))
            info['bb'] = str(Decimal(mg['SB']).quantize(Decimal("0.01")))

        logging.debug(f"Game info: {info}")
        return info

    def readHandInfo(self, hand):
        logging.debug("Reading hand info")
        info = {}
        m = self.re_HandInfo.search(hand.handText, re.DOTALL)
        m2 = self.re_GameInfo.search(hand.handText)
        
        if m is None or m2 is None:
            tmp = hand.handText[:200]
            logging.error(f"SealsWithClubsToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError

        info.update(m.groupdict())
        logging.debug(f"HandInfo groups: {m.groupdict()}")
        info.update(m2.groupdict())
        logging.debug(f"GameInfo groups: {m2.groupdict()}")

        if info['TOURNO'] is not None:
            words = m['TABLE'].split()
            new_string = words[1]
            info['TABLE'] = f"{m2['TABLE2']} {new_string}"
            logging.debug(f"Table name updated to: {info['TABLE']}")
            hand.tablename = f"{info['TABLE']}"
        else:
            # for cash game
            info['TABLE'] = m['TABLE']
            logging.debug(f"Table name for cash game: {info['TABLE']}")
            hand.tablename = f"{info['TABLE']}"

        for key in info:
            if key == 'DATETIME':
                m1 = self.re_DateTime.finditer(info[key])
                datetimestr = "2000-01-01 00:00:00"
                for a in m1:
                    datetimestr = "%s-%s-%s %s:%s:%s" % (a.group('Y'), a.group('M'), a.group('D'), a.group('H'), a.group('MIN'), a.group('S'))
                hand.startTime = datetime.datetime.strptime(datetimestr, "%Y-%m-%d %H:%M:%S")
                hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")
            if key == 'HID':
                hand.handid = info[key]
                logging.debug(f"Hand ID: {hand.handid}")
            if key == 'TOURNO':
                hand.tourNo = info[key]
            if key == 'BUYIN':
                if hand.tourNo is not None:
                    if info[key] == 'Freeroll':
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "FREE"
                    else:
                        hand.buyinCurrency = "mBTC"
                        hand.buyin = int(100 * Decimal(info['BIAMT']))
                        hand.fee = int(100 * Decimal(info['BIRAKE']))
            if key == 'LEVEL':
                hand.level = info[key]
            if key == 'MAX' and info[key] is not None:
                hand.maxseats = int(info[key])
            if key == 'HU' and info[key] is not None:
                hand.maxseats = 2

        logging.debug(f"Final hand info: {info}")

        if not hand.handid:
            logging.error("Hand ID not found, unable to process hand.")
            raise FpdbParseError("Hand ID not found.")
        
        if self.re_Cancelled.search(hand.handText):
            raise FpdbHandPartial(f"Hand '{hand.handid}' was cancelled.")


    def readButton(self, hand):
        logging.debug("Reading button position")
        if m := self.re_ButtonPos.search(hand.handText):
            hand.buttonpos = int(m.group('BUTTON'))
        else:
            logging.debug('readButton: not found')

    def readPlayerStacks(self, hand):
        handsplit = hand.handText.split('*** SUMMARY ***')
        if len(handsplit) != 2:
            raise FpdbHandPartial(
                f"Hand is not cleanly split into pre and post Summary {hand.handid}."
            )
        pre, post = handsplit
        m = self.re_PlayerInfo.finditer(pre)
        plist = {}

        for a in m:
            if plist.get(a.group('PNAME')) is None:
                hand.addPlayer(int(a.group('SEAT')), a.group('PNAME'), a.group('CASH'))
                plist[a.group('PNAME')] = [int(a.group('SEAT')), a.group('CASH')]

        if len(plist.keys()) < 2:
            raise FpdbHandPartial(f"Less than 2 players in hand! {hand.handid}.")

    def markStreets(self, hand):
        logging.debug("Marking streets")
        if self.re_Turn.search(hand.handText) and not self.re_Flop.search(hand.handText):
            raise FpdbParseError
        if self.re_River.search(hand.handText) and not self.re_Turn.search(hand.handText):
            raise FpdbParseError

        m = re.search(r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>[\s\S]*?(?=\*\*\* FLOP \*\*\*)|.+)"
                      r"(\*\*\* FLOP \*\*\*(?P<FLOP>[\s\S]*?(?=\*\*\* TURN \*\*\*)|.+))?"
                      r"(\*\*\* TURN \*\*\*(?P<TURN>[\s\S]*?(?=\*\*\* RIVER \*\*\*)|.+))?"
                      r"(\*\*\* RIVER \*\*\*(?P<RIVER>[\s\S]*?(?=\*\*\* SHOW DOWN \*\*\*)|.+))?", hand.handText,re.DOTALL)

        if not m:
            raise FpdbParseError

        hand.addStreets(m)

    def readCommunityCards(self, hand, street):
        logging.debug(f"Reading community cards for street: {street}")
        if street in ('FLOP','TURN','RIVER'):
            m = self.re_Board.search(hand.streets[street])
            hand.setCommunityCards(street, m.group('CARDS').split(' '))

    def readAntes(self, hand):
        logging.debug("Reading antes")
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            logging.debug(f"hand.addAnte({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(player.group('PNAME'), player.group('ANTE'))

    def readBlinds(self, hand):
        logging.debug("Reading blinds")
        liveBlind = True
        for a in self.re_PostSB.finditer(hand.handText):
            if liveBlind:
                hand.addBlind(a.group('PNAME'), 'small blind', a.group('SB'))
                liveBlind = False
            else:
                hand.addBlind(a.group('PNAME'), 'secondsb', a.group('SB'))
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'big blind', a.group('BB'))
        for a in self.re_PostBoth.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'both', a.group('SBBB'))

    def readHoleCards(self, hand):
        logging.debug("Reading hole cards")
        for street in ('PREFLOP', 'DEAL'):
            if street in list(hand.streets.keys()):
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group('PNAME')
                    newcards = found.group('NEWCARDS').split(' ')
                    hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)

    def readAction(self, hand, street):
        logging.debug(f"Reading actions for street: {street}")
        m = self.re_Action.finditer(hand.streets[street])
        for action in m:
            acts = action.groupdict()
            logging.debug(f"Action details: {acts}")
            if action.group('ATYPE') == ' folds':
                hand.addFold(street, action.group('PNAME'))
            elif action.group('ATYPE') == ' checks':
                hand.addCheck(street, action.group('PNAME'))
            elif action.group('ATYPE') == ' calls':
                hand.addCall(street, action.group('PNAME'), action.group('BET'))
            elif action.group('ATYPE') == ' raises':
                hand.addRaiseTo(street, action.group('PNAME'), action.group('BET'))
            elif action.group('ATYPE') == ' bets':
                hand.addBet(street, action.group('PNAME'), action.group('BET'))
            else:
                logging.debug(f"DEBUG: Unimplemented {action.group('ATYPE')}: '{action.group('PNAME')}'")

    def readShownCards(self, hand):
        logging.debug("Reading shown cards")
        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group('CARDS') is not None:
                cards = m.group('CARDS').split(' ')
                string = m.group('STRING')
                if m.group('STRING2'):
                    string += '|' + m.group('STRING2')
                (shown, mucked) = (False, False)
                if m.group('SHOWED') == "showed":
                    shown = True
                elif m.group('SHOWED') == "mucked":
                    mucked = True
                hand.addShownCards(cards=cards, player=m.group('PNAME'), shown=shown, mucked=mucked, string=string)

    def readShowdownActions(self, hand):
        logging.debug("Reading showdown actions")
        for shows in self.re_ShowdownAction.finditer(hand.handText):
            if shows.group('CARDS') is not None:
                cards = shows.group('CARDS').split(' ')
                hand.addShownCards(cards, shows.group('PNAME'))
        for mucks in self.re_CollectPot.finditer(hand.handText):
            if mucks.group('SHOWED') == "mucked" and mucks.group('CARDS') is not None:
                cards = mucks.group('CARDS').split(' ')
                hand.addShownCards(cards, mucks.group('PNAME'))

    def readCollectPot(self, hand):
        logging.debug("Reading collected pot")
        if self.re_Uncalled.search(hand.handText) is None:
            rake = Decimal(0)
            totalpot = Decimal(0)
            for m in self.re_CollectPot.finditer(hand.handText):
                if m.group('POT') is not None:
                    hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT'))
                elif m.group('POT2') is not None:
                    hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT2'))
            if self.re_rake.search(hand.handText) is not None:
                for m in self.re_rake.finditer(hand.handText):
                    rake = rake + Decimal(m.group('RAKE'))
                    if ',' in m.group('TOTALPOT'):
                        newtotalpot = m.group('TOTALPOT').replace(',', '')
                        totalpot = totalpot + Decimal(newtotalpot)
                    else:
                        totalpot = totalpot + Decimal(m.group('TOTALPOT'))
            if hand.rake is None:
                hand.rake = rake            
            elif hand.rakes.get('rake'):
                hand.rakes['rake'] += rake
            else:
                hand.rakes['rake'] = rake
            hand.totalpot = totalpot
        else:
            hand.setUncalledBets(True)
            rake = Decimal(0)
            totalpot = Decimal(0)
            if self.re_rake.search(hand.handText) is not None:
                for m in self.re_rake.finditer(hand.handText):
                    rake = rake + Decimal(m.group('RAKE'))
                    if ',' in m.group('TOTALPOT'):
                        newtotalpot = m.group('TOTALPOT').replace(',', '')
                        totalpot = totalpot + Decimal(newtotalpot)
                    else:
                        totalpot = totalpot + Decimal(m.group('TOTALPOT'))
            if hand.rake is None:
                hand.rake = rake            
            elif hand.rakes.get('rake'):
                hand.rakes['rake'] += rake
            else:
                hand.rakes['rake'] = rake
            hand.totalpot = totalpot
            total = rake + totalpot
            for m in self.re_CollectPot.finditer(hand.handText):
                if m.group('POT') is not None:
                    if totalpot == Decimal(m.group('POT')):
                        uncalledpot = Decimal(0)
                        for m in self.re_Uncalled.finditer(hand.handText):
                            if ',' in m.group('BET'):
                                newbet = m.group('BET').replace(',', '')
                                uncalledpot = uncalledpot + Decimal(newbet)
                            else:
                                uncalledpot = uncalledpot + Decimal(m.group('BET'))
                        collectpot = totalpot
                        total = total + uncalledpot
                        hand.totalpot = total
                        hand.addCollectPot(player=m.group('PNAME'), pot=collectpot)
                    else:
                        hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT'))
                elif m.group('POT2') is not None:
                    if totalpot == Decimal(m.group('POT2')):
                        uncalledpot = Decimal(0)
                        for m in self.re_Uncalled.finditer(hand.handText):
                            if ',' in m.group('BET'):
                                newbet = m.group('BET').replace(',', '')
                                uncalledpot = uncalledpot + Decimal(newbet)
                            else:
                                uncalledpot = uncalledpot + Decimal(m.group('BET'))
                        collectpot = totalpot
                        total = total + uncalledpot
                        hand.totalpot = total
                        hand.addCollectPot(player=m.group('PNAME'), pot=collectpot)
                    else:
                        hand.addCollectPot(player=m.group('PNAME'), pot=m.group('POT2'))

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        logging.debug(f"Seals.getTableTitleRe: table_name='{table_name}' tournament='{tournament}' table_number='{table_number}'")
        
        if not table_name:
            logging.debug("Seals.getTableTitleRe: no valid input provided")
            return ""

        logging.debug(f"Initial table_name: {table_name}")

        regex = f"{table_name}"
        words = regex.split()

        if type in ["tour", "ring"]:
            if len(words) > 2:
                regex = ' '.join(words[1:-1])
            logging.debug(f"Seals.getTableTitleRe: regex after processing='{regex}'")
            return regex

        if type == "tour":
            match = re.match(r"(\d+)\s(.+)\s(\[\d+\sChips\])\s(\d+)", table_name)
            if match:
                tournament_id, game_type, chips_info, table_number = match.groups()
                regex = f"{tournament_id} {game_type} {chips_info} {table_number}"
                logging.debug(f"Seals.getTableTitleRe: regex for tour='{regex}'")
                return regex

        regex = f"{table_name}"
        logging.debug(f"Seals.getTableTitleRe: regex='{regex}'")
        return regex
