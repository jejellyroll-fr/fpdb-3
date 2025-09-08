#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock

# Add the parent directory to sys.path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PokerStarsToFpdb import PokerStars


class TestPokerStarsShowdown(unittest.TestCase):
    """Test suite for PokerStars readShowdownActions method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.parser = PokerStars(self.config)

    def test_readShowdownActions_shows_single_player(self):
        """Test showdown with single player showing cards."""
        hand_text = """Hero: shows [As Ks] (a pair of Aces)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["As", "Ks"], "Hero")

    def test_readShowdownActions_shows_multiple_players(self):
        """Test showdown with multiple players showing cards."""
        hand_text = """Hero: shows [As Ks] (a pair of Aces)
Player1: shows [Qh Qd] (a pair of Queens)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        self.assertEqual(hand.addShownCards.call_count, 2)
        calls = hand.addShownCards.call_args_list
        self.assertEqual(calls[0][0], (["As", "Ks"], "Hero"))
        self.assertEqual(calls[1][0], (["Qh", "Qd"], "Player1"))

    def test_readShowdownActions_mucks_single_player(self):
        """Test showdown with single player mucking cards."""
        hand_text = """Player1: mucks [7h 2c]"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["7h", "2c"], "Player1")

    def test_readShowdownActions_mucked_single_player(self):
        """Test showdown with single player having mucked cards."""
        hand_text = """Player2: mucked [3s 9d]"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["3s", "9d"], "Player2")

    def test_readShowdownActions_showed_single_player(self):
        """Test showdown with single player having showed cards."""
        hand_text = """Player3: showed [Ac Kc] (a flush, Ace high)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["Ac", "Kc"], "Player3")

    def test_readShowdownActions_mixed_actions(self):
        """Test showdown with mix of shows, mucks, mucked, and showed actions."""
        hand_text = """Hero: shows [As Ks] (a pair of Aces)
Player1: mucks [7h 2c]
Player2: mucked [3s 9d]
Player3: showed [Ac Kc] (a flush, Ace high)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        self.assertEqual(hand.addShownCards.call_count, 4)
        calls = hand.addShownCards.call_args_list
        self.assertEqual(calls[0][0], (["As", "Ks"], "Hero"))
        self.assertEqual(calls[1][0], (["7h", "2c"], "Player1"))
        self.assertEqual(calls[2][0], (["3s", "9d"], "Player2"))
        self.assertEqual(calls[3][0], (["Ac", "Kc"], "Player3"))

    def test_readShowdownActions_no_showdown(self):
        """Test hand with no showdown actions."""
        hand_text = """Player1 folds before Flop (didn't bet)
Player2 folds on the Flop"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_not_called()

    def test_readShowdownActions_empty_hand_text(self):
        """Test with empty hand text."""
        hand = Mock()
        hand.handText = ""
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_not_called()

    def test_readShowdownActions_special_characters_in_name(self):
        """Test showdown with special characters in player names."""
        hand_text = """Player-123: shows [As Ks] (a pair of Aces)
Player_456: mucks [7h 2c]"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        self.assertEqual(hand.addShownCards.call_count, 2)
        calls = hand.addShownCards.call_args_list
        self.assertEqual(calls[0][0], (["As", "Ks"], "Player-123"))
        self.assertEqual(calls[1][0], (["7h", "2c"], "Player_456"))

    def test_readShowdownActions_three_cards(self):
        """Test showdown with three cards (e.g., Omaha variant)."""
        hand_text = """Hero: shows [As Ks Qh] (a straight, Ten to Ace)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["As", "Ks", "Qh"], "Hero")

    def test_readShowdownActions_four_cards(self):
        """Test showdown with four cards (Omaha variant)."""
        hand_text = """Player1: shows [As Ks Qh Jd] (a straight, Ten to Ace)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["As", "Ks", "Qh", "Jd"], "Player1")

    def test_readShowdownActions_long_player_name(self):
        """Test showdown with long player names."""
        hand_text = """VeryLongPlayerName123: shows [As Ks] (a pair of Aces)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["As", "Ks"], "VeryLongPlayerName123")

    def test_readShowdownActions_malformed_cards_ignored(self):
        """Test that malformed card entries are handled gracefully."""
        # This tests current behavior - malformed entries are still processed
        hand_text = """Player1: shows [As] (incomplete hand)"""

        hand = Mock()
        hand.handText = hand_text
        hand.addShownCards = Mock()

        self.parser.readShowdownActions(hand)

        hand.addShownCards.assert_called_once_with(["As"], "Player1")


if __name__ == "__main__":
    unittest.main()
