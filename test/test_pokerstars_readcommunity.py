"""
Tests spécifiques pour la méthode readCommunityCards de PokerStarsToFpdb.

Ce module contient des tests exhaustifs pour couvrir tous les cas d'usage
de la méthode readCommunityCards.
"""

import re
import unittest
from unittest.mock import Mock

from Exceptions import FpdbHandPartial
from PokerStarsToFpdb import PokerStars


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
    """Tests pour la méthode readCommunityCards."""

    def setUp(self):
        """Configuration des tests."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

        # Mock des regex patterns utilisés
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
        """Test que les cartes vides lèvent une exception FpdbHandPartial."""
        hand = Mock()
        hand.streets = {"FLOP": "[]"}

        with self.assertRaises(FpdbHandPartial) as context:
            self.parser.readCommunityCards(hand, "FLOP")

        self.assertEqual(str(context.exception), "'Blank community card'")

    def test_readCommunityCards_flopet_with_flop_present(self):
        """Test FLOPET quand FLOP est présent - ne fait rien."""
        hand = Mock()
        hand.streets = {"FLOPET": "[Qh Jh Ts]", "FLOP": "[Ah Kh Qc]"}
        hand.setCommunityCards = Mock()

        self.parser.readCommunityCards(hand, "FLOPET")

        # Ne doit pas appeler setCommunityCards car FLOP existe
        hand.setCommunityCards.assert_not_called()

    def test_readCommunityCards_flopet_without_flop(self):
        """Test FLOPET quand FLOP n'est pas présent - traite normalement."""
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

        # Mock re_board2 pour qu'il matche
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

        # Mock re_board2 pour qu'il ne matche pas
        self.parser.re_board2 = Mock()
        self.parser.re_board2.search = Mock(return_value=None)

        # Mock re_board pour qu'il matche
        mock_match = Mock()
        mock_match.group = Mock(return_value="9c")
        self.parser.re_board = Mock()
        self.parser.re_board.search = Mock(return_value=mock_match)

        self.parser.readCommunityCards(hand, "TURN")

        hand.setCommunityCards.assert_called_once_with("TURN", ["9c"])

    def test_readCommunityCards_sets_runittimes_flop1(self):
        """Test que runItTimes est défini à 2 pour FLOP1."""
        hand = Mock()
        hand.streets = {"FLOP1": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "FLOP1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_turn1(self):
        """Test que runItTimes est défini à 2 pour TURN1."""
        hand = Mock()
        hand.streets = {"TURN1": "[9c]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "TURN1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_river1(self):
        """Test que runItTimes est défini à 2 pour RIVER1."""
        hand = Mock()
        hand.streets = {"RIVER1": "[Ad]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "RIVER1")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_flop2(self):
        """Test que runItTimes est défini à 2 pour FLOP2."""
        hand = Mock()
        hand.streets = {"FLOP2": "[Kc Qd Jh]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "FLOP2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_turn2(self):
        """Test que runItTimes est défini à 2 pour TURN2."""
        hand = Mock()
        hand.streets = {"TURN2": "[5h]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "TURN2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_sets_runittimes_river2(self):
        """Test que runItTimes est défini à 2 pour RIVER2."""
        hand = Mock()
        hand.streets = {"RIVER2": "[3s]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 0

        self.parser.readCommunityCards(hand, "RIVER2")

        self.assertEqual(hand.runItTimes, 2)

    def test_readCommunityCards_does_not_set_runittimes_normal_streets(self):
        """Test que runItTimes n'est pas modifié pour les streets normales."""
        hand = Mock()
        hand.streets = {"FLOP": "[Qh Jh Ts]"}
        hand.setCommunityCards = Mock()
        hand.runItTimes = 1

        self.parser.readCommunityCards(hand, "FLOP")

        # runItTimes ne doit pas être modifié
        self.assertEqual(hand.runItTimes, 1)

    def test_readCommunityCards_multiple_cards_with_spaces(self):
        """Test parsing de cartes multiples avec espaces."""
        hand = Mock()
        hand.streets = {"FLOP": "[Ah  Kh   Qc]"}
        hand.setCommunityCards = Mock()

        # Mock re_board2 pour ne pas matcher à cause des espaces irréguliers
        self.parser.re_board2 = Mock()
        self.parser.re_board2.search = Mock(return_value=None)

        # Mock re_board pour matcher
        mock_match = Mock()
        mock_match.group = Mock(return_value="Ah  Kh   Qc")
        self.parser.re_board = Mock()
        self.parser.re_board.search = Mock(return_value=mock_match)

        self.parser.readCommunityCards(hand, "FLOP")

        # Vérifie que split(" ") avec un espace comme délimiteur gère les espaces multiples
        # split(" ") garde les éléments vides contrairement à split() sans argument
        expected_cards = "Ah  Kh   Qc".split(" ")  # Simule le comportement réel
        hand.setCommunityCards.assert_called_once_with("FLOP", expected_cards)


if __name__ == "__main__":
    unittest.main()
