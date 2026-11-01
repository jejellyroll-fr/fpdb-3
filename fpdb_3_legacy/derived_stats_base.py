"""Shared ground of the DerivedStats mixins: constants, small helpers and the action-list helpers."""

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

from decimal import Decimal
from typing import Any

from fpdb_3_legacy.autonotes_aof import is_aof_category
from fpdb_3_legacy.loggingFpdb import get_logger

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


def _to_decimal(value: Any) -> Decimal:
    """Best-effort Decimal conversion. Accepts numbers and numeric strings
    (parsers store blinds as strings); returns 0 for anything else (e.g. mocks)."""
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)


def _pot_stp(hand: Any) -> Decimal:
    """Bomb / 'Escape to Pot' money seeded into the pot (currency units, 0 if absent)."""
    return _to_decimal(getattr(getattr(hand, "pot", None), "stp", 0))


# Constants for betting levels
THREE_BET_LEVEL = 2
FOUR_BET_LEVEL = 3
FOLD_TO_4BET_LEVEL = 4

# Constants for poker evaluations
MIN_POSTFLOP_BOARD_SIZE = 3
MIN_MAXCARDS_SIZE = 5
ANTE_ALL_IN_POSITION = 9
MIN_RUN_IT_TIMES = 2


def _chip_increment(factor: int) -> Decimal:
    """Return the smallest distributable unit without mixing Decimal and float."""
    return Decimal(1) / Decimal(factor)


def _is_all_in_or_fold(hand: Any) -> bool:
    """True for a game whose only decision is all-in or fold.

    fpdb models it with the flop as street zero, so the columns filled here
    for "preflop" are filled from that decision -- but the conventions built
    around a preflop round do not all carry over to it.
    """
    return is_aof_category((getattr(hand, "gametype", {}) or {}).get("category"))


class DerivedStatsBase:
    """The state every DerivedStats mixin works on, and the helpers they share."""

    hands: dict[str, Any]
    handsplayers: dict[str, dict[str, Any]]
    handsactions: dict[Any, Any]
    situations: list[Any]
    hand_states: list[Any]
    handsstove: list[Any]
    handspots: list[Any]
    raw_actions_snapshot: dict[Any, list[Any]]
    use_round_down: bool

    @staticmethod
    def _players_who_called_aggressor(actions: list, aggressor: str | None) -> set[str]:
        """Return players who called after the aggressor bet or raised on a street."""
        if not aggressor:
            return set()

        callers = set()
        aggressor_bet_seen = False
        for action in actions:
            player, action_type = action[0], action[1]
            if player == aggressor and action_type in ("bets", "raises"):
                aggressor_bet_seen = True
            elif aggressor_bet_seen and player != aggressor and action_type == "calls":
                callers.add(player)
        return callers

    def _set_float_stats(
        self,
        street_actions: list,
        previous_actions: list,
        previous_aggressor: str | None,
        seen_key: str,
        float_opp_key: str,
        float_done_key: str,
        float_def_opp_key: str,
        log_prefix: str,
    ) -> None:
        """Set float opportunity/done flags when an IP caller bets after the aggressor checks."""
        candidates = self._players_who_called_aggressor(previous_actions, previous_aggressor)
        if not previous_aggressor or not candidates:
            log.debug(
                "%s: No float candidates (previous_aggressor=%s, candidates=%s)",
                log_prefix,
                previous_aggressor,
                candidates,
            )
            return

        aggressor_checked = False
        for action in street_actions:
            player, action_type = action[0], action[1]
            if player == previous_aggressor and action_type == "checks":
                aggressor_checked = True
                log.debug("%s: Previous aggressor %s checked", log_prefix, previous_aggressor)
                continue

            if not aggressor_checked:
                continue

            if player in candidates and player in self.handsplayers and self.handsplayers[player].get(seen_key, False):
                log.debug("%s: Setting %s=True for player %s", log_prefix, float_opp_key, player)
                self.handsplayers[player][float_opp_key] = True
                if action_type in ("bets", "raises"):
                    log.debug("%s: Setting %s=True for player %s", log_prefix, float_done_key, player)
                    self.handsplayers[player][float_done_key] = True
                    if previous_aggressor in self.handsplayers and self.handsplayers[previous_aggressor].get(
                        seen_key, False
                    ):
                        log.debug(
                            "%s: Setting %s=True for previous aggressor %s",
                            log_prefix,
                            float_def_opp_key,
                            previous_aggressor,
                        )
                        self.handsplayers[previous_aggressor][float_def_opp_key] = True
                    break
            elif action_type in ("bets", "raises"):
                break

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
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Calls" not in player_stats:
                    player_stats[f"street{i}Calls"] = 0
                player_stats[f"street{i}Calls"] = 1 + player_stats[f"street{i}Calls"]

    def bets(self, hand: Any, i: int) -> None:
        """Calculate bet statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("bets"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Bets" not in player_stats:
                    player_stats[f"street{i}Bets"] = 0
                player_stats[f"street{i}Bets"] = 1 + player_stats[f"street{i}Bets"]

    def raises(self, hand: Any, i: int) -> None:
        """Calculate raise statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("completes", "raises"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Raises" not in player_stats:
                    player_stats[f"street{i}Raises"] = 0
                player_stats[f"street{i}Raises"] = 1 + player_stats[f"street{i}Raises"]

    def folds(self, hand: Any, i: int) -> None:
        """Calculate fold statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("folds"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"otherRaisedStreet{i}" not in player_stats:
                    player_stats[f"otherRaisedStreet{i}"] = False
                if f"foldToOtherRaisedStreet{i}" not in player_stats:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = False
                if player_stats[f"otherRaisedStreet{i}"]:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = True
                    # print "DEBUG: fold detected on handid %s for %s on actionStreet[%s]: %s"
                    #                       %(hand.handid, act[0],hand.actionStreets[i+1], i)
