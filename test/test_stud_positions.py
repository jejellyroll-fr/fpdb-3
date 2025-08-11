#!/usr/bin/env python

"""Test suite for Stud positions and bring-in handling in DerivedStats."""

import os

# Add parent directory to path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import _INIT_STATS, DerivedStats


class TestStudPositions:
    """Test Stud-specific position calculations."""

    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance."""
        return DerivedStats()

    @pytest.fixture
    def mock_stud_hand(self):
        """Create a mock Stud hand."""
        hand = Mock()
        hand.handid = "12345"
        hand.tablename = "Test Table"
        hand.startTime = "2024-01-01 12:00:00"
        hand.gametype = {
            "type": "ring",
            "base": "stud",
            "category": "studhi",
            "limitType": "fl",
            "sb": 0.5,
            "bb": 1.0,
            "currency": "USD",
        }

        # Players
        hand.players = [
            [1, "Player1", 100.0, 0, None],
            [2, "Player2", 100.0, 0, None],
            [3, "Player3", 100.0, 0, None],
            [4, "Player4", 100.0, 0, None],
        ]

        # Streets
        hand.allStreets = ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.actionStreets = ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.holeStreets = ["THIRD"]
        hand.communityStreets = []

        # Actions - Player2 has the bring-in
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", 0.05),
                ("Player2", "ante", 0.05),
                ("Player3", "ante", 0.05),
                ("Player4", "ante", 0.05),
            ],
            "THIRD": [
                ("Player2", "bringin", 0.10),  # Player2 is bring-in
                ("Player3", "folds"),
                ("Player4", "completes", 0.25),
                ("Player1", "calls", 0.25),
                ("Player2", "calls", 0.15),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        # Other required attributes
        hand.board = {}
        hand.holecards = {}
        hand.pot = Mock()
        hand.pot.committed = {"Player1": 0.3, "Player2": 0.3, "Player3": 0.05, "Player4": 0.3}
        hand.pot.common = {"Player1": 0, "Player2": 0, "Player3": 0, "Player4": 0}
        hand.pot.pots = [(0.95, ["Player1", "Player2", "Player4"])]
        hand.totalpot = 0.95
        hand.rake = 0
        hand.collectees = {}
        hand.hero = None
        hand.shown = set()
        hand.sitout = []
        hand.tourneyId = None
        hand.tourneyTypeId = None
        hand.endBounty = {}
        hand.runItTimes = 0

        return hand

    def test_bring_in_position(self, stats, mock_stud_hand) -> None:
        """Test that bring-in player gets correct position."""
        # Initialize players
        for player in mock_stud_hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()

        # Set positions
        stats.setPositions(mock_stud_hand)

        # Player2 should be bring-in with position 'S'
        assert stats.handsplayers["Player2"]["position"] == "S"
        assert stats.handsplayers["Player2"]["street0FirstToAct"] == True

        # Other players should have numeric positions
        assert isinstance(stats.handsplayers["Player1"]["position"], int)
        assert isinstance(stats.handsplayers["Player3"]["position"], int)
        assert isinstance(stats.handsplayers["Player4"]["position"], int)

    def test_stud_in_position(self, stats, mock_stud_hand) -> None:
        """Test that last player to act gets street0InPosition in Stud."""
        # Initialize players
        for player in mock_stud_hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()

        # Set positions
        stats.setPositions(mock_stud_hand)

        # Find player with position 0 (last to act)
        last_player = None
        for player, data in stats.handsplayers.items():
            if data["position"] == 0:
                last_player = player
                break

        assert last_player is not None
        assert stats.handsplayers[last_player]["street0InPosition"] == True

    def test_bring_in_completes(self, stats, mock_stud_hand) -> None:
        """Test that bring-in player who completes still has bring-in position."""
        # Modify actions so bring-in completes
        mock_stud_hand.actions["THIRD"] = [
            ("Player2", "completes", 0.25),  # Bring-in completes
            ("Player3", "folds"),
            ("Player4", "calls", 0.25),
            ("Player1", "calls", 0.25),
        ]

        # Initialize players
        for player in mock_stud_hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()

        # Set positions
        stats.setPositions(mock_stud_hand)

        # Player2 should still be bring-in even though they completed
        assert stats.handsplayers["Player2"]["position"] == "S"
        assert stats.handsplayers["Player2"]["street0FirstToAct"] == True

    def test_stud_steal_positions(self, stats, mock_stud_hand) -> None:
        """Test steal positions for Stud games."""
        # Initialize players
        for player in mock_stud_hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
            stats.handsplayers[player[1]]["sitout"] = False

        # Set positions first
        stats.setPositions(mock_stud_hand)

        # Calculate steals
        stats.calcSteals(mock_stud_hand)

        # In Stud, steal positions are (2, 1, 0)
        # Player4 completed first, so they should have steal opportunity
        assert stats.handsplayers["Player4"]["raiseFirstInChance"] == True

        # Check if Player4 is in steal position
        player4_pos = stats.handsplayers["Player4"]["position"]
        if player4_pos in (2, 1, 0):
            assert stats.handsplayers["Player4"]["stealChance"] == True
            assert stats.handsplayers["Player4"]["stealDone"] == True

    def test_heads_up_stud(self, stats) -> None:
        """Test heads-up Stud positions."""
        hand = Mock()
        hand.handid = "12346"
        hand.gametype = {"base": "stud"}
        hand.players = [
            [1, "Player1", 100.0, 0, None],
            [2, "Player2", 100.0, 0, None],
        ]
        hand.actionStreets = ["BLINDSANTES", "THIRD"]
        hand.holeStreets = ["THIRD"]
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", 0.05),
                ("Player2", "ante", 0.05),
            ],
            "THIRD": [
                ("Player1", "bringin", 0.10),
                ("Player2", "completes", 0.25),
                ("Player1", "calls", 0.15),
            ],
        }

        # Initialize players
        stats.handsplayers = {}
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()

        # Set positions
        stats.setPositions(hand)

        # Player1 is bring-in
        assert stats.handsplayers["Player1"]["position"] == "S"
        assert stats.handsplayers["Player1"]["street0FirstToAct"] == True

        # Player2 should have position 0 and be in position
        assert stats.handsplayers["Player2"]["position"] == 0
        assert stats.handsplayers["Player2"]["street0InPosition"] == True

    def test_no_actions_stud(self, stats) -> None:
        """Test Stud with no actions (all-in antes)."""
        hand = Mock()
        hand.handid = "12347"
        hand.gametype = {"base": "stud"}
        hand.players = [
            [1, "Player1", 0.05, 0, None],  # All-in with ante
            [2, "Player2", 100.0, 0, None],
        ]
        hand.actionStreets = ["BLINDSANTES", "THIRD"]
        hand.holeStreets = ["THIRD"]
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", 0.05),
                ("Player2", "ante", 0.05),
            ],
            "THIRD": [],  # No actions on third street
        }

        # Initialize players
        stats.handsplayers = {}
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()

        # Set positions - should not crash
        stats.setPositions(hand)

        # Both players should have default positions
        assert "position" in stats.handsplayers["Player1"]
        assert "position" in stats.handsplayers["Player2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
