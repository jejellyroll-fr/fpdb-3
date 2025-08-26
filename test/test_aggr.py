#!/usr/bin/env python3
"""Test suite for aggr function in DerivedStats module.

This module tests the aggr functionality which calculates aggression statistics
for players based on their betting actions on specific streets.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DerivedStats import DerivedStats


class TestAggr:
    """Test suite for aggr function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.derived_stats = DerivedStats()
        self.derived_stats.handsplayers = {}

    def create_mock_hand(self, action_streets=None, actions=None, players=None):
        """Create a mock hand object with specified actions and players."""
        hand = Mock()
        hand.actionStreets = action_streets or ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        hand.actions = actions or {}
        hand.players = players or []
        return hand

    def test_no_actions_on_street(self):
        """Test aggr when there are no actions on the specified street."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": []},  # No actions on flop
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # No aggression stats should be set
        assert "street1Aggr" not in self.derived_stats.handsplayers["player1"]
        assert "street1Aggr" not in self.derived_stats.handsplayers["player2"]

    def test_single_aggressor(self):
        """Test aggr with a single aggressive player."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player2", "calls", 50, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # player1 should be marked as aggressor
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True
        # player2 should not be marked as aggressor
        assert "street1Aggr" not in self.derived_stats.handsplayers["player2"]

    def test_multiple_aggressors(self):
        """Test aggr with multiple aggressive players."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}, "player3": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None],
            [3, "player3", "300.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player2", "raises", 150, None, False),
            ("player3", "calls", 150, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Both player1 and player2 should be marked as aggressors
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True
        assert self.derived_stats.handsplayers["player2"]["street1Aggr"] is True
        # player3 should not be marked as aggressor (only called)
        assert "street1Aggr" not in self.derived_stats.handsplayers["player3"]

    def test_completes_action(self):
        """Test that 'completes' action is recognized as aggression."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        players = [[1, "player1", "100.00", None, None]]
        
        street_actions = [("player1", "completes", 25, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": street_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True

    def test_other_raised_street_postflop(self):
        """Test otherRaisedStreet tracking for postflop streets."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}, "player3": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None],
            [3, "player3", "300.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),  # First aggressor
            ("player2", "calls", 50, None, False),  # Should get otherRaisedStreet1
            ("player3", "folds", None, None, False),  # Should get otherRaisedStreet1
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # player1 should be aggressor
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True
        
        # player2 and player3 should have otherRaisedStreet1 (acted after first aggression)
        assert self.derived_stats.handsplayers["player2"]["otherRaisedStreet1"] is True
        assert self.derived_stats.handsplayers["player3"]["otherRaisedStreet1"] is True

    def test_no_other_raised_street_on_preflop(self):
        """Test that otherRaisedStreet is not set on preflop (i=0)."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        preflop_actions = [
            ("player1", "raises", 20, None, False),  # First aggressor
            ("player2", "calls", 20, None, False),   # Acts after aggression
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": preflop_actions, "FLOP": []},
            players=players
        )
        
        self.derived_stats.aggr(hand, 0)  # Street 0 = PREFLOP
        
        # player1 should be aggressor
        assert self.derived_stats.handsplayers["player1"]["street0Aggr"] is True
        
        # player2 should NOT have otherRaisedStreet0 (i=0 condition)
        assert "otherRaisedStreet0" not in self.derived_stats.handsplayers["player2"]

    def test_first_aggr_made_tracking(self):
        """Test that only actions after first aggression are tracked as 'others'."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}, "player3": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None],
            [3, "player3", "300.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "checks", None, None, False),  # Before first aggression - should not be in 'others'
            ("player2", "bets", 50, None, False),     # First aggression
            ("player3", "calls", 50, None, False),     # After first aggression - should be in 'others'
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # player2 should be aggressor
        assert self.derived_stats.handsplayers["player2"]["street1Aggr"] is True
        
        # Only player3 should have otherRaisedStreet1 (acted after first aggression)
        assert "otherRaisedStreet1" not in self.derived_stats.handsplayers["player1"]
        assert self.derived_stats.handsplayers["player3"]["otherRaisedStreet1"] is True

    def test_player_not_in_handsplayers(self):
        """Test that function assumes all players in hand.players are in handsplayers."""
        # The function assumes all players in hand.players exist in handsplayers
        # This test verifies that both players get their aggr stats when they act aggressively
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player2", "raises", 150, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Both players should be marked as aggressors
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True
        assert self.derived_stats.handsplayers["player2"]["street1Aggr"] is True

    def test_stat_initialization(self):
        """Test that aggr stats are properly initialized before being set to True."""
        self.derived_stats.handsplayers = {"player1": {"existingstat": "value"}}
        
        players = [[1, "player1", "100.00", None, None]]
        
        flop_actions = [("player1", "bets", 50, None, False)]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Existing stats should be preserved
        assert self.derived_stats.handsplayers["player1"]["existingstat"] == "value"
        # New aggr stat should be set
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True

    def test_other_raised_stat_initialization(self):
        """Test that otherRaisedStreet stats are properly initialized."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {"existingstat": "value"}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player2", "calls", 50, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Existing stats should be preserved
        assert self.derived_stats.handsplayers["player2"]["existingstat"] == "value"
        # New otherRaised stat should be set
        assert self.derived_stats.handsplayers["player2"]["otherRaisedStreet1"] is True

    def test_multiple_streets_aggression(self):
        """Test aggr calculation across multiple streets."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None]
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN"],
            actions={
                "PREFLOP": [("player1", "raises", 20, None, False)],
                "FLOP": [("player2", "bets", 50, None, False)],
                "TURN": [("player1", "raises", 200, None, False)]
            },
            players=players
        )
        
        # Test each street separately
        self.derived_stats.aggr(hand, 0)  # PREFLOP
        self.derived_stats.aggr(hand, 1)  # FLOP
        self.derived_stats.aggr(hand, 2)  # TURN
        
        # Check aggression stats
        assert self.derived_stats.handsplayers["player1"]["street0Aggr"] is True
        assert self.derived_stats.handsplayers["player2"]["street1Aggr"] is True
        assert self.derived_stats.handsplayers["player1"]["street2Aggr"] is True
        
        # Check that non-aggressors don't have aggr stats
        assert "street1Aggr" not in self.derived_stats.handsplayers["player1"]  # Didn't bet on flop
        assert "street0Aggr" not in self.derived_stats.handsplayers["player2"]  # Didn't raise preflop
        assert "street2Aggr" not in self.derived_stats.handsplayers["player2"]  # Didn't raise on turn

    def test_duplicate_aggression_actions(self):
        """Test that the same player can have multiple aggressive actions on same street."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        players = [[1, "player1", "100.00", None, None]]
        
        flop_actions = [
            ("player1", "bets", 50, None, False),
            ("player1", "raises", 150, None, False),  # Player acts aggressively twice
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Should still be marked as aggressor (set should handle duplicates)
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True

    def test_different_action_types(self):
        """Test that all aggressive action types are recognized."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}, "player3": {}}
        
        players = [
            [1, "player1", "100.00", None, None],
            [2, "player2", "200.00", None, None],
            [3, "player3", "300.00", None, None]
        ]
        
        # Test different streets with different action types
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
            actions={
                "PREFLOP": [("player1", "completes", 25, None, False)],  # completes
                "FLOP": [("player2", "bets", 50, None, False)],          # bets
                "TURN": [("player3", "raises", 200, None, False)],       # raises
                "RIVER": []
            },
            players=players
        )
        
        self.derived_stats.aggr(hand, 0)  # PREFLOP
        self.derived_stats.aggr(hand, 1)  # FLOP  
        self.derived_stats.aggr(hand, 2)  # TURN
        
        # All should be marked as aggressors on their respective streets
        assert self.derived_stats.handsplayers["player1"]["street0Aggr"] is True  # completes
        assert self.derived_stats.handsplayers["player2"]["street1Aggr"] is True  # bets
        assert self.derived_stats.handsplayers["player3"]["street2Aggr"] is True  # raises

    def test_empty_others_set(self):
        """Test behavior when no players act after first aggression."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        players = [[1, "player1", "100.00", None, None]]
        
        flop_actions = [("player1", "bets", 50, None, False)]  # Only one action
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": [], "FLOP": flop_actions},
            players=players
        )
        
        self.derived_stats.aggr(hand, 1)  # Street 1 = FLOP
        
        # Should work fine with empty 'others' set
        assert self.derived_stats.handsplayers["player1"]["street1Aggr"] is True


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])