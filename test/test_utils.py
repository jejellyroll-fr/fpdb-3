#!/usr/bin/env python

"""Final test suite for utility methods in DerivedStats.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from unittest.mock import Mock

from DerivedStats import DerivedStats


class TestUtilityMethodsFinal:
    """Test cases for utility methods with correct understanding of their behavior."""

    def setup_method(self) -> None:
        """Setup test data before each test."""
        self.stats = DerivedStats()
        self.stats.hand = Mock()
        self.stats.hand.actions = {"PREFLOP": [], "FLOP": [], "TURN": [], "RIVER": []}
        # Initialize handsplayers for tests that need it
        self.stats.handsplayers = {}

    def test_pfba_returns_players(self) -> None:
        """Test pfba returns set of players who performed actions."""
        # Add preflop actions
        actions = [
            ("Player1", "raises", 6, 6, 5, False),
            ("Player2", "calls", 4, False),
            ("Player3", "raises", 20, 20, 14, False),
            ("Player4", "folds"),
            ("Player1", "calls", 14, False),
            ("Player2", "folds"),
        ]

        # Get all players who acted
        all_players = self.stats.pfba(actions)

        # Should return all players who acted
        assert all_players == {"Player1", "Player2", "Player3", "Player4"}

    def test_pfba_with_forbidden_actions(self) -> None:
        """Test pfba with forbidden actions."""
        actions = [
            ("Player1", "raises", 6, 6, 5, False),
            ("Player2", "calls", 4, False),
            ("Player3", "folds"),
            ("Player4", "checks"),
        ]

        # Get players who didn't fold
        non_folders = self.stats.pfba(actions, f=("folds",))
        assert non_folders == {"Player1", "Player2", "Player4"}

    def test_pfbao_returns_ordered_players(self) -> None:
        """Test pfbao returns ordered list of players."""
        actions = [
            ("Player1", "raises", 8, 8, 6, False),
            ("Player2", "calls", 8, False),
            ("Player3", "raises", 24, 24, 16, False),
            ("Player1", "raises", 72, 72, 48, False),
            ("Player2", "folds"),
            ("Player3", "calls", 48, False),
        ]

        # Get ordered list of all players
        ordered_players = self.stats.pfbao(actions)

        # Should be in order of first action
        assert ordered_players == ["Player1", "Player2", "Player3"]

    def test_pfbao_non_unique(self) -> None:
        """Test pfbao with non-unique flag."""
        actions = [
            ("Player1", "raises", 8, 8, 6, False),
            ("Player2", "calls", 8, False),
            ("Player1", "raises", 24, 24, 16, False),
            ("Player2", "calls", 16, False),
        ]

        # Get non-unique list (includes duplicates)
        non_unique = self.stats.pfbao(actions, unique=False)
        assert non_unique == ["Player1", "Player2", "Player1", "Player2"]

        # Get unique list (default)
        unique = self.stats.pfbao(actions, unique=True)
        assert unique == ["Player1", "Player2"]

    def test_firsts_bet_or_raiser(self) -> None:
        """Test firstsBetOrRaiser returns first player to bet/raise."""
        actions = [
            ("Player1", "calls", 2, False),
            ("Player2", "calls", 2, False),
            ("Player3", "raises", 8, 8, 6, False),  # First raiser
            ("Player4", "calls", 8, False),
            ("Player1", "folds"),
            ("Player2", "calls", 6, False),
        ]

        first_raiser = self.stats.firstsBetOrRaiser(actions)
        assert first_raiser == "Player3"

    def test_firsts_bet_or_raiser_with_bet(self) -> None:
        """Test firstsBetOrRaiser with bet action."""
        actions = [
            ("Player1", "checks"),
            ("Player2", "checks"),
            ("Player3", "bets", 4, False),  # First bettor
            ("Player4", "raises", 12, 12, 8, False),
            ("Player1", "folds"),
        ]

        first_bettor = self.stats.firstsBetOrRaiser(actions)
        assert first_bettor == "Player3"

    def test_firsts_bet_or_raiser_no_aggressor(self) -> None:
        """Test firstsBetOrRaiser when no one bets or raises."""
        actions = [("Player1", "checks"), ("Player2", "checks"), ("Player3", "checks"), ("Player4", "folds")]

        first_bettor = self.stats.firstsBetOrRaiser(actions)
        assert first_bettor is None

    def test_lasts_bet_or_raiser_simple(self) -> None:
        """Test lastBetOrRaiser with simple scenario."""
        # Need to mock the hand.actions structure
        self.stats.hand.actions = {
            "PREFLOP": [
                ("Player1", "raises", 8, 8, 6, False),  # Only raiser
                ("Player2", "calls", 8, False),
                ("Player3", "calls", 8, False),
                ("Player4", "calls", 8, False),
            ],
        }

        # lastBetOrRaiser expects actions dict and street
        last_raiser = self.stats.lastBetOrRaiser(self.stats.hand.actions, "PREFLOP")
        assert last_raiser == "Player1"

    def test_lasts_bet_or_raiser_multiple(self) -> None:
        """Test lastBetOrRaiser with multiple raises."""
        self.stats.hand.actions = {
            "PREFLOP": [
                ("Player1", "raises", 8, 8, 6, False),
                ("Player2", "raises", 20, 20, 12, False),
                ("Player3", "raises", 60, 60, 40, False),  # Last raiser
                ("Player4", "folds"),
                ("Player1", "folds"),
                ("Player2", "calls", 40, False),
            ],
        }

        last_raiser = self.stats.lastBetOrRaiser(self.stats.hand.actions, "PREFLOP")
        assert last_raiser == "Player3"

    def test_lasts_bet_or_raiser_no_raiser(self) -> None:
        """Test lastBetOrRaiser when no one raises."""
        self.stats.hand.actions = {
            "PREFLOP": [
                ("Player1", "calls", 2, False),
                ("Player2", "calls", 2, False),
                ("Player3", "checks"),
                ("Player4", "folds"),
            ],
        }

        last_raiser = self.stats.lastBetOrRaiser(self.stats.hand.actions, "PREFLOP")
        assert last_raiser is None

    def test_get_raise_amounts_from_actions(self) -> None:
        """Test extracting raise amounts from actions (custom logic)."""
        actions = [
            ("Player1", "raises", 8, 8, 6, False),
            ("Player2", "calls", 8, False),
            ("Player3", "raises", 24, 24, 16, False),
            ("Player4", "raises", 72, 72, 48, False),
            ("Player1", "folds"),
            ("Player2", "folds"),
            ("Player3", "calls", 48, False),
        ]

        # Extract raise amounts manually
        raise_amounts = []
        for action in actions:
            if action[1] == "raises" and len(action) > 3:
                raise_amounts.append(action[3])  # raiseTo amount

        assert raise_amounts == [8, 24, 72]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
