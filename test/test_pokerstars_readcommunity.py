"""
Tests spécifiques pour la méthode readCommunityCards de PokerStarsToFpdb.

Ce module contient des tests exhaustifs pour couvrir tous les cas d'usage
de la méthode readCommunityCards.
"""

import re
import unittest
from unittest.mock import Mock

from fpdb_3_legacy.Exceptions import FpdbHandPartial
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return import parameters for testing."""
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [
                "holdem",
                "omahahi",
                "omahahilo",
                "studhi",
                "studlo",
                "razz",
                "27_1draw",
                "27_3draw",
                "fivedraw",
                "badugi",
                "baduci",
            ],
            "handCount": 0,
            "fastFold": False,
        }

    def get_site_id(self, sitename: str) -> int:
        """Return the site ID for the given site name."""
        return 32  # PokerStars.COM


class TestReadCommunityCards(unittest.TestCase):
    """Tests for the readCommunityCards method."""

    def setUp(self):
        """Configuration des tests."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

        # Mock the regex patterns used
        self.parser.re_empty_card = re.compile(r"\[\s*\]")
        self.parser.re_board2 = re.compile(r"\[(?P<C1>\w{2})\s+(?P<C2>\w{2})\s+(?P<C3>\w{2})\]")
        self.parser.re_board = re.compile(r"\[(?P<CARDS>.+)\]")

    def test_readCommunityCards_flop_normal(self):
        """Test lecture des cartes communautaires pour le flop normal."""
        hand = Mock()
        hand.streets = {"FLOP": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "FLOP")

        hand.setCommunityCards.assert_called_once_with("FLOP", ["Qh", "Jh", "Ts"])

    def test_readCommunityCards_turn_normal(self):
        """Test lecture des cartes communautaires pour le turn normal."""
        hand = Mock()
        hand.streets = {"TURN": "[9c]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "TURN")

        hand.setCommunityCards.assert_called_once_with("TURN", ["9c"])

    def test_readCommunityCards_river_normal(self):
        """Test lecture des cartes communautaires pour la river normale."""
        hand = Mock()
        hand.streets = {"RIVER": "[Ad]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "RIVER")

        hand.setCommunityCards.assert_called_once_with("RIVER", ["Ad"])

    def test_readCommunityCards_empty_card_raises_exception(self):
        """Test that empty cards raise FpdbHandPartial."""
        hand = Mock()
        hand.streets = {"FLOP": "[]"}
        # No SUMMARY Board line, so board recovery finds nothing and the empty
        # FLOP still raises (readCommunityCards reads handText to attempt recovery).
        hand.handText = "*** FLOP *** []\n"

        with self.assertRaises(FpdbHandPartial) as context:
            self.parser.readCommunityCards(hand, "FLOP")

        self.assertEqual(str(context.exception), "'Blank community card'")

    def test_readCommunityCards_flopet_with_flop_present(self):
        """Test FLOPET when FLOP is present - do nothing."""
        hand = Mock()
        hand.streets = {"FLOPET": "[Qh Jh Ts]", "FLOP": "[Ah Kh Qc]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "FLOPET")

        # Ne doit pas appeler setCommunityCards car FLOP existe
        hand.setCommunityCards.assert_not_called()

    def test_readCommunityCards_flopet_without_flop(self):
        """Test FLOPET when FLOP is absent - process normally."""
        hand = Mock()
        hand.streets = {"FLOPET": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "FLOPET")

        hand.setCommunityCards.assert_called_once_with("FLOPET", ["Qh", "Jh", "Ts"])

    def test_readCommunityCards_with_re_board2_match(self):
        """Test avec correspondance du pattern re_board2."""
        hand = Mock()
        hand.streets = {"FLOP": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()

        # Mock re_board2 so that it matches
        mock_match = Mock()
        mock_match.group = Mock(side_effect=lambda x: {"C1": "Qh", "C2": "Jh", "C3": "Ts"}[x])
        self.parser.re_board2 = Mock()
        self.parser.re_board2.search = Mock(return_value=mock_match)

        self.parser.readCommunityCards(hand, "FLOP")

        hand.setCommunityCards.assert_called_once_with("FLOP", ["Qh", "Jh", "Ts"])

    def test_readCommunityCards_with_re_board_fallback(self):
        """Test avec fallback sur re_board quand re_board2 ne matche pas."""
        hand = Mock()
        hand.streets = {"TURN": "[9c]"}
        hand.setCommunityCards = Mock()

        # Mock re_board2 so that it does not match
        self.parser.re_board2 = Mock()
        self.parser.re_board2.search = Mock(return_value=None)

        # Mock re_board so that it matches
        mock_match = Mock()
        mock_match.group = Mock(return_value="9c")
        self.parser.re_board = Mock()
        self.parser.re_board.search = Mock(return_value=mock_match)

        self.parser.readCommunityCards(hand, "TURN")

        hand.setCommunityCards.assert_called_once_with("TURN", ["9c"])

    def test_readCommunityCards_sets_runittimes_flop1(self):
        """Test that runItTimes is set to 2 for FLOP1."""
        hand = Mock()
        hand.streets = {"FLOP1": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "FLOP1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_turn1(self):
        """Test that runItTimes is set to 2 for TURN1."""
        hand = Mock()
        hand.streets = {"TURN1": "[9c]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "TURN1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_river1(self):
        """Test that runItTimes is set to 2 for RIVER1."""
        hand = Mock()
        hand.streets = {"RIVER1": "[Ad]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "RIVER1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_flop2(self):
        """Test that runItTimes is set to 2 for FLOP2."""
        hand = Mock()
        hand.streets = {"FLOP2": "[Kc Qd Jh]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "FLOP2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_turn2(self):
        """Test that runItTimes is set to 2 for TURN2."""
        hand = Mock()
        hand.streets = {"TURN2": "[5h]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "TURN2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_river2(self):
        """Test that runItTimes is set to 2 for RIVER2."""
        hand = Mock()
        hand.streets = {"RIVER2": "[3s]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "RIVER2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_does_not_set_runittimes_normal_streets(self):
        """Test that runItTimes is unchanged for normal streets."""
        hand = Mock()
        hand.streets = {"FLOP": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 1

        self.parser.readCommunityCards(hand, "FLOP")

        # runItTimes must not be modified
        self.assertEqual(hand.runItTimes, 1)

    def test_readCommunityCards_multiple_cards_with_spaces(self):
        """Test parsing de cartes multiples avec espaces."""
        hand = Mock()
        hand.streets = {"FLOP": "[Ah  Kh   Qc]"}
        hand.setCommunityCards = Mock()

        # Mock re_board2 to avoid matching because of irregular spacing
        self.parser.re_board2 = Mock()
        self.parser.re_board2.search = Mock(return_value=None)

        # Mock re_board for matching
        mock_match = Mock()
        mock_match.group = Mock(return_value="Ah  Kh   Qc")
        self.parser.re_board = Mock()
        self.parser.re_board.search = Mock(return_value=mock_match)

        self.parser.readCommunityCards(hand, "FLOP")

        # Verify that split(" ") with a space delimiter handles multiple spaces
        # split(" ") preserves empty elements, unlike split() without an argument
        expected_cards = "Ah  Kh   Qc".split(" ")  # Simulate the actual behavior
        hand.setCommunityCards.assert_called_once_with("FLOP", expected_cards)


if __name__ == "__main__":
    unittest.main()
