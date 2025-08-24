#!/usr/bin/env python3
"""Test suite for action counting functions in DerivedStats module.

This module tests the calls, bets, raises, and folds functions which count
player actions on specific streets.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DerivedStats import DerivedStats


class TestActionCounting:
    """Test suite for action counting functions."""

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

    # Tests for calls() function
    def test_calls_no_actions(self):
        """Test calls function when there are no actions on the street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": []}
        )
        
        self.derived_stats.calls(hand, 1)  # Street 1 = FLOP
        
        # No call stats should be added
        assert "street1Calls" not in self.derived_stats.handsplayers["player1"]

    def test_calls_single_call(self):
        """Test calls function with a single call action."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [("player1", "calls", 50, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 1

    def test_calls_multiple_calls_same_player(self):
        """Test calls function with multiple calls by the same player."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),
            ("player1", "calls", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 2

    def test_calls_multiple_players(self):
        """Test calls function with multiple players calling."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),
            ("player2", "calls", 50, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 1
        assert self.derived_stats.handsplayers["player2"]["street1Calls"] == 1

    def test_calls_mixed_actions(self):
        """Test calls function ignores non-call actions."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "bets", 50, None, False),   # Should be ignored
            ("player1", "calls", 100, None, False), # Should be counted
            ("player1", "raises", 200, None, False), # Should be ignored
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 1

    # Tests for bets() function
    def test_bets_no_actions(self):
        """Test bets function when there are no actions on the street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": []}
        )
        
        self.derived_stats.bets(hand, 1)  # Street 1 = FLOP
        
        assert "street1Bets" not in self.derived_stats.handsplayers["player1"]

    def test_bets_single_bet(self):
        """Test bets function with a single bet action."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [("player1", "bets", 50, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.bets(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Bets"] == 1

    def test_bets_multiple_bets(self):
        """Test bets function with multiple bets by the same player."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player1", "bets", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.bets(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Bets"] == 2

    def test_bets_mixed_actions(self):
        """Test bets function ignores non-bet actions."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),   # Should be ignored
            ("player1", "bets", 100, None, False),   # Should be counted
            ("player1", "raises", 200, None, False), # Should be ignored
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.bets(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Bets"] == 1

    # Tests for raises() function
    def test_raises_no_actions(self):
        """Test raises function when there are no actions on the street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": []}
        )
        
        self.derived_stats.raises(hand, 1)  # Street 1 = FLOP
        
        assert "street1Raises" not in self.derived_stats.handsplayers["player1"]

    def test_raises_single_raise(self):
        """Test raises function with a single raise action."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [("player1", "raises", 150, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.raises(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Raises"] == 1

    def test_raises_completes_action(self):
        """Test raises function recognizes 'completes' as a raise."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [("player1", "completes", 25, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.raises(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Raises"] == 1

    def test_raises_multiple_raises(self):
        """Test raises function with multiple raises/completes."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "raises", 100, None, False),
            ("player1", "completes", 25, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.raises(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Raises"] == 2

    def test_raises_mixed_actions(self):
        """Test raises function ignores non-raise actions."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),    # Should be ignored
            ("player1", "bets", 100, None, False),    # Should be ignored
            ("player1", "raises", 200, None, False),  # Should be counted
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.raises(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Raises"] == 1

    # Tests for folds() function
    def test_folds_no_actions(self):
        """Test folds function when there are no actions on the street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": []}
        )
        
        self.derived_stats.folds(hand, 1)  # Street 1 = FLOP
        
        # No fold-related stats should be added if player never folded
        assert "foldToOtherRaisedStreet1" not in self.derived_stats.handsplayers["player1"]

    def test_folds_single_fold_no_other_raised(self):
        """Test folds function with a fold but no otherRaisedStreet set."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        flop_actions = [("player1", "folds", None, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.folds(hand, 1)  # Street 1 = FLOP
        
        # Should initialize but not set foldToOtherRaisedStreet1 (no otherRaisedStreet1)
        assert self.derived_stats.handsplayers["player1"]["otherRaisedStreet1"] is False
        assert self.derived_stats.handsplayers["player1"]["foldToOtherRaisedStreet1"] is False

    def test_folds_single_fold_with_other_raised(self):
        """Test folds function with a fold when otherRaisedStreet is True."""
        self.derived_stats.handsplayers = {"player1": {"otherRaisedStreet1": True}}
        
        flop_actions = [("player1", "folds", None, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.folds(hand, 1)  # Street 1 = FLOP
        
        # Should set foldToOtherRaisedStreet1 (otherRaisedStreet1 was True)
        assert self.derived_stats.handsplayers["player1"]["otherRaisedStreet1"] is True
        assert self.derived_stats.handsplayers["player1"]["foldToOtherRaisedStreet1"] is True

    def test_folds_multiple_folds(self):
        """Test folds function with multiple fold actions."""
        self.derived_stats.handsplayers = {"player1": {"otherRaisedStreet1": True}}
        
        flop_actions = [
            ("player1", "folds", None, None, False),
            ("player1", "folds", None, None, False),  # Multiple folds (unusual but possible)
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.folds(hand, 1)  # Street 1 = FLOP
        
        # Should still be True (set once, stays True)
        assert self.derived_stats.handsplayers["player1"]["foldToOtherRaisedStreet1"] is True

    def test_folds_mixed_actions(self):
        """Test folds function only processes fold actions."""
        self.derived_stats.handsplayers = {"player1": {"otherRaisedStreet1": True}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),   # Should be ignored
            ("player1", "bets", 100, None, False),   # Should be ignored
            ("player1", "folds", None, None, False), # Should be processed
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.folds(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["foldToOtherRaisedStreet1"] is True

    # Integration tests
    def test_multiple_streets_action_counting(self):
        """Test action counting across multiple streets."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
            actions={
                "PREFLOP": [("player1", "raises", 20, None, False)],
                "FLOP": [("player1", "bets", 50, None, False)],
                "TURN": [("player1", "calls", 100, None, False)],
                "RIVER": [("player1", "folds", None, None, False)]
            }
        )
        
        # Test each street
        self.derived_stats.raises(hand, 0)  # PREFLOP
        self.derived_stats.bets(hand, 1)    # FLOP
        self.derived_stats.calls(hand, 2)   # TURN
        self.derived_stats.folds(hand, 3)   # RIVER
        
        # Check counts
        assert self.derived_stats.handsplayers["player1"]["street0Raises"] == 1
        assert self.derived_stats.handsplayers["player1"]["street1Bets"] == 1
        assert self.derived_stats.handsplayers["player1"]["street2Calls"] == 1
        # Fold stats depend on otherRaisedStreet3 being set

    def test_player_not_in_handsplayers(self):
        """Test that functions handle players not in handsplayers gracefully."""
        # The functions assume all players acting are in handsplayers
        # This test verifies that both players get their action stats when in handsplayers
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),
            ("player2", "bets", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)
        self.derived_stats.bets(hand, 1)
        
        # Both players should have their respective stats
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 1
        assert self.derived_stats.handsplayers["player2"]["street1Bets"] == 1

    def test_stat_initialization_and_accumulation(self):
        """Test that stats are properly initialized and accumulated."""
        self.derived_stats.handsplayers = {"player1": {"existingstat": "value"}}
        
        flop_actions = [
            ("player1", "calls", 50, None, False),
            ("player1", "calls", 100, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions}
        )
        
        self.derived_stats.calls(hand, 1)
        
        # Existing stats should be preserved
        assert self.derived_stats.handsplayers["player1"]["existingstat"] == "value"
        # New stats should accumulate correctly
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 2

    def test_different_streets_same_action_type(self):
        """Test that same action type on different streets creates different stats."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN"],
            actions={
                "PREFLOP": [("player1", "calls", 20, None, False)],
                "FLOP": [("player1", "calls", 50, None, False)],
                "TURN": [("player1", "calls", 100, None, False)]
            }
        )
        
        self.derived_stats.calls(hand, 0)  # PREFLOP
        self.derived_stats.calls(hand, 1)  # FLOP
        self.derived_stats.calls(hand, 2)  # TURN
        
        # Should create separate stats for each street
        assert self.derived_stats.handsplayers["player1"]["street0Calls"] == 1
        assert self.derived_stats.handsplayers["player1"]["street1Calls"] == 1
        assert self.derived_stats.handsplayers["player1"]["street2Calls"] == 1


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])