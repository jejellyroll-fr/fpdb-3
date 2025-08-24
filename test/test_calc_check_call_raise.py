#!/usr/bin/env python3
"""Test suite for calcCheckCallRaise function in DerivedStats module.

This module tests the calcCheckCallRaise functionality which calculates
check-call and check-raise statistics for players based on hand actions.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DerivedStats import DerivedStats, MIN_ACTIONS_FOR_CHECK_CALL_RAISE


class TestCalcCheckCallRaise:
    """Test suite for calcCheckCallRaise function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.derived_stats = DerivedStats()
        self.derived_stats.handsplayers = {}

    def create_mock_hand(self, action_streets=None, actions=None):
        """Create a mock hand object with specified actions."""
        hand = Mock()
        hand.actionStreets = action_streets or ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        hand.actions = actions or {}
        return hand

    def test_no_handsplayers_attribute(self):
        """Test that function returns early if handsplayers attribute doesn't exist."""
        derived_stats = DerivedStats()
        # Don't set handsplayers attribute
        hand = self.create_mock_hand()
        
        # Should return without error
        derived_stats.calcCheckCallRaise(hand)

    def test_no_actions_for_player(self):
        """Test that no stats are set if player has no actions on street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = []  # No actions for any player
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # No check-call-raise stats should be added
        assert "street1CheckCallRaiseChance" not in self.derived_stats.handsplayers["player1"]

    def test_insufficient_actions(self):
        """Test that no stats are set if player has less than MIN_ACTIONS_FOR_CHECK_CALL_RAISE actions."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # Only one action (less than MIN_ACTIONS_FOR_CHECK_CALL_RAISE)
        flop_actions = [("player1", "checks", None, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # No check-call-raise stats should be added
        assert "street1CheckCallRaiseChance" not in self.derived_stats.handsplayers["player1"]

    def test_first_action_not_check(self):
        """Test that no stats are set if player's first action is not a check."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # First action is not a check
        flop_actions = [
            ("player1", "bets", 100, None, False),
            ("player1", "calls", 200, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # No check-call-raise stats should be added
        assert "street1CheckCallRaiseChance" not in self.derived_stats.handsplayers["player1"]

    def test_check_call_opportunity_initialization(self):
        """Test that check-call-raise opportunity is properly initialized."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # Check followed by fold (no call or raise)
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "folds", None, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Should initialize all three stats
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is False
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is False

    def test_check_call_done(self):
        """Test that check-call done is set when player checks then calls."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "calls", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is False

    def test_check_raise_done(self):
        """Test that check-raise done is set when player checks then raises."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "raises", 200, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is False
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is True

    def test_check_then_multiple_actions(self):
        """Test that only the first subsequent action after check is considered."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # Check, call, then raise - should only register the call
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "calls", 100, None, False),
            ("player1", "raises", 200, None, False),  # This should be ignored
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is False

    def test_multiple_streets(self):
        """Test check-call-raise calculation across multiple streets."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "calls", 100, None, False),
        ]
        turn_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "raises", 200, None, False),
        ]
        river_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "folds", None, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
            actions={
                "PREFLOP": [],
                "FLOP": flop_actions,
                "TURN": turn_actions,
                "RIVER": river_actions,
            }
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Flop: check-call
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is False
        
        # Turn: check-raise
        assert self.derived_stats.handsplayers["player1"]["street2CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street2CheckCallDone"] is False
        assert self.derived_stats.handsplayers["player1"]["street2CheckRaiseDone"] is True
        
        # River: check-fold (no call or raise)
        assert self.derived_stats.handsplayers["player1"]["street3CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street3CheckCallDone"] is False
        assert self.derived_stats.handsplayers["player1"]["street3CheckRaiseDone"] is False

    def test_multiple_players(self):
        """Test check-call-raise calculation for multiple players."""
        self.derived_stats.handsplayers = {
            "player1": {},
            "player2": {},
            "player3": {}
        }
        
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player2", "bets", 100, None, False),
            ("player3", "checks", None, None, False),
            ("player1", "calls", 100, None, False),  # check-call
            ("player3", "raises", 300, None, False),  # check-raise
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # player1: check-call
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is True
        assert self.derived_stats.handsplayers["player1"]["street1CheckRaiseDone"] is False
        
        # player2: no check-call-raise opportunity (didn't check first)
        assert "street1CheckCallRaiseChance" not in self.derived_stats.handsplayers["player2"]
        
        # player3: check-raise
        assert self.derived_stats.handsplayers["player3"]["street1CheckCallRaiseChance"] is True
        assert self.derived_stats.handsplayers["player3"]["street1CheckCallDone"] is False
        assert self.derived_stats.handsplayers["player3"]["street1CheckRaiseDone"] is True

    def test_existing_stats_preservation(self):
        """Test that existing stats are preserved when initializing new ones."""
        self.derived_stats.handsplayers = {
            "player1": {
                "street1CheckCallRaiseChance": True,  # Already exists
                "existingstat": "value"
            }
        }
        
        flop_actions = [
            ("player1", "checks", None, None, False),
            ("player1", "calls", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Existing stats should be preserved
        assert self.derived_stats.handsplayers["player1"]["existingstat"] == "value"
        # New stats should be set
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallDone"] is True

    def test_limited_streets_processing(self):
        """Test that only up to 4 streets are processed (flop, turn, river, 7th)."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # Create hand with many streets
        action_streets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER", "7TH", "8TH", "9TH"]
        actions = {
            "PREFLOP": [],
            "FLOP": [("player1", "checks", None, None, False), ("player1", "calls", 100, None, False)],
            "TURN": [("player1", "checks", None, None, False), ("player1", "calls", 200, None, False)],
            "RIVER": [("player1", "checks", None, None, False), ("player1", "calls", 400, None, False)],
            "7TH": [("player1", "checks", None, None, False), ("player1", "calls", 800, None, False)],
            "8TH": [("player1", "checks", None, None, False), ("player1", "calls", 1600, None, False)],  # Should be ignored
            "9TH": [("player1", "checks", None, None, False), ("player1", "calls", 3200, None, False)],  # Should be ignored
        }
        
        hand = self.create_mock_hand(action_streets=action_streets, actions=actions)
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Should have stats for streets 1-4 only
        assert "street1CheckCallRaiseChance" in self.derived_stats.handsplayers["player1"]
        assert "street2CheckCallRaiseChance" in self.derived_stats.handsplayers["player1"]
        assert "street3CheckCallRaiseChance" in self.derived_stats.handsplayers["player1"]
        assert "street4CheckCallRaiseChance" in self.derived_stats.handsplayers["player1"]
        # Should not have stats for street5 and beyond
        assert "street5CheckCallRaiseChance" not in self.derived_stats.handsplayers["player1"]

    def test_mixed_action_sequences(self):
        """Test various action sequences after initial check."""
        self.derived_stats.handsplayers = {
            "checker_folder": {},
            "checker_caller": {},
            "checker_raiser": {},
            "checker_better": {}  # Check then bet (not call/raise)
        }
        
        flop_actions = [
            ("checker_folder", "checks", None, None, False),
            ("checker_caller", "checks", None, None, False),
            ("checker_raiser", "checks", None, None, False),
            ("checker_better", "checks", None, None, False),
            ("checker_folder", "folds", None, None, False),
            ("checker_caller", "calls", 100, None, False),
            ("checker_raiser", "raises", 300, None, False),
            ("checker_better", "bets", 150, None, False),  # Should not count as call or raise
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # All should have the opportunity
        for player in ["checker_folder", "checker_caller", "checker_raiser", "checker_better"]:
            assert self.derived_stats.handsplayers[player]["street1CheckCallRaiseChance"] is True
        
        # Only caller should have CheckCallDone
        assert self.derived_stats.handsplayers["checker_folder"]["street1CheckCallDone"] is False
        assert self.derived_stats.handsplayers["checker_caller"]["street1CheckCallDone"] is True
        assert self.derived_stats.handsplayers["checker_raiser"]["street1CheckCallDone"] is False
        assert self.derived_stats.handsplayers["checker_better"]["street1CheckCallDone"] is False
        
        # Only raiser should have CheckRaiseDone
        assert self.derived_stats.handsplayers["checker_folder"]["street1CheckRaiseDone"] is False
        assert self.derived_stats.handsplayers["checker_caller"]["street1CheckRaiseDone"] is False
        assert self.derived_stats.handsplayers["checker_raiser"]["street1CheckRaiseDone"] is True
        assert self.derived_stats.handsplayers["checker_better"]["street1CheckRaiseDone"] is False

    def test_min_actions_constant(self):
        """Test that the MIN_ACTIONS_FOR_CHECK_CALL_RAISE constant is used correctly."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # Create exactly MIN_ACTIONS_FOR_CHECK_CALL_RAISE actions
        flop_actions = []
        for i in range(MIN_ACTIONS_FOR_CHECK_CALL_RAISE):
            if i == 0:
                flop_actions.append(("player1", "checks", None, None, False))
            else:
                flop_actions.append(("player1", "calls", 100, None, False))
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Should have stats (exactly at minimum threshold)
        assert self.derived_stats.handsplayers["player1"]["street1CheckCallRaiseChance"] is True
        
        # Test with one less action
        self.derived_stats.handsplayers = {"player1": {}}
        flop_actions_insufficient = flop_actions[:-1]  # Remove one action
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions_insufficient}
        )
        
        self.derived_stats.calcCheckCallRaise(hand)
        
        # Should not have stats (below minimum threshold)
        assert "street1CheckCallRaiseChance" not in self.derived_stats.handsplayers["player1"]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])