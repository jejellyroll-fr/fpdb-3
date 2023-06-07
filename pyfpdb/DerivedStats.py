#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

#fpdb modules
from __future__ import division

from past.utils import old_div
#import L10n
#_ = L10n.get_translation()
import Card
from decimal_wrapper import Decimal, ROUND_DOWN

import sys
import logging
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("parser")

try:
    from pokereval import PokerEval
    pokereval = PokerEval()
except Exception:
    pokereval = None
    
def _buildStatsInitializer():
    """
    Creates and returns a dictionary with initial values for various statistics.

    Returns:
        A dictionary with initial values for various statistics.
    """
    # Create dictionary with initial values for various statistics.
    # All stud street4 need this when importing holdem
    init = {
        'effStack': 0,
        'startBounty': None,
        'endBounty': None,
        'common': 0,
        'committed': 0,
        'winnings': 0,
        'rake': 0,
        'rakeDealt': 0,
        'rakeContributed': 0,
        'rakeWeighted': 0,
        'totalProfit': 0,
        'allInEV': 0,
        'showdownWinnings': 0,
        'nonShowdownWinnings': 0,
        'sawShowdown': False,
        'showed': False,
        'wonAtSD': False,
        'startCards': 170,
        'handString': None,
        'position': 9,
        'street0CalledRaiseChance': 0,
        'street0CalledRaiseDone': 0,
        'street0VPIChance': True,
        'street0VPI': False,
        'street0AggrChance': True,
        'street0_2BChance': False,
        'street0_2BDone': False,
        'street0_3BChance': False,
        'street0_3BDone': False,
        'street0_4BChance': False,
        'street0_4BDone': False,
        'street0_C4BChance': False,
        'street0_C4BDone': False,
        'street0_FoldTo2BChance': False,
        'street0_FoldTo2BDone': False,
        'street0_FoldTo3BChance': False,
        'street0_FoldTo3BDone': False,
        'street0_FoldTo4BChance': False,
        'street0_FoldTo4BDone': False,
        'street0_SqueezeChance': False,
        'street0_SqueezeDone': False,
        'stealChance': False,
        'stealDone': False,
        'success_Steal': False,
        'raiseToStealChance': False,
        'raiseToStealDone': False,
        'raiseFirstInChance': False,
        'raisedFirstIn': False,
        'foldBbToStealChance': False,
        'foldSbToStealChance': False,
        'foldedSbToSteal': False,
        'foldedBbToSteal': False,
        'tourneyTypeId': None,
        'street1Seen': False,
        'street2Seen': False,
        'street3Seen': False,
        'street4Seen': False,
        'otherRaisedStreet0': False,
        'foldToOtherRaisedStreet0': False,
        'wentAllIn': False,
    }
    # Initialize variables for each street.
    for i in range(5):
        init['street%dCalls' % i] = 0
        init['street%dBets' % i] = 0
        init['street%dRaises' % i] = 0
        init['street%dAggr' % i] = False        
        init['street%dInPosition' % i] = False
        init['street%dFirstToAct' % i] = False
        init['street%dAllIn' % i] = False

    # Initialize variables for discards on streets 1-3.
    for i in range(1,4):
        init['street%dDiscards' % i] = 0

    for i in range(1,5):
        init['street%dCBChance' %i]             = False
        init['street%dCBDone' %i]               = False
        init['street%dCheckCallRaiseChance' %i] = False
        init['street%dCheckCallDone' %i]        = False
        init['street%dCheckRaiseDone' %i]       = False
        init['otherRaisedStreet%d' %i]          = False
        init['foldToOtherRaisedStreet%d' %i]    = False
        init['foldToStreet%dCBChance' %i]       = False
        init['foldToStreet%dCBDone' %i]         = False
        init['wonWhenSeenStreet%d' %i]          = False
    return init

_INIT_STATS = _buildStatsInitializer()

class DerivedStats:
    def __init__(self):
        """
        Initializes a new DerivedStats object.
        """
        self.hands = {}  # Dictionary of hand histories.
        self.handsplayers = {}  # Dictionary of players in each hand.
        self.handsactions = {}  # Dictionary of actions in each hand.
        self.handsstove = []  # List of hands and their corresponding showdown results.
        self.handspots = []  # List of hands and the spots players were in at the end of the hand.


    def getStats(self, hand):
        """
        Calculates the statistics of a poker hand.

        Args:
            hand (PokerHand): An instance of the PokerHand class representing the hand to calculate statistics for.

        Returns:
            None
        """
        # Initialize the stats dictionary for each player in the hand
        for player in hand.players:
            self.handsplayers[player[1]] = _INIT_STATS.copy()

        # Assemble the hands for each player
        self.assembleHands(hand)
        # Assemble the hands and board for each player
        self.assembleHandsPlayers(hand)
        # Assemble the actions for each player
        self.assembleHandsActions(hand)

        # If pokereval is installed and the game type is valid, assemble the hands for the stove
        if pokereval and hand.gametype['category'] in Card.games:
            self.assembleHandsStove(hand)
            # Assemble the pots for each player
            self.assembleHandsPots(hand)

    def getHands(self):
        """
        Returns the hands of the class instance.
        """
        return self.hands

    def getHandsPlayers(self):
        """Returns the hands players"""
        return self.handsplayers

    def getHandsActions(self):
        """
        Returns the hands actions.

        Returns:
        list: A list of hand actions.
        """
        return self.handsactions
    
    def getHandsStove(self):
        """
        Returns the state of the hands stove.
        """
        return self.handsstove
    
    def getHandsPots(self):
        """Get the hand spots."""
        return self.handspots

    def assembleHands(self, hand):
        """
        Assemble hand data for insertion into the database

        Args:
            hand (Hand): Hand object to assemble data from

        Returns:
            None
        """

        # Set initial hand data
        self.hands['tableName'] = hand.tablename
        self.hands['siteHandNo'] = hand.handid
        self.hands['gametypeId'] = None  # Leave None, handled later after checking db
        self.hands['sessionId'] = None  # Leave None, added later if caching sessions
        self.hands['gameId'] = None  # Leave None, added later if caching sessions
        self.hands['startTime'] = hand.startTime  # format this!
        self.hands['importTime'] = None
        self.hands['seats'] = self.countPlayers(hand)
        self.hands['maxPosition'] = -1
        #self.hands['maxSeats']      = hand.maxseats
        self.hands['texture'] = None  # No calculation done for this yet.
        self.hands['tourneyId'] = hand.tourneyId

        # Set hero seat
        self.hands['heroSeat'] = 0
        for player in hand.players:
            if hand.hero == player[1]:
                self.hands['heroSeat'] = player[0]

        # Set board cards
        boardcards = []
        if hand.board.get('FLOPET') != None:
            boardcards += hand.board.get('FLOPET')
        for street in hand.communityStreets:
            boardcards += hand.board[street]
        boardcards += [u'0x', u'0x', u'0x', u'0x', u'0x']
        cards = [Card.encodeCard(c) for c in boardcards[:5]]
        self.hands['boardcard1'] = cards[0]
        self.hands['boardcard2'] = cards[1]
        self.hands['boardcard3'] = cards[2]
        self.hands['boardcard4'] = cards[3]
        self.hands['boardcard5'] = cards[4]

        # Set boards
        self.hands['boards'] = []
        self.hands['runItTwice'] = False
        for i in range(hand.runItTimes):
            boardcards = []
            for street in hand.communityStreets:
                boardId = i+1
                street_i = street + str(boardId)
                if street_i in hand.board:
                    boardcards += hand.board[street_i]
            if hand.gametype['split']:
                boardcards = boardcards + [u'0x', u'0x', u'0x', u'0x', u'0x']
                cards = [Card.encodeCard(c) for c in boardcards[:5]]
            else:
                self.hands['runItTwice'] = True
                boardcards = [u'0x', u'0x', u'0x', u'0x', u'0x'] + boardcards
                cards = [Card.encodeCard(c) for c in boardcards[-5:]]
            self.hands['boards'] += [[boardId] + cards]

        # Set pot data
        #print "DEBUG: %s self.getStreetTotals = (%s, %s, %s, %s, %s, %s)" %  tuple([hand.handid] + list(hand.getStreetTotals()))
        totals = hand.getStreetTotals()
        totals = [int(100*i) for i in totals]
        self.hands['street0Pot']  = totals[0]
        self.hands['street1Pot']  = totals[1]
        self.hands['street2Pot']  = totals[2]
        self.hands['street3Pot']  = totals[3]
        self.hands['street4Pot']  = totals[4]
        self.hands['finalPot'] = totals[5]

        self.vpip(hand) # Gives playersVpi (num of players vpip)
        #print "DEBUG: vpip: %s" %(self.hands['playersVpi'])
        self.playersAtStreetX(hand) # Gives playersAtStreet1..4 and Showdown
        #print "DEBUG: playersAtStreet 1:'%s' 2:'%s' 3:'%s' 4:'%s'" %(self.hands['playersAtStreet1'],self.hands['playersAtStreet2'],self.hands['playersAtStreet3'],self.hands['playersAtStreet4'])
        self.streetXRaises(hand)

    def assembleHandsPlayers(self, hand):
        """
        Assembles player stats for a given hand.

        Args:
            hand: The hand object for which to assemble player stats.

        Returns:
            None
        """
        #street0VPI/vpip already called in Hand
        # sawShowdown is calculated in playersAtStreetX, as that calculation gives us a convenient list of names

        #hand.players = [[seat, name, chips],[seat, name, chips]]
        for player in hand.players:
            player_name = player[1]
            player_stats = self.handsplayers.get(player_name)
            player_stats['seatNo'] = player[0]
            player_stats['startCash'] = int(100 * Decimal(player[2]))
            if player[4] != None:
                player_stats['startBounty'] = int(100 * Decimal(player[4]))
                player_stats['endBounty'] = int(100 * Decimal(player[4]))
            if player_name in hand.endBounty:
                player_stats['endBounty'] = int(hand.endBounty.get(player_name))
            player_stats['sitout'] = player_name in hand.sitout
            if hand.gametype["type"]=="tour":
                player_stats['tourneyTypeId']=hand.tourneyTypeId
                player_stats['tourneysPlayersId'] = hand.tourneysPlayersIds[player[1]]
            else:
                player_stats['tourneysPlayersId'] = None
            if player_name in hand.shown:
                player_stats['showed'] = True

        #### seen now processed in playersAtStreetX()
        # XXX: enumerate(list, start=x) is python 2.6 syntax; 'start'
        #for i, street in enumerate(hand.actionStreets[2:], start=1):
        #for i, street in enumerate(hand.actionStreets[2:]):
        #    self.seen(self.hand, i+1)

        for i, street in enumerate(hand.actionStreets[1:]):
            self.aggr(hand, i)
            self.calls(hand, i)
            self.bets(hand, i)
            self.raises(hand, i)
            if i>0:
                self.folds(hand, i)

        # Winnings is a non-negative value of money collected from the pot, which already includes the
        # rake taken out. hand.collectees is Decimal, database requires cents
        num_collectees, i = len(hand.collectees), 0
        even_split = old_div(hand.totalpot, num_collectees) if num_collectees > 0 else 0
        unraked = [c for c in list(hand.collectees.values()) if even_split == c]
        for player, winnings in list(hand.collectees.items()):
            collectee_stats = self.handsplayers.get(player)
            collectee_stats['winnings'] = int(100 * winnings)
            # Splits evenly on split pots and gives remainder to first player
            # Gets overwritten when calculating multi-way pots in assembleHandsPots
            if num_collectees == 0:
                collectee_stats['rake'] = 0
            elif not unraked:
                rake = old_div(int(100 * hand.rake),num_collectees)
                remainder_1, remainder_2 = 0, 0
                if rake > 0 and i==0:
                    leftover = int(100 * hand.rake) - (rake * num_collectees)
                    remainder_1 = int(100 * hand.rake) % rake
                    remainder_2 = leftover if remainder_1 == 0 else 0
                collectee_stats['rake'] = rake + remainder_1 + remainder_2
            else:
                collectee_stats['rake'] = int(100 *(even_split - Decimal(str(winnings))))
            if collectee_stats['street1Seen'] == True:
                collectee_stats['wonWhenSeenStreet1'] = True
            if collectee_stats['street2Seen'] == True:
                collectee_stats['wonWhenSeenStreet2'] = True
            if collectee_stats['street3Seen'] == True:
                collectee_stats['wonWhenSeenStreet3'] = True
            if collectee_stats['street4Seen'] == True:
                collectee_stats['wonWhenSeenStreet4'] = True
            if collectee_stats['sawShowdown'] == True:
                collectee_stats['wonAtSD'] = True
            i+=1

        contributed, i = [], 0
        for player, money_committed in list(hand.pot.committed.items()):
            committed_player_stats = self.handsplayers.get(player)
            paid = (100 * money_committed) + (100*hand.pot.common[player])
            committed_player_stats['common'] = int(100 * hand.pot.common[player])
            committed_player_stats['committed'] = int(100 * money_committed) 
            committed_player_stats['totalProfit'] = int(committed_player_stats['winnings'] - paid)
            committed_player_stats['allInEV'] = committed_player_stats['totalProfit']
            committed_player_stats['rakeDealt'] = 100 * hand.rake/len(hand.players)
            committed_player_stats['rakeWeighted'] = 100 * hand.rake * paid/(100*hand.totalpot) if hand.rake>0 else 0
            if paid > 0: contributed.append(player)
            i+=1

        for i, player in enumerate(contributed):
            self.handsplayers[player]['rakeContributed'] = 100 * hand.rake/len(contributed)

        self.calcCBets(hand)

        # More inner-loop speed hackery.
        encodeCard = Card.encodeCard
        calcStartCards = Card.calcStartCards
        for player in hand.players:
            player_name = player[1]
            hcs = hand.join_holecards(player_name, asList=True)
            hcs = hcs + [u'0x']*18
            #for i, card in enumerate(hcs[:20, 1): #Python 2.6 syntax
            #    self.handsplayers[player[1]]['card%s' % i] = Card.encodeCard(card)
            player_stats = self.handsplayers.get(player_name)
            if player_stats['sawShowdown']:
                player_stats['showdownWinnings'] = player_stats['totalProfit']
            else:
                player_stats['nonShowdownWinnings'] = player_stats['totalProfit']
            for i, card in enumerate(hcs[:20]):
                player_stats['card%d' % (i+1)] = encodeCard(card)
            try:
                player_stats['startCards'] = calcStartCards(hand, player_name)
            except IndexError:
                log.error(
                    f"IndexError: string index out of range {hand.handid} {hand.in_path}"
                )

        self.setPositions(hand)
        self.calcEffectiveStack(hand)
        self.calcCheckCallRaise(hand)
        self.calc34BetStreet0(hand)
        self.calcSteals(hand)
        self.calcCalledRaiseStreet0(hand)
        # Additional stats
        # 3betSB, 3betBB
        # Squeeze, Ratchet?

    def assembleHandsActions(self, hand):
        """
        Assemble hands actions.

        :param hand: the current hand
        """
        k = 0
        for i, street in enumerate(hand.actionStreets):
            for j, act in enumerate(hand.actions[street]):
                k += 1
                self.handsactions[k] = {
                    'amount': 0,
                    'raiseTo': 0,
                    'amountCalled': 0,
                    'numDiscarded': 0,
                    'cardsDiscarded': None,
                    'allIn': False,
                    'player': act[0],
                    'street': i - 1,
                    'actionNo': k,
                    'streetActionNo': j + 1,
                    'actionId': hand.ACTION[act[1]],
                }
                # Set amount if not a discard and has an amount
                if act[1] not in ('discards') and len(act) > 2:
                    self.handsactions[k]['amount'] = int(100 * act[2])
                # Set raiseTo and amountCalled if raise or complete
                if act[1] in ('raises', 'completes'):
                    self.handsactions[k]['raiseTo'] = int(100 * act[3])
                    self.handsactions[k]['amountCalled'] = int(100 * act[4])
                # Set numDiscarded and street discards if discard
                if act[1] in ('discards'):
                    self.handsactions[k]['numDiscarded'] = int(act[2])
                    self.handsplayers[act[0]]['street%dDiscards' %(i-1)] = int(act[2])
                # Set cards discarded if discard and has cards
                if act[1] in ('discards') and len(act) > 3:
                    self.handsactions[k]['cardsDiscarded'] = act[3]
                # Set allIn if more than 3 elements and not a discard
                if len(act) > 3 and act[1] not in ('discards'):
                    self.handsactions[k]['allIn'] = act[-1]
                    if act[-1]: 
                        self.handsplayers[act[0]]['wentAllIn'] = True
                        self.handsplayers[act[0]]['street%dAllIn' %(i-1)] = True

    
    def assembleHandsStove(self, hand):
        """
        Given a hand, assembles the hands stove containing information about the hand's players,
        hole cards, boards, and their respective evaluation.

        Args:
            hand: A Hand object.

        Returns:
            None.
        """

        # Initializing variables
        category = hand.gametype['category']
        holecards, holeplayers, allInStreets = {}, [], hand.allStreets[1:]
        base, evalgame, hilo, streets, last, hrange = Card.games[category]
        hiLoKey = {'h': [('h', 'hi')], 'l': [('l', 'low')], 's': [('h', 'hi'),('l', 'low')], 'r': [('l', 'hi')]}
        boards = self.getBoardsDict(hand, base, streets)

        # Looping through each player in the hand
        for player in hand.players:
            pname = player[1]
            hp = self.handsplayers.get(pname)

            # If it's an evaluation game, evaluate the hole cards for each street
            if evalgame:
                hcs = hand.join_holecards(pname, asList=True)
                holecards[pname] = {'cards': [], 'eq': 0, 'committed': 0}
                holeplayers.append(pname)

                # Looping through each street and evaluating if the player qualifies to see the board
                for street, board in list(boards.items()):
                    streetId = streets[street]
                    streetSeen = hp[f'street{str(streetId)}Seen'] if streetId > 0 else True
                    if ((pname==hand.hero and streetSeen) or (hp['showed'] and streetSeen) or hp['sawShowdown']):

                        # Initializing variables for board evaluation
                        boardId, hl, rankId, value, _cards = 0, 'n', 1, 0, None

                        # Looping through each card in the board and evaluating the cards
                        for n in range(len(board['board'])):
                            streetIdx = -1 if base=='hold' else streetId
                            cards = hcs[hrange[streetIdx][0]:hrange[streetIdx][1]]
                            boardId   = (n + 1) if (len(board['board']) > 1) else n
                            cards    += board['board'][n] if (board['board'][n] and 'omaha' not in evalgame) else []
                            bcards    = board['board'][n] if (board['board'][n] and 'omaha' in evalgame) else []
                            cards     = [str(c) if Card.encodeCardList.get(c) else '0x' for c in cards]
                            bcards    = [str(b) if Card.encodeCardList.get(b) else '0x' for b in bcards]
                            holecards[pname]['hole'] = cards[hrange[streetIdx][0]:hrange[streetIdx][1]]
                            holecards[pname]['cards'] += [cards]
                            notnull  = ('0x' not in cards) and ('0x' not in bcards)
                            postflop = (base=='hold' and len(board['board'][n])>=3)
                            maxcards = (base!='hold' and len(cards)>=5)

                            # Evaluating the cards if they qualify
                            if notnull and (postflop or maxcards):
                                for hl, side in hiLoKey[hilo]:
                                    value, rank = pokereval.best(side, cards, bcards)
                                    rankId = Card.hands[rank[0]][0]

                                    if rank!=None and rank[0] != 'Nothing':
                                        _cards = ''.join([pokereval.card2string(i)[0] for i in rank[1:]])
                                    else:
                                        _cards = None

                                    self.handsstove.append([hand.dbid_hands, hand.dbid_pids[pname], streetId, boardId, hl, rankId, value, _cards, 0])
                            else:
                                self.handsstove.append([hand.dbid_hands, hand.dbid_pids[pname], streetId, boardId, 'n', 1, 0, None, 0])

            # If it's not an evaluation game, add the player's hand to the hands stove
            else:
                hl, streetId = hiLoKey[hilo][0][0], 0
                if (hp['sawShowdown'] or hp['showed']):
                    hp['handString'] = hand.showdownStrings.get(pname)
                    streetId = streets[last]
                self.handsstove.append([hand.dbid_hands, hand.dbid_pids[player[1]], streetId, 0, hl, 1, 0, None, 0])

        # If it's a hold'em game and an evaluation game, calculate the all-in EV for each player
        if base=='hold' and evalgame:
            self.getAllInEV(hand, evalgame, holeplayers, boards, streets, holecards)

                
    def getAllInEV(self, hand, evalgame, holeplayers, boards, streets, holecards):
        """Calculate the all-in expected value for each player based on their hole cards and the board.

        Args:
            hand (Hand): The current hand being played.
            evalgame (str): The type of poker being played (e.g. "holdem").
            holeplayers (List[str]): A list of player IDs still in the hand.
            boards (Dict[str, Dict]): A dictionary of boards for each street.
            streets (Dict[str, int]): A dictionary of street names and their corresponding IDs.
            holecards (Dict[str, Dict]): A dictionary of each player's hole cards.

        Returns:
            None
        """
        # Initialize variables
        startstreet, potId, allInStreets, allplayers = None, 0, hand.allStreets[1:], []

        # Loop through each pot
        for pot, players in hand.pot.pots:
            if potId ==0: pot += (sum(hand.pot.common.values()) + hand.pot.stp)
            potId+=1

            # Loop through each street where all-in has occurred
            for street in allInStreets:
                board = boards[street]
                streetId = streets[street]

                # Loop through each board card
                for n in range(len(board['board'])):
                    # Determine board card ID
                    boardId = n + 1 if len(board['board']) > 1 else n

                    # Determine players with valid hole cards
                    valid = [p for p in players if self.handsplayers[p]['sawShowdown'] and u'0x' not in holecards[p]['cards'][n]]

                    # If it is the first pot, all players are still in and no dead cards
                    if potId == 1:
                        allplayers = valid
                        deadcards, deadplayers = [], []
                    # Otherwise, determine dead players and cards
                    else:
                        deadplayers = [d for d in allplayers if d not in valid]
                        _deadcards = [holecards[d]['hole'] for d in deadplayers]
                        deadcards = [item for sublist in _deadcards for item in sublist]

                    # If all players are still in, calculate equities
                    if len(players) == len(valid) and (board['allin'] or hand.publicDB):
                        if board['allin'] and not startstreet: startstreet = street
                        if len(valid) > 1:
                            evs = pokereval.poker_eval(
                                game = evalgame, 
                                iterations = Card.iter[streetId],
                                pockets = [holecards[p]['hole'] for p in valid],
                                dead = deadcards, 
                                board = [str(b) for b in board['board'][n]] + (5 - len(board['board'][n])) * ['__']
                            )
                            equities = [e['ev'] for e in evs['eval']]
                        else:
                            equities = [1000]

                        # Divide remaining equity equally among players
                        remainder = old_div((1000 - sum(equities)), Decimal(len(equities)))
                        for i in range(len(equities)):
                            equities[i] += remainder

                            # Update each player's expected value
                            p = valid[i]
                            pid = hand.dbid_pids[p]
                            if street == startstreet:
                                rake = Decimal(0) if hand.cashedOut else (hand.rake * (old_div(Decimal(pot),Decimal(hand.totalpot))))
                                holecards[p]['eq'] += old_div(((pot - rake) * equities[i]),Decimal(10))
                                holecards[p]['committed'] = 100*hand.pot.committed[p] + 100*hand.pot.common[p]
                            for j in self.handsstove:
                                if [pid, streetId, boardId] == j[1:4] and len(valid) == len(hand.pot.contenders):
                                    j[-1] = equities[i]

                        # Update each player's allInEV
                        for p in holeplayers:
                            if holecards[p]['committed'] != 0: 
                                self.handsplayers[p]['allInEV'] = holecards[p]['eq'] - holecards[p]['committed']


    def getBoardsList(self, hand):
        """
        Returns a list of possible board card combinations for a given hand.

        Args:
            hand (Hand): An instance of the Hand class representing the poker hand.

        Returns:
            list: A list of lists, where each inner list contains strings representing the cards in a possible board.

        """
        boards, community = [], []

        # If the game type is "hold'em", add the cards from each street to the community cards list.
        if hand.gametype['base'] == 'hold':
            for s in hand.communityStreets:
                community += hand.board[s]

            # Generate all possible board card combinations based on the number of times to run the simulation.
            for i in range(hand.runItTimes):
                boardcards = []
                for street in hand.communityStreets:
                    boardId = i + 1
                    street_i = street + str(boardId)
                    if street_i in hand.board:
                        boardcards += hand.board[street_i]
                cards = [str(c) for c in community + boardcards]
                boards.append(cards)

        # If no board card combinations were generated, use the community cards as the only possible board.
        if not boards:
            boards = [community]

        return boards

    
    def getBoardsDict(self, hand, base, streets):
        """Returns a dictionary of boards for each street in the given hand.

        Args:
            hand (Hand): The hand object for which to generate boards.
            base (str): The base game being played ('hold' or 'omaha').
            streets (list): A list of streets for which to generate boards.

        Returns:
            dict: A dictionary of boards for each street in the given hand.
        """
        boards, boardcards, allInStreets, showdown = {}, [], hand.allStreets[1:], False

        # Check if any players saw showdown
        for player in hand.players:
            if (self.handsplayers[player[1]]['sawShowdown']):
                showdown = True

        # Generate boards for hold'em
        if base == 'hold':
            for s in allInStreets:
                streetId = streets[s]
                b = [x for sublist in [hand.board[k] for k in allInStreets[:streetId+1]] for x in sublist]
                boards[s] = {'board': [b], 'allin': False}
                boardcards += hand.board[s]

                # Mark the board as all-in if there are no more actions and a player saw showdown
                if not hand.actions[s] and showdown:
                    if streetId > 0:
                        boards[allInStreets[streetId-1]]['allin'] = True
                    boards[s]['allin'] = True

            # Generate runout boards for each street
            boardStreets = [[], [], []]
            for i in range(hand.runItTimes):
                runitcards = []
                for street in hand.communityStreets:
                    street_i = street + str((i+1))
                    if street_i in hand.board:
                        runitcards += hand.board[street_i]
                        sId = len(boardcards + runitcards) - 3
                        boardStreets[sId].append(boardcards + runitcards)

            # Add the generated runout boards to the board dictionary
            for i in range(len(boardStreets)):
                if boardStreets[i]:
                    boards[allInStreets[i+1]]['board'] = boardStreets[i]

        # Generate boards for omaha
        else:   
            for s in allInStreets:
                if s in streets:
                    streetId = streets[s]
                    boards[s] = {'board': [[]], 'allin': False}

        return boards

    
    def awardPots(self, hand):
        """Distributes the pot(s) to the winning player(s) in the given hand"""
        # Initialize variables
        holeshow = True
        base, evalgame, hilo, streets, last, hrange = Card.games[hand.gametype['category']]
        factor = 100

        # Check if the pot factor needs to be updated
        if ((hand.gametype["type"]=="tour" or 
            (hand.gametype["type"]=="ring" and 
            (hand.gametype["currency"]=="play" and 
            (hand.sitename not in ('Winamax', 'PacificPoker'))))) and
            (not [n for (n,v) in hand.pot.pots if (n % Decimal('1.00'))!=0])):
            factor = 1

        # Check if pokereval is available and if the hand has multiple pots and valid hole cards
        if pokereval and len(hand.pot.pots)>1 and evalgame and holeshow: #hrange
            # Initialize variables
            hand.collected = [] #list of ?
            hand.collectees = {} # dict from player names to amounts collected (?)
            rakes, totrake, potId = {}, 0, 0
            totalrake = hand.rakes.get('rake')

            # Calculate total rake if it is not already provided
            if not totalrake:
                if totalpot := hand.rakes.get('pot'):
                    totalrake = hand.totalpot - totalpot
                else:
                    totalrake = 0

            # Set up dictionary for high/low split games
            hiLoKey = {'h':['hi'],'l':['low'],'r':['low'],'s':['hi','low']}

            # Loop through each pot and its players
            for pot, players in hand.pot.pots:
                # Calculate total pot size for this pot
                if potId ==0: 
                    pot += (sum(hand.pot.common.values()) + hand.pot.stp)
                potId+=1

                # Calculate pot size for each board and if there are multiple boards, adjust pot size for remainder
                boards, boardId, sumpot = self.getBoardsList(hand), 0, 0
                for b in boards:
                    boardId += (hand.runItTimes>=2)
                    potBoard = Decimal(int(pot/len(boards)*factor))/factor
                    modBoard = pot - potBoard*len(boards)
                    if boardId==1: 
                        potBoard+=modBoard

                    # Find valid hole cards for each player
                    holeplayers, holecards = [], []
                    for p in players:
                        hcs = hand.join_holecards(p, asList=True)
                        holes = [str(c) for c in hcs[hrange[-1][0]:hrange[-1][1]] if Card.encodeCardList.get(c)!=None or c=='0x']
                        board = [str(c) for c in b if 'omaha' in evalgame]
                        if 'omaha' not in evalgame:
                            holes += [str(c) for c in b if base=='hold']
                        if '0x' not in holes and '0x' not in board:
                            holecards.append(holes)
                            holeplayers.append(p)

                    # Calculate winners and their pots for high/low split games
                    if len(holecards)>1:
                        try:
                            win = pokereval.winners(game = evalgame, pockets = holecards, board = board)
                        except RuntimeError:
                            log.error(
                                f"awardPots: error evaluating winners for hand {hand.handid} {hand.in_path}"
                            )
                            win = {hiLoKey[hilo][0]: [0]}
                    else:
                        win = {hiLoKey[hilo][0]: [0]}

                    for hl in hiLoKey[hilo]:
                        if hl in win and len(win[hl])>0:
                            potHiLo = Decimal(int(potBoard/len(win)*factor))/factor
                            modHiLo = potBoard - potHiLo*len(win)
                            if len(win)==1 or hl=='hi':
                                potHiLo+=modHiLo
                            potSplit = Decimal(int(potHiLo/len(win[hl])*factor))/factor
                            modSplit = potHiLo - potSplit*len(win[hl])
                            pnames = [holeplayers[w] for w in win[hl]] if holeplayers else players
                            for p in pnames:
                                ppot = potSplit
                                if modSplit>0:
                                    cent = (Decimal('0.01') * (100/factor))
                                    ppot += cent
                                    modSplit -= cent
                                rake = (totalrake * (ppot/hand.totalpot)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                                hand.addCollectPot(player=p,pot=(ppot-rake))

             
    
    def assembleHandsPots(self, hand):
        """
        Assemble pots for a given hand.

        Args:
            hand: A Hand object.

        Returns:
            None
        """
        # initialize variables
        category, positions, playersPots, potFound, positionDict, showdown = hand.gametype['category'], [], {}, {}, {}, False

        # assign variables for each player in the hand
        for p in hand.players:
            playersPots[p[1]] = [0,[]]
            potFound[p[1]] = [0,0]
            positionDict[self.handsplayers[p[1]]['position']] = p[1]
            positions.append(self.handsplayers[p[1]]['position'])
            if self.handsplayers[p[1]]['sawShowdown']:
                showdown = True
        positions.sort(reverse=True)
        factor = 100

        # modify factor if criteria is met
        if ((hand.gametype["type"]=="tour" or 
            (hand.gametype["type"]=="ring" and 
            (hand.gametype["currency"]=="play" and 
            (hand.sitename not in ('Winamax', 'PacificPoker'))))) and
            (not [n for (n,v) in hand.pot.pots if (n % Decimal('1.00'))!=0])):
            factor = 1

        # create dictionary of keys and values for each game type
        hiLoKey = {'h':['hi'],'l':['low'],'r':['low'],'s':['hi','low']}
        base, evalgame, hilo, streets, last, hrange = Card.games[category]

        # assemble pots for each player in the hand
        if ((hand.sitename != 'KingsClub' or hand.adjustCollected) and # Can't trust KingsClub draw/stud holecards  
            evalgame and 
            (len(hand.pot.pots)>1 or (showdown and (hilo=='s' or hand.runItTimes>=2)))
            ):
            rakes, totrake, potId = {}, 0, 0
            for pot, players in hand.pot.pots:
                if potId ==0: pot += (sum(hand.pot.common.values()) + hand.pot.stp)
                potId+=1
                boards, boardId, sumpot = self.getBoardsList(hand), 0, 0

                # evaluate pots for each possible board
                for b in boards:
                    boardId += (hand.runItTimes>=2)
                    potBoard = Decimal(int(pot/len(boards)*factor))/factor
                    modBoard = pot - potBoard*len(boards)
                    if boardId==1: 
                        potBoard+=modBoard
                    holeplayers, holecards = [], []

                    # assemble holecards for each player in the hand
                    for p in players:
                        hcs = hand.join_holecards(p, asList=True)
                        holes = [str(c) for c in hcs[hrange[-1][0]:hrange[-1][1]] if Card.encodeCardList.get(c)!=None or c=='0x']
                        board = [str(c) for c in b if 'omaha' in evalgame]
                        if 'omaha' not in evalgame:
                            holes += [str(c) for c in b if base=='hold']
                        if '0x' not in holes and '0x' not in board:
                            holecards.append(holes)
                            holeplayers.append(p)

                    # evaluate winners
                    if len(holecards)>1:
                        try:
                            win = pokereval.winners(game = evalgame, pockets = holecards, board = board)
                        except RuntimeError:
                            # Error handling in case the evaluation of the winners fails
                            log.error(
                                f"assembleHandsPots: error evaluating winners for hand {hand.handid} {hand.in_path}"
                            )
                            win = {hiLoKey[hilo][0]: [0]}

                        # Loop through the hi-lo keys
                        for hl in hiLoKey[hilo]:
                            if hl in win and len(win[hl])>0:
                                # Calculate the pot amount for the given hi-lo key
                                potHiLo = old_div(Decimal(int(potBoard/len(win)*factor)),factor)
                                modHiLo = potBoard - potHiLo*len(win)
                                if len(win)==1 or hl=='hi':
                                    potHiLo+=modHiLo
                                    potSplit = old_div(Decimal(int(potHiLo/len(win[hl])*factor)),factor)
                                modSplit = potHiLo - potSplit*len(win[hl])
                                pnames = [holeplayers[w] for w in win[hl]] if holeplayers else players

                                # assign pots to players based on position
                                for n in positions:
                                    if positionDict[n] in pnames:
                                        pname = positionDict[n]
                                        ppot = potSplit
                                        if modSplit>0:
                                            cent = (Decimal('0.01') * (old_div(100,factor)))
                                            ppot += cent
                                            modSplit -= cent
                                        playersPots[pname][0] += ppot
                                        potFound[pname][0] += ppot
                                        data = {'potId': potId, 'boardId': boardId, 'hiLo': hl,'ppot':ppot, 'winners': [m for m in pnames if pname!=n], 'mod': ppot>potSplit}
                                        playersPots[pname][1].append(data)
                                        self.handsplayers[pname]['rake'] = 0

                        for p, (total, info) in list(playersPots.items()):
                            if hand.collectees.get(p) and info:
                                potFound[p][1] = hand.collectees.get(p)
                                for item in info:
                                    # Calculate the split pot and rake
                                    split = [n for n in item['winners'] if len(playersPots[n][1])==1 and hand.collectees.get(n)!=None]
                                    if len(info)==1:
                                        ppot = item['ppot']
                                        rake = ppot - hand.collectees[p]
                                        collected = hand.collectees[p]
                                    elif item==info[-1]:
                                        ppot, collected = potFound[p]
                                        rake = ppot - collected
                                    elif len(split)>0 and not item['mod']:
                                        ppot = item['ppot']
                                        collected = min([hand.collectees[s] for s in split] + [ppot])
                                        rake = ppot - collected
                                    else:
                                        ppot = item['ppot']
                                        totalrake = total - hand.collectees[p]
                                        rake = (totalrake * (old_div(ppot,total))).quantize(Decimal("0.01"))
                                        collected = ppot - rake 
                                    potFound[p][0] -= ppot
                                    potFound[p][1] -= collected
                                    insert = [None, item['potId'], item['boardId'], item['hiLo'][0], hand.dbid_pids[p], int(item['ppot']*100), int(collected*100), int(rake*100)]   
                                    # Add the pot information to the handsplayers dictionary and the handspots list
                                    self.handspots.append(insert)
                                    self.handsplayers[p]['rake'] += int(rake*100)



    def setPositions(self, hand):
        """Sets the position for each player in HandsPlayers
        any blinds are negative values, and the last person to act on the
        first betting round is 0
        NOTE: HU, both values are negative for non-stud games
        NOTE2: I've never seen a HU stud match

        Args:
        - self: the object of class that the method belongs to
        - hand: the Hand object that contains information regarding the current game state

        Returns:
        - None
        """
        actions = hand.actions[hand.holeStreets[0]]
        # Note:  pfbao list may not include big blind if all others folded
        players = self.pfbao(actions)

        # set blinds first, then others from pfbao list, avoids problem if bb
        # is missing from pfbao list or if there is no small blind
        sb, bb, bi, ub, st = False, False, False, False, False
        if hand.gametype['base'] == 'stud':
            # Stud position is determined after cards are dealt
            # First player to act is always the bring-in position in stud
            # even if they decided to bet/completed
            if len(hand.actions[hand.actionStreets[1]])>0:
                bi = [hand.actions[hand.actionStreets[1]][0][0]]
            #else:
                # TODO fix: if ante all and no actions and no bring in
            #    bi = [hand.actions[hand.actionStreets[0]][0][0]]
        else:
            ub = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == 'button blind']
            bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == 'big blind']
            sb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == 'small blind']
            st = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == 'straddle']

        # if there are > 1 sb or bb only the first is used!
        if ub:
            self.handsplayers[ub[0]]['street0InPosition'] = True
            if ub[0] not in players: players.append(ub[0])              
        if bb:
            self.handsplayers[bb[0]]['position'] = 'B'
            self.handsplayers[bb[0]]['street0InPosition'] = True
            if bb[0] in players: players.remove(bb[0])
        if sb:
            self.handsplayers[sb[0]]['position'] = 'S'
            self.handsplayers[sb[0]]['street0FirstToAct'] = True
            if sb[0] in players: players.remove(sb[0])
        if bi:
            self.handsplayers[bi[0]]['position'] = 'S'
            self.handsplayers[bi[0]]['street0FirstToAct'] = True
            if bi[0] in players: players.remove(bi[0])
        if st and st[0] in players:
            players.insert(0, players.pop())

        #print "DEBUG: actions: '%s'" % actions
        #print "DEBUG: ub: '%s' bb: '%s' sb: '%s' bi: '%s' plyrs: '%s'" %(ub, bb, sb, bi, players)

        # Set the position for each player in `players`
        for i, player in enumerate(reversed(players)): 
            self.handsplayers[player]['position'] = i
            self.hands['maxPosition'] = i
            if i==0 and hand.gametype['base'] == 'stud':
                self.handsplayers[player]['street0InPosition'] = True
            elif (i-1)==len(players):
                self.handsplayers[player]['street0FirstToAct'] = True
                

    def assembleHudCache(self, hand):
        # No real work to be done - HandsPlayers data already contains the correct info
        pass

    def vpip(self, hand):
        """
        Calculates the VPIP (Voluntarily Put money In Pot) statistic for each player in the hand.

        Args:
            hand (Hand): The current hand being played.

        Returns:
            None
        """
        # Get the players who posted the big blind or button blind
        bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] in ('big blind', 'button blind')]

        # Get the players who voluntarily put money in the pot (calls, bets, raises, or completes)
        vpipers = {act[0] for act in hand.actions[hand.actionStreets[1]] if act[1] in ('calls', 'bets', 'raises', 'completes')}
        self.hands['playersVpi'] = len(vpipers)

        # Set the 'street0VPI' attribute for players who voluntarily put money in the pot and update the respective player's stats
        for player in hand.players:
            pname = player[1]
            player_stats = self.handsplayers.get(pname)
            if pname in vpipers:
                player_stats['street0VPI'] = True
            elif pname in hand.sitout:
                player_stats['street0VPIChance'] = False
                player_stats['street0AggrChance'] = False

        # If no player voluntarily put money in the pot, set the 'street0VPIChance' and 'street0AggrChance' attributes to False for the big blind player
        if not vpipers and bb:
            self.handsplayers[bb[0]]['street0VPIChance'] = False
            self.handsplayers[bb[0]]['street0AggrChance'] = False


    def playersAtStreetX(self, hand):
        """
        Calculates the number of players who saw each street and reached the showdown.

        Args:
            hand (Hand): An object representing the hand being played.

        Returns:
            None
        """
        """ playersAtStreet1 SMALLINT NOT NULL,   /* num of players seeing flop/street4/draw1 */"""
        # self.actions[street] is a list of all actions in a tuple, contining the player name first
        # [ (player, action, ....), (player2, action, ...) ]
        # The number of unique players in the list per street gives the value for playersAtStreetXXX

        # FIXME?? - This isn't couting people that are all in - at least showdown needs to reflect this
        #     ... new code below hopefully fixes this
        # partly fixed, allins are now set as seeing streets because they never do a fold action

        # Initialize the count of players at each street to 0
        self.hands['playersAtStreet1']  = 0
        self.hands['playersAtStreet2']  = 0
        self.hands['playersAtStreet3']  = 0
        self.hands['playersAtStreet4']  = 0
        self.hands['playersAtShowdown'] = 0

#        alliners = set()
#        for (i, street) in enumerate(hand.actionStreets[2:]):
#            actors = set()
#            for action in hand.actions[street]:
#                if len(action) > 2 and action[-1]: # allin
#                    alliners.add(action[0])
#                actors.add(action[0])
#            if len(actors)==0 and len(alliners)<2:
#                alliners = set()
#            self.hands['playersAtStreet%d' % (i+1)] = len(set.union(alliners, actors))
#
#        actions = hand.actions[hand.actionStreets[-1]]
#        print "p_actions:", self.pfba(actions), "p_folds:", self.pfba(actions, l=('folds',)), "alliners:", alliners
#        pas = set.union(self.pfba(actions) - self.pfba(actions, l=('folds',)),  alliners)

        # hand.players includes people that are sitting out on some sites for cash games
        # actionStreets[1] is 'DEAL', 'THIRD', 'PREFLOP', so any player dealt cards
        # must act on this street if dealt cards. Almost certainly broken for the 'all-in blind' case
        # and right now i don't care - CG

        # Get the players who were dealt cards
        p_in = {x[0] for x in hand.actions[hand.actionStreets[1]]}

        #Add in players who were allin blind
        if hand.pot.pots and len(hand.pot.pots[0][1])>1:
            p_in = p_in.union(hand.pot.pots[0][1])

        #
        # discover who folded on each street and remove them from p_in
        #
        # i values as follows 0=BLINDSANTES 1=PREFLOP 2=FLOP 3=TURN 4=RIVER
        #   (for flop games)
        #
        # At the beginning of the loop p_in contains the players with cards
        # at the start of that street.
        # p_in is reduced each street to become a list of players still-in
        # e.g. when i=1 (preflop) all players who folded during preflop
        # are found by pfba() and eliminated from p_in.
        # Therefore at the end of the loop, p_in contains players remaining
        # at the end of the action on that street, and can therefore be set
        # as the value for the number of players who saw the next street
        #
        # note that i is 1 in advance of the actual street numbers in the db
        #
        # if p_in reduces to 1 player, we must bomb-out immediately
        # because the hand is over, this will ensure playersAtStreetx
        # is accurate.
        #

        # Loop over each street to count the number of players who saw it
        for (i, street) in enumerate(hand.actionStreets):
            if (i-1) in (1,2,3,4):
                # p_in stores players with cards at start of this street,
                # so can set streetxSeen & playersAtStreetx with this information
                # This hard-coded for i-1 =1,2,3,4 because those are the only columns
                # in the db! this code section also replaces seen() - more info log 66
                # nb i=2=flop=street1Seen, hence i-1 term needed
                self.hands['playersAtStreet%d' % (i-1)] = len(p_in)
                for player_with_cards in p_in:
                    self.handsplayers[player_with_cards][f'street{i - 1}Seen'] = True

                players = self.pfbao(hand.actions[street], f=('discards','stands pat'))
                if len(players)>0:
                    self.handsplayers[players[0]]['street%dFirstToAct' % (i-1)] = True
                    self.handsplayers[players[-1]]['street%dInPosition' % (i-1)] = True
            #
            # find out who folded, and eliminate them from p_in
            #
            actions = hand.actions[street]
            p_in = p_in - self.pfba(actions, l=('folds',))
            #
            # if everyone folded, we are done, so exit this method
            #
            if len(p_in) == 1: 
                if (i-1) in (1,2,3,4) and len(players)>0 and list(p_in)[0] not in players:
                    # corrects which player is "in position"
                    # if everyone folds before the last player could act
                    self.handsplayers[players[-1]]['street%dInPosition' % (i-1)] = False
                    self.handsplayers[list(p_in)[0]]['street%dInPosition' % (i-1)] = True
                return None

        #
        # The remaining players in p_in reached showdown (including all-ins
        # because they never did a "fold" action in pfba() above)
        #
        self.hands['playersAtShowdown'] = len(p_in)
        for showdown_player in p_in:
            self.handsplayers[showdown_player]['sawShowdown'] = True

    def streetXRaises(self, hand):
        """
        Calculates the number of raises, bets, and completes made in each street of a poker hand and stores
        the result in the dictionary self.hands.

        Args:
            hand (Hand): A Hand object representing a completed poker hand.

        Returns:
            None
        """
        # self.actions[street] is a list of all actions in a tuple, contining the action as the second element
        # [ (player, action, ....), (player2, action, ...) ]
        # No idea what this value is actually supposed to be
        # In theory its "num small bets paid to see flop/street4, including blind" which makes sense for limit. Not so useful for nl
        # Leaving empty for the moment,

        # Initialize the number of raises, bets, and completes to 0 for each street
        for i in range(5):
            self.hands['street%dRaises' % i] = 0

        # Iterate over each street in the hand except for the first one (pre-flop)
        for (i, street) in enumerate(hand.actionStreets[1:]):
            # Count the number of raises, bets, and completes made in the current street
            num_raises_bets_completes = len([action for action in hand.actions[street] if action[1] in ('raises','bets','completes')])
            # Store the result in the dictionary
            self.hands['street%dRaises' % i] = num_raises_bets_completes


    def calcSteals(self, hand):
        """Fills raiseFirstInChance|raisedFirstIn, fold(Bb|Sb)ToSteal(Chance|)

        Steal attempt - open raise on positions 1 0 S - i.e. CO, BU, SB
                        (note: I don't think PT2 counts SB steals in HU hands, maybe we shouldn't?)
        Fold to steal - folding blind after steal attemp wo any other callers or raisers
        """
        steal_attempt = False
        raised = False
        if hand.gametype['base'] == 'stud':
            steal_positions = (2, 1, 0)
        elif len([x for x in hand.actions[hand.actionStreets[0]] if x[1] == 'button blind']) > 0:
            steal_positions = (3, 2, 1)
        else:
            steal_positions = (1, 0, 'S')
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act = action[0], action[1]
            player_stats = self.handsplayers.get(pname)
            if player_stats['sitout']: continue
            posn = player_stats['position']
            #print "\naction:", action[0], posn, type(posn), steal_attempt, act
            if posn == 'B':
                #NOTE: Stud games will never hit this section
                if steal_attempt:
                    player_stats['foldBbToStealChance'] = True
                    player_stats['raiseToStealChance'] = True
                    player_stats['foldedBbToSteal'] = act == 'folds'
                    player_stats['raiseToStealDone'] = act == 'raises'
                    self.handsplayers[stealer]['success_Steal'] = act == 'folds'
                break
            elif posn == 'S':
                player_stats['raiseToStealChance'] = steal_attempt
                player_stats['foldSbToStealChance'] = steal_attempt
                player_stats['foldedSbToSteal'] = steal_attempt and act == 'folds'
                player_stats['raiseToStealDone'] = steal_attempt and act == 'raises'
                if steal_attempt:
                    self.handsplayers[stealer]['success_Steal'] = act == 'folds' and hand.gametype['base'] == 'stud'

            if steal_attempt and act != 'folds':
                break

            if not steal_attempt and not raised and not act in ('bringin'):
                player_stats['raiseFirstInChance'] = True
                if posn in steal_positions:
                    player_stats['stealChance'] = True
                if act in ('bets', 'raises', 'completes'):
                    player_stats['raisedFirstIn'] = True
                    raised = True
                    if posn in steal_positions:
                        player_stats['stealDone'] = True
                        steal_attempt = True
                        stealer = pname
                if act == 'calls':
                    break
            
            if posn not in steal_positions and act not in ('folds', 'bringin'):
                break

    def calc34BetStreet0(self, hand):
        """
        Fills street0_(3|4)B(Chance|Done), other(3|4)BStreet0

        Args:
        - hand: object representing the current hand state

        Returns:
        - None
        """
        # Determine bet level based on gametype
        bet_level = 0 if hand.gametype['base'] == 'stud' else 1

        # Initialize variables for chance of squeeze, chance of raise, action count, and first aggressor
        squeeze_chance, raise_chance, action_cnt, first_agressor = False, True, {}, None

        # Get set of players who have acted in street 0 and 1
        p0_in = {x[0] for x in hand.actions[hand.actionStreets[0]] if not x[-1]}
        p1_in = {x[0] for x in hand.actions[hand.actionStreets[1]]}
        p_in = p1_in.union(p0_in)

        # Initialize action count for each player in p_in
        for p in p_in: 
            action_cnt[p] = 0

        # Loop through each action in street 1
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act, aggr, allin = action[0], action[1], action[1] in ('raises', 'bets', 'completes'), False

            # Get player stats and update action count for current player
            player_stats = self.handsplayers.get(pname)
            action_cnt[pname] += 1

            # Check if the current action is an all-in
            if len(action) > 3 and act != 'discards':
                allin = action[-1]

            # Update raise chance if only one player is left and this is their first action
            if len(p_in)==1 and action_cnt[pname]==1:
                raise_chance = False
                player_stats['street0AggrChance'] = raise_chance

            # Remove player from p_in if they have folded, gone all-in, or are sitting out
            if act == 'folds' or allin or player_stats['sitout']:
                p_in.discard(pname)
            if player_stats['sitout']:
                continue

            # Determine bet level for current action
            if bet_level == 0:
                if aggr:
                    # Update first aggressor and increase bet level
                    if first_agressor is None:
                        first_agressor = pname
                    bet_level += 1
                continue
            elif bet_level == 1:
                # Update chance of 2B and mark 2B as done if current player is the first aggressor
                player_stats['street0_2BChance'] = raise_chance
                if aggr:
                    player_stats['street0_3BDone'] = True
                    player_stats['street0_SqueezeDone'] = squeeze_chance
                    second_agressor = pname
                    bet_level += 1
                continue
            elif bet_level == 3:
                if pname == first_agressor:
                    # Update chance of 4B and mark fold-to-3B chance as done if current player is the first aggressor
                    player_stats['street0_4BChance'] = raise_chance
                    player_stats['street0_FoldTo3BChance'] = True
                    if aggr:
                        player_stats['street0_4BDone'] = raise_chance
                        bet_level += 1
                    elif act == 'folds':
                        player_stats['street0_FoldTo3BDone'] = True
                        break
                else:
                    # Update chance of capped 4B
                    player_stats['street0_C4BChance'] = raise_chance
                    if aggr:
                        player_stats['street0_C4BDone'] = raise_chance
                        bet_level += 1
                continue
            elif bet_level == 4:
                if pname != first_agressor: 
                    # Mark fold-to-4B chance as done if current player is not the first aggressor
                    player_stats['street0_FoldTo4BChance'] = True
                    if act == 'folds':
                        player_stats['street0_FoldTo4BDone'] = True


    def calcCBets(self, hand):
        """
        Fill streetXCBChance, streetXCBDone, foldToStreetXCBDone, foldToStreetXCBChance

        Continuation Bet chance and action:
        - Had the last bet (initiative) on previous street, got called, close street action
        - Then no bets before the player with initiatives first action on current street
        - ie. if player on street-1 had initiative and no donkbets occurred

        Args:
        - hand: Hand object representing a poker hand

        Returns:
        - None
        """
        # XXX: enumerate(list, start=x) is python 2.6 syntax; 'start' came there
        # Loop through each street of the hand starting from the third street (index 2)
        for i, street in enumerate(hand.actionStreets[2:]):
            # Check if the last bet or raise was made on the previous street
            if name := self.lastBetOrRaiser(hand.actions, hand.actionStreets[i + 1]):
                # Check if there were no bets made before the player with initiatives first action on the current street
                chance = self.noBetsBefore(hand.actions, hand.actionStreets[i+2], name) # this street
                if chance == True:
                    # Get the player's stats
                    player_stats = self.handsplayers.get(name)
                    # Set the player's chance of making a continuation bet on the current street to True
                    player_stats[f'street{i+1}CBChance'] = True
                    # Set the amount of the player's continuation bet on the current street
                    player_stats[f'street{i+1}CBDone'] = self.betStreet(hand.actions, hand.actionStreets[i+2], name)
                    # If the player made a continuation bet on the current street
                    if player_stats[f'street{i+1}CBDone']:
                        # Loop through each player who folded to the player's continuation bet
                        for pname, folds in list(self.foldTofirstsBetOrRaiser(hand.actions, street, name).items()):
                            # Set the player's chance of folding to a continuation bet on the current street to True
                            self.handsplayers[pname][f'foldToStreet{i + 1}CBChance'] = True
                            # Set the amount the player folded to the player's continuation bet on the current street
                            self.handsplayers[pname][f'foldToStreet{i + 1}CBDone'] = folds


    def calcCalledRaiseStreet0(self, hand):
        """
        Fill street0CalledRaiseChance, street0CalledRaiseDone

        For flop games, go through the preflop actions:
            skip through first raise
            For each subsequent action:
                if the next action is fold :
                    player chance + 1
                if the next action is raise :
                    player chance + 1
                if the next non-fold action is call :
                    player chance + 1
                    player done + 1
                    skip through list to the next raise action

        Parameters:
        -----------
        hand : Hand
            The hand object representing the current hand being analyzed

        """
        # Skip through preflop raises to get to flop actions
        fast_forward = True
        for tupleread in hand.actions[hand.actionStreets[1]]:
            action = tupleread[1]
            if fast_forward:
                if action in ('raises', 'completes'):
                    fast_forward = False # raisefound, end fast-forward
            else:
                player = tupleread[0]
                player_stats = self.handsplayers.get(player)
                player_stats['street0CalledRaiseChance'] += 1
                if action == 'calls':
                    player_stats['street0CalledRaiseDone'] += 1
                    fast_forward = True


    def calcCheckCallRaise(self, hand):
        """
        Fill streetXCheckCallRaiseChance, streetXCheckCallRaiseDone

        streetXCheckCallRaiseChance = got raise/bet after check
        streetXCheckCallRaiseDone = checked. got raise/bet. didn't fold

        CG: CheckCall would be a much better name for this.
        """
        # XXX: enumerate(list, start=x) is python 2.6 syntax; 'start'
        # for i, street in enumerate(hand.actionStreets[2:], start=1):
        for i, street in enumerate(hand.actionStreets[2:]):
            actions = hand.actions[street]
            checkers = set()
            acted = set()
            initial_raiser = None
            for action in actions:
                pname, act = action[0], action[1]
                if act in ('bets', 'raises') and initial_raiser is None:
                    initial_raiser = pname
                elif act == 'checks' and initial_raiser is None:
                    checkers.add(pname)
                # got raise/bet after check
                elif initial_raiser is not None and pname in checkers and pname not in acted:
                    player_stats = self.handsplayers.get(pname)
                    player_stats[f'street{i+1}CheckCallRaiseChance'] = True
                    player_stats[f'street{i+1}CheckCallDone'] = act == 'calls'
                    player_stats[f'street{i+1}CheckRaiseDone'] = act == 'raises'
                    acted.add(pname)


    def aggr(self, hand, i):
        """
        Given a `hand` and an index `i`, this function identifies the players that made the first aggression in the given street.
        Then, it sets a flag on the corresponding dictionary for each of those players.

        Args:
        - self: The object itself.
        - hand: A dictionary representing a poker hand.
        - i: An integer that indicates the index of the current street.

        Returns:
        - None
        """
        aggrers = set()   # set of players who made the first aggression
        others = set()    # set of players who did not make the first aggression

        # Growl - actionStreets contains 'BLINDSANTES', which isn't actually an action street
        firstAggrMade = False   # flag for whether the first aggression has been made
        for act in hand.actions[hand.actionStreets[i+1]]:
            if firstAggrMade:
                others.add(act[0])   # add the player to others set if they are not the first to make aggression
            if act[1] in ('completes', 'bets', 'raises'):
                aggrers.add(act[0])   # add the player to the aggrers set if they made aggression
                firstAggrMade = True   # set the flag to true if the first aggression has been made

        for player in hand.players:
            if player[1] in aggrers:
                self.handsplayers[player[1]][f'street{i}Aggr'] = True   # set flag for the player who made aggression

        if aggrers and i > 0:
            for playername in others:
                self.handsplayers[playername][f'otherRaisedStreet{i}'] = True   # set flag for each player in others set
                # print "otherRaised detected on handid "+str(hand.handid)+" for "+playername+" on street "+str(i)

        if i > 0 and aggrers:
            for playername in others:
                self.handsplayers[playername][f'otherRaisedStreet{i}'] = True   # set flag for each player in others set
                # print "DEBUG: otherRaised detected on handid %s for %s on actionStreet[%s]: %s" 
                #                           %(hand.handid, playername, hand.actionStreets[i+1], i)


    def calls(self, hand, i):
        """
        Adds +1 to the 'street{i}Calls' stat of players who made a call action on the given street.

        Args:
            hand (Hand): The current hand being played.
            i (int): The index of the current street.
        """
        callers = []
        # Loop through all actions on the next street
        for act in hand.actions[hand.actionStreets[i+1]]:
            # If the action is a call
            if act[1] in ('calls'):
                # Get the player's stats
                player_stats = self.handsplayers.get(act[0])
                # Increment the 'street{i}Calls' stat
                player_stats[f'street{i}Calls'] = 1 + player_stats[f'street{i}Calls']


    def bets(self, hand, i):
        """
        Increments the 'street{i}Bets' count for each player that has made a bet on the (i+1)-th street of the hand.

        Args:
            hand (Hand): the hand being analyzed
            i (int): the current street being analyzed

        Returns:
            None
        """
        # Loop through each action in the (i+1)-th street of the hand
        for act in hand.actions[hand.actionStreets[i+1]]:
            # Check if the action is a bet
            if act[1] in ('bets'):
                # Get the stats for the player that made the bet
                player_stats = self.handsplayers.get(act[0])
                # Increment the 'street{i}Bets' count for the player
                player_stats[f'street{i}Bets'] = 1 + player_stats[f'street{i}Bets']

                
    def raises(self, hand, i):
        """
        Increments the 'street{i}Raises' counter for players who raised or completed the current street.

        Args:
        - hand: Hand object containing information about the current hand.
        - i: An integer representing the current street.

        Returns:
        - None
        """
        # Iterate over the actions taken by players on the next street after i
        for act in hand.actions[hand.actionStreets[i+1]]:
            # If the action is a raise or a completion of a bet, increment the 'street{i}Raises' counter for the player
            if act[1] in ('completes', 'raises'):
                player_stats = self.handsplayers.get(act[0])
                player_stats[f'street{i}Raises'] = 1 + player_stats[f'street{i}Raises']

        
    def folds(self, hand, i):
        """Detects if a player has folded to another player's raise on a given street.

        Args:
            hand (Hand): The hand being analyzed.
            i (int): The index of the current street.

        Returns:
            None
        """
        # Iterate through the actions on the next street
        for act in hand.actions[hand.actionStreets[i+1]]:
            # If a player has folded
            if act[1] in ('folds'):
                # Get the stats for the player who folded
                player_stats = self.handsplayers.get(act[0])
                # If the player was previously raised by another player on this street
                if player_stats[f'otherRaisedStreet{i}'] == True:
                    # Mark that the player folded to the other player's raise
                    player_stats[f'foldToOtherRaisedStreet{i}'] = True
                    # Uncomment the following line to print a debug message
                    # print(f"DEBUG: fold detected on handid {hand.handid} for {act[0]} on actionStreet[{hand.actionStreets[i+1]}]: {i}")


    def countPlayers(self, hand):
        pass


    def pfba(self, actions, f=None, l=None):
        """Helper method. Returns set of PlayersFilteredByActions

        Args:
            actions (list): A list of tuples. Each tuple contains a player and their action.
            f (list, optional): A list of forbidden actions. Defaults to None.
            l (list, optional): A list of limited actions. Defaults to None.

        Returns:
            set: A set of players who performed the filtered actions.
        """
        players = set()  # Create an empty set to store players who performed the filtered actions
        for action in actions:  # Iterate over each action in the provided list
            if l is not None and action[1] not in l:  # If the limited action list is provided and the current action is not in it, skip to the next action
                continue
            if f is not None and action[1] in f:  # If the forbidden action list is provided and the current action is in it, skip to the next action
                continue
            players.add(action[0])  # Add the player of the current action to the set of players who performed the filtered actions
        return players  # Return the set of players who performed the filtered actions


    def pfbao(self, actions, f=None, l=None, unique=True):
        """
        Helper method that returns set of PlayersFilteredByActionsOrdered.

        Args:
            actions (list): List of actions.
            f (list): List of forbidden actions.
            l (list): List of allowed actions.
            unique (bool): Flag to indicate if the returned list should be unique.

        Returns:
            list: List of players.

        Note:
            This is an adaptation of function 5 from http://www.peterbe.com/plog/uniqifiers-benchmark
        """
        seen = {}           # create an empty dictionary to store seen players
        players = []        # create an empty list to store players
        for action in actions:
            if l is not None and action[1] not in l:   # if limited actions are specified and current action is not in them
                continue                                # skip this iteration and move to the next one
            if f is not None and action[1] in f:       # if forbidden actions are specified and current action is in them
                continue                                # skip this iteration and move to the next one
            if action[0] in seen and unique:           # if the current player has already been seen and unique flag is set to True
                continue                                # skip this iteration and move to the next one
            seen[action[0]] = 1                         # mark the current player as seen
            players.append(action[0])                   # add the current player to the players list
        return players                                   # return the players list

    
    def calcEffectiveStack(self, hand):
        """
        Calculates the effective stack for each player on the first street of play.

        Args:
            hand: An object representing the current state of the hand being played.

        Returns:
            None.
        """
        # Dictionary to keep track of players seen so far
        seen = {}

        # List of actions taken on the first street of play
        actions = hand.actions[hand.holeStreets[0]]

        # Dictionary of player stacks, with players who are sitting out excluded
        pstacks = {
            p[1]: int(100 * Decimal(p[2]))
            for p in hand.players
            if p[1] not in hand.sitout
        }

        # Iterate through each action taken on the first street of play
        for action in actions:
            # If the player has already been seen, skip to the next action
            if action[0] in seen:
                continue

            # If the player is not in our list of player stacks, skip to the next action
            if action[0] not in pstacks:
                continue

            # Mark the player as seen
            seen[action[0]] = 1

            # Get the stacks of all opponents
            oppstacks = [
                v for (k, v) in list(pstacks.items()) if k != action[0]
            ]

            # Calculate the effective stack for the player
            self.handsplayers[action[0]]['effStack'] = min(
                pstacks[action[0]], max(oppstacks)
            )

            # If the player folded, set their stack to 0
            if action[1] == 'folds':
                pstacks[action[0]] = 0


    def firstsBetOrRaiser(self, actions):
        """
        Returns the name of the player who placed the first bet or raise.

        Args:
            actions (list): A list of tuples representing player's actions.

        Returns:
            str or None: The name of the player who placed the first bet or raise. None if there were no bets or raises on that street.
        """
        return next(
            (
                act[0]  # The name of the player
                for act in actions
                if act[1] in ('bets', 'raises', 'completes')  # Actions that qualify as a bet or raise
            ),
            None,  # Return None if no bet or raise was found
        )

    
    def foldTofirstsBetOrRaiser(self, actions, street, aggressor):
        """
        Returns the name of the first player to place a bet or raise on a given street, or the aggressor in the hand.
        If there were no bets or raises on that street, return None.

        :param actions: list of actions taken by players in the hand
        :param street: the current street of the hand
        :param aggressor: the player who initiated the action preflop, or the player who made the last aggressive action on the previous street
        :return: the name of the first player to place a bet or raise on a given street, or the aggressor in the hand
        """
        # Initialize variables
        i, players = 0, {}

        # Loop through each action on the current street
        for act in actions[street]:
            # If two players have already acted, break out of the loop
            if i > 1:
                break
            # If the current action is not from the aggressor
            if act[0] != aggressor:
                # Add the player to the dictionary of players who have folded
                players[act[0]] = act[1] == 'folds'
                # If the player raised or completed the bet, break out of the loop
                if act[1] in ['raises', 'completes']:
                    break
            # If the current action is from the aggressor
            elif act[1] != 'discards':
                # Increment the number of aggressive actions on the street
                i += 1
        # Return the dictionary of players who have folded
        return players


    def lastBetOrRaiser(self, actions, street):
        """Returns the name of the player who placed the last bet, raise or completion for a given street.

        Args:
            actions (list): A list of tuples containing a player's action and the amount.
            street (str): The current street of the game.

        Returns:
            str or None: The name of the player who placed the last bet, raise or completion, or None if no bets, raises or completions occurred on the street.
        """

        lastbet = None   # Initialize variable to keep track of the last bet
        for act in actions[street]:   # Loop through all actions on the current street
            if act[1] in ('bets', 'raises', 'completes'):   # Check if the action is a bet, raise or completion
                lastbet = act[0]   # If it is, update the last bet variable with the player's name
        return lastbet   # Return the name of the player who made the last bet or raise, or None if there were none



    def noBetsBefore(self, actions, street, player):
        """
        Returns True if there were no bets before the specified player's turn, False otherwise.

        Parameters:
        actions (list): The list of actions taken during the game.
        street (str): The current street of the game.
        player (int): The player for whom we want to check if there were no bets before their turn.

        Returns:
        bool: True if there were no bets before the specified player's turn, False otherwise.
        """
        noBetsBefore = False

        # Loop through each action in the current street
        for act in actions[street]:
            # Must test for player first in case they are UTG
            if act[0] == player:
                noBetsBefore = True
                break
            # If a bet, raise, or completion is made, then there were bets before the specified player's turn
            if act[1] in ('bets', 'raises', 'completes'):
                break

        return noBetsBefore



    def betStreet(self, actions, street, player):
        """
        Returns true if player bet/raised the street as their first action.

        :param actions: A list of tuples representing the actions taken by players.
        :type actions: list
        :param street: The current betting round.
        :type street: str
        :param player: The player in question.
        :type player: int
        :return: True if the player bet/raised the street as their first action, False otherwise.
        :rtype: bool
        """
        betOrRaise = False   # Initializing the variable that keeps track of whether the player bet/raised
        for act in actions[street]:   # Looping through the actions taken during the current betting round
            if act[0] == player and act[1] not in ('discards', 'stands pat'):   # Checking if the player took an action and didn't discard or stand pat
                if act[1] in ('bets', 'raises', 'completes'):   # Checking if the player bet, raised, or completed
                    betOrRaise = True   # Setting the variable to True if the player bet/raised
                break   # Exiting the loop after the first action by the player
                #else:
                    # haven't found player's first action yet
        return betOrRaise   # Returning whether the player bet/raised

