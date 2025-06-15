#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2011 Carl Gherardi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.

# fpdb modules
from __future__ import division


# import L10n
# _ = L10n.get_translation()
import Card
from decimal import Decimal, ROUND_DOWN

from loggingFpdb import get_logger

try:
    from pokereval import PokerEval

    pokereval = PokerEval()
except Exception:
    pokereval = None


# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("parser")


def _buildStatsInitializer():
    init = {}
    # Init vars that may not be used, but still need to be inserted.
    # All stud street4 need this when importing holdem
    init["effStack"] = 0
    init["startBounty"] = None
    init["endBounty"] = None
    init["common"] = 0
    init["committed"] = 0
    init["winnings"] = 0
    init["rake"] = 0
    init["rakeDealt"] = 0
    init["rakeContributed"] = 0
    init["rakeWeighted"] = 0
    init["totalProfit"] = 0
    init["allInEV"] = 0
    init["showdownWinnings"] = 0
    init["nonShowdownWinnings"] = 0
    init["sawShowdown"] = False
    init["showed"] = False
    init["wonAtSD"] = False
    init["startCards"] = 170
    init["handString"] = None
    init["position"] = 9  # ANTE ALL IN
    init["street0CalledRaiseChance"] = 0
    init["street0CalledRaiseDone"] = 0
    init["street0VPIChance"] = True
    init["street0VPI"] = False
    init["street0AggrChance"] = True
    init["street0_2BChance"] = False
    init["street0_2BDone"] = False
    init["street0_3BChance"] = False
    init["street0_3BDone"] = False
    init["street0_4BChance"] = False
    init["street0_4BDone"] = False
    init["street0_C4BChance"] = False
    init["street0_C4BDone"] = False
    init["street0_FoldTo2BChance"] = False
    init["street0_FoldTo2BDone"] = False
    init["street0_FoldTo3BChance"] = False
    init["street0_FoldTo3BDone"] = False
    init["street0_FoldTo4BChance"] = False
    init["street0_FoldTo4BDone"] = False
    init["street0_SqueezeChance"] = False
    init["street0_SqueezeDone"] = False
    init["stealChance"] = False
    init["stealDone"] = False
    init["success_Steal"] = False
    init["raiseToStealChance"] = False
    init["raiseToStealDone"] = False
    init["raiseFirstInChance"] = False
    init["raisedFirstIn"] = False
    init["foldBbToStealChance"] = False
    init["foldSbToStealChance"] = False
    init["foldedSbToSteal"] = False
    init["foldedBbToSteal"] = False
    init["tourneyTypeId"] = None
    init["street1Seen"] = False
    init["street2Seen"] = False
    init["street3Seen"] = False
    init["street4Seen"] = False
    init["otherRaisedStreet0"] = False
    init["foldToOtherRaisedStreet0"] = False
    init["wentAllIn"] = False

    for i in range(5):
        init["street%dCalls" % i] = 0
        init["street%dBets" % i] = 0
        init["street%dRaises" % i] = 0
        init["street%dAggr" % i] = False
        init["street%dInPosition" % i] = False
        init["street%dFirstToAct" % i] = False
        init["street%dAllIn" % i] = False

    for i in range(1, 4):
        init["street%dDiscards" % i] = 0

    for i in range(1, 5):
        init["street%dCBChance" % i] = False
        init["street%dCBDone" % i] = False
        init["street%dCheckCallRaiseChance" % i] = False
        init["street%dCheckCallDone" % i] = False
        init["street%dCheckRaiseDone" % i] = False
        init["otherRaisedStreet%d" % i] = False
        init["foldToOtherRaisedStreet%d" % i] = False
        init["foldToStreet%dCBChance" % i] = False
        init["foldToStreet%dCBDone" % i] = False
        init["wonWhenSeenStreet%d" % i] = False
    return init


_INIT_STATS = _buildStatsInitializer()


class DerivedStats(object):
    def __init__(self):
        self.hands = {}
        self.handsplayers = {}
        self.handsactions = {}
        self.handsstove = []
        self.handspots = []

    def getStats(self, hand):
        for player in hand.players:
            self.handsplayers[player[1]] = _INIT_STATS.copy()

        self.assembleHands(hand)
        self.assembleHandsPlayers(hand)
        self.assembleHandsActions(hand)

        if pokereval and hand.gametype["category"] in Card.games:
            self.assembleHandsStove(hand)
            self.assembleHandsPots(hand)

    def getHands(self):
        return self.hands

    def getHandsPlayers(self):
        return self.handsplayers

    def getHandsActions(self):
        return self.handsactions

    def getHandsStove(self):
        return self.handsstove

    def getHandsPots(self):
        return self.handspots

    def assembleHands(self, hand):
        try:
            log.debug(f"Starting assembleHands for hand ID: {hand.handid}")

            # Initialize basic hand details
            self.hands["tableName"] = hand.tablename
            log.debug(f"Set tableName: {hand.tablename}")

            self.hands["siteHandNo"] = hand.handid
            log.debug(f"Set siteHandNo: {hand.handid}")

            self.hands["gametypeId"] = None  # Handled later after checking DB
            self.hands["sessionId"] = None  # Added later if caching sessions
            self.hands["gameId"] = None  # Added later if caching sessions
            self.hands["startTime"] = hand.startTime  # Ensure proper formatting
            log.debug(f"Set startTime: {hand.startTime}")

            self.hands["importTime"] = None
            self.hands["seats"] = self.countPlayers(hand)
            log.debug(f"Set seats: {self.hands['seats']}")

            self.hands["maxPosition"] = -1
            self.hands["texture"] = None  # No calculation done yet
            self.hands["tourneyId"] = hand.tourneyId
            log.debug(f"Set tourneyId: {hand.tourneyId}")

            # Determine hero seat
            self.hands["heroSeat"] = 0
            for player in hand.players:
                if hand.hero == player[1]:
                    self.hands["heroSeat"] = player[0]
                    log.debug(f"Hero found: {player[1]} at seat {player[0]}")
                    break
            else:
                log.warning("No hero found in the hand.")

            # Assemble board cards
            boardcards = []
            if hand.board.get("FLOPET") is not None:
                boardcards += hand.board.get("FLOPET")
                log.debug(f"Added FLOPET cards: {hand.board.get('FLOPET')}")

            for street in hand.communityStreets:
                if street in hand.board:
                    boardcards += hand.board[street]
                    log.debug(f"Added {street} cards: {hand.board[street]}")
                else:
                    log.warning(f"Street {street} not found in hand.board.")

            # Fill remaining board slots with placeholders
            boardcards += ["0x", "0x", "0x", "0x", "0x"]
            log.debug(f"Completed boardcards with placeholders: {boardcards}")

            # Encode first five board cards
            try:
                cards = [Card.encodeCard(c) for c in boardcards[0:5]]
                self.hands["boardcard1"] = cards[0]
                self.hands["boardcard2"] = cards[1]
                self.hands["boardcard3"] = cards[2]
                self.hands["boardcard4"] = cards[3]
                self.hands["boardcard5"] = cards[4]
                log.debug(f"Encoded board cards: {cards}")
            except IndexError as e:
                log.error(f"Error encoding board cards: {e}")
                raise

            # Initialize boards list
            self.hands["boards"] = []
            self.hands["runItTwice"] = False

            for i in range(hand.runItTimes):
                boardcards = []
                for street in hand.communityStreets:
                    boardId = i + 1
                    street_i = f"{street}{boardId}"
                    if street_i in hand.board:
                        boardcards += hand.board[street_i]
                        log.debug(f"Run {i+1}: Added {street_i} cards: {hand.board[street_i]}")
                    else:
                        log.warning(f"Run {i+1}: Street {street_i} not found in hand.board.")

                if hand.gametype.get("split"):
                    boardcards += ["0x", "0x", "0x", "0x", "0x"]
                    log.debug(f"Run {i+1}: Split game, added placeholders.")
                    try:
                        cards = [Card.encodeCard(c) for c in boardcards[:5]]
                    except IndexError as e:
                        log.error(f"Run {i+1}: Error encoding split board cards: {e}")
                        cards = ["0x"] * 5
                else:
                    self.hands["runItTwice"] = True
                    boardcards = ["0x", "0x", "0x", "0x", "0x"] + boardcards
                    log.debug(f"Run {i+1}: Non-split game, prefixed with placeholders.")
                    try:
                        cards = [Card.encodeCard(c) for c in boardcards[-5:]]
                    except IndexError as e:
                        log.error(f"Run {i+1}: Error encoding board cards: {e}")
                        cards = ["0x"] * 5

                self.hands["boards"].append([boardId] + cards)
                log.debug(f"Run {i+1}: Appended to boards: {[boardId] + cards}")

            # Calculate street totals
            try:
                totals = hand.getStreetTotals()
                totals = [int(100 * i) for i in totals]
                self.hands["street0Pot"] = totals[0]
                self.hands["street1Pot"] = totals[1]
                self.hands["street2Pot"] = totals[2]
                self.hands["street3Pot"] = totals[3]
                self.hands["street4Pot"] = totals[4]
                self.hands["finalPot"] = totals[5]
                log.debug(f"Street totals: {totals}")
            except Exception as e:
                log.error(f"Error calculating street totals: {e}")
                raise

            # Calculate VPIP
            try:
                self.vpip(hand)
                log.debug(f"VPIP calculated: {self.hands.get('playersVpi')}")
            except Exception as e:
                log.error(f"Error calculating VPIP: {e}")
                raise

            # Determine players at each street
            try:
                self.playersAtStreetX(hand)
                log.debug(
                    f"Players at streets: 1={self.hands.get('playersAtStreet1')}, "
                    f"2={self.hands.get('playersAtStreet2')}, 3={self.hands.get('playersAtStreet3')}, "
                    f"4={self.hands.get('playersAtStreet4')}, Showdown={self.hands.get('playersAtShowdown')}"
                )
            except Exception as e:
                log.error(f"Error determining players at streets: {e}")
                raise

            # Calculate raises per street
            try:
                self.streetXRaises(hand)
                log.debug(
                    f"Raises per street: street0Raises={self.hands.get('street0Raises')}, "
                    f"street1Raises={self.hands.get('street1Raises')}, "
                    f"street2Raises={self.hands.get('street2Raises')}, "
                    f"street3Raises={self.hands.get('street3Raises')}, "
                    f"street4Raises={self.hands.get('street4Raises')}"
                )
            except Exception as e:
                log.error(f"Error calculating raises per street: {e}")
                raise

            # Log hand details at debug level
            log.debug(f"Hand detail: {hand}")

        except Exception as e:
            log.error(f"Error in assembleHands for hand ID {hand.handid}: {e}")
            raise

    def assembleHandsPlayers(self, hand):
        """
        Assemble and calculate player-specific stats for a hand, including net collected, total profit,
        all-in EV, and other derived statistics. Also counts post-flop actions.
        """
        try:
            log.debug(f"Starting assembleHandsPlayers for hand ID: {hand.handid}")

            # Step 1: Initialize stats for each player (using _INIT_STATS)
            log.debug("Initializing player stats...")
            for player in hand.players:
                player_name = player[1]
                # Creates a new copy of the initialization dictionary for each player
                self.handsplayers[player_name] = _INIT_STATS.copy()
                player_stats = self.handsplayers.get(player_name)
                log.debug(f"Processing player: {player_name}")

                # --- Initialisation ---
                try:
                    player_stats["seatNo"] = player[0]
                    log.debug(f"Player {player_name} seatNo={player_stats['seatNo']}")

                    player_stats["startCash"] = int(100 * Decimal(player[2]))
                    log.debug(f"Player {player_name} startCash={player_stats['startCash']}")

                    if player[4] is not None:
                        player_stats["startBounty"] = int(100 * Decimal(player[4]))
                        player_stats["endBounty"] = int(100 * Decimal(player[4]))
                        log.debug(
                            f"Player {player_name} startBounty={player_stats['startBounty']} endBounty={player_stats['endBounty']}"
                        )

                    if player_name in hand.endBounty:
                        player_stats["endBounty"] = int(hand.endBounty.get(player_name))
                        log.debug(f"Player {player_name} endBounty updated={player_stats['endBounty']}")

                    player_stats["sitout"] = player_name in hand.sitout
                    log.debug(f"Player {player_name} sitout={player_stats['sitout']}")

                    if hand.gametype.get("type") == "tour":
                        player_stats["tourneyTypeId"] = hand.tourneyTypeId
                        player_stats["tourneysPlayersId"] = hand.tourneysPlayersIds.get(player_name)
                        log.debug(
                            f"Player {player_name} tourneyTypeId={hand.tourneyTypeId}, "
                            f"tourneysPlayersId={player_stats['tourneysPlayersId']}"
                        )
                    else:
                        player_stats["tourneysPlayersId"] = None
                        log.debug(f"Player {player_name} tourneysPlayersId=None (cash game)")

                    player_stats["showed"] = player_name in hand.shown
                    log.debug(f"Player {player_name} showed={player_stats['showed']}")
                except Exception as e:
                    log.error(f"Error initializing stats for player {player_name}: {e}")



           # post-flop share count AND streetXAggr UPDATE
            log.debug("Counting post-flop actions and updating aggression flags...")
            street_indices = {}
            relevant_streets = []
            # Determining post-flop streets
            for idx, street_name in enumerate(hand.actionStreets):
                if idx >= 2 and idx < len(hand.actionStreets): # Start after PREFLOP/DEAL/THIRD
                    numeric_street_index = idx - 1 
                    if numeric_street_index <= 4:
                       street_indices[street_name] = numeric_street_index
                       relevant_streets.append(street_name)

            log.debug(f"Relevant streets for action counting: {relevant_streets}, mapping: {street_indices}")

            for street_name in relevant_streets:
                numeric_street_index = street_indices.get(street_name)
                if numeric_street_index is None:
                    continue

                log.debug(f"Counting actions for street: {street_name} (numeric index: {numeric_street_index})")
                for action in hand.actions.get(street_name, []):
                    player_name = action[0]
                    action_type = action[1]

                    if player_name in self.handsplayers:
                        player_stats = self.handsplayers[player_name]

                        # Increment counters
                        if action_type == 'calls':
                            player_stats[f'street{numeric_street_index}Calls'] += 1
                            log.debug(f"Incremented street{numeric_street_index}Calls for {player_name}")
                        elif action_type == 'bets':
                            player_stats[f'street{numeric_street_index}Bets'] += 1
                            player_stats[f'street{numeric_street_index}Aggr'] = True
                            log.debug(f"Incremented street{numeric_street_index}Bets for {player_name}")
                        elif action_type in ('raises', 'completes'):
                            player_stats[f'street{numeric_street_index}Raises'] += 1
                            player_stats[f'street{numeric_street_index}Aggr'] = True
                            log.debug(f"Incremented street{numeric_street_index}Raises for {player_name}")
                        elif action_type == 'allin':
                            player_stats[f'street{numeric_street_index}AllIn'] = True
                            player_stats[f'street{numeric_street_index}Aggr'] = True
                            log.debug(f"Set street{numeric_street_index}AllIn and Aggr to True for {player_name}")
                        elif action_type == 'discards':
                            try:
                                num_discarded = int(action[2]) if len(action) > 2 else 0 # Recover the number of cards
                            except (IndexError, ValueError, TypeError):
                                num_discarded = 0 #Handle cases where the number is missing or invalid
                                log.warning(f"Could not determine number of discarded cards for action: {action}")

                            # Make sure the key exists before adding
                            player_stats[f'street{numeric_street_index}Discards'] = player_stats.get(f'street{numeric_street_index}Discards', 0) + num_discarded
                            log.debug(f"Added {num_discarded} to street{numeric_street_index}Discards for {player_name}")
                        # Note: 'streetXAggr' is set to True for bets, raises, and all-ins.

                    else:
                        log.warning(f"Player '{player_name}' from action not found in initialized handsplayers for street {street_name}.")
            # --- 


            # Step 2: Calculate net collected for each player
            log.debug("Calculating net collected for each player...")

            hand.net_collected = {}
            for player, committed in hand.pot.committed.items():
                try:
                    collected = hand.collectees.get(player, Decimal("0.00"))
                    uncalled_bets = hand.pot.returned.get(player, Decimal("0.00"))
                    net = collected + uncalled_bets - committed
                    hand.net_collected[player] = net
                    log.debug(
                        f"Player {player}: collected={collected}, uncalled_bets={uncalled_bets}, "
                        f"committed={committed}, net_collected={net:.2f}"
                    )
                except Exception as e:
                    log.error(f"Error calculating net collected for player {player}: {e}")


            # Step 3: Update player stats based on net collected
            log.debug("Updating player stats based on net collected...")
            for player_name, committed in hand.pot.committed.items():
                if player_name not in self.handsplayers:
                    continue 
                player_stats = self.handsplayers.get(player_name, {})
                log.debug(f"Updating stats for player: {player_name}")
                try:
                    common = hand.pot.common.get(player_name, Decimal("0.00"))
                    paid = int(100 * committed) + int(100 * common)
                    log.debug(
                        f"Player {player_name} paid: committed={int(100 * committed)}, common={int(100 * common)}"
                    )

                    player_stats["common"] = int(100 * common)
                    player_stats["committed"] = int(100 * committed)

                    net_collected = int(100 * hand.net_collected.get(player_name, Decimal("0.00"))) 
                    player_stats["totalProfit"] = net_collected
                    player_stats["winnings"] = net_collected
                    player_stats["allInEV"] = net_collected # Will be recalculated later if EV is relevant
                    log.debug(
                        f"Player {player_name} totalProfit={net_collected}, winnings={net_collected}, allInEV={net_collected}"
                    )

                    player_stats["rake"] = int(100 * hand.rake) if hand.rake is not None else 0
                    num_players = len(hand.players)
                    if num_players > 0:
                        player_stats["rakeDealt"] = int(100 * hand.rake) / num_players if hand.rake is not None else 0
                    else:
                        player_stats["rakeDealt"] = 0
                        log.warning("No players found to calculate rakeDealt!")

                    total_pot = int(100 * hand.totalpot) if hand.totalpot is not None else 0
                    if total_pot > 0:
                        player_stats["rakeWeighted"] = int(100 * hand.rake) * paid / total_pot if hand.rake is not None else 0
                    else:
                        player_stats["rakeWeighted"] = 0
                        log.warning(f"Total pot is zero. rakeWeighted for {player_name}=0")

                except ZeroDivisionError:
                    log.error(f"Division by zero calculating rakeDealt for player {player_name}. Setting to 0.")
                    player_stats["rakeDealt"] = 0
                except Exception as e:
                    log.error(f"Error updating net stats for player {player_name}: {e}")

            # Step 4: Additional calculations (rakeContributed)
            log.debug("Calculating rakeContributed...")
            contributed_players = [p for p in hand.pot.committed if hand.pot.committed[p] > 0]
            if contributed_players:
                try:
                    rake_contribution = int(100 * hand.rake) / len(contributed_players) if hand.rake is not None else 0
                    for player_name in contributed_players:
                         if player_name in self.handsplayers: 
                            self.handsplayers[player_name]["rakeContributed"] = rake_contribution
                            log.debug(f"Player {player_name} rakeContributed={rake_contribution}")
                except Exception as e:
                    log.error(f"Error calculating rakeContributed: {e}")
            else:
                log.warning("No players contributed to the pot.")

            # Step 5: Encode cards and update additional stats
            log.debug("Encoding cards and updating additional stats for each player...")
            for player in hand.players:
                player_name = player[1]
                if player_name not in self.handsplayers:
                    continue 
                player_stats = self.handsplayers.get(player_name, {})
                try:
                    hcs = hand.join_holecards(player_name, asList=True) + ["0x"] * 18
                    for i, card in enumerate(hcs[:20]):
                        encoded_card = Card.encodeCard(card)
                        player_stats[f"card{i + 1}"] = encoded_card
                        log.debug(f"Player {player_name} card{i + 1}={encoded_card}")

                    player_stats["nonShowdownWinnings"] = (
                        player_stats["totalProfit"] if not player_stats["sawShowdown"] else 0
                    )
                    player_stats["showdownWinnings"] = player_stats["totalProfit"] if player_stats["sawShowdown"] else 0
                    log.debug(
                        f"Player {player_name} nonShowdownWinnings={player_stats['nonShowdownWinnings']}, "
                        f"showdownWinnings={player_stats['showdownWinnings']}"
                    )

                    player_stats["startCards"] = Card.calcStartCards(hand, player_name)
                    log.debug(f"Player {player_name} startCards={player_stats['startCards']}")
                except IndexError as e:
                    log.error(f"IndexError encoding cards for player {player_name}: {e}")
                    player_stats["startCards"] = []
                except Exception as e:
                    log.error(f"Error encoding cards for player {player_name}: {e}")

            # Calls to functions for calculating derived statistics
            # These functions now use streetXCalls counters etc.
            log.debug("Calculating derived stats (CBets, CheckCallRaise, etc.)...")
            try:
                self.calcCBets(hand)
                log.debug("Calculated CBets.")
            except Exception as e:
                log.error(f"Error calculating CBets: {e}")

            try:
                self.calcCheckCallRaise(hand)
                log.debug("Calculated CheckCallRaise.")
            except Exception as e:
                log.error(f"Error calculating CheckCallRaise: {e}")

            try:
                self.calc34BetStreet0(hand)
                log.debug("Calculated 3/4 Bet on Street0.")
            except Exception as e:
                log.error(f"Error calculating 3/4 Bet on Street0: {e}")

            try:
                self.calcSteals(hand)
                log.debug("Calculated Steals.")
            except Exception as e:
                log.error(f"Error calculating Steals: {e}")

            try:
                self.calcCalledRaiseStreet0(hand)
                log.debug("Calculated Called Raise on Street0.")
            except Exception as e:
                log.error(f"Error calculating Called Raise on Street0: {e}")

            try:
                self.calcEffectiveStack(hand)
                self.setPositions(hand) # Must be after the calculations that depend on it
                log.debug("Calculated Effective Stack and set positions.")  
            except Exception as e:
                log.error(f"Error calculating Effective Stack: {e}")

            # Set player positions
            try:
                self.setPositions(hand)
                log.debug(f"Positions set for hand ID: {hand.handid}")
            except Exception as e:
                log.error(f"Error setting player positions for hand ID {hand.handid}: {e}")

            log.debug(f"assembleHandsPlayers completed for hand ID: {hand.handid}.")

        except Exception as e:
            log.error(f"Error in assembleHandsPlayers for hand ID {hand.handid}: {e}")
            raise

    def assembleHandsActions(self, hand):
        """
        Assemble and record all actions taken during the hand, capturing player moves, amounts, and all-in statuses.
        """
        try:
            log.debug(f"Starting assembleHandsActions for hand ID: {hand.handid}")
            k = 0
            for i, street in enumerate(hand.actionStreets):
                log.debug(f"Processing street: {street} (index: {i})")
                for j, act in enumerate(hand.actions.get(street, [])):
                    k += 1
                    log.debug(f"Processing action {k}: {act}")

                    self.handsactions[k] = {}
                    # Initialize default values
                    self.handsactions[k]["amount"] = 0
                    self.handsactions[k]["raiseTo"] = 0
                    self.handsactions[k]["amountCalled"] = 0
                    self.handsactions[k]["numDiscarded"] = 0
                    self.handsactions[k]["cardsDiscarded"] = None
                    self.handsactions[k]["allIn"] = False

                    # Insert values from hand.actions
                    player_name = act[0]
                    action_type = act[1]
                    self.handsactions[k]["player"] = player_name
                    self.handsactions[k]["street"] = i - 1
                    self.handsactions[k]["actionNo"] = k
                    self.handsactions[k]["streetActionNo"] = j + 1

                    # Safely get actionId
                    try:
                        self.handsactions[k]["actionId"] = hand.ACTION.get(action_type, None)
                        if self.handsactions[k]["actionId"] is None:
                            log.warning(f"Unknown action type '{action_type}' for player {player_name} in action {k}.")
                    except Exception as e:
                        log.error(f"Error retrieving actionId for action {k}: {e}")
                        self.handsactions[k]["actionId"] = None

                    # Handle different action types
                    if action_type not in ("discards") and len(act) > 2:
                        try:
                            self.handsactions[k]["amount"] = int(100 * act[2])
                            log.debug(
                                f"Action {k}: Set amount to {self.handsactions[k]['amount']} for player {player_name}."
                            )
                        except (TypeError, ValueError) as e:
                            log.error(f"Error converting amount for action {k}: {e}")

                    if action_type in ("raises", "completes") and len(act) > 4:
                        try:
                            self.handsactions[k]["raiseTo"] = int(100 * act[3])
                            self.handsactions[k]["amountCalled"] = int(100 * act[4])
                            log.debug(
                                f"Action {k}: Set raiseTo to {self.handsactions[k]['raiseTo']} and "
                                f"amountCalled to {self.handsactions[k]['amountCalled']} for player {player_name}."
                            )
                        except (TypeError, ValueError) as e:
                            log.error(f"Error converting raiseTo or amountCalled for action {k}: {e}")

                    if action_type in ("discards"):
                        try:
                            self.handsactions[k]["numDiscarded"] = int(act[2])
                            self.handsplayers[player_name][f"street{(i - 1)}Discards"] = int(act[2])
                            log.debug(
                                f"Action {k}: Set numDiscarded to {self.handsactions[k]['numDiscarded']} for player {player_name}."
                            )
                        except (TypeError, ValueError, IndexError) as e:
                            log.error(f"Error setting numDiscarded for action {k} and player {player_name}: {e}")

                    if action_type in ("discards") and len(act) > 3:
                        try:
                            self.handsactions[k]["cardsDiscarded"] = act[3]
                            log.debug(
                                f"Action {k}: Set cardsDiscarded to {self.handsactions[k]['cardsDiscarded']} for player {player_name}."
                            )
                        except Exception as e:
                            log.error(f"Error setting cardsDiscarded for action {k} and player {player_name}: {e}")

                    if len(act) > 3 and action_type not in ("discards"):
                        try:
                            self.handsactions[k]["allIn"] = act[-1]
                            log.debug(
                                f"Action {k}: Set allIn to {self.handsactions[k]['allIn']} for player {player_name}."
                            )
                            if act[-1]:
                                self.handsplayers[player_name]["wentAllIn"] = True
                                self.handsplayers[player_name][f"street{(i - 1)}AllIn"] = True
                                log.debug(f"Player {player_name} wentAllIn set to True for street {i - 1}.")
                        except IndexError as e:
                            log.error(f"Error accessing allIn flag for action {k} and player {player_name}: {e}")

                    # Additional validation or logging can be added here as needed

            log.debug(f"Completed assembleHandsActions for hand ID: {hand.handid}")

        except Exception as e:
            log.error(f"Error in assembleHandsActions for hand ID {hand.handid}: {e}")
            raise

    def assembleHandsStove(self, hand):
        """
        Assemble and evaluate hands for Stove analysis, calculating player equities and updating handsstove data.
        """
        try:
            log.debug(f"Starting assembleHandsStove for hand ID: {hand.handid}")

            # Extract game category and related configurations
            category = hand.gametype.get("category", "unknown")
            holecards, holeplayers = {}, []
            try:
                base, evalgame, hilo, streets, last, hrange = Card.games[category]
                log.debug(
                    f"Game configuration for category '{category}': base={base}, evalgame={evalgame}, hilo={hilo}, streets={streets}, last={last}, hrange={hrange}"
                )
            except KeyError:
                log.error(f"Unknown game category '{category}' for hand ID: {hand.handid}")
                return  # Exit the function as the category is unrecognized

            hiLoKey = {"h": [("h", "hi")], "l": [("l", "low")], "s": [("h", "hi"), ("l", "low")], "r": [("l", "hi")]}
            boards = self.getBoardsDict(hand, base, streets)

            log.debug(f"Hand category: {category}, base: {base}, evalgame: {evalgame}, hilo: {hilo}")
            log.debug(f"Extracted boards: {boards}")

            for player in hand.players:
                pname = player[1]
                hp = self.handsplayers.get(pname, {})
                log.debug(f"Processing player {pname}")

                if evalgame:
                    try:
                        hcs = hand.join_holecards(pname, asList=True)
                        holecards[pname] = {"cards": [], "eq": 0, "committed": 0}
                        holeplayers.append(pname)
                        log.debug(f"Player {pname} preflop cards: {hcs}")
                    except Exception as e:
                        log.error(f"Error joining hole cards for player {pname}: {e}")
                        continue  # Skip to the next player

                    for street, board in boards.items():
                        streetId = streets.get(street, -1)
                        streetSeen = hp.get(f"street{streetId}Seen", False) if streetId > 0 else True

                        # Condition to evaluate the hand
                        if (
                            (pname == hand.hero and streetSeen)
                            or (hp.get("showed", False) and streetSeen)
                            or hp.get("sawShowdown", False)
                            or hp.get("wentAllIn", False)
                        ):
                            log.debug(
                                f"Evaluating hand for {pname} at street '{street}' (id: {streetId}): "
                                f"streetSeen={streetSeen}, hero={pname == hand.hero}, showed={hp.get('showed', False)}, "
                                f"sawShowdown={hp.get('sawShowdown', False)}, wentAllIn={hp.get('wentAllIn', False)}"
                            )
                            boardId, hl, rankId, value, _cards = 0, "n", 1, 0, None
                            for n in range(len(board["board"])):
                                streetIdx = -1 if base == "hold" else streetId
                                try:
                                    cards = hcs[hrange[streetIdx][0] : hrange[streetIdx][1]]
                                    boardId = (n + 1) if (len(board["board"]) > 1) else n
                                    if "omaha" not in evalgame:
                                        cards += board["board"][n] if board["board"][n] else []
                                    else:
                                        bcards = board["board"][n] if board["board"][n] else []
                                        cards += bcards

                                    # Secure the cards
                                    cards = [str(c) if Card.encodeCardList.get(c) else "0x" for c in cards]
                                    bcards = (
                                        [str(b) if Card.encodeCardList.get(b) else "0x" for b in bcards]
                                        if "omaha" in evalgame
                                        else []
                                    )

                                    holecards[pname]["hole"] = cards[hrange[streetIdx][0] : hrange[streetIdx][1]]
                                    holecards[pname]["cards"] += [cards]

                                    notnull = ("0x" not in cards) and ("0x" not in bcards)
                                    postflop = base == "hold" and len(board["board"][n]) >= 3
                                    maxcards = base != "hold" and len(cards) >= 5

                                    log.debug(
                                        f"{pname}, street {streetId}, boardId {boardId}, cards: {cards}, board: {bcards}, "
                                        f"notnull={notnull}, postflop={postflop}, maxcards={maxcards}"
                                    )

                                    if notnull and (postflop or maxcards):
                                        for hl, side in hiLoKey.get(hilo, [("n", "hi")]):
                                            try:
                                                value, rank = pokereval.best(side, cards, bcards)
                                                rankId = Card.hands.get(rank[0], [1])[0] if rank else 1
                                                _cards = (
                                                    "".join([pokereval.card2string(i)[0] for i in rank[1:]])
                                                    if rank and rank[0] != "Nothing"
                                                    else None
                                                )

                                                self.handsstove.append(
                                                    [
                                                        hand.dbid_hands,
                                                        hand.dbid_pids.get(pname, 0),
                                                        streetId,
                                                        boardId,
                                                        hl,
                                                        rankId,
                                                        value,
                                                        _cards,
                                                        0,
                                                    ]
                                                )
                                                log.debug(
                                                    f"{pname} : Added result to handsstove (rankId={rankId}, value={value})"
                                                )
                                            except RuntimeError as e:
                                                log.error(
                                                    f"RuntimeError determining value and rank for hand {hand.handid}, path {hand.in_path}: {e}"
                                                )
                                                self.handsstove.append(
                                                    [
                                                        hand.dbid_hands,
                                                        hand.dbid_pids.get(pname, 0),
                                                        streetId,
                                                        boardId,
                                                        "n",
                                                        1,
                                                        0,
                                                        None,
                                                        0,
                                                    ]
                                                )
                                    else:
                                        self.handsstove.append(
                                            [
                                                hand.dbid_hands,
                                                hand.dbid_pids.get(pname, 0),
                                                streetId,
                                                boardId,
                                                "n",
                                                1,
                                                0,
                                                None,
                                                0,
                                            ]
                                        )
                                        log.debug(f"{pname} : No valid combination, added default value to handsstove.")
                                except Exception as e:
                                    log.error(f"Error processing street '{street}' for player {pname}: {e}")
                else:
                    hl, streetId = hiLoKey.get(hilo, [("n", "low")])[0][0], 0
                    if hp.get("sawShowdown", False) or hp.get("showed", False) or hp.get("wentAllIn", False):
                        hp["handString"] = hand.showdownStrings.get(pname, "")
                        streetId = streets.get(last, 0)
                    self.handsstove.append(
                        [hand.dbid_hands, hand.dbid_pids.get(pname, 0), streetId, 0, hl, 1, 0, None, 0]
                    )
                    log.debug(f"{pname} : No evalgame, added simplified entry to handsstove.")

            # If in hold and evalgame, calculate All-In EV
            if base == "hold" and evalgame:
                try:
                    log.debug("Calculating All-In EV for the hand.")
                    self.getAllInEV(hand, evalgame, holeplayers, boards, streets, holecards)
                except Exception as e:
                    log.error(f"Error calculating All-In EV for hand {hand.handid}: {e}")

            log.debug(f"Completed assembleHandsStove for hand ID: {hand.handid}")

        except Exception as e:
            log.error(f"Error in assembleHandsStove for hand ID {hand.handid}: {e}")
            raise

    def getAllInEV(self, hand, evalgame, holeplayers, boards, streets, holecards):
        log.debug(f"Starting getAllInEV for hand {hand.handid}")
        startstreet, potId, allInStreets, allplayers = None, 0, hand.allStreets[1:], []

        for pot, players in hand.pot.pots:
            log.debug(f"Pot {potId}: amount={pot}, players={players}")
            if potId == 0:
                pot += sum(hand.pot.common.values()) + hand.pot.stp
                log.debug(f"Main pot adjusted to {pot}")
            potId += 1
            for street in allInStreets:
                board = boards[street]
                streetId = streets[street]
                log.debug(f"Street {street} (id: {streetId}), board: {board['board']}")

                for n in range(len(board["board"])):
                    boardId = n + 1 if len(board["board"]) > 1 else n

                    # Modified condition: Include all-in players (wentAllIn) in valid
                    # if their hand is known (no '0x'), to calculate EV.
                    valid = [
                        p
                        for p in players
                        if (self.handsplayers[p]["sawShowdown"] or self.handsplayers[p]["wentAllIn"])
                        and "0x" not in holecards[p]["cards"][n]
                    ]

                    log.debug(f"BoardId {boardId}: valid showdown or all-in players: {valid}")
                    if not valid:
                        log.warning(
                            "No valid players found. Either no one saw the showdown, is all-in, or the cards are unknown (0x)."
                        )

                    if potId == 1:
                        allplayers = valid
                        deadcards, deadplayers = [], []
                        log.debug(f"Initial players set (allplayers): {allplayers}")
                    else:
                        deadplayers = [d for d in allplayers if d not in valid]
                        _deadcards = [holecards[d]["hole"] for d in deadplayers]
                        deadcards = [item for sublist in _deadcards for item in sublist]
                        log.debug(f"Eliminated players: {deadplayers}, dead cards: {deadcards}")

                    # Condition for calculating equities
                    # Check if all players in the current pot are in valid
                    # and if the board is all-in or the hand is public.
                    # This allows EV calculation when players are all-in.
                    if len(players) == len(valid) and (board["allin"] or hand.publicDB):
                        log.debug(
                            f"All pot players are valid, all-in, or public. board['allin']={board['allin']}, hand.publicDB={hand.publicDB}"
                        )
                        if board["allin"] and not startstreet:
                            startstreet = street
                            log.debug(f"Setting startstreet to {startstreet}")

                        if len(valid) > 1:
                            try:
                                pockets = [holecards[p]["hole"] for p in valid]
                                log.debug(
                                    f"Calculating equities with poker_eval: game={evalgame}, pockets={pockets}, dead={deadcards}"
                                )
                                evs = pokereval.poker_eval(
                                    game=evalgame,
                                    iterations=Card.iter[streetId],
                                    pockets=pockets,
                                    dead=deadcards,
                                    board=[str(b) for b in board["board"][n]] + (5 - len(board["board"][n])) * ["__"],
                                )
                                equities = [e["ev"] for e in evs["eval"]]
                                log.debug(f"Calculated equities: {equities}")
                            except RuntimeError as e:
                                log.error(
                                    f"getAllInEV: Error running poker_eval for hand {hand.handid} {hand.in_path}: {e}"
                                )
                                equities = [1000]
                        else:
                            equities = [1000]
                            log.debug("Only one valid player, default equity = [1000]")

                        # Adjust equities if necessary
                        total_equity = sum(equities)
                        if total_equity != 1000:
                            remainder = (1000 - total_equity) / Decimal(len(equities))
                            log.debug(f"Adjusting equities with remainder={remainder}")
                            for i in range(len(equities)):
                                equities[i] += remainder
                                log.debug(f"Adjusted equity for player {valid[i]}: {equities[i]}")

                        for i, p in enumerate(valid):
                            pid = hand.dbid_pids[p]
                            if street == startstreet:
                                rake = (
                                    Decimal(0)
                                    if hand.cashedOut
                                    else (hand.rake * (Decimal(pot) / Decimal(hand.totalpot)))
                                )
                                holecards[p]["eq"] += ((pot - rake) * equities[i]) / Decimal(10)
                                holecards[p]["committed"] = 100 * hand.pot.committed[p] + 100 * hand.pot.common[p]
                                log.debug(
                                    f"{p}: Updated eq={holecards[p]['eq']} and committed={holecards[p]['committed']}"
                                )

                            for j in self.handsstove:
                                # Update values in handsstove
                                if [pid, streetId, boardId] == j[1:4] and len(valid) == len(hand.pot.contenders):
                                    j[-1] = equities[i]
                                    log.debug(
                                        f"Updated handsstove for {p}, streetId={streetId}, boardId={boardId}, equity={equities[i]}"
                                    )
                    else:
                        log.debug(
                            f"EV calculation conditions not met here. len(players)={len(players)}, len(valid)={len(valid)}, board['allin']={board['allin']}, hand.publicDB={hand.publicDB}"
                        )

        # Final allInEV calculation
        for p in holeplayers:
            if holecards[p]["committed"] != 0:
                self.handsplayers[p]["allInEV"] = holecards[p]["eq"] - holecards[p]["committed"]
                log.debug(f"{p}: Final allInEV calculation = {self.handsplayers[p]['allInEV']}")

        log.debug("Completed getAllInEV")

    def getBoardsList(self, hand):
        log.debug(f"Starting getBoardsList for hand {hand.handid}")
        boards, community = [], []

        try:
            if hand.gametype.get("base") == "hold":
                log.debug("Game type is 'hold'. Processing community streets.")
                for s in hand.communityStreets:
                    if s in hand.board:
                        community += hand.board[s]
                        log.debug(f"Added cards from street '{s}': {hand.board[s]}")
                    else:
                        log.warning(f"Street '{s}' not found in hand.board.")

                log.debug(f"Community cards accumulated: {community}")

                for i in range(hand.runItTimes):
                    boardcards = []
                    log.debug(f"Processing run {i + 1}/{hand.runItTimes}")
                    for street in hand.communityStreets:
                        boardId = i + 1
                        street_i = f"{street}{boardId}"
                        if street_i in hand.board:
                            boardcards += hand.board[street_i]
                            log.debug(f"Run {i + 1}: Added cards from '{street_i}': {hand.board[street_i]}")
                        else:
                            log.warning(f"Run {i + 1}: Street '{street_i}' not found in hand.board.")

                    cards = [str(c) for c in community + boardcards]
                    log.debug(f"Run {i + 1}: Combined community and board cards: {cards}")
                    boards.append(cards)

            if not boards:
                log.debug("No boards generated from runs. Using community cards only.")
                boards = [community]
                log.debug(f"Final boards list: {boards}")
            else:
                log.debug(f"Final boards list generated from runs: {boards}")

        except Exception as e:
            log.error(f"getBoardsList: Unexpected error for hand {hand.handid}: {e}", exc_info=True)
            # Depending on desired behavior, you might want to re-raise the exception or handle it accordingly
            raise

        log.debug(f"Completed getBoardsList for hand {hand.handid}")
        return boards

    def getBoardsDict(self, hand, base, streets):
        log.debug(f"Starting getBoardsDict for hand {hand.handid}, base={base}")
        boards, boardcards, allInStreets, showdown = {}, [], hand.allStreets[1:], False

        # Determine if any player saw the showdown
        for player in hand.players:
            pname = player[1]
            if self.handsplayers[pname]["sawShowdown"]:
                showdown = True
                log.debug(f"Player {pname} saw the showdown.")
                break  # No need to check further once showdown is confirmed

        if base == "hold":
            log.debug("Base game type is 'hold'. Processing all-in streets.")
            for s in allInStreets:
                if s not in streets:
                    log.warning(f"Street '{s}' not found in streets dictionary.")
                    continue

                streetId = streets[s]
                log.debug(f"Processing street '{s}' with streetId={streetId}.")

                try:
                    # Flatten the list of board cards up to the current street
                    b = [
                        x
                        for sublist in [hand.board[k] for k in allInStreets[: streetId + 1] if k in hand.board]
                        for x in sublist
                    ]
                    boards[s] = {"board": [b], "allin": False}
                    boardcards += hand.board.get(s, [])
                    log.debug(f"Added board cards for street '{s}': {hand.board.get(s, [])}")
                except KeyError as e:
                    log.error(f"Missing board information for street '{s}': {e}")
                    continue

                # Original logic retention: Mark streets as all-in if no actions and showdown occurred
                if not hand.actions.get(s) and showdown:
                    if streetId > 0 and allInStreets[streetId - 1] in boards:
                        boards[allInStreets[streetId - 1]]["allin"] = True
                        log.debug(f"Marked previous street '{allInStreets[streetId - 1]}' as all-in.")
                    boards[s]["allin"] = True
                    log.debug(f"Marked current street '{s}' as all-in.")

            # Initialize boardStreets for run iterations
            boardStreets = [[] for _ in range(3)]  # Assuming maximum 3 streets for run iterations
            log.debug(f"Initialized boardStreets: {boardStreets}")

            for i in range(hand.runItTimes):
                runitcards = []
                log.debug(f"Processing run iteration {i + 1}/{hand.runItTimes}.")
                for street in hand.communityStreets:
                    street_i = f"{street}{i + 1}"
                    if street_i in hand.board:
                        runitcards += hand.board[street_i]
                        log.debug(f"Run {i + 1}: Added cards from '{street_i}': {hand.board[street_i]}")
                    else:
                        log.warning(f"Run {i + 1}: Street '{street_i}' not found in hand.board.")

                # Calculate the street index for boardStreets
                sId = len(boardcards + runitcards) - 3
                log.debug(f"Run {i + 1}: Calculated sId={sId} for boardStreets.")

                if 0 <= sId < len(boardStreets):
                    boardStreets[sId].append(boardcards + runitcards)
                    log.debug(f"Run {i + 1}: Updated boardStreets[{sId}] with cards: {boardcards + runitcards}")
                else:
                    log.warning(f"Run {i + 1}: sId={sId} is out of range for boardStreets.")

            # Assign the collected run iterations to the boards
            for i, street in enumerate(allInStreets[1:], start=1):
                if i < len(boardStreets) and boardStreets[i]:
                    boards[street]["board"] = boardStreets[i]
                    log.debug(f"Assigned boardStreets[{i}] to street '{street}': {boardStreets[i]}")
                elif street in boards:
                    log.debug(f"No additional board cards for street '{street}' from runs.")

        else:
            log.debug(f"Base game type is '{base}'. Initializing empty boards for all-in streets.")
            for s in allInStreets:
                if s in streets:
                    boards[s] = {"board": [[]], "allin": False}
                    log.debug(f"Initialized board for street '{s}': {boards[s]}")
                else:
                    log.warning(f"Street '{s}' not found in streets dictionary.")

        # ---- Detection of Multiway All-In ----
        log.debug("Detecting multiway all-in scenarios in getBoardsDict.")
        for s in allInStreets:
            if s not in boards:
                log.debug(f"Street '{s}' not present in boards. Skipping all-in detection.")
                continue
            if boards[s]["allin"]:
                log.debug(f"Street '{s}' is already marked as all-in. Continuing to next street.")
                continue

            streetId = streets[s]
            log.debug(f"Checking all-in status for street '{s}' with streetId={streetId}.")

            # Determine alive players after this street
            alive_players = set()
            log.debug(f"Determining alive players for street '{s}'.")
            for p in hand.players:
                pname = p[1]
                folded_earlier = False
                for street_action in hand.actionStreets:
                    if street_action in streets and streets[street_action] < streetId:
                        folds = self.pfba(hand.actions.get(street_action, []), f=None, limit_actions=("folds",))
                        if pname in folds:
                            folded_earlier = True
                            log.debug(f"Player {pname} folded earlier at street '{street_action}'.")
                            break
                if not folded_earlier:
                    alive_players.add(pname)
                    log.debug(f"Player {pname} is still alive for street '{s}'.")

            log.debug(f"Alive players on street '{s}': {alive_players}")

            if not alive_players:
                log.warning(f"No alive players found for street '{s}'. Cannot mark as all-in.")
                continue

            # Check if all alive players are all-in
            all_allin = True
            for pname in alive_players:
                wp = self.handsplayers[pname]["wentAllIn"]
                log.debug(f"Player {pname} wentAllIn={wp}")
                if not wp:
                    all_allin = False
                    log.debug(f"Player {pname} is not all-in.")
                    break

            if all_allin:
                boards[s]["allin"] = True
                log.debug(f"All alive players are all-in at street '{s}'. Marked board['allin']=True.")
            else:
                log.debug(f"Not all alive players are all-in at street '{s}'. board['allin'] remains False.")

        log.debug(f"Completed getBoardsDict for hand {hand.handid}. Final boards: {boards}")
        return boards

    def awardPots(self, hand):
        holeshow = True
        base, evalgame, hilo, streets, last, hrange = Card.games[hand.gametype["category"]]
        for pot, players in hand.pot.pots:
            for p in players:
                hcs = hand.join_holecards(p, asList=True)
                holes = [
                    str(c)
                    for c in hcs[hrange[-1][0] : hrange[-1][1]]
                    if Card.encodeCardList.get(c) is not None or c == "0x"
                ]
                # log.error((p, holes))
                if "0x" in holes:
                    holeshow = False
        factor = 100
        if (
            hand.gametype["type"] == "tour"
            or (
                hand.gametype["type"] == "ring"
                and (hand.gametype["currency"] == "play" and (hand.sitename not in ("Winamax", "PacificPoker")))
            )
        ) and (not [n for (n, v) in hand.pot.pots if (n % Decimal("1.00")) != 0]):
            factor = 1
        hiLoKey = {"h": ["hi"], "l": ["low"], "r": ["low"], "s": ["hi", "low"]}
        # log.error((len(hand.pot.pots)>1, evalgame, holeshow))
        if pokereval and len(hand.pot.pots) > 1 and evalgame and holeshow:  # hrange
            hand.collected = []  # list of ?
            hand.collectees = {}  # dict from player names to amounts collected (?)
            # rakes, totrake, potId = {}, 0, 0
            potId = 0
            totalrake = hand.rakes.get("rake")
            if not totalrake:
                totalpot = hand.rakes.get("pot")
                if totalpot:
                    totalrake = hand.totalpot - totalpot
                else:
                    totalrake = 0
            for pot, players in hand.pot.pots:
                if potId == 0:
                    pot += sum(hand.pot.common.values()) + hand.pot.stp
                potId += 1
                # boards, boardId, sumpot = self.getBoardsList(hand), 0, 0
                boards, boardId = self.getBoardsList(hand), 0
                for b in boards:
                    boardId += hand.runItTimes >= 2
                    potBoard = Decimal(int(pot / len(boards) * factor)) / factor
                    modBoard = pot - potBoard * len(boards)
                    if boardId == 1:
                        potBoard += modBoard
                    holeplayers, holecards = [], []
                    for p in players:
                        hcs = hand.join_holecards(p, asList=True)
                        holes = [
                            str(c)
                            for c in hcs[hrange[-1][0] : hrange[-1][1]]
                            if Card.encodeCardList.get(c) is not None or c == "0x"
                        ]
                        board = [str(c) for c in b if "omaha" in evalgame]
                        if "omaha" not in evalgame:
                            holes = holes + [str(c) for c in b if base == "hold"]
                        if "0x" not in holes and "0x" not in board:
                            holecards.append(holes)
                            holeplayers.append(p)
                    if len(holecards) > 1:
                        try:
                            win = pokereval.winners(game=evalgame, pockets=holecards, board=board)
                        except RuntimeError:
                            # log.error((evalgame, holecards, board))
                            log.error(f"awardPots: error evaluating winners for hand {hand.handid} {hand.in_path}")
                            win = {}
                            win[hiLoKey[hilo][0]] = [0]
                    else:
                        win = {}
                        win[hiLoKey[hilo][0]] = [0]
                    for hl in hiLoKey[hilo]:
                        if hl in win and len(win[hl]) > 0:
                            potHiLo = Decimal(int(potBoard / len(win) * factor)) / factor
                            modHiLo = potBoard - potHiLo * len(win)
                            if len(win) == 1 or hl == "hi":
                                potHiLo += modHiLo
                            potSplit = Decimal(int(potHiLo / len(win[hl]) * factor)) / factor
                            modSplit = potHiLo - potSplit * len(win[hl])
                            pnames = players if len(holeplayers) == 0 else [holeplayers[w] for w in win[hl]]
                            for p in pnames:
                                ppot = potSplit
                                if modSplit > 0:
                                    cent = Decimal("0.01") * (100 / factor)
                                    ppot += cent
                                    modSplit -= cent
                                rake = (totalrake * (ppot / hand.totalpot)).quantize(
                                    Decimal("0.01"), rounding=ROUND_DOWN
                                )
                                hand.addCollectPot(player=p, pot=(ppot - rake))

    def assembleHandsPots(self, hand):
        log.debug(f"Starting assembleHandsPots for hand {hand.handid}")

        # Initialization
        category = hand.gametype.get("category", "Unknown")
        positions = []
        playersPots = {}
        potFound = {}
        positionDict = {}
        showdown = False

        log.debug(f"Game category: {category}")

        # Initialize player's pot dictionary
        for p in hand.players:
            pname = p[1]
            playersPots[pname] = [Decimal("0.00"), []]
            potFound[pname] = [Decimal("0.00"), Decimal("0.00")]
            position = self.handsplayers[pname].get("position", "Unknown")

            if not position:
                log.warning(f"Player {pname} has no position. Setting to 'Unknown'.")
                position = "Unknown"

            positionDict[str(position)] = pname
            positions.append(str(position))
            log.debug(f"Player {pname}: position={position}")

            if self.handsplayers[pname].get("sawShowdown", False):
                showdown = True
                log.debug(f"Player {pname} saw the showdown.")

        log.debug(f"Position Dictionary: {positionDict}")
        log.debug(f"Positions before sorting: {positions}")

        # Sort positions in reverse order
        positions.sort(reverse=True)
        log.debug(f"Positions after sorting: {positions}")

        # Define factor based on game type and conditions
        factor = Decimal("100")
        gametype_type = hand.gametype.get("type", "")
        gametype_currency = hand.gametype.get("currency", "")
        sitename = hand.sitename

        condition = (
            gametype_type == "tour"
            or (gametype_type == "ring" and gametype_currency == "play" and sitename not in ("Winamax", "PacificPoker"))
        ) and not any((n % Decimal("1.00")) != 0 for (n, v) in hand.pot.pots)

        if condition:
            factor = Decimal("1")
            log.debug("Factor set to 1 based on game type and pot conditions.")
        else:
            log.debug(f"Factor remains at {factor}.")

        # Configure game settings
        hiLoKey = {"h": ["hi"], "l": ["low"], "r": ["low"], "s": ["hi", "low"]}
        game_settings = Card.games.get(category, ("hold", "default_game", "h", {}, [], {}))
        base, evalgame, hilo, streets, last, hrange = game_settings
        log.debug(f"Game settings: base={base}, evalgame={evalgame}, hilo={hilo}, streets={streets}, hrange={hrange}")

        # Process pots
        if (
            (sitename != "KingsClub" or hand.adjustCollected)
            and evalgame
            and (len(hand.pot.pots) > 1 or (showdown and (hilo == "s" or hand.runItTimes >= 2)))
        ):
            log.debug("Processing multiple pots based on conditions.")
            potId = 0
            for pot, players in hand.pot.pots:
                log.debug(f"Processing potId {potId}: amount={pot}, players={players}")
                if potId == 0:
                    additional_pot = sum(hand.pot.common.values()) + hand.pot.stp
                    pot += additional_pot
                    log.debug(f"Main pot adjusted by adding common pot and stp: +{additional_pot} => {pot}")
                potId += 1

                # Retrieve boards for the current pot
                boards = self.getBoardsList(hand)
                boardId = 0
                log.debug(f"Boards for potId {potId}: {boards}")

                for b in boards:
                    boardId += 1 if hand.runItTimes >= 2 else 0
                    potBoard = (Decimal(int(pot / len(boards) * factor)) / factor).quantize(Decimal("0.01"))
                    modBoard = pot - (potBoard * len(boards))
                    if boardId == 1:
                        potBoard += modBoard
                        log.debug(f"First boardId {boardId}: Adjusted potBoard with modBoard: {potBoard}")

                    holeplayers, holecards = [], []
                    for p in players:
                        hcs = hand.join_holecards(p, asList=True)
                        holes = [
                            str(c)
                            for c in hcs[hrange[-1][0] : hrange[-1][1]]
                            if Card.encodeCardList.get(c) is not None or c == "0x"
                        ]
                        board = [str(c) for c in b if "omaha" in evalgame]
                        if "omaha" not in evalgame:
                            holes += [str(c) for c in b if base == "hold"]

                        if "0x" not in holes and "0x" not in board:
                            holecards.append(holes)
                            holeplayers.append(p)
                            log.debug(f"Player {p}: holecards={holes}, board={board}")

                    if len(holecards) > 1:
                        try:
                            log.debug(f"Evaluating winners with pokereval for potId {potId}, boardId {boardId}")
                            win = pokereval.winners(game=evalgame, pockets=holecards, board=board)
                            log.debug(f"Winners determined: {win}")
                        except RuntimeError as e:
                            log.error(f"Error evaluating winners for hand {hand.handid} at path {hand.in_path}: {e}")
                            win = {}
                            win[hiLoKey[hilo][0]] = [0]
                    else:
                        log.debug("Only one player with valid holecards. Assigning default winner.")
                        win = {}
                        win[hiLoKey[hilo][0]] = [0]

                    for hl in hiLoKey.get(hilo, []):
                        if hl in win and len(win[hl]) > 0:
                            potHiLo = (Decimal(int(potBoard / len(win) * factor)) / factor).quantize(Decimal("0.01"))
                            modHiLo = potBoard - (potHiLo * len(win))
                            if len(win) == 1 or hl == "hi":
                                potHiLo += modHiLo
                                potSplit = (Decimal(int(potHiLo / len(win[hl]) * factor)) / factor).quantize(
                                    Decimal("0.01")
                                )
                            else:
                                potSplit = (Decimal(int(potHiLo / len(win[hl]) * factor)) / factor).quantize(
                                    Decimal("0.01")
                                )

                            modSplit = potHiLo - (potSplit * len(win[hl]))
                            pnames = players if not holeplayers else [holeplayers[w] for w in win[hl]]
                            log.debug(f"Pot split for {hl}: potSplit={potSplit}, modSplit={modSplit}, pnames={pnames}")

                            for n in positions:
                                pname = positionDict.get(n)
                                if pname in pnames:
                                    ppot = potSplit
                                    if modSplit > 0:
                                        cent = Decimal("0.01") * (Decimal("100") / factor)
                                        ppot += cent
                                        modSplit -= cent
                                        log.debug(
                                            f"Adjusted potSplit for player {pname} by cent={cent}. New ppot={ppot}"
                                        )

                                    playersPots[pname][0] += ppot
                                    potFound[pname][0] += ppot
                                    data = {
                                        "potId": potId,
                                        "boardId": boardId,
                                        "hiLo": hl,
                                        "ppot": ppot,
                                        "winners": [m for m in pnames if m != pname],
                                        "mod": ppot > potSplit,
                                    }
                                    playersPots[pname][1].append(data)
                                    self.handsplayers[pname]["rake"] = 0
                                    log.debug(f"Updated playersPots for {pname}: {playersPots[pname]}")

                    log.debug(f"Completed processing boardId {boardId} for potId {potId}")

            # Finalizing pot distributions
            log.debug("Finalizing pot distributions for all players.")
            for p, (total, info) in playersPots.items():
                if hand.collectees.get(p) and info:
                    potFound[p][1] = hand.collectees.get(p)
                    log.debug(f"Player {p} has collectees: {hand.collectees[p]}")
                    for item in info:
                        split = [
                            n
                            for n in item["winners"]
                            if len(playersPots.get(n, [0, []])[1]) == 1 and hand.collectees.get(n) is not None
                        ]
                        log.debug(f"Processing pot split for player {p}: item={item}, split={split}")

                        if len(info) == 1:
                            ppot = item["ppot"]
                            rake = ppot - hand.collectees[p]
                            collected = hand.collectees[p]
                            log.debug(f"Single pot split: ppot={ppot}, collected={collected}, rake={rake}")
                        elif item == info[-1]:
                            ppot, collected = potFound[p]
                            rake = ppot - collected
                            log.debug(f"Last pot split: ppot={ppot}, collected={collected}, rake={rake}")
                        elif split and not item["mod"]:
                            ppot = item["ppot"]
                            collected = min([hand.collectees[s] for s in split] + [ppot])
                            rake = ppot - collected
                            log.debug(f"Partial pot split: ppot={ppot}, collected={collected}, rake={rake}")
                        else:
                            ppot = item["ppot"]
                            totalrake = total - hand.collectees[p]
                            rake = (totalrake * (ppot / total)).quantize(Decimal("0.01"))
                            collected = ppot - rake
                            log.debug(f"General pot split: ppot={ppot}, collected={collected}, rake={rake}")

                        potFound[p][0] -= ppot
                        potFound[p][1] -= collected
                        insert = [
                            None,
                            item["potId"],
                            item["boardId"],
                            item["hiLo"][0],
                            hand.dbid_pids.get(p, 0),
                            int(ppot * 100),
                            int(collected * 100),
                            int(rake * 100),
                        ]
                        self.handspots.append(insert)
                        self.handsplayers[p]["rake"] += int(rake * 100)
                        log.debug(f"Inserted handspot for player {p}: {insert}")

            log.debug(f"Completed assembleHandsPots for hand {hand.handid}")

    def setPositions(self, hand):
        """Sets the position for each player in HandsPlayers
        any blinds are negative values, and the last person to act on the
        first betting round is 0
        NOTE: HU, both values are negative for non-stud games
        NOTE2: I've never seen a HU stud match"""
        actions = hand.actions[hand.holeStreets[0]]
        # Note:  pfbao list may not include big blind if all others folded
        players = self.pfbao(actions)

        # set blinds first, then others from pfbao list, avoids problem if bb
        # is missing from pfbao list or if there is no small blind
        sb, bb, bi, ub, st = False, False, False, False, False
        if hand.gametype["base"] == "stud":
            # Stud position is determined after cards are dealt
            # First player to act is always the bring-in position in stud
            # even if they decided to bet/completed
            if len(hand.actions[hand.actionStreets[1]]) > 0:
                bi = [hand.actions[hand.actionStreets[1]][0][0]]
            # else:
            # TODO fix: if ante all and no actions and no bring in
            #    bi = [hand.actions[hand.actionStreets[0]][0][0]]
        else:
            ub = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "button blind"]
            bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "big blind"]
            sb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "small blind"]
            st = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "straddle"]

        # if there are > 1 sb or bb only the first is used!
        if ub:
            self.handsplayers[ub[0]]["street0InPosition"] = True
            if ub[0] not in players:
                players.append(ub[0])
        if bb:
            self.handsplayers[bb[0]]["position"] = "B"
            self.handsplayers[bb[0]]["street0InPosition"] = True
            if bb[0] in players:
                players.remove(bb[0])
        if sb:
            self.handsplayers[sb[0]]["position"] = "S"
            self.handsplayers[sb[0]]["street0FirstToAct"] = True
            if sb[0] in players:
                players.remove(sb[0])
        if bi:
            self.handsplayers[bi[0]]["position"] = "S"
            self.handsplayers[bi[0]]["street0FirstToAct"] = True
            if bi[0] in players:
                players.remove(bi[0])
        if st and st[0] in players:
            players.insert(0, players.pop())

        # print "DEBUG: actions: '%s'" % actions
        # print "DEBUG: ub: '%s' bb: '%s' sb: '%s' bi: '%s' plyrs: '%s'" %(ub, bb, sb, bi, players)
        for i, player in enumerate(reversed(players)):
            self.handsplayers[player]["position"] = i
            self.hands["maxPosition"] = i
            if i == 0 and hand.gametype["base"] == "stud":
                self.handsplayers[player]["street0InPosition"] = True
            elif (i - 1) == len(players):
                self.handsplayers[player]["street0FirstToAct"] = True

    def assembleHudCache(self, hand):
        # No real work to be done - HandsPlayers data already contains the correct info
        pass

    def vpip(self, hand):
        vpipers = set()
        bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] in ("big blind", "button blind")]
        for act in hand.actions[hand.actionStreets[1]]:
            if act[1] in ("calls", "bets", "raises", "completes"):
                vpipers.add(act[0])

        self.hands["playersVpi"] = len(vpipers)

        for player in hand.players:
            pname = player[1]
            player_stats = self.handsplayers.get(pname)
            if pname in vpipers:
                player_stats["street0VPI"] = True
            elif pname in hand.sitout:
                player_stats["street0VPIChance"] = False
                player_stats["street0AggrChance"] = False

        if len(vpipers) == 0 and bb:
            self.handsplayers[bb[0]]["street0VPIChance"] = False
            self.handsplayers[bb[0]]["street0AggrChance"] = False

    def playersAtStreetX(self, hand):
        """playersAtStreet1 SMALLINT NOT NULL,   /* num of players seeing flop/street4/draw1 */"""
        # self.actions[street] is a list of all actions in a tuple, contining the player name first
        # [ (player, action, ....), (player2, action, ...) ]
        # The number of unique players in the list per street gives the value for playersAtStreetXXX

        # FIXME?? - This isn't couting people that are all in - at least showdown needs to reflect this
        #     ... new code below hopefully fixes this
        # partly fixed, allins are now set as seeing streets because they never do a fold action

        self.hands["playersAtStreet1"] = 0
        self.hands["playersAtStreet2"] = 0
        self.hands["playersAtStreet3"] = 0
        self.hands["playersAtStreet4"] = 0
        self.hands["playersAtShowdown"] = 0

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

        p_in = set([x[0] for x in hand.actions[hand.actionStreets[1]]])
        # Add in players who were allin blind
        if hand.pot.pots:
            if len(hand.pot.pots[0][1]) > 1:
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

        for i, street in enumerate(hand.actionStreets):
            if (i - 1) in (1, 2, 3, 4):
                # p_in stores players with cards at start of this street,
                # so can set streetxSeen & playersAtStreetx with this information
                # This hard-coded for i-1 =1,2,3,4 because those are the only columns
                # in the db! this code section also replaces seen() - more info log 66
                # nb i=2=flop=street1Seen, hence i-1 term needed
                self.hands["playersAtStreet%d" % (i - 1)] = len(p_in)
                for player_with_cards in p_in:
                    self.handsplayers[player_with_cards]["street%sSeen" % (i - 1)] = True

                players = self.pfbao(hand.actions[street], f=("discards", "stands pat"))
                if len(players) > 0:
                    self.handsplayers[players[0]]["street%dFirstToAct" % (i - 1)] = True
                    self.handsplayers[players[-1]]["street%dInPosition" % (i - 1)] = True
            #
            # find out who folded, and eliminate them from p_in
            #
            actions = hand.actions[street]
            p_in = p_in - self.pfba(actions, ("folds",))
            #
            # if everyone folded, we are done, so exit this method
            #
            if len(p_in) == 1:
                if (i - 1) in (1, 2, 3, 4) and len(players) > 0 and list(p_in)[0] not in players:
                    # corrects which player is "in position"
                    # if everyone folds before the last player could act
                    self.handsplayers[players[-1]]["street%dInPosition" % (i - 1)] = False
                    self.handsplayers[list(p_in)[0]]["street%dInPosition" % (i - 1)] = True
                return None

        #
        # The remaining players in p_in reached showdown (including all-ins
        # because they never did a "fold" action in pfba() above)
        #
        self.hands["playersAtShowdown"] = len(p_in)
        for showdown_player in p_in:
            self.handsplayers[showdown_player]["sawShowdown"] = True

    def streetXRaises(self, hand):
        # self.actions[street] is a list of all actions in a tuple, contining the action as the second element
        # [ (player, action, ....), (player2, action, ...) ]
        # No idea what this value is actually supposed to be
        # In theory its "num small bets paid to see flop/street4, including blind" which makes sense for limit. Not so useful for nl
        # Leaving empty for the moment,

        for i in range(5):
            self.hands["street%dRaises" % i] = 0

        for i, street in enumerate(hand.actionStreets[1:]):
            self.hands["street%dRaises" % i] = len(
                [action for action in hand.actions[street] if action[1] in ("raises", "bets", "completes")]
            )

    def calcSteals(self, hand):
        """Fills raiseFirstInChance|raisedFirstIn, fold(Bb|Sb)ToSteal(Chance|)

        Steal attempt - open raise on positions 1 0 S - i.e. CO, BU, SB
                        (note: I don't think PT2 counts SB steals in HU hands, maybe we shouldn't?)
        Fold to steal - folding blind after steal attemp wo any other callers or raisers
        """
        steal_attempt = False
        raised = False
        stealer = ""
        if hand.gametype["base"] == "stud":
            steal_positions = (2, 1, 0)
        elif len([x for x in hand.actions[hand.actionStreets[0]] if x[1] == "button blind"]) > 0:
            steal_positions = (3, 2, 1)
        else:
            steal_positions = (1, 0, "S")
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act = action[0], action[1]
            player_stats = self.handsplayers.get(pname)
            if player_stats["sitout"]:
                continue
            posn = player_stats["position"]
            # print "\naction:", action[0], posn, type(posn), steal_attempt, act
            if posn == "B":
                # NOTE: Stud games will never hit this section
                if steal_attempt:
                    player_stats["foldBbToStealChance"] = True
                    player_stats["raiseToStealChance"] = True
                    player_stats["foldedBbToSteal"] = act == "folds"
                    player_stats["raiseToStealDone"] = act == "raises"
                    self.handsplayers[stealer]["success_Steal"] = act == "folds"
                break
            elif posn == "S":
                player_stats["raiseToStealChance"] = steal_attempt
                player_stats["foldSbToStealChance"] = steal_attempt
                player_stats["foldedSbToSteal"] = steal_attempt and act == "folds"
                player_stats["raiseToStealDone"] = steal_attempt and act == "raises"
                if steal_attempt:
                    self.handsplayers[stealer]["success_Steal"] = act == "folds" and hand.gametype["base"] == "stud"

            if steal_attempt and act != "folds":
                break

            if not steal_attempt and not raised and not act in ("bringin"):
                player_stats["raiseFirstInChance"] = True
                if posn in steal_positions:
                    player_stats["stealChance"] = True
                if act in ("bets", "raises", "completes"):
                    player_stats["raisedFirstIn"] = True
                    raised = True
                    if posn in steal_positions:
                        player_stats["stealDone"] = True
                        steal_attempt = True
                        stealer = pname
                if act == "calls":
                    break

            if posn not in steal_positions and act not in ("folds", "bringin"):
                break

    def calc34BetStreet0(self, hand):
        """Fills street0_(3|4)B(Chance|Done), other(3|4)BStreet0"""
        if hand.gametype["base"] == "stud":
            bet_level = 0  # bet_level after 3-bet is equal to 3
        else:
            bet_level = 1  # bet_level after 3-bet is equal to 3
        squeeze_chance, raise_chance, action_cnt, first_agressor = False, True, {}, None
        p0_in = set([x[0] for x in hand.actions[hand.actionStreets[0]] if not x[-1]])
        p1_in = set([x[0] for x in hand.actions[hand.actionStreets[1]]])
        p_in = p1_in.union(p0_in)
        for p in p_in:
            action_cnt[p] = 0
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act, aggr, allin = action[0], action[1], action[1] in ("raises", "bets", "completes"), False
            player_stats = self.handsplayers.get(pname)
            action_cnt[pname] += 1
            if len(action) > 3 and act != "discards":
                allin = action[-1]
            if len(p_in) == 1 and action_cnt[pname] == 1:
                raise_chance = False
                player_stats["street0AggrChance"] = raise_chance
            if act == "folds" or allin or player_stats["sitout"]:
                p_in.discard(pname)
                if player_stats["sitout"]:
                    continue
            if bet_level == 0:
                if aggr:
                    if first_agressor is None:
                        first_agressor = pname
                    bet_level += 1
                continue
            elif bet_level == 1:
                player_stats["street0_2BChance"] = raise_chance
                if aggr:
                    if first_agressor is None:
                        first_agressor = pname
                    player_stats["street0_2BDone"] = True
                    bet_level += 1
                continue
            elif bet_level == 2:
                player_stats["street0_3BChance"] = raise_chance
                player_stats["street0_SqueezeChance"] = squeeze_chance
                if pname == first_agressor:
                    player_stats["street0_FoldTo2BChance"] = True
                    if act == "folds":
                        player_stats["street0_FoldTo2BDone"] = True
                if not squeeze_chance and act == "calls":
                    squeeze_chance = True
                    continue
                if aggr:
                    player_stats["street0_3BDone"] = True
                    player_stats["street0_SqueezeDone"] = squeeze_chance
                    # second_agressor = pname
                    bet_level += 1
                continue
            elif bet_level == 3:
                if pname == first_agressor:
                    player_stats["street0_4BChance"] = raise_chance
                    player_stats["street0_FoldTo3BChance"] = True
                    if aggr:
                        player_stats["street0_4BDone"] = raise_chance
                        bet_level += 1
                    elif act == "folds":
                        player_stats["street0_FoldTo3BDone"] = True
                        break
                else:
                    player_stats["street0_C4BChance"] = raise_chance
                    if aggr:
                        player_stats["street0_C4BDone"] = raise_chance
                        bet_level += 1
                continue
            elif bet_level == 4:
                if pname != first_agressor:
                    player_stats["street0_FoldTo4BChance"] = True
                    if act == "folds":
                        player_stats["street0_FoldTo4BDone"] = True

    def calcCBets(self, hand):
        """Fill streetXCBChance, streetXCBDone, foldToStreetXCBDone, foldToStreetXCBChance

        Continuation Bet chance, action:
        Had the last bet (initiative) on previous street, got called, close street action
        Then no bets before the player with initiatives first action on current street
        ie. if player on street-1 had initiative and no donkbets occurred
        """
        # XXX: enumerate(list, start=x) is python 2.6 syntax; 'start'
        # came there
        # for i, street in enumerate(hand.actionStreets[2:], start=1):
        for i, street in enumerate(hand.actionStreets[2:]):
            name = self.lastBetOrRaiser(hand.actions, hand.actionStreets[i + 1])  # previous street
            if name:
                chance = self.noBetsBefore(hand.actions, hand.actionStreets[i + 2], name)  # this street
                if chance is True:
                    player_stats = self.handsplayers.get(name)
                    player_stats["street%dCBChance" % (i + 1)] = True
                    player_stats["street%dCBDone" % (i + 1)] = self.betStreet(
                        hand.actions, hand.actionStreets[i + 2], name
                    )
                    if player_stats["street%dCBDone" % (i + 1)]:
                        for pname, folds in list(self.foldTofirstsBetOrRaiser(hand.actions, street, name).items()):
                            # print "DEBUG:", hand.handid, pname.encode('utf8'), street, folds, '--', name, 'lastbet on ', hand.actionStreets[i+1]
                            self.handsplayers[pname]["foldToStreet%sCBChance" % (i + 1)] = True
                            self.handsplayers[pname]["foldToStreet%sCBDone" % (i + 1)] = folds

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
        """

        fast_forward = True
        for tupleread in hand.actions[hand.actionStreets[1]]:
            action = tupleread[1]
            if fast_forward:
                if action in ("raises", "completes"):
                    fast_forward = False  # raisefound, end fast-forward
            else:
                player = tupleread[0]
                player_stats = self.handsplayers.get(player)
                player_stats["street0CalledRaiseChance"] += 1
                if action == "calls":
                    player_stats["street0CalledRaiseDone"] += 1
                    fast_forward = True

    def calcCheckCallRaise(self, hand):
        """Fill streetXCheckCallRaiseChance, streetXCheckCallRaiseDone

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
                if act in ("bets", "raises") and initial_raiser is None:
                    initial_raiser = pname
                elif act == "checks" and initial_raiser is None:
                    checkers.add(pname)
                elif initial_raiser is not None and pname in checkers and pname not in acted:
                    player_stats = self.handsplayers.get(pname)
                    player_stats["street%dCheckCallRaiseChance" % (i + 1)] = True
                    player_stats["street%dCheckCallDone" % (i + 1)] = act == "calls"
                    player_stats["street%dCheckRaiseDone" % (i + 1)] = act == "raises"
                    acted.add(pname)

    def aggr(self, hand, i):
        aggrers = set()
        others = set()
        # Growl - actionStreets contains 'BLINDSANTES', which isn't actually an action street

        firstAggrMade = False
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if firstAggrMade:
                others.add(act[0])
            if act[1] in ("completes", "bets", "raises"):
                aggrers.add(act[0])
                firstAggrMade = True

        for player in hand.players:
            if player[1] in aggrers:
                self.handsplayers[player[1]]["street%sAggr" % i] = True

        if len(aggrers) > 0 and i > 0:
            for playername in others:
                self.handsplayers[playername]["otherRaisedStreet%s" % i] = True
                # print "otherRaised detected on handid "+str(hand.handid)+" for "+playername+" on street "+str(i)

        if i > 0 and len(aggrers) > 0:
            for playername in others:
                self.handsplayers[playername]["otherRaisedStreet%s" % i] = True
                # print "DEBUG: otherRaised detected on handid %s for %s on actionStreet[%s]: %s"
                #                           %(hand.handid, playername, hand.actionStreets[i+1], i)

    def calls(self, hand, i):
        # callers = []
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("calls"):
                player_stats = self.handsplayers.get(act[0])
                player_stats["street%sCalls" % i] = 1 + player_stats["street%sCalls" % i]

    def bets(self, hand, i):
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("bets"):
                player_stats = self.handsplayers.get(act[0])
                player_stats["street%sBets" % i] = 1 + player_stats["street%sBets" % i]

    def raises(self, hand, i):
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("completes", "raises"):
                player_stats = self.handsplayers.get(act[0])
                player_stats["street%sRaises" % i] = 1 + player_stats["street%sRaises" % i]

    def folds(self, hand, i):
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("folds"):
                player_stats = self.handsplayers.get(act[0])
                if player_stats["otherRaisedStreet%s" % i] is True:
                    player_stats["foldToOtherRaisedStreet%s" % i] = True
                    # print "DEBUG: fold detected on handid %s for %s on actionStreet[%s]: %s"
                    #                       %(hand.handid, act[0],hand.actionStreets[i+1], i)

    def countPlayers(self, hand):
        pass

    def pfba(self, actions, f=None, limit_actions=None):
        """Helper method. Returns set of PlayersFilteredByActions

        f - forbidden actions
        limit_actions - limited to actions
        """
        players = set()
        for action in actions:
            if limit_actions is not None and action[1] not in limit_actions:
                continue
            if f is not None and action[1] in f:
                continue
            players.add(action[0])
        return players

    def pfbao(self, actions, f=None, limit_actions=None, unique=True):
        """Helper method. Returns set of PlayersFilteredByActionsOrdered

        f - forbidden actions
        limit_actions - limited to actions
        """
        # Note, this is an adaptation of function 5 from:
        # http://www.peterbe.com/plog/uniqifiers-benchmark
        seen = {}
        players = []
        for action in actions:
            if limit_actions is not None and action[1] not in limit_actions:
                continue
            if f is not None and action[1] in f:
                continue
            if action[0] in seen and unique:
                continue
            seen[action[0]] = 1
            players.append(action[0])
        return players

    def calcEffectiveStack(self, hand):
        """Calculates the effective stack for each player on street 1"""
        seen = {}
        pstacks = {}
        actions = hand.actions[hand.holeStreets[0]]
        for p in hand.players:
            if p[1] not in hand.sitout:
                pstacks[p[1]] = int(100 * Decimal(p[2]))
        for action in actions:
            if action[0] in seen:
                continue
            if action[0] not in pstacks:
                continue
            seen[action[0]] = 1
            oppstacks = [v for (k, v) in list(pstacks.items()) if k != action[0]]
            if oppstacks:
                if pstacks[action[0]] > max(oppstacks):
                    self.handsplayers[action[0]]["effStack"] = max(oppstacks)
                else:
                    self.handsplayers[action[0]]["effStack"] = pstacks[action[0]]
                if action[1] == "folds":
                    pstacks[action[0]] = 0

    def firstsBetOrRaiser(self, actions):
        """Returns player name that placed the first bet or raise.

        None if there were no bets or raises on that street
        """
        for act in actions:
            if act[1] in ("bets", "raises", "completes"):
                return act[0]
        return None

    def foldTofirstsBetOrRaiser(self, actions, street, aggressor):
        """Returns player name that placed the first bet or raise.

        None if there were no bets or raises on that street
        """
        i, players = 0, {}
        for act in actions[street]:
            if i > 1:
                break
            if act[0] != aggressor:
                if act[1] == "folds":
                    players[act[0]] = True
                else:
                    players[act[0]] = False
                if act[1] == "raises" or act[1] == "completes":
                    break
            elif act[1] not in ("discards", "stands pat"):
                i += 1
        return players

    def lastBetOrRaiser(self, actions, street):
        """Returns player name that placed the last bet or raise for that street.
        None if there were no bets or raises on that street"""
        lastbet = None
        for act in actions[street]:
            if act[1] in ("bets", "raises", "completes"):
                lastbet = act[0]
        return lastbet

    def noBetsBefore(self, actions, street, player):
        """Returns true if there were no bets before the specified players turn, false otherwise"""
        noBetsBefore = False
        for act in actions[street]:
            # Must test for player first in case UTG
            if act[0] == player:
                noBetsBefore = True
                break
            if act[1] in ("bets", "raises", "completes"):
                break
        return noBetsBefore

    def betStreet(self, actions, street, player):
        """Returns true if player bet/raised the street as their first action"""
        betOrRaise = False
        for act in actions[street]:
            if act[0] == player and act[1] not in ("discards", "stands pat"):
                if act[1] in ("bets", "raises", "completes"):
                    betOrRaise = True
                else:
                    # player found but did not bet or raise as their first action
                    pass
                break
            # else:
            # haven't found player's first action yet
        return betOrRaise
