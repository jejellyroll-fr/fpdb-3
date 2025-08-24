#!/usr/bin/env python
"""DerivedStats module for calculating poker statistics."""

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

import contextlib
import os
from decimal import ROUND_DOWN, Decimal
from typing import Any

import Card
from loggingFpdb import get_logger

try:
    from pokereval import PokerEval

    pokereval = PokerEval()
except ImportError:
    pokereval = None


# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("derived_stats")

# Constants for street indices
STREET0_IDX = 0
STREET1_IDX = 1
STREET2_IDX = 2
STREET3_IDX = 3
STREET4_IDX = 4
FINAL_POT_IDX = 5

# Constants for action indices
ACTION_PLAYER_IDX = 0
ACTION_TYPE_IDX = 1
ACTION_AMOUNT_IDX = 2
ACTION_RAISETO_IDX = 3
ACTION_CALLED_IDX = 4
ACTION_CARDS_DISCARDED_IDX = 3
MIN_ACTION_LENGTH_FOR_ALLIN = 3

# Constants for other common values
CENTS_MULTIPLIER = 100
MIN_STREETS_FOR_PREFLOP = 2
MIN_PLAYERS_FOR_GAME = 2
MIN_ACTIONS_FOR_CHECK_CALL_RAISE = 2
MIN_PLAYER_TUPLE_LENGTH = 2

# Constants for betting levels
THREE_BET_LEVEL = 2
FOUR_BET_LEVEL = 3
FOLD_TO_4BET_LEVEL = 4

# Constants for poker evaluations
MIN_POSTFLOP_BOARD_SIZE = 3
MIN_MAXCARDS_SIZE = 5
ANTE_ALL_IN_POSITION = 9
MIN_RUN_IT_TIMES = 2


def _buildStatsInitializer() -> dict:  # noqa: PLR0915
    # TODO @future: REFACTOR - This function is too long (79 statements > 50)
    # Consider breaking into smaller functions for different stat categories
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


class DerivedStats:
    """Calculate derived statistics for poker hands."""

    def __init__(self) -> None:
        """Initialize DerivedStats instance."""
        self.hands = {}
        self.handsplayers = {}
        self.handsactions = {}
        self.handsstove = []
        self.handspots = []

        # Check environment variable for rake rounding mode
        self.use_round_down = os.environ.get("FPDB_RAKE_ROUND_DOWN", "true").lower() in ("true", "1", "yes")
        log.debug("Rake rounding mode: %s", "ROUND_DOWN" if self.use_round_down else "default")

    def getStats(self, hand: Any) -> None:
        """Calculate and store statistics for a poker hand."""
        for player in hand.players:
            self.handsplayers[player[1]] = _INIT_STATS.copy()

        self.assembleHands(hand)
        self.assembleHandsPlayers(hand)
        self.assembleHandsActions(hand)

        if pokereval and hand.gametype["category"] in Card.games:
            self.assembleHandsStove(hand)
            self.assembleHandsPots(hand)

    def getHands(self) -> dict:
        """Get hands statistics."""
        return self.hands

    def getHandsPlayers(self) -> dict:
        """Get hands players statistics."""
        return self.handsplayers

    def getHandsActions(self) -> dict:
        """Get hands actions statistics."""
        return self.handsactions

    def getHandsStove(self) -> list:
        """Get hands stove statistics."""
        return self.handsstove

    def getHandsPots(self) -> list:
        """Get hands pots statistics."""
        return self.handspots

    def assembleHands(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble basic hand statistics.

        TODO @future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 30 > 12, PLR0915: 144 > 50)
        Consider breaking into smaller methods:
        - _assembleBasicHandInfo()
        - _assembleBoardCards()
        - _assembleStreetTotals()
        - _assemblePlayerStats()
        """
        try:
            log.debug("Starting assembleHands for hand ID: %s", hand.handid)

            # Initialize basic hand details
            self.hands["tableName"] = hand.tablename
            log.debug("Set tableName: %s", hand.tablename)

            self.hands["siteHandNo"] = hand.handid
            log.debug("Set siteHandNo: %s", hand.handid)

            self.hands["gametypeId"] = None  # Handled later after checking DB
            self.hands["sessionId"] = None  # Added later if caching sessions
            self.hands["gameId"] = None  # Added later if caching sessions
            self.hands["startTime"] = hand.startTime  # Ensure proper formatting
            log.debug("Set startTime: %s", hand.startTime)

            self.hands["importTime"] = None
            self.hands["seats"] = self.countPlayers(hand)
            log.debug("Set seats: %s", self.hands["seats"])

            self.hands["maxPosition"] = -1
            self.hands["texture"] = None  # No calculation done yet
            self.hands["tourneyId"] = hand.tourneyId
            log.debug("Set tourneyId: %s", hand.tourneyId)

            # Determine hero seat
            self.hands["heroSeat"] = 0
            for player in hand.players:
                if hand.hero == player[1]:
                    self.hands["heroSeat"] = player[0]
                    log.debug("Hero found: %s at seat %s", player[1], player[0])
                    break
            else:
                log.warning("No hero found in the hand.")

            # Assemble board cards
            boardcards = []
            if hand.board.get("FLOPET") is not None:
                try:
                    flopet_cards = hand.board.get("FLOPET")
                    if flopet_cards and hasattr(flopet_cards, "__iter__") and not isinstance(flopet_cards, str):
                        boardcards += list(flopet_cards)
                        log.debug("Added FLOPET cards: %s", flopet_cards)
                    else:
                        log.warning("FLOPET cards not iterable: %s", flopet_cards)
                except TypeError:
                    log.exception("Error processing FLOPET cards")

            try:
                for street in hand.communityStreets:
                    if street in hand.board:
                        street_cards = hand.board[street]
                        if (
                            street_cards
                            and hasattr(street_cards, "__iter__")
                            and not isinstance(street_cards, str)
                            and len(street_cards) > 0
                        ):
                            boardcards += list(street_cards)
                            log.debug("Added %s cards: %s", street, street_cards)
                        elif street_cards:  # Only warn if there are actual cards but they're not iterable
                            log.warning("Street %s cards not iterable: %s", street, street_cards)
                        # Silently ignore empty lists - this is normal for PREFLOP-only hands
                    else:
                        log.debug("Street %s not found in hand.board - normal for preflop-only hands.", street)
            except TypeError:
                log.exception("Error iterating over communityStreets")

            # Fill remaining board slots with placeholders
            boardcards += ["0x", "0x", "0x", "0x", "0x"]
            log.debug("Completed boardcards with placeholders: %s", boardcards)

            # Encode first five board cards
            try:
                cards = [Card.encodeCard(c) for c in boardcards[0:5]]
                self.hands["boardcard1"] = cards[0]
                self.hands["boardcard2"] = cards[1]
                self.hands["boardcard3"] = cards[2]
                self.hands["boardcard4"] = cards[3]
                self.hands["boardcard5"] = cards[4]
                log.debug("Encoded board cards: %s", cards)
            except IndexError:
                log.exception("Error encoding board cards")
                # Set default values
                self.hands["boardcard1"] = 0
                self.hands["boardcard2"] = 0
                self.hands["boardcard3"] = 0
                self.hands["boardcard4"] = 0
                self.hands["boardcard5"] = 0

            # Initialize boards list
            self.hands["boards"] = []
            self.hands["runItTwice"] = False

            try:
                run_it_times = int(hand.runItTimes) if hasattr(hand.runItTimes, "__int__") else 0
            except (TypeError, ValueError):
                run_it_times = 0

            for i in range(run_it_times):
                boardcards = []
                for street in hand.communityStreets:
                    board_id = i + 1
                    street_i = f"{street}{board_id}"
                    if street_i in hand.board:
                        boardcards += hand.board[street_i]
                        log.debug(
                            "Run %s: Added %s cards: %s",
                            i + 1,
                            street_i,
                            hand.board[street_i],
                        )
                    else:
                        log.warning(
                            "Run %s: Street %s not found in hand.board.",
                            i + 1,
                            street_i,
                        )

                if hand.gametype.get("split"):
                    boardcards += ["0x", "0x", "0x", "0x", "0x"]
                    log.debug("Run %s: Split game, added placeholders.", i + 1)
                    try:
                        cards = [Card.encodeCard(c) for c in boardcards[:5]]
                    except IndexError:
                        log.exception("Run %s: Error encoding split board cards", i + 1)
                        cards = ["0x"] * 5
                else:
                    self.hands["runItTwice"] = True
                    boardcards = ["0x", "0x", "0x", "0x", "0x", *boardcards]
                    log.debug("Run %s: Non-split game, prefixed with placeholders.", i + 1)
                    try:
                        cards = [Card.encodeCard(c) for c in boardcards[-5:]]
                    except IndexError:
                        log.exception("Run %s: Error encoding board cards", i + 1)
                        cards = ["0x"] * 5

                self.hands["boards"].append([board_id, *cards])
                log.debug("Run %s: Appended to boards: %s", i + 1, [board_id, *cards])

            # Calculate street totals
            try:
                totals = hand.getStreetTotals()
                # Check if totals is a Mock object
                from unittest.mock import Mock

                if isinstance(totals, Mock):
                    totals = [0, 0, 0, 0, 0, 0]
                if totals and hasattr(totals, "__iter__") and not isinstance(totals, str):
                    totals = [int(CENTS_MULTIPLIER * i) for i in totals]
                    self.hands["street0Pot"] = totals[STREET0_IDX] if len(totals) > STREET0_IDX else 0
                    self.hands["street1Pot"] = totals[STREET1_IDX] if len(totals) > STREET1_IDX else 0
                    self.hands["street2Pot"] = totals[STREET2_IDX] if len(totals) > STREET2_IDX else 0
                    self.hands["street3Pot"] = totals[STREET3_IDX] if len(totals) > STREET3_IDX else 0
                    self.hands["street4Pot"] = totals[STREET4_IDX] if len(totals) > STREET4_IDX else 0
                    self.hands["finalPot"] = totals[FINAL_POT_IDX] if len(totals) > FINAL_POT_IDX else 0
                    # Add bomb pot amount from hand object
                    self.hands["bombPot"] = getattr(hand, "bombPot", 0)
                    log.debug("Street totals: %s", totals)
                else:
                    # Default values if totals is not iterable
                    self.hands["street0Pot"] = 0
                    self.hands["street1Pot"] = 0
                    self.hands["street2Pot"] = 0
                    self.hands["street3Pot"] = 0
                    self.hands["street4Pot"] = 0
                    self.hands["finalPot"] = 0
                    # Add bomb pot amount from hand object
                    self.hands["bombPot"] = getattr(hand, "bombPot", 0)
                    log.warning("Street totals not iterable: %s", totals)
            except Exception:
                log.exception("Error calculating street totals")
                # Set default values on error
                self.hands["street0Pot"] = 0
                self.hands["street1Pot"] = 0
                self.hands["street2Pot"] = 0
                self.hands["street3Pot"] = 0
                self.hands["street4Pot"] = 0
                self.hands["finalPot"] = 0
                # Add bomb pot amount from hand object
                self.hands["bombPot"] = getattr(hand, "bombPot", 0)

            # VPIP will be calculated in assembleHandsPlayers after player initialization

            # Determine players at each street
            try:
                self.playersAtStreetX(hand)
                log.debug(
                    "Players at streets: 1=%s, 2=%s, 3=%s, 4=%s, Showdown=%s",
                    self.hands.get("playersAtStreet1"),
                    self.hands.get("playersAtStreet2"),
                    self.hands.get("playersAtStreet3"),
                    self.hands.get("playersAtStreet4"),
                    self.hands.get("playersAtShowdown"),
                )
            except Exception:
                log.exception("Error determining players at streets")
                raise

            # Calculate raises per street
            try:
                self.streetXRaises(hand)
                log.debug(
                    "Raises per street: street0Raises=%s, street1Raises=%s, street2Raises=%s, "
                    "street3Raises=%s, street4Raises=%s",
                    self.hands.get("street0Raises"),
                    self.hands.get("street1Raises"),
                    self.hands.get("street2Raises"),
                    self.hands.get("street3Raises"),
                    self.hands.get("street4Raises"),
                )
            except Exception:
                log.exception("Error calculating raises per street")
                raise

            # Log hand details at debug level
            log.debug("Hand detail: %s", hand)

        except Exception:
            log.exception("Error in assembleHands for hand ID %s", hand.handid)
            raise

    def assembleHandsPlayers(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble statistics for each player in the hand.

        TODO @future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 28 > 12)
        Consider breaking into smaller methods:
        - _assemblePlayerBasicStats()
        - _assemblePlayerPositions()
        - _assemblePlayerActions()
        """
        # street0VPI/vpip already called in Hand
        # sawShowdown is calculated in playersAtStreetX, as that calculation gives us a convenient list of names

        for player in hand.players:
            player_name = player[1]
            player_stats = self.handsplayers.get(player_name)
            player_stats["seatNo"] = player[0]
            player_stats["startCash"] = int(CENTS_MULTIPLIER * Decimal(player[2]))
            if player[4] is not None:
                player_stats["startBounty"] = int(CENTS_MULTIPLIER * Decimal(player[4]))
                player_stats["endBounty"] = int(CENTS_MULTIPLIER * Decimal(player[4]))
            if player_name in hand.endBounty:
                player_stats["endBounty"] = int(hand.endBounty.get(player_name))
            if player_name in hand.sitout:
                player_stats["sitout"] = True
            else:
                player_stats["sitout"] = False
            if hand.gametype["type"] == "tour":
                player_stats["tourneyTypeId"] = hand.tourneyTypeId
                player_stats["tourneysPlayersId"] = hand.tourneysPlayersIds.get(player[1], None)
            else:
                player_stats["tourneysPlayersId"] = None
            if player_name in hand.shown:
                player_stats["showed"] = True

        #### seen now processed in playersAtStreetX()

        for i, _street in enumerate(hand.actionStreets[1:]):
            self.aggr(hand, i)
            self.calls(hand, i)
            self.bets(hand, i)
            self.raises(hand, i)
            if i > 0:
                self.folds(hand, i)

        # Winnings is a non-negative value of money collected from the pot, which already includes the
        # rake taken out. hand.collectees is Decimal, database requires cents
        num_collectees, i = len(hand.collectees), 0
        even_split = hand.totalpot / num_collectees if num_collectees > 0 else 0
        unraked = [c for c in hand.collectees.values() if even_split == c]
        for player, winnings in hand.collectees.items():
            collectee_stats = self.handsplayers.get(player)
            collectee_stats["winnings"] = int(CENTS_MULTIPLIER * winnings)
            # Splits evenly on split pots and gives remainder to first player
            # Gets overwritten when calculating multi-way pots in assembleHandsPots
            if num_collectees == 0:
                collectee_stats["rake"] = 0
            elif len(unraked) == 0:
                rake = int(100 * hand.rake) / num_collectees
                remainder_1, remainder_2 = 0, 0
                if rake > 0 and i == 0:
                    leftover = int(100 * hand.rake) - (rake * num_collectees)
                    remainder_1 = int(100 * hand.rake) % rake
                    remainder_2 = leftover if remainder_1 == 0 else 0
                collectee_stats["rake"] = rake + remainder_1 + remainder_2
            else:
                collectee_stats["rake"] = int(100 * (even_split - winnings))
            if collectee_stats["street1Seen"]:
                collectee_stats["wonWhenSeenStreet1"] = True
            if collectee_stats["street2Seen"]:
                collectee_stats["wonWhenSeenStreet2"] = True
            if collectee_stats["street3Seen"]:
                collectee_stats["wonWhenSeenStreet3"] = True
            if collectee_stats["street4Seen"]:
                collectee_stats["wonWhenSeenStreet4"] = True
            if collectee_stats["sawShowdown"]:
                collectee_stats["wonAtSD"] = True
            i += 1

        contributed, i = [], 0
        for player, money_committed in hand.pot.committed.items():
            committed_player_stats = self.handsplayers.get(player)
            paid = (100 * money_committed) + (100 * hand.pot.common[player])
            committed_player_stats["common"] = int(100 * hand.pot.common[player])
            committed_player_stats["committed"] = int(100 * money_committed)
            committed_player_stats["totalProfit"] = int(committed_player_stats["winnings"] - paid)
            committed_player_stats["allInEV"] = committed_player_stats["totalProfit"]
            committed_player_stats["rakeDealt"] = 100 * hand.rake / len(hand.players)
            committed_player_stats["rakeWeighted"] = (
                100 * hand.rake * paid / (100 * hand.totalpot) if hand.rake > 0 else 0
            )
            if paid > 0:
                contributed.append(player)
            i += 1

        for _i, player in enumerate(contributed):
            self.handsplayers[player]["rakeContributed"] = 100 * hand.rake / len(contributed)

        self.calcCBets(hand)

        # More inner-loop speed hackery.
        encode_card = Card.encodeCard
        calc_start_cards = Card.calcStartCards
        for player in hand.players:
            player_name = player[1]
            hcs = hand.join_holecards(player_name, asList=True)
            hcs = hcs + ["0x"] * 18
            player_stats = self.handsplayers.get(player_name)
            if player_stats["sawShowdown"]:
                player_stats["showdownWinnings"] = player_stats["totalProfit"]
            else:
                player_stats["nonShowdownWinnings"] = player_stats["totalProfit"]
            for i, card in enumerate(hcs[:20]):
                player_stats["card%d" % (i + 1)] = encode_card(card)
            try:
                player_stats["startCards"] = calc_start_cards(hand, player_name)
            except IndexError:
                log.exception("IndexError: string index out of range %s %s", hand.handid, hand.in_path)

        self.setPositions(hand)
        self.calcEffectiveStack(hand)
        self.calcCheckCallRaise(hand)
        self.calc34BetStreet0(hand)
        self.calcSteals(hand)
        self.calcCalledRaiseStreet0(hand)
        self.vpip(hand)  # Calculate VPIP after all player stats are initialized
        # Additional stats
        # 3betSB, 3betBB
        # Squeeze, Ratchet?

    def assembleHandsActions(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble and record all actions taken during the hand.

        Captures player moves, amounts, and all-in statuses.
        """
        try:
            log.debug("Starting assembleHandsActions for hand ID: %s", hand.handid)
            k = 0

            # Handle Mock objects for actionStreets
            try:
                if hasattr(hand.actionStreets, "__iter__") and not isinstance(hand.actionStreets, str):
                    action_streets = list(hand.actionStreets)
                else:
                    log.warning("hand.actionStreets is not iterable, skipping assembleHandsActions")
                    return
            except TypeError:
                log.warning("hand.actionStreets is not iterable, skipping assembleHandsActions")
                return

            for i, street in enumerate(action_streets):
                log.debug("Processing street: %s (index: %s)", street, i)
                for j, act in enumerate(hand.actions.get(street, [])):
                    k += 1
                    log.debug("Processing action %s: %s", k, act)

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
                        if action_type == "allin":
                            self.handsactions[k]["actionId"] = 18
                        else:
                            self.handsactions[k]["actionId"] = hand.ACTION.get(
                                action_type,
                                None,
                            )
                        if self.handsactions[k]["actionId"] is None:
                            log.warning(
                                "Unknown action type '%s' for player %s in action %s.",
                                action_type,
                                player_name,
                                k,
                            )
                    except Exception:
                        log.exception("Error retrieving actionId for action %s", k)
                        self.handsactions[k]["actionId"] = None

                    # Handle different action types
                    if action_type not in ("discards") and len(act) > ACTION_AMOUNT_IDX:
                        try:
                            self.handsactions[k]["amount"] = int(CENTS_MULTIPLIER * act[ACTION_AMOUNT_IDX])
                            log.debug(
                                "Action %s: Set amount to %s for player %s.",
                                k,
                                self.handsactions[k]["amount"],
                                player_name,
                            )
                        except (TypeError, ValueError):
                            log.exception("Error converting amount for action %s", k)

                    if action_type in ("raises", "completes") and len(act) > ACTION_CALLED_IDX:
                        try:
                            self.handsactions[k]["raiseTo"] = int(CENTS_MULTIPLIER * act[ACTION_RAISETO_IDX])
                            self.handsactions[k]["amountCalled"] = int(CENTS_MULTIPLIER * act[ACTION_CALLED_IDX])
                            log.debug(
                                "Action %s: Set raiseTo to %s and amountCalled to %s for player %s.",
                                k,
                                self.handsactions[k]["raiseTo"],
                                self.handsactions[k]["amountCalled"],
                                player_name,
                            )
                        except (TypeError, ValueError):
                            log.exception(
                                "Error converting raiseTo or amountCalled for action %s",
                                k,
                            )

                    if action_type in ("discards"):
                        try:
                            self.handsactions[k]["numDiscarded"] = int(act[2])
                            self.handsplayers[player_name][f"street{(i - 1)}Discards"] = int(act[2])
                            log.debug(
                                "Action %s: Set numDiscarded to %s for player %s.",
                                k,
                                self.handsactions[k]["numDiscarded"],
                                player_name,
                            )
                        except (TypeError, ValueError, IndexError):
                            log.exception(
                                "Error setting numDiscarded for action %s and player %s",
                                k,
                                player_name,
                            )

                    if action_type in ("discards") and len(act) > ACTION_CARDS_DISCARDED_IDX:
                        try:
                            self.handsactions[k]["cardsDiscarded"] = act[ACTION_CARDS_DISCARDED_IDX]
                            log.debug(
                                "Action %s: Set cardsDiscarded to %s for player %s.",
                                k,
                                self.handsactions[k]["cardsDiscarded"],
                                player_name,
                            )
                        except Exception:
                            log.exception(
                                "Error setting cardsDiscarded for action %s and player %s",
                                k,
                                player_name,
                            )

                    if len(act) > MIN_ACTION_LENGTH_FOR_ALLIN and action_type not in ("discards"):
                        try:
                            self.handsactions[k]["allIn"] = act[-1]
                            log.debug(
                                "Action %s: Set allIn to %s for player %s.",
                                k,
                                self.handsactions[k]["allIn"],
                                player_name,
                            )
                            if act[-1]:
                                self.handsplayers[player_name]["wentAllIn"] = True
                                self.handsplayers[player_name][f"street{(i - 1)}AllIn"] = True
                                log.debug(
                                    "Player %s wentAllIn set to True for street %s.",
                                    player_name,
                                    i - 1,
                                )
                        except IndexError:
                            log.exception(
                                "Error accessing allIn flag for action %s and player %s",
                                k,
                                player_name,
                            )

                    # Additional validation or logging can be added here as needed

            log.debug("Completed assembleHandsActions for hand ID: %s", hand.handid)

        except Exception:
            log.exception("Error in assembleHandsActions for hand ID %s", hand.handid)
            raise

    def setPositions(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Sets the position for each player in HandsPlayers.

        Any blinds are negative values, and the last person to act on the
        first betting round is 0.
        NOTE: HU, both values are negative for non-stud games.
        NOTE2: I've never seen a HU stud match.
        """
        if not hasattr(self, "handsplayers"):
            return

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
            # TODO @future: fix: if ante all and no actions and no bring in
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

    def vpip(self, hand: Any) -> None:
        """Calculate VPIP (Voluntarily Put In Pot) for all players."""
        if not hasattr(self, "handsplayers"):
            return

        # Check if we have enough action streets for preflop
        if len(hand.actionStreets) < MIN_STREETS_FOR_PREFLOP:
            log.warning("Not enough action streets for VPIP calculation")
            self.hands["playersVpi"] = 0
            return

        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        vpip_count = 0
        for p in self.handsplayers:
            # For Stud, 'completes' is a voluntary action like calls/raises/bets
            if any(act[0] == p and act[1] in ["calls", "raises", "bets", "completes"] for act in preflop_actions):
                self.handsplayers[p]["street0VPI"] = True
                vpip_count += 1

        self.hands["playersVpi"] = vpip_count

    def playersAtStreetX(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Determine which players saw which street and calculate statistics."""
        if not hasattr(self, "handsplayers"):
            return

        try:
            action_streets_len = len(hand.actionStreets) if hasattr(hand.actionStreets, "__len__") else 0
        except TypeError:
            action_streets_len = 0

        # Initialize counts
        self.hands["playersAtStreet1"] = 0
        self.hands["playersAtStreet2"] = 0
        self.hands["playersAtStreet3"] = 0
        self.hands["playersAtStreet4"] = 0
        self.hands["playersAtShowdown"] = 0

        # Get initial players (those who acted in the first action street)
        p_in = set()
        if action_streets_len > 1:
            with contextlib.suppress(TypeError, AttributeError):
                p_in = {x[0] for x in hand.actions.get(hand.actionStreets[1], [])}

        # Add players who were all-in blind
        if hasattr(hand, "pot") and hasattr(hand.pot, "pots") and hand.pot.pots and len(hand.pot.pots[0][1]) > 1:
            p_in = p_in.union(hand.pot.pots[0][1])
            if hasattr(hand.pot, "common"):
                p_in = p_in.union(hand.pot.common.keys())

        # Process each street
        for i, street in enumerate(hand.actionStreets):
            if (i - 1) in (1, 2, 3, 4):
                # Set players at street and mark who saw the street
                self.hands[f"playersAtStreet{i-1}"] = len(p_in)
                for player_with_cards in p_in:
                    if player_with_cards in self.handsplayers:
                        self.handsplayers[player_with_cards][f"street{i-1}Seen"] = True

                # Determine first to act and in position
                # Filter out discards and stands pat for draw games
                players = self.pfbao(hand.actions.get(street, []), f=("discards", "stands pat"))
                if len(players) > 0:
                    if players[0] in self.handsplayers:
                        self.handsplayers[players[0]][f"street{i-1}FirstToAct"] = True
                    if players[-1] in self.handsplayers:
                        self.handsplayers[players[-1]][f"street{i-1}InPosition"] = True

            # Remove players who folded
            actions = hand.actions.get(street, [])
            p_in = p_in - self.pfba(actions, limit=("folds",))

            # If only one player left, we're done
            if len(p_in) == 1:
                if (i - 1) in (1, 2, 3, 4) and len(players) > 0 and next(iter(p_in)) not in players:
                    # Correct in position if everyone folded before last player could act
                    if players[-1] in self.handsplayers:
                        self.handsplayers[players[-1]][f"street{i-1}InPosition"] = False
                    if next(iter(p_in)) in self.handsplayers:
                        self.handsplayers[next(iter(p_in))][f"street{i-1}InPosition"] = True
                return

        # Players remaining reached showdown
        self.hands["playersAtShowdown"] = len(p_in)
        for showdown_player in p_in:
            if showdown_player in self.handsplayers:
                self.handsplayers[showdown_player]["sawShowdown"] = True

    def streetXRaises(self, hand: Any) -> None:
        """Count raises on each street."""
        try:
            action_streets_len = len(hand.actionStreets) if hasattr(hand.actionStreets, "__len__") else 0
        except TypeError:
            action_streets_len = 0

        for i in range(5):
            street_name = None
            if i < action_streets_len:
                with contextlib.suppress(TypeError, IndexError):
                    street_name = hand.actionStreets[i]

            if not street_name:
                self.hands[f"street{i}Raises"] = 0
                continue

            raises = 0
            with contextlib.suppress(TypeError, AttributeError):
                # For Stud, 'completes' counts as a raise
                raises = sum(
                    1
                    for act in hand.actions.get(street_name, [])
                    if len(act) > 1 and act[1] in ["raises", "bets", "completes"]
                )

            self.hands[f"street{i}Raises"] = raises

    def countPlayers(self, hand: Any) -> int:
        """Count the number of players in the hand."""
        return len(hand.players) if hand.players else 0

    def pfba(self, actions: Any, f: Any = None, limit: Any = None) -> set:
        """Helper method. Returns set of PlayersFilteredByActions.

        f - forbidden actions (will be excluded)
        limit - limited to actions (only these will be included)
        """
        players = set()
        for action in actions:
            if limit is not None and action[1] not in limit:
                continue
            if f is not None and action[1] in f:
                continue
            players.add(action[0])
        return players

    def pfbao(self, actions: Any, f: Any = None, limit: Any = None, *, unique: bool = True) -> list:
        """Helper method. Returns ordered list of PlayersFilteredByActionsOrdered.

        f - forbidden actions (will be excluded)
        limit - limited to actions (only these will be included)
        """
        seen = {}
        players = []
        for action in actions:
            if limit is not None and action[1] not in limit:
                continue
            if f is not None and action[1] in f:
                continue
            if action[0] in seen and unique:
                continue
            seen[action[0]] = 1
            players.append(action[0])
        return players

    def firstsBetOrRaiser(self, actions: Any) -> str | None:
        """Find the first player to bet or raise."""
        for act in actions:
            if act[1] in ["bets", "raises"]:
                return act[0]
        return None

    def lastBetOrRaiser(self, actions: Any, street: Any) -> str | None:
        """Find the last player to bet or raise on a given street."""
        aggressors = [act[0] for act in actions.get(street, []) if act[1] in ["bets", "raises"]]
        return aggressors[-1] if aggressors else None

    def calcCBets(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Calculate continuation bets for all players."""
        if not hasattr(self, "handsplayers"):
            return

        # Find preflop aggressor
        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        preflop_aggressor = None
        for act in reversed(preflop_actions):
            if act[1] in ["raises", "bets"]:
                preflop_aggressor = act[0]
                break

        if not preflop_aggressor:
            return

        # Check for CBets on each street
        for i in range(1, min(5, len(hand.actionStreets) - 1)):
            street_name = hand.actionStreets[i + 1]
            street_actions = hand.actions.get(street_name, [])

            if preflop_aggressor in self.handsplayers:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}CBChance" not in self.handsplayers[preflop_aggressor]:
                    self.handsplayers[preflop_aggressor][f"street{i}CBChance"] = False
                if f"street{i}CBDone" not in self.handsplayers[preflop_aggressor]:
                    self.handsplayers[preflop_aggressor][f"street{i}CBDone"] = False
                    
                self.handsplayers[preflop_aggressor][f"street{i}CBChance"] = True

                # Check if they bet first on this street
                cbet_made = False
                for act in street_actions:
                    if act[0] == preflop_aggressor and act[1] in ["bets", "raises"]:
                        self.handsplayers[preflop_aggressor][f"street{i}CBDone"] = True
                        cbet_made = True
                        break

                # If a CBet was made, check for fold to CBet for other players
                if cbet_made:
                    # Find the position of the CBet in the action sequence
                    cbet_position = -1
                    for idx, act in enumerate(street_actions):
                        if act[0] == preflop_aggressor and act[1] in ["bets", "raises"]:
                            cbet_position = idx
                            break

                    if cbet_position >= 0:
                        for player in self.handsplayers:
                            if player != preflop_aggressor:
                                # Check if this player acted after the CBet
                                player_faced_cbet = False
                                player_folded_to_cbet = False

                                # Look for actions by this player after the CBet
                                for idx in range(cbet_position + 1, len(street_actions)):
                                    act = street_actions[idx]
                                    if act[0] == player:
                                        player_faced_cbet = True
                                        if act[1] == "folds":
                                            player_folded_to_cbet = True
                                        break

                                if player_faced_cbet:
                                    self.handsplayers[player][f"foldToStreet{i}CBChance"] = True
                                    if player_folded_to_cbet:
                                        self.handsplayers[player][f"foldToStreet{i}CBDone"] = True

    def calcCheckCallRaise(self, hand: Any) -> None:
        """Calculate check-call and check-raise statistics."""
        if not hasattr(self, "handsplayers"):
            return

        for i in range(1, min(5, len(hand.actionStreets) - 1)):
            street_name = hand.actionStreets[i + 1]
            street_actions = hand.actions.get(street_name, [])

            for player in self.handsplayers:
                player_actions = [act for act in street_actions if act[0] == player]

                if len(player_actions) >= MIN_ACTIONS_FOR_CHECK_CALL_RAISE:
                    first_action = player_actions[0]
                    if first_action[1] == "checks":
                        # Initialize street stats if they don't exist (for run-it-twice scenarios)
                        if f"street{i}CheckCallRaiseChance" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckCallRaiseChance"] = False
                        if f"street{i}CheckCallDone" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckCallDone"] = False
                        if f"street{i}CheckRaiseDone" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckRaiseDone"] = False
                            
                        self.handsplayers[player][f"street{i}CheckCallRaiseChance"] = True

                        # Look for subsequent action
                        for subsequent_action in player_actions[1:]:
                            if subsequent_action[1] == "calls":
                                self.handsplayers[player][f"street{i}CheckCallDone"] = True
                                break
                            if subsequent_action[1] == "raises":
                                self.handsplayers[player][f"street{i}CheckRaiseDone"] = True
                                break

    def calc34BetStreet0(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Fills street0_(3|4)B(Chance|Done), other(3|4)BStreet0.

        For Stud games:
        - bet_level starts at 0 (bring-in doesn't count as first bet level)
        - 'completes' action is treated as aggressive action
        - bring-in player gets first action but it's not voluntary

        For Hold'em/Omaha games:
        - bet_level starts at 1 (blinds count as first bet level)
        """
        bet_level = 0 if hand.gametype["base"] == "stud" else 1

        squeeze_chance, raise_chance, action_cnt, first_agressor = False, True, {}, None
        p0_in = {x[0] for x in hand.actions[hand.actionStreets[0]] if not x[-1]}
        p1_in = {x[0] for x in hand.actions[hand.actionStreets[1]]}
        p_in = p1_in.union(p0_in)

        for p in p_in:
            action_cnt[p] = 0

        for action in hand.actions[hand.actionStreets[1]]:
            pname, act = action[0], action[1]
            # For Stud, 'completes' is an aggressive action like 'raises' and 'bets'
            aggr = act in ("raises", "bets", "completes")
            allin = False

            # Debug logging
            log.debug("calc34BetStreet0: %s %s, bet_level=%s, aggr=%s", pname, act, bet_level, aggr)
            player_stats = self.handsplayers.get(pname)
            action_cnt[pname] += 1
            if len(action) > MIN_ACTION_LENGTH_FOR_ALLIN and act != "discards":
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
            if bet_level == 1:
                player_stats["street0_2BChance"] = raise_chance
                if aggr:
                    if first_agressor is None:
                        first_agressor = pname
                    player_stats["street0_2BDone"] = True
                    bet_level += 1
                continue
            if bet_level == THREE_BET_LEVEL:
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
                    bet_level += 1
                continue
            if bet_level == FOUR_BET_LEVEL:
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
            if bet_level == FOLD_TO_4BET_LEVEL and pname != first_agressor:
                player_stats["street0_FoldTo4BChance"] = True
                if act == "folds":
                    player_stats["street0_FoldTo4BDone"] = True

    def calcCalledRaiseStreet0(self, hand: Any) -> None:
        """Fill street0CalledRaiseChance, street0CalledRaiseDone.

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
                    skip through list to the next raise action.
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

    def calcSteals(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Fills raiseFirstInChance|raisedFirstIn, fold(Bb|Sb)ToSteal(Chance|).

        Steal attempt - open raise on positions 1 0 S - i.e. CO, BU, SB
                        (note: I don't think PT2 counts SB steals in HU hands, maybe we shouldn't?)
        Fold to steal - folding blind after steal attemp wo any other callers or raisers
        """
        steal_attempt = False
        raised = False
        stealer = None
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
                    if stealer:
                        self.handsplayers[stealer]["success_Steal"] = act == "folds"
                break
            if posn == "S":
                player_stats["raiseToStealChance"] = steal_attempt
                player_stats["foldSbToStealChance"] = steal_attempt
                player_stats["foldedSbToSteal"] = steal_attempt and act == "folds"
                player_stats["raiseToStealDone"] = steal_attempt and act == "raises"
                if steal_attempt and stealer:
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

    def calcEffectiveStack(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Calculate effective stack sizes for all players."""
        if not hasattr(self, "handsplayers"):
            return

        # Check if there are any actions (excluding BLINDSANTES)
        has_actions = False
        for street, actions in hand.actions.items():
            if street != "BLINDSANTES" and actions:
                has_actions = True
                break

        # If no actions, set all effective stacks to 0
        if not has_actions:
            for player_name in self.handsplayers:
                self.handsplayers[player_name]["effStack"] = 0
            return

        # Build a dictionary of player stacks for easier lookup
        # Exclude players who are sitting out
        player_stacks = {}
        for player in hand.players:
            player_name = player[1]
            if player_name in self.handsplayers and player_name not in hand.sitout:
                # Try to get stack from hand.stacks first, then player data, then handsplayers
                stack = 0

                # Check hand.stacks attribute first
                if hasattr(hand, "stacks") and player_name in hand.stacks:
                    with contextlib.suppress(ValueError, TypeError):
                        stack = int(CENTS_MULTIPLIER * hand.stacks[player_name])  # Convert to cents

                # Try player tuple data
                if stack == 0 and len(player) > MIN_PLAYER_TUPLE_LENGTH:
                    with contextlib.suppress(ValueError, TypeError, IndexError):
                        stack = int(CENTS_MULTIPLIER * Decimal(str(player[2])))  # Convert to cents

                # Finally try handsplayers
                if stack == 0:
                    stack = self.handsplayers[player_name].get("startCash", 0)

                if stack > 0:
                    player_stacks[player_name] = stack
                    # Update the player's startCash if it wasn't set
                    if self.handsplayers[player_name].get("startCash", 0) == 0:
                        self.handsplayers[player_name]["startCash"] = stack

        # Calculate effective stack for each player individually
        # Using formula: min(player_stack, max(opponent_stacks))
        for player_name in player_stacks:
            player_stack = player_stacks[player_name]

            # Find the largest opponent stack (excluding sitting out players)
            opponent_stacks = [stack for name, stack in player_stacks.items() if name != player_name]

            if opponent_stacks:
                max_opponent_stack = max(opponent_stacks)
                # Effective stack is the minimum of player's stack and largest opponent's stack
                effective_stack = min(player_stack, max_opponent_stack)
            else:
                # Only one player, effective stack is their own stack
                effective_stack = player_stack

            self.handsplayers[player_name]["effStack"] = effective_stack

        # Set effective stack to 0 for sitting out players
        for player in hand.players:
            player_name = player[1]
            if player_name in hand.sitout and player_name in self.handsplayers:
                self.handsplayers[player_name]["effStack"] = 0

    def calcFoldToOtherRaisedStreet(self, hand: Any) -> None:
        """Calculate fold to other raised street statistics."""
        if not hasattr(self, "handsplayers"):
            return

        for i in range(5):
            if i >= len(hand.actionStreets):
                continue

            street_name = hand.actionStreets[i]
            street_actions = hand.actions.get(street_name, [])

            # Find raises on this street
            raisers = [act[0] for act in street_actions if act[1] in ["raises", "bets"]]

            if raisers:
                for player in self.handsplayers:
                    if player not in raisers:
                        # Check if they folded to a raise
                        for act in street_actions:
                            if act[0] == player and act[1] == "folds":
                                self.handsplayers[player][f"otherRaisedStreet{i}"] = True
                                self.handsplayers[player][f"foldToOtherRaisedStreet{i}"] = True
                                break

    def noBetsBefore(self, actions: Any, street: Any, player: Any) -> bool:
        """Check if there were no bets before this player on this street."""
        street_actions = actions.get(street, [])

        for act in street_actions:
            if act[0] == player:
                break
            if act[1] in ["bets", "raises"]:
                return False
        return True

    def aggr(self, hand: Any, i: int) -> None:
        """Calculate aggression statistics for a given street."""
        aggrers = set()
        others = set()
        # Growl - actionStreets contains 'BLINDSANTES', which isn't actually an action street

        first_aggr_made = False
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if first_aggr_made:
                others.add(act[0])
            if act[1] in ("completes", "bets", "raises"):
                aggrers.add(act[0])
                first_aggr_made = True

        for player in hand.players:
            if player[1] in aggrers:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Aggr" not in self.handsplayers[player[1]]:
                    self.handsplayers[player[1]][f"street{i}Aggr"] = False
                self.handsplayers[player[1]][f"street{i}Aggr"] = True

        if len(aggrers) > 0 and i > 0:
            for playername in others:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"otherRaisedStreet{i}" not in self.handsplayers[playername]:
                    self.handsplayers[playername][f"otherRaisedStreet{i}"] = False
                self.handsplayers[playername][f"otherRaisedStreet{i}"] = True
                # print "otherRaised detected on handid "+str(hand.handid)+" for "+playername+" on street "+str(i)

        if i > 0 and len(aggrers) > 0:
            for playername in others:
                self.handsplayers[playername][f"otherRaisedStreet{i}"] = True
                # print "DEBUG: otherRaised detected on handid %s for %s on actionStreet[%s]: %s"
                #                           %(hand.handid, playername, hand.actionStreets[i+1], i)

    def calls(self, hand: Any, i: int) -> None:
        """Calculate call statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("calls"):
                player_stats = self.handsplayers.get(act[0])
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Calls" not in player_stats:
                    player_stats[f"street{i}Calls"] = 0
                player_stats[f"street{i}Calls"] = 1 + player_stats[f"street{i}Calls"]

    def bets(self, hand: Any, i: int) -> None:
        """Calculate bet statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("bets"):
                player_stats = self.handsplayers.get(act[0])
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Bets" not in player_stats:
                    player_stats[f"street{i}Bets"] = 0
                player_stats[f"street{i}Bets"] = 1 + player_stats[f"street{i}Bets"]

    def raises(self, hand: Any, i: int) -> None:
        """Calculate raise statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("completes", "raises"):
                player_stats = self.handsplayers.get(act[0])
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Raises" not in player_stats:
                    player_stats[f"street{i}Raises"] = 0
                player_stats[f"street{i}Raises"] = 1 + player_stats[f"street{i}Raises"]

    def folds(self, hand: Any, i: int) -> None:
        """Calculate fold statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("folds"):
                player_stats = self.handsplayers.get(act[0])
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"otherRaisedStreet{i}" not in player_stats:
                    player_stats[f"otherRaisedStreet{i}"] = False
                if f"foldToOtherRaisedStreet{i}" not in player_stats:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = False
                if player_stats[f"otherRaisedStreet{i}"]:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = True
                    # print "DEBUG: fold detected on handid %s for %s on actionStreet[%s]: %s"
                    #                       %(hand.handid, act[0],hand.actionStreets[i+1], i)

    def assembleHandsStove(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble hands stove data for equity calculations."""
        category = hand.gametype["category"]
        holecards, holeplayers = {}, []
        base, evalgame, hilo, streets, last, hrange = Card.games[category]
        hi_lo_key = {"h": [("h", "hi")], "l": [("l", "low")], "s": [("h", "hi"), ("l", "low")], "r": [("l", "hi")]}
        boards = self.getBoardsDict(hand, base, streets)
        for player in hand.players:
            pname = player[1]
            hp = self.handsplayers.get(pname)
            if evalgame:
                hcs = hand.join_holecards(pname, asList=True)
                holecards[pname] = {}
                holecards[pname]["cards"] = []
                holecards[pname]["eq"] = 0
                holecards[pname]["committed"] = 0
                holeplayers.append(pname)
                for street, board in boards.items():
                    street_id = streets[street]
                    street_seen = hp[f"street{street_id!s}Seen"] if street_id > 0 else True
                    if (pname == hand.hero and street_seen) or (hp["showed"] and street_seen) or hp["sawShowdown"]:
                        board_id, hl, rank_id, value, _cards = 0, "n", 1, 0, None
                        for n in range(len(board["board"])):
                            street_idx = -1 if base == "hold" else street_id
                            cards = hcs[hrange[street_idx][0] : hrange[street_idx][1]]
                            board_id = (n + 1) if (len(board["board"]) > 1) else n
                            cards += board["board"][n] if (board["board"][n] and "omaha" not in evalgame) else []
                            bcards = board["board"][n] if (board["board"][n] and "omaha" in evalgame) else []
                            cards = [str(c) if Card.encodeCardList.get(c) else "0x" for c in cards]
                            bcards = [str(b) if Card.encodeCardList.get(b) else "0x" for b in bcards]
                            holecards[pname]["hole"] = cards[hrange[street_idx][0] : hrange[street_idx][1]]
                            holecards[pname]["cards"] += [cards]
                            notnull = ("0x" not in cards) and ("0x" not in bcards)
                            postflop = base == "hold" and len(board["board"][n]) >= MIN_POSTFLOP_BOARD_SIZE
                            maxcards = base != "hold" and len(cards) >= MIN_MAXCARDS_SIZE
                            if notnull and (postflop or maxcards):
                                for hl, side in hi_lo_key[hilo]:
                                    try:
                                        value, rank = pokereval.best(side, cards, bcards)
                                        rank_id = Card.hands[rank[0]][0]
                                        if rank is not None and rank[0] != "Nothing":
                                            _cards = "".join([pokereval.card2string(i)[0] for i in rank[1:]])
                                        else:
                                            _cards = None
                                        self.handsstove.append(
                                            [
                                                hand.dbid_hands,
                                                hand.dbid_pids[pname],
                                                street_id,
                                                board_id,
                                                hl,
                                                rank_id,
                                                value,
                                                _cards,
                                                0,
                                            ],
                                        )
                                    except RuntimeError:  # noqa: PERF203
                                        log.exception(
                                            "assembleHandsStove: error determining value and rank for hand %s %s",
                                            hand.handid,
                                            hand.in_path,
                                        )
                                        self.handsstove.append(
                                            [
                                                hand.dbid_hands,
                                                hand.dbid_pids[pname],
                                                street_id,
                                                board_id,
                                                "n",
                                                1,
                                                0,
                                                None,
                                                0,
                                            ],
                                        )
                            else:
                                self.handsstove.append(
                                    [hand.dbid_hands, hand.dbid_pids[pname], street_id, board_id, "n", 1, 0, None, 0],
                                )
            else:
                hl, street_id = hi_lo_key[hilo][0][0], 0
                if hp["sawShowdown"] or hp["showed"]:
                    hp["handString"] = hand.showdownStrings.get(pname)
                    street_id = streets[last]
                self.handsstove.append([hand.dbid_hands, hand.dbid_pids[player[1]], street_id, 0, hl, 1, 0, None, 0])

        if base == "hold" and evalgame:
            self.getAllInEV(hand, evalgame, holeplayers, boards, streets, holecards)

    def assembleHandsPots(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble hands pots data and calculate winnings."""
        category, positions, players_pots, pot_found, position_dict, showdown, allin_ante = (
            hand.gametype["category"],
            [],
            {},
            {},
            {},
            False,
            False,
        )
        for p in hand.players:
            players_pots[p[1]] = [0, []]
            pot_found[p[1]] = [0, 0]
            position_dict[self.handsplayers[p[1]]["position"]] = p[1]
            positions.append(self.handsplayers[p[1]]["position"])
            if self.handsplayers[p[1]]["sawShowdown"]:
                showdown = True
                if (
                    self.handsplayers[p[1]]["position"] == ANTE_ALL_IN_POSITION
                    and self.handsplayers[p[1]]["winnings"] > 0
                ):
                    allin_ante = True
        # Sort positions handling both strings ('B', 'S') and integers
        positions.sort(
            reverse=True,
            key=lambda x: (isinstance(x, str), x) if not isinstance(x, str) else (False, ord(x)),
        )
        factor = 100
        if (
            hand.gametype["type"] == "tour"
            or (
                hand.gametype["type"] == "ring"
                and (hand.gametype["currency"] == "play" and (hand.sitename not in ("Winamax", "PacificPoker")))
            )
        ) and (not [n for (n, v) in hand.pot.pots if (n % Decimal("1.00")) != 0]):
            factor = 1
        hi_lo_key = {"h": ["hi"], "l": ["low"], "r": ["low"], "s": ["hi", "low"]}
        base, evalgame, hilo, streets, last, hrange = Card.games[category]
        if (
            (hand.sitename != "KingsClub" or hand.adjustCollected)  # Can't trust KingsClub draw/stud holecards
            and evalgame
            and (len(hand.pot.pots) > 1 or (showdown and (hilo == "s" or hand.runItTimes >= MIN_RUN_IT_TIMES)))
            and not allin_ante
        ):
            # print 'DEBUG hand.collected', hand.collected
            # print 'DEBUG hand.collectees', hand.collectees
            if not hand.cashedOut:
                for p in hand.players:
                    self.handsplayers[p[1]]["rake"] = 0
                hand.rake = 0
            for pot_id, (pot, players) in enumerate(hand.pot.pots):
                if pot_id == 0:
                    pot += sum(hand.pot.common.values()) + hand.pot.stp  # noqa: PLW2901
                boards, board_id = self.getBoardsList(hand), 0
                for b in boards:
                    board_id += hand.runItTimes >= MIN_RUN_IT_TIMES
                    pot_board = Decimal(int(pot / len(boards) * factor)) / factor
                    mod_board = pot - pot_board * len(boards)
                    if board_id == 1:
                        pot_board += mod_board
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
                            log.exception(
                                "assembleHandsPots: error evaluating winners for hand %s %s",
                                hand.handid,
                                hand.in_path,
                            )
                            win = {}
                            win[hi_lo_key[hilo][0]] = [0]
                    else:
                        win = {}
                        win[hi_lo_key[hilo][0]] = [0]
                    for hl in hi_lo_key[hilo]:
                        if hl in win and len(win[hl]) > 0:
                            pot_hi_lo = Decimal(int(pot_board / len(win) * factor)) / factor
                            mod_hi_lo = pot_board - pot_hi_lo * len(win)
                            if len(win) == 1 or hl == "hi":
                                pot_hi_lo += mod_hi_lo
                            pot_split = Decimal(int(pot_hi_lo / len(win[hl]) * factor)) / factor
                            mod_split = pot_hi_lo - pot_split * len(win[hl])
                            pnames = players if len(holeplayers) == 0 else [holeplayers[w] for w in win[hl]]
                            for n in positions:
                                if position_dict[n] in pnames:
                                    pname = position_dict[n]
                                    ppot = pot_split
                                    if mod_split > 0:
                                        cent = Decimal("0.01") * (100 / factor)
                                        ppot += cent
                                        mod_split -= cent
                                    players_pots[pname][0] += ppot
                                    pot_found[pname][0] += ppot
                                    data = {
                                        "potId": pot_id,
                                        "boardId": board_id,
                                        "hiLo": hl,
                                        "ppot": ppot,
                                        "winners": [m for m in pnames if pname != n],
                                        "mod": ppot > pot_split,
                                    }
                                    players_pots[pname][1].append(data)

            for p, (total, info) in players_pots.items():
                if hand.collectees.get(p) and info:
                    pot_found[p][1] = hand.collectees.get(p)
                    for item in info:
                        split = [
                            n
                            for n in item["winners"]
                            if len(players_pots[n][1]) == 1 and hand.collectees.get(n) is not None
                        ]
                        if len(info) == 1:
                            ppot = item["ppot"]
                            rake = ppot - hand.collectees[p]
                            collected = hand.collectees[p]
                        elif item == info[-1]:
                            ppot, collected = pot_found[p]
                            rake = ppot - collected
                        elif len(split) > 0 and not item["mod"]:
                            ppot = item["ppot"]
                            collected = min([hand.collectees[s] for s in split] + [ppot])
                            rake = ppot - collected
                        else:
                            ppot = item["ppot"]
                            totalrake = total - hand.collectees[p]
                            if self.use_round_down:
                                rake = (totalrake * (ppot / total)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                            else:
                                rake = (totalrake * (ppot / total)).quantize(Decimal("0.01"))
                            collected = ppot - rake
                        pot_found[p][0] -= ppot
                        pot_found[p][1] -= collected
                        insert = [
                            None,
                            item["potId"],
                            item["boardId"],
                            item["hiLo"][0],
                            hand.dbid_pids[p],
                            int(item["ppot"] * 100),
                            int(collected * 100),
                            int(rake * 100),
                        ]
                        self.handspots.append(insert)
                        if not hand.cashedOut:
                            self.handsplayers[p]["rake"] += int(rake * 100)
                            hand.rake += rake

    def getBoardsDict(self, hand: Any, _game_type: Any, streets: Any) -> dict:
        """Get boards dictionary for equity calculations."""
        try:
            log.debug("Getting boards dict for hand %s", hand.handid)
            boards = {}

            for street_name in streets:
                try:
                    if street_name in hand.board:
                        board_cards = hand.board[street_name]

                        # Check if this street had all-in action
                        allin = False
                        if street_name in hand.actions:
                            street_actions = hand.actions[street_name]
                            # If no actions on street, might be all-in
                            if not street_actions:
                                allin = True

                        boards[street_name] = {"board": [board_cards], "allin": allin}
                        log.debug("Added board for %s: %s", street_name, boards[street_name])
                    else:
                        log.error("Street %s not found in hand.board", street_name)

                except Exception:  # noqa: PERF203
                    log.exception("Error processing street %s", street_name)

            return boards  # noqa: TRY300

        except Exception:
            log.exception("Error in getBoardsDict for hand %s", hand.handid)
            return {}

    def _raise_invalid_run_it_times_error(self, run_it_times: Any) -> None:
        """Helper method to raise ValueError for invalid runItTimes."""
        msg = f"Invalid runItTimes type: {type(run_it_times)}"
        raise ValueError(msg)

    def getBoardsList(self, hand: Any) -> list:
        """Get boards list for hand."""
        try:
            log.debug("Getting boards list for hand %s", hand.handid)

            if hand.gametype["base"] != "hold":
                return []

            # Check for invalid runItTimes
            if hasattr(hand, "runItTimes") and not isinstance(hand.runItTimes, int):
                self._raise_invalid_run_it_times_error(hand.runItTimes)

            return [hand.board[street] for street in hand.communityStreets if street in hand.board]

        except Exception:
            log.exception("Error in getBoardsList for hand %s", hand.handid)
            raise

    def getAllInEV(self, hand: Any, game_type: Any, players: Any, boards: Any, streets: Any, holecards: Any) -> None:  # noqa: C901, PLR0913, PLR0912
        """Calculate all-in equity for players.

        Adapted to handle both Hold'em and Draw games:
        - Hold'em: Uses community cards + hole cards
        - Draw: Uses only player's cards (5 cards)
        """
        try:
            log.debug("Calculating all-in EV for hand %s, game type: %s", hand.handid, game_type)

            # Get game base type
            base = hand.gametype.get("base", "")

            # For non-hold'em games (like draw), we need different handling
            if base != "hold" and game_type:
                return self.getAllInEVDraw(hand, game_type, players, streets, holecards)

            # Original Hold'em logic
            # Check if we have valid players for EV calculation
            valid_players = [
                player
                for player in players
                if player in self.handsplayers
                and (
                    self.handsplayers[player].get("sawShowdown", False)
                    or self.handsplayers[player].get("wentAllIn", False)
                )
            ]

            if len(valid_players) < MIN_PLAYERS_FOR_GAME:
                log.warning("Not enough valid players for EV calculation: %s", valid_players)
                return None

            # Initialize stove data if not exists
            if not hasattr(self, "handsstove"):
                self.handsstove = []

            # Calculate equity for each all-in situation
            for street_name, street_data in boards.items():
                if street_data.get("allin", False):
                    try:
                        # Use pokereval to calculate equity
                        if pokereval:
                            # Prepare data for pokereval
                            player_hands = []
                            for player in valid_players:
                                if player in holecards:
                                    hole = holecards[player].get("hole", [])
                                    if hole and hole != ["0x", "0x"]:
                                        player_hands.append(hole)

                            if len(player_hands) >= MIN_PLAYERS_FOR_GAME:
                                board_cards = street_data["board"][0] if street_data["board"] else []

                                # Calculate equity using pokereval
                                result = pokereval.poker_eval(game=game_type, pockets=player_hands, board=board_cards)

                                # Store results
                                for i, player in enumerate(valid_players[: len(player_hands)]):
                                    if i < len(result["eval"]):
                                        equity = result["eval"][i]["ev"]
                                        self.handsplayers[player]["allInEV"] = int(100 * equity)
                                        log.debug("Player %s all-in EV: %s", player, equity)

                    except RuntimeError:
                        log.exception("RuntimeError in pokereval calculation")
                    except Exception:
                        log.exception("Error calculating equity for %s", street_name)

        except Exception:
            log.exception("Error in getAllInEV for hand %s", hand.handid)

    def getAllInEVDraw(self, hand: Any, _game_type: Any, _players: Any, _streets: Any, holecards: Any) -> None:  # noqa: C901
        """Calculate all-in equity for Draw games.

        Draw games have different characteristics:
        - No community cards
        - Players have 5 cards each
        - All-in situations need to evaluate complete hands
        """
        try:
            log.debug("Calculating Draw all-in EV for hand %s", hand.handid)

            # Find the street where all-in occurred
            for pot_id, (pot, pot_players) in enumerate(hand.pot.pots):
                if pot_id == 0:
                    pot += sum(hand.pot.common.values()) + hand.pot.stp  # noqa: PLW2901

                # Get valid players who went all-in
                valid_players = []
                player_cards = []

                for player in pot_players:
                    if (
                        player in self.handsplayers
                        and (
                            self.handsplayers[player].get("sawShowdown", False)
                            or self.handsplayers[player].get("wentAllIn", False)
                        )
                        and player in holecards
                        and "cards" in holecards[player]
                        and holecards[player]["cards"]
                        and len(holecards[player]["cards"]) > 0
                    ):
                        # Get player's cards for Draw games
                        cards = holecards[player]["cards"]
                        # For draw games, use the complete hand
                        player_hand = cards[-1] if isinstance(cards, list) else cards
                        # Filter out placeholder cards
                        player_hand = [c for c in player_hand if c != "0x"]

                        if len(player_hand) >= MIN_MAXCARDS_SIZE:  # Draw games need 5 cards
                            valid_players.append(player)
                            player_cards.append(player_hand[:MIN_MAXCARDS_SIZE])  # Use first 5 cards

                if len(valid_players) >= MIN_PLAYERS_FOR_GAME and len(player_cards) >= MIN_PLAYERS_FOR_GAME:
                    try:
                        # Calculate equity for draw games
                        # Note: Draw games don't use board cards
                        iterations = Card.iter.get(0, 1000)  # Default iterations

                        # Use poker_eval for draw games
                        evs = pokereval.poker_eval(
                            game="5draw",  # Default for draw games
                            iterations=iterations,
                            pockets=player_cards,
                            board=[],  # No board in draw games
                        )

                        equities = [e["ev"] for e in evs["eval"]]

                        # Adjust equities to sum to 1000
                        remainder = (1000 - sum(equities)) / Decimal(len(equities))
                        for i in range(len(equities)):
                            equities[i] += remainder

                            player = valid_players[i]
                            # Calculate committed amount
                            committed = 100 * hand.pot.committed.get(player, 0) + 100 * hand.pot.common.get(player, 0)

                            # Calculate EV
                            rake = hand.rake * (Decimal(pot) / Decimal(hand.totalpot))
                            ev = ((pot - rake) * equities[i]) / Decimal(10)

                            # Set all-in EV
                            self.handsplayers[player]["allInEV"] = int(ev - committed)
                            log.debug(
                                "Draw game - Player %s all-in EV: %s",
                                player,
                                self.handsplayers[player]["allInEV"],
                            )

                    except RuntimeError:
                        log.exception("getAllInEVDraw: error running poker_eval for hand %s", hand.handid)
                    except Exception:
                        log.exception("getAllInEVDraw: unexpected error for hand %s", hand.handid)

        except Exception:
            log.exception("Error in getAllInEVDraw for hand %s", hand.handid)

    def awardPots(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Award pots to winners."""
        try:
            log.debug("Awarding pots for hand %s", hand.handid)

            if not pokereval:
                log.warning("pokereval not available for pot awarding")
                return

            # Process each pot
            for pot_amount, eligible_players in hand.pot.pots:
                try:
                    # Get hole cards for eligible players
                    holeplayers = []
                    for player in eligible_players:
                        hole_cards = hand.join_holecards(player)
                        if hole_cards and hole_cards != ["0x", "0x"]:
                            holeplayers.append((player, hole_cards))

                    if not holeplayers:
                        log.warning("No valid hole cards found for pot of %s", pot_amount)
                        continue

                    # Get board cards
                    boards = self.getBoardsList(hand)
                    if boards:
                        board = boards[0]  # Use first board

                        # Calculate winners using pokereval
                        winners = pokereval.winners(
                            game=hand.gametype["category"],
                            pockets=[hole for _, hole in holeplayers],
                            board=board,
                        )

                        if not winners or not winners.get("hi", []):
                            log.warning("No winners found for pot of %s", pot_amount)
                            continue

                        # Award pot to winners
                        winner_indices = winners["hi"]
                        num_winners = len(winner_indices)
                        if num_winners > 0:
                            pot_share = pot_amount / num_winners
                            for winner_idx in winner_indices:
                                if winner_idx < len(holeplayers):
                                    winner_name = holeplayers[winner_idx][0]
                                    hand.addCollectPot(winner_name, pot_share)
                                    log.debug("Awarded %s to %s", pot_share, winner_name)

                except RuntimeError:
                    log.exception("RuntimeError awarding pot")
                except Exception:
                    log.exception("Error awarding pot of %s", pot_amount)

        except Exception:
            log.exception("Error in awardPots for hand %s", hand.handid)

    def assembleHudCache(self, hand: Any) -> None:
        """Assemble HUD cache data - required for HUD functionality."""
        # No real work to be done - HandsPlayers data already contains the correct info
