import os
import sys
import unittest
from unittest.mock import Mock

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PokerStarsToFpdb import SITE_MERGE, PokerStars


class TestCalculateBovadaAdjustments(unittest.TestCase):
    """Test cases for the _calculateBovadaAdjustments method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.parser = PokerStars(self.config, "PokerStars", "USD")

        # Mock the regex pattern
        self.parser.re_uncalled = Mock()

    def _create_mock_hand(self, players=None, actions=None, bb=2.0, sb=1.0, hand_text=""):
        """Create a mock hand object for testing."""
        hand = Mock()
        hand.players = players or [("seat1", "Player1"), ("seat2", "Player2")]
        hand.actions = actions or {}
        hand.bb = bb
        hand.sb = sb
        hand.handText = hand_text
        return hand

    def test_no_special_names_returns_default(self):
        """Test that normal players without special names return default values."""
        hand = self._create_mock_hand(
            players=[("seat1", "Player1"), ("seat2", "Player2")], actions={"PREFLOP": [("Player1", "folds", 0)]}
        )

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)
        self.assertEqual(result, expected)

    def test_big_blind_player_all_fold_with_uncalled_bet_equal_bb(self):
        """Test Bovada uncalled v2 scenario with uncalled bet equal to big blind."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")],
            actions={"PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)]},
            bb=2.0,
        )

        # Mock regex match for uncalled bet
        mock_match = Mock()
        mock_match.group.return_value = "2.0"
        self.parser.re_uncalled.search.return_value = mock_match

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, True, 0, 0)
        self.assertEqual(result, expected)

    def test_small_blind_player_all_fold_no_uncalled_bet_with_sb(self):
        """Test Bovada uncalled v1 scenario with small blind present."""
        hand = self._create_mock_hand(
            players=[("seat1", "Small Blind"), ("seat2", "Player2")],
            actions={
                "PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)],
                "BLINDSANTES": [("Player1", "small blind", 1.0), ("Player2", "big blind", 2.0)],
            },
            bb=2.0,
            sb=1.0,
        )

        # Mock no uncalled bet found
        self.parser.re_uncalled.search.return_value = None

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (True, False, 3.0, 1.0)  # blindsantes=3.0, adjustment=bb-sb=1.0
        self.assertEqual(result, expected)

    def test_dealer_player_all_fold_no_uncalled_bet_no_sb(self):
        """Test Bovada uncalled v1 scenario without small blind."""
        hand = self._create_mock_hand(
            players=[("seat1", "Dealer"), ("seat2", "Player2")],
            actions={
                "PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)],
                "BLINDSANTES": [("Player2", "big blind", 2.0)],
            },
            bb=2.0,
            sb=1.0,
        )

        # Mock no uncalled bet found
        self.parser.re_uncalled.search.return_value = None

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (True, False, 2.0, 2.0)  # blindsantes=2.0, adjustment=bb=2.0
        self.assertEqual(result, expected)

    def test_site_merge_all_fold_scenario(self):
        """Test scenario with SITE_MERGE."""
        self.parser.site_id = SITE_MERGE

        hand = self._create_mock_hand(
            players=[("seat1", "Player1"), ("seat2", "Player2")],
            actions={"PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)]},
            bb=2.0,
        )

        # Mock uncalled bet found but not equal to big blind
        mock_match = Mock()
        mock_match.group.return_value = "1.5"
        self.parser.re_uncalled.search.return_value = mock_match

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)  # No match for bovada_uncalled_v2
        self.assertEqual(result, expected)

    def test_preflop_actions_with_non_fold_actions(self):
        """Test that non-fold actions prevent Bovada adjustments."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")],
            actions={"PREFLOP": [("Player1", "calls", 2.0), ("Player2", "folds", 0)]},
            bb=2.0,
        )

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)
        self.assertEqual(result, expected)

    def test_no_preflop_actions(self):
        """Test scenario with no PREFLOP actions."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")], actions={"FLOP": [("Player1", "checks", 0)]}, bb=2.0
        )

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)
        self.assertEqual(result, expected)

    def test_none_preflop_actions(self):
        """Test scenario with None PREFLOP actions."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")], actions={"PREFLOP": None}, bb=2.0
        )

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)
        self.assertEqual(result, expected)

    def test_uncalled_bet_not_equal_to_bb(self):
        """Test uncalled bet present but not equal to big blind."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")],
            actions={"PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)]},
            bb=2.0,
        )

        # Mock regex match for uncalled bet not equal to bb
        mock_match = Mock()
        mock_match.group.return_value = "1.5"
        self.parser.re_uncalled.search.return_value = mock_match

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (False, False, 0, 0)
        self.assertEqual(result, expected)

    def test_complex_blindsantes_calculation(self):
        """Test complex BLINDSANTES calculation with multiple entries."""
        hand = self._create_mock_hand(
            players=[("seat1", "Big Blind"), ("seat2", "Player2")],
            actions={
                "PREFLOP": [("Player1", "folds", 0), ("Player2", "folds", 0)],
                "BLINDSANTES": [
                    ("Player1", "small blind", 1.0),
                    ("Player2", "big blind", 2.0),
                    ("Player3", "ante", 0.25),
                    ("Player4", "ante", 0.25),
                ],
            },
            bb=2.0,
            sb=1.0,
        )

        # Mock no uncalled bet found
        self.parser.re_uncalled.search.return_value = None

        result = self.parser._calculateBovadaAdjustments(hand)
        expected = (True, False, 3.5, 1.0)  # blindsantes=1+2+0.25+0.25=3.5, adjustment=1.0
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
