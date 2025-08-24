#!/usr/bin/env python3
"""Test suite for calcCBets function in DerivedStats module.

This module tests the calcCBets functionality which calculates continuation bet
statistics for players based on hand actions.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DerivedStats import DerivedStats


class TestCalcCBets:
    """Test suite for calcCBets function."""

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
        derived_stats.calcCBets(hand)

    def test_no_preflop_aggressor(self):
        """Test that function returns early if no preflop aggressor found."""
        self.derived_stats.handsplayers = {"player1": {}}
        
        # No preflop actions
        hand = self.create_mock_hand(actions={"PREFLOP": []})
        
        self.derived_stats.calcCBets(hand)
        
        # No cbet stats should be added
        assert "street1CBChance" not in self.derived_stats.handsplayers["player1"]

    def test_preflop_aggressor_identification(self):
        """Test that preflop aggressor is correctly identified."""
        self.derived_stats.handsplayers = {"player1": {}, "player2": {}}
        
        # player2 is last aggressor preflop
        preflop_actions = [
            ("player1", "calls", 100, None, False),
            ("player2", "raises", 200, None, False),
            ("player1", "calls", 200, None, False),
        ]
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": preflop_actions, "FLOP": []}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # player2 should have cbet chance on flop
        assert self.derived_stats.handsplayers["player2"]["street1CBChance"] is True
        # player1 should not have cbet chance
        assert "street1CBChance" not in self.derived_stats.handsplayers["player1"]

    def test_cbet_chance_initialization(self):
        """Test that cbet chance and done stats are properly initialized."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = []
        
        hand = self.create_mock_hand(
            action_streets=["BLINDSANTES", "PREFLOP", "FLOP"],
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # Should initialize both chance and done stats
        assert self.derived_stats.handsplayers["aggressor"]["street1CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is False

    def test_cbet_done_when_betting(self):
        """Test that cbet done is set when aggressor bets on flop."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "bets", 150, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        assert self.derived_stats.handsplayers["aggressor"]["street1CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True

    def test_cbet_done_when_raising(self):
        """Test that cbet done is set when aggressor raises on flop."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "raises", 300, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True

    def test_no_cbet_when_not_betting(self):
        """Test that cbet done is False when aggressor doesn't bet."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "checks", None, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        assert self.derived_stats.handsplayers["aggressor"]["street1CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is False

    def test_multiple_streets(self):
        """Test cbet calculation across multiple streets."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "bets", 150, None, False)]
        turn_actions = [("aggressor", "checks", None, None, False)]
        river_actions = [("aggressor", "bets", 300, None, False)]
        
        hand = self.create_mock_hand(
            actions={
                "PREFLOP": preflop_actions,
                "FLOP": flop_actions,
                "TURN": turn_actions,
                "RIVER": river_actions,
            }
        )
        
        self.derived_stats.calcCBets(hand)
        
        # Flop: chance and done
        assert self.derived_stats.handsplayers["aggressor"]["street1CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True
        
        # Turn: chance but not done
        assert self.derived_stats.handsplayers["aggressor"]["street2CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street2CBDone"] is False
        
        # River: chance and done
        assert self.derived_stats.handsplayers["aggressor"]["street3CBChance"] is True
        assert self.derived_stats.handsplayers["aggressor"]["street3CBDone"] is True

    def test_fold_to_cbet_chance(self):
        """Test that fold to cbet chance is set for players facing cbets."""
        self.derived_stats.handsplayers = {
            "aggressor": {},
            "opponent1": {},
            "opponent2": {}
        }
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [
            ("aggressor", "bets", 150, None, False),
            ("opponent1", "folds", None, None, False),
            ("opponent2", "calls", 150, None, False),
        ]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # opponent1 should have fold to cbet chance and done
        assert self.derived_stats.handsplayers["opponent1"]["foldToStreet1CBChance"] is True
        assert self.derived_stats.handsplayers["opponent1"]["foldToStreet1CBDone"] is True
        
        # opponent2 should have fold to cbet chance but not done
        assert self.derived_stats.handsplayers["opponent2"]["foldToStreet1CBChance"] is True
        assert "foldToStreet1CBDone" not in self.derived_stats.handsplayers["opponent2"]

    def test_no_fold_to_cbet_when_no_action(self):
        """Test that fold to cbet is not set if player doesn't act after cbet."""
        self.derived_stats.handsplayers = {
            "aggressor": {},
            "opponent": {}
        }
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "bets", 150, None, False)]  # opponent doesn't act
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # opponent should not have fold to cbet stats
        assert "foldToStreet1CBChance" not in self.derived_stats.handsplayers["opponent"]

    def test_existing_stats_preservation(self):
        """Test that existing stats are preserved when initializing new ones."""
        self.derived_stats.handsplayers = {
            "aggressor": {
                "street1CBChance": True,  # Already exists
                "existingstat": "value"
            }
        }
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "bets", 150, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # Existing stats should be preserved
        assert self.derived_stats.handsplayers["aggressor"]["existingstat"] == "value"
        # New stats should be set
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True

    def test_bet_vs_raise_identification(self):
        """Test that both bets and raises count as cbets."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        # Test with 'bets' action
        preflop_actions = [("aggressor", "bets", 200, None, False)]
        flop_actions = [("aggressor", "bets", 150, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True
        
        # Reset and test with 'raises' action
        self.derived_stats.handsplayers = {"aggressor": {}}
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [("aggressor", "raises", 150, None, False)]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True

    def test_limited_streets_processing(self):
        """Test that only up to 4 streets are processed (flop, turn, river, 7th)."""
        self.derived_stats.handsplayers = {"aggressor": {}}
        
        # Create hand with many streets
        action_streets = ["PREFLOP", "FLOP", "TURN", "RIVER", "7TH", "8TH", "9TH"]
        actions = {
            "PREFLOP": [("aggressor", "raises", 200, None, False)],
            "FLOP": [("aggressor", "bets", 150, None, False)],
            "TURN": [("aggressor", "bets", 300, None, False)],
            "RIVER": [("aggressor", "bets", 600, None, False)],
            "7TH": [("aggressor", "bets", 1200, None, False)],
            "8TH": [("aggressor", "bets", 2400, None, False)],  # Should be ignored
            "9TH": [("aggressor", "bets", 4800, None, False)],  # Should be ignored
        }
        
        hand = self.create_mock_hand(action_streets=action_streets, actions=actions)
        
        self.derived_stats.calcCBets(hand)
        
        # Should have stats for streets 1-4 only
        assert "street1CBChance" in self.derived_stats.handsplayers["aggressor"]
        assert "street2CBChance" in self.derived_stats.handsplayers["aggressor"]
        assert "street3CBChance" in self.derived_stats.handsplayers["aggressor"]
        assert "street4CBChance" in self.derived_stats.handsplayers["aggressor"]
        # Should not have stats for street5 and beyond
        assert "street5CBChance" not in self.derived_stats.handsplayers["aggressor"]

    def test_complex_multiway_action(self):
        """Test complex scenario with multiple players and actions."""
        self.derived_stats.handsplayers = {
            "aggressor": {},
            "caller": {},
            "folder": {},
            "raiser": {}
        }
        
        preflop_actions = [("aggressor", "raises", 200, None, False)]
        flop_actions = [
            ("aggressor", "bets", 150, None, False),  # Cbet
            ("caller", "calls", 150, None, False),   # Doesn't fold
            ("folder", "folds", None, None, False),  # Folds to cbet
            ("raiser", "raises", 450, None, False),  # Doesn't fold
        ]
        
        hand = self.create_mock_hand(
            actions={"PREFLOP": preflop_actions, "FLOP": flop_actions}
        )
        
        self.derived_stats.calcCBets(hand)
        
        # Aggressor should have cbet done
        assert self.derived_stats.handsplayers["aggressor"]["street1CBDone"] is True
        
        # All opponents should have fold to cbet chance
        assert self.derived_stats.handsplayers["caller"]["foldToStreet1CBChance"] is True
        assert self.derived_stats.handsplayers["folder"]["foldToStreet1CBChance"] is True
        assert self.derived_stats.handsplayers["raiser"]["foldToStreet1CBChance"] is True
        
        # Only folder should have fold to cbet done
        assert "foldToStreet1CBDone" not in self.derived_stats.handsplayers["caller"]
        assert self.derived_stats.handsplayers["folder"]["foldToStreet1CBDone"] is True
        assert "foldToStreet1CBDone" not in self.derived_stats.handsplayers["raiser"]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])