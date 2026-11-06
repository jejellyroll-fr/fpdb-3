#!/usr/bin/env python
from __future__ import annotations

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

import os
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.derived_stats_actions import DerivedStatsActionsMixin
from fpdb_3_legacy.derived_stats_allin import DerivedStatsAllInMixin
from fpdb_3_legacy.derived_stats_allin import pokereval as pokereval
from fpdb_3_legacy.derived_stats_base import ACTION_AMOUNT_IDX as ACTION_AMOUNT_IDX
from fpdb_3_legacy.derived_stats_base import ACTION_CALLED_IDX as ACTION_CALLED_IDX
from fpdb_3_legacy.derived_stats_base import ACTION_CARDS_DISCARDED_IDX as ACTION_CARDS_DISCARDED_IDX
from fpdb_3_legacy.derived_stats_base import ACTION_PLAYER_IDX as ACTION_PLAYER_IDX
from fpdb_3_legacy.derived_stats_base import ACTION_RAISETO_IDX as ACTION_RAISETO_IDX
from fpdb_3_legacy.derived_stats_base import ACTION_TYPE_IDX as ACTION_TYPE_IDX
from fpdb_3_legacy.derived_stats_base import ANTE_ALL_IN_POSITION as ANTE_ALL_IN_POSITION
from fpdb_3_legacy.derived_stats_base import CENTS_MULTIPLIER as CENTS_MULTIPLIER
from fpdb_3_legacy.derived_stats_base import FINAL_POT_IDX as FINAL_POT_IDX
from fpdb_3_legacy.derived_stats_base import FOLD_TO_4BET_LEVEL as FOLD_TO_4BET_LEVEL
from fpdb_3_legacy.derived_stats_base import FOUR_BET_LEVEL as FOUR_BET_LEVEL
from fpdb_3_legacy.derived_stats_base import MIN_ACTION_LENGTH_FOR_ALLIN as MIN_ACTION_LENGTH_FOR_ALLIN
from fpdb_3_legacy.derived_stats_base import MIN_ACTIONS_FOR_CHECK_CALL_RAISE as MIN_ACTIONS_FOR_CHECK_CALL_RAISE
from fpdb_3_legacy.derived_stats_base import MIN_MAXCARDS_SIZE as MIN_MAXCARDS_SIZE
from fpdb_3_legacy.derived_stats_base import MIN_PLAYER_TUPLE_LENGTH as MIN_PLAYER_TUPLE_LENGTH
from fpdb_3_legacy.derived_stats_base import MIN_PLAYERS_FOR_GAME as MIN_PLAYERS_FOR_GAME
from fpdb_3_legacy.derived_stats_base import MIN_POSTFLOP_BOARD_SIZE as MIN_POSTFLOP_BOARD_SIZE
from fpdb_3_legacy.derived_stats_base import MIN_RUN_IT_TIMES as MIN_RUN_IT_TIMES
from fpdb_3_legacy.derived_stats_base import MIN_STREETS_FOR_PREFLOP as MIN_STREETS_FOR_PREFLOP
from fpdb_3_legacy.derived_stats_base import STREET0_IDX as STREET0_IDX
from fpdb_3_legacy.derived_stats_base import STREET1_IDX as STREET1_IDX
from fpdb_3_legacy.derived_stats_base import STREET2_IDX as STREET2_IDX
from fpdb_3_legacy.derived_stats_base import STREET3_IDX as STREET3_IDX
from fpdb_3_legacy.derived_stats_base import STREET4_IDX as STREET4_IDX
from fpdb_3_legacy.derived_stats_base import THREE_BET_LEVEL as THREE_BET_LEVEL
from fpdb_3_legacy.derived_stats_base import _chip_increment as _chip_increment
from fpdb_3_legacy.derived_stats_base import _is_all_in_or_fold as _is_all_in_or_fold
from fpdb_3_legacy.derived_stats_base import _pot_stp as _pot_stp
from fpdb_3_legacy.derived_stats_base import _to_decimal as _to_decimal
from fpdb_3_legacy.derived_stats_facing import DerivedStatsFacingMixin
from fpdb_3_legacy.derived_stats_hands import DerivedStatsHandsMixin
from fpdb_3_legacy.derived_stats_init import _INIT_STATS as _INIT_STATS
from fpdb_3_legacy.derived_stats_init import ACTION_ENUM_KEYS as ACTION_ENUM_KEYS
from fpdb_3_legacy.derived_stats_init import _buildStatsInitializer as _buildStatsInitializer
from fpdb_3_legacy.derived_stats_players import DerivedStatsPlayersMixin
from fpdb_3_legacy.derived_stats_postflop import DerivedStatsPostflopMixin
from fpdb_3_legacy.derived_stats_preflop import DerivedStatsPreflopMixin
from fpdb_3_legacy.hand_state_store import enumerate_hand_states
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.player_situations import enumerate_situations

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("derived_stats")


class DerivedStats(
    DerivedStatsHandsMixin,
    DerivedStatsPlayersMixin,
    DerivedStatsActionsMixin,
    DerivedStatsFacingMixin,
    DerivedStatsPreflopMixin,
    DerivedStatsPostflopMixin,
    DerivedStatsAllInMixin,
):
    """Calculate derived statistics for poker hands."""

    def __init__(self) -> None:
        """Initialize DerivedStats instance."""
        self.hands: dict[str, Any] = {}
        self.handsplayers: dict[str, dict[str, Any]] = {}
        self.handsactions: dict[Any, Any] = {}
        self.situations: list[Any] = []
        self.hand_states: list[Any] = []
        self.handsstove: list[Any] = []
        self.handspots: list[Any] = []

        # Check environment variable for rake rounding mode
        self.use_round_down = os.environ.get("FPDB_RAKE_ROUND_DOWN", "true").lower() in ("true", "1", "yes")
        log.debug("Rake rounding mode: %s", "ROUND_DOWN" if self.use_round_down else "default")

    def getStats(self, hand: Any) -> None:
        """Calculate and store statistics for a poker hand."""
        # Snapshot the raw action tuples before downstream calculators may
        # condense/replace hand.actions (calcActionEnums depends on them).
        self.raw_actions_snapshot = {
            st: list(acts) for st, acts in getattr(hand, "actions", {}).items()
        }
        for player in hand.players:
            self.handsplayers[player[1]] = _INIT_STATS.copy()

        self.assembleHands(hand)
        self.assembleHandsPlayers(hand)
        self.assembleHandsActions(hand)
        # Third pass, over what the two above produced: one named situation per
        # decision (issue #294). Purely additive -- no calculator reads it yet.
        self.situations = list(enumerate_situations(hand, self.handsplayers, self.handsactions))
        # Fourth pass, over the situations: what each postflop decision was
        # holding (issue #302). It reads the two encoded cards the player rows
        # already carry, so a player whose cards were never shown simply has no
        # state -- there is nothing to guess from.
        self.hand_states = list(enumerate_hand_states(self.situations, self.handsplayers))

        if pokereval and hand.gametype["category"] in Card.games and getattr(hand, "playerIds", None):
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

    def getSituations(self) -> list:
        """Get the named decision situations of the hand (issue #294)."""
        return self.situations

    def getHandStates(self) -> list:
        """Get the classified postflop decisions of the hand (issue #302)."""
        return self.hand_states

    def getHandsStove(self) -> list:
        """Get hands stove statistics."""
        return self.handsstove

    def getHandsPots(self) -> list:
        """Get hands pots statistics."""
        return self.handspots

    def _calcDerivedPlayerStats(self, hand: Any) -> None:
        """Run the per-player calculators, whose order is significant."""
        self.setPositions(hand)
        self.calcSpecialBlinds(hand)
        self.calcFacedAllin(hand)
        self.calcBetFacing(hand)
        self.calcPreflopRaiseFacing(hand)
        self.calcPostflopRaiseFacing(hand)
        self.calcRaiseMade(hand)
        self.calcBetAmounts(hand)
        self.calcEffectiveStack(hand)
        self.calcStreetSPR(hand)
        self.calcCheckCallRaise(hand)
        self.calc34BetStreet0(hand)
        self.calcSqueezeDefense(hand)
        self.calcActionEnums(hand)
        self.calcFaceLimpers(hand)
        self.calc3BetPostflop(hand)
        self.calc4BetPostflop(hand)
        self.calcPostflopOpen(hand)
        self.calcPostflopFirstRaise(hand)
        self.calcFaceRaise(hand)
        self.calcCalledRaiseStreet0(hand)
        self.calcSteals(hand)
        self.calcFlopStats(hand)
        self.calcTurnStats(hand)
        self.calcRiverStats(hand)
        self.calcGpStats(hand)  # after calcSteals: needs raiseFirstInChance/raisedFirstIn
        self.vpip(hand)  # Calculate VPIP after all player stats are initialized
        # Additional stats
        # 3betSB, 3betBB
        # Squeeze, Ratchet?

    def assembleHandsPlayers(self, hand: Any) -> None:
        """Assemble statistics for each player in the hand."""
        # street0VPI/vpip already called in Hand
        # sawShowdown is calculated in playersAtStreetX, as that calculation gives us a convenient list of names
        self._assemblePlayerSeats(hand)
        self._assemblePlayerActionCounts(hand)
        self._assemblePlayerWinnings(hand)
        self._assemblePlayerContributions(hand)
        self._assemblePlayerCashOuts(hand)
        self.calcCBets(hand)
        self.calcLimpStreet0(hand)
        self._assemblePlayerHoleCards(hand)
        self._calcDerivedPlayerStats(hand)

    def assembleHudCache(self, hand: Any) -> None:
        """Assemble HUD cache data - required for HUD functionality."""
        # No real work to be done - HandsPlayers data already contains the correct info
