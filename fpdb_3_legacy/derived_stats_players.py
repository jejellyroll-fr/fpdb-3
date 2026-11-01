"""The HandsPlayers row's seats, money, hole cards, positions and effective stacks."""

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

from __future__ import annotations

import contextlib
from decimal import Decimal
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.derived_stats_base import (
    ANTE_ALL_IN_POSITION,
    CENTS_MULTIPLIER,
    MIN_PLAYER_TUPLE_LENGTH,
    DerivedStatsBase,
    _pot_stp,
    _to_decimal,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("derived_stats")


class DerivedStatsPlayersMixin(DerivedStatsBase):
    """Assemble each player's seat, money and position."""

    def _assemblePlayerSeats(self, hand: Any) -> None:
        """Seat, stack, bounty, sit-out and tournament identity per player."""
        # Set seat and cnt_players for all players
        total_players = len(hand.players)
        for player in hand.players:
            player_name = player[1]
            player_stats = self.handsplayers[player_name]
            player_stats["seatNo"] = player[0]
            player_stats["seat"] = player[0]  # Duplicate for consistency with requested name
            player_stats["cnt_players"] = total_players
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

            # Cash out fees - convert from Decimal to cents for database storage
            # and set cash out flag
            if hasattr(hand, "cashOutFees") and player_name in hand.cashOutFees:
                player_stats["cashOutFee"] = int(CENTS_MULTIPLIER * hand.cashOutFees[player_name])
                player_stats["isCashOut"] = True
            else:
                player_stats["cashOutFee"] = 0
                player_stats["isCashOut"] = False

    def _assemblePlayerActionCounts(self, hand: Any) -> None:
        """Count each player's actions on every street after preflop."""
        #### seen now processed in playersAtStreetX()

        for i, _street in enumerate(hand.actionStreets[1:]):
            self.aggr(hand, i)
            self.calls(hand, i)
            self.bets(hand, i)
            self.raises(hand, i)
            if i > 0:
                self.folds(hand, i)

    def _assemblePlayerWinnings(self, hand: Any) -> None:
        """Money collected from the pot, and the rake taken out of it."""
        # Winnings is a non-negative value of money collected from the pot, which already includes the
        # rake taken out. hand.collectees is Decimal, database requires cents
        num_collectees, i = len(hand.collectees), 0
        even_split = hand.totalpot / num_collectees if num_collectees > 0 else 0
        unraked = [c for c in hand.collectees.values() if even_split == c]
        for player, winnings in hand.collectees.items():
            collectee_stats = self.handsplayers[player]
            collectee_stats["winnings"] = int(CENTS_MULTIPLIER * winnings)
            # Splits evenly on split pots and gives remainder to first player
            # Gets overwritten when calculating multi-way pots in assembleHandsPots
            if num_collectees == 0:
                collectee_stats["rake"] = 0
            elif len(unraked) == 0:
                rake_share = int(100 * hand.rake) / num_collectees
                remainder_1 = 0.0
                remainder_2 = 0.0
                if rake_share > 0 and i == 0:
                    leftover = int(100 * hand.rake) - (rake_share * num_collectees)
                    remainder_1 = int(100 * hand.rake) % rake_share
                    remainder_2 = leftover if remainder_1 == 0 else 0
                collectee_stats["rake"] = rake_share + remainder_1 + remainder_2
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

    def _assemblePlayerContributions(self, hand: Any) -> None:
        """Money put in, resulting profit and rake attribution."""
        contributed, i = [], 0
        for player, money_committed in hand.pot.committed.items():
            committed_player_stats = self.handsplayers[player]

            # Note: pot.committed already has uncalled bets subtracted via pot.removeMoney()
            # So we use money_committed directly without additional subtraction

            # Calculate paid amount
            paid = (100 * money_committed) + (100 * hand.pot.common[player])

            committed_player_stats["common"] = int(100 * hand.pot.common[player])
            committed_player_stats["committed"] = int(100 * money_committed)
            committed_player_stats["totalProfit"] = int(committed_player_stats["winnings"] - paid)
            # Live-capture builders keep splash payouts outside pot collections,
            # while hand-history converters include STP in the pot. Normalize the
            # stored profit so the graph's optional splash subtraction is valid
            # for both representations.
            if not _pot_stp(hand) and getattr(hand, "splashWinnings", None):
                committed_player_stats["totalProfit"] += int(
                    CENTS_MULTIPLIER * _to_decimal(hand.splashWinnings.get(player, 0)),
                )
            committed_player_stats["flg_won_hand"] = committed_player_stats["totalProfit"] > 0
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

    def _assemblePlayerCashOuts(self, hand: Any) -> None:
        """Insurance payouts, kept apart from pot winnings."""
        # Cash Out handling - store amounts separately from winnings
        # Cash out is an insurance payout, not pot winnings
        if hasattr(hand, "cashOutAmounts") and hand.cashOutAmounts:
            for player, amount in hand.cashOutAmounts.items():
                if player in self.handsplayers:
                    self.handsplayers[player]["cashOutAmount"] = int(100 * amount)

        if getattr(hand, "splashWinnings", None):
            for player, amount in hand.splashWinnings.items():
                if player in self.handsplayers:
                    self.handsplayers[player]["splashWinnings"] = int(100 * amount)

        if hasattr(hand, "cashOutFees") and hand.cashOutFees:
            for player, fee in hand.cashOutFees.items():
                if player in self.handsplayers:
                    self.handsplayers[player]["cashOutFee"] = int(100 * fee)

    def _assemblePlayerHoleCards(self, hand: Any) -> None:
        """Encode each player's holding and split showdown winnings."""
        # More inner-loop speed hackery.
        encode_card = Card.encodeCard
        calc_start_cards = Card.calcStartCards
        for player in hand.players:
            player_name = player[1]
            hcs = hand.join_holecards(player_name, asList=True)
            hcs = hcs + ["0x"] * 18
            player_stats = self.handsplayers[player_name]
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
        seated_players = [p[1] for p in getattr(hand, "players", [])]

        # set blinds first, then others from pfbao list, avoids problem if bb
        # is missing from pfbao list or if there is no small blind
        sb: list[str] = []
        bb: list[str] = []
        bi: list[str] = []
        ub: list[str] = []
        if hand.gametype["base"] == "stud":
            # Stud position is determined after cards are dealt
            # First player to act is always the bring-in position in stud
            # even if they decided to bet/completed
            opening_actions = hand.actions[hand.actionStreets[1]]
            if not opening_actions:
                for player in self.handsplayers.values():
                    player["position"] = ANTE_ALL_IN_POSITION
                self.hands["maxPosition"] = -1
                return
            bi = [opening_actions[0][0]]
        else:
            ub = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "button blind"]
            bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "big blind"]
            sb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "small blind"]
        # Set positions in order: Button=0, SB=S, BB=B, then others backwards (CO=1, HJ=2...)

        # Button position
        if ub:
            self.handsplayers[ub[0]]["position"] = 0
            self.handsplayers[ub[0]]["street0InPosition"] = True

        # Small blind position
        if sb:
            self.handsplayers[sb[0]]["position"] = "S"
            self.handsplayers[sb[0]]["flg_blind_s"] = True
            self.handsplayers[sb[0]]["street0FirstToAct"] = True

        # Big blind position
        if bb:
            self.handsplayers[bb[0]]["position"] = "B"
            self.handsplayers[bb[0]]["flg_blind_b"] = True
            self.handsplayers[bb[0]]["street0InPosition"] = True

        # Bring-in position (stud). Legacy HUD/database code treats this like
        # the first blind slot ("S") and uses numeric positions for the rest.
        if bi:
            self.handsplayers[bi[0]]["position"] = "S"
            self.handsplayers[bi[0]]["street0FirstToAct"] = True

            action_order = []
            for action in hand.actions[hand.actionStreets[1]][1:]:
                pname = action[0]
                if pname == bi[0]:
                    break
                if pname not in action_order:
                    action_order.append(pname)

            pos_val = 0
            for pname in reversed(action_order):
                if pname in self.handsplayers:
                    self.handsplayers[pname]["position"] = pos_val
                    if pos_val == 0:
                        self.handsplayers[pname]["street0InPosition"] = True
                    pos_val += 1
            self.hands["maxPosition"] = max(pos_val - 1, 0)
            return

        # Assign positions to remaining players
        # The CO is 1, HJ is 2, etc. (distance backwards from button)
        assigned_players = set()
        if ub:
            assigned_players.add(ub[0])
        if sb:
            assigned_players.add(sb[0])
        if bb:
            assigned_players.add(bb[0])
        if bi:
            assigned_players.add(bi[0])

        # We want to find players who are NOT blinds/BTN and assign them CO, HJ, etc.
        # starting from the player right before the Button (CO).

        try:
            log.debug("setPositions: players=%s, sb=%s, bb=%s", players, sb, bb)
            btn_idx = -1
            if ub:
                if ub[0] in players:
                    btn_idx = players.index(ub[0])
                    log.debug("setPositions: Found button via ub: %s (idx %s)", ub[0], btn_idx)
                elif ub[0] in seated_players:
                    if ub[0] in self.handsplayers:
                        self.handsplayers[ub[0]]["position"] = 0
                        self.handsplayers[ub[0]]["street0InPosition"] = True
                        assigned_players.add(ub[0])
            elif sb:
                # Button is the player before SB
                if sb[0] in players:
                    sb_idx = players.index(sb[0])
                    btn_idx = (sb_idx - 1) % len(players)
                    log.debug("setPositions: Found button via sb fallback: %s (idx %s)", players[btn_idx], btn_idx)
                elif sb[0] in seated_players:
                    seat_idx = seated_players.index(sb[0])
                    button_name = seated_players[seat_idx - 1]
                    if button_name in players:
                        btn_idx = players.index(button_name)
                    elif button_name in self.handsplayers:
                        self.handsplayers[button_name]["position"] = 0
                        self.handsplayers[button_name]["street0InPosition"] = True
                        assigned_players.add(button_name)
            elif bb and seated_players and bb[0] in seated_players:
                bb_idx = seated_players.index(bb[0])
                button_name = seated_players[bb_idx - 1]
                if button_name in players:
                    btn_idx = players.index(button_name)
                elif button_name in self.handsplayers:
                    self.handsplayers[button_name]["position"] = 0
                    self.handsplayers[button_name]["street0InPosition"] = True
                    assigned_players.add(button_name)

            if btn_idx != -1:
                # Set Button position to 0 explicitly, except heads-up where
                # the button is also the small blind and keeps the blind marker.
                btn_p = players[btn_idx]
                if btn_p not in assigned_players:
                    self.handsplayers[btn_p]["position"] = 0
                    self.handsplayers[btn_p]["street0InPosition"] = True
                    assigned_players.add(btn_p)

                # Iterate backwards from btn_idx - 1
                pos_val = 1
                for i in range(1, len(players)):
                    idx = (btn_idx - i) % len(players)
                    p = players[idx]
                    if p not in assigned_players:
                        self.handsplayers[p]["position"] = pos_val
                        log.debug("setPositions: Set %s to position %s", p, pos_val)
                        pos_val += 1
                self.hands["maxPosition"] = pos_val - 1
                for p in self.handsplayers:
                    log.debug("setPositions: Final position for %s: %s", p, self.handsplayers[p].get("position"))
            elif 0 in [self.handsplayers[p].get("position") for p in self.handsplayers]:
                pos_val = 1
                for pname in reversed(seated_players):
                    if pname not in assigned_players and pname in self.handsplayers:
                        self.handsplayers[pname]["position"] = pos_val
                        pos_val += 1
                self.hands["maxPosition"] = pos_val - 1
        except (ValueError, ZeroDivisionError):
            log.exception("setPositions: Error calculating positions")

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
