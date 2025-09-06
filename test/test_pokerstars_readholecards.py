"""Comprehensive tests for PokerStars readHoleCards function."""

import unittest
from unittest.mock import Mock

from Hand import Hand
from PokerStarsToFpdb import STUD_HOLE_CARDS_COUNT, PokerStars


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

    def get_site_parameters(self, site_name: str) -> dict:
        """Return site parameters for testing."""
        return {}

    def get_db_parameters(self) -> dict:
        """Return database parameters for testing."""
        return {}


class TestPokerStarsReadHoleCards(unittest.TestCase):
    """Test readHoleCards method comprehensively."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def create_mock_hand(self, streets_dict: dict = None) -> Mock:
        """Create a mock Hand object."""
        hand = Mock(spec=Hand)
        hand.streets = streets_dict or {}
        hand.addHoleCards = Mock()
        hand.dealt = set()
        hand.hero = None
        return hand

    def create_mock_regex_match(self, pname: str, newcards: str = None, oldcards: str = None) -> Mock:
        """Create a mock regex match object."""
        mock_match = Mock()

        def side_effect(key):
            values = {"PNAME": pname, "NEWCARDS": newcards, "OLDCARDS": oldcards}
            return values.get(key)

        mock_match.group.side_effect = side_effect
        return mock_match

    def test_preflop_hero_cards_basic(self) -> None:
        """Test basic PREFLOP hero cards extraction."""
        hand = self.create_mock_hand({"PREFLOP": "Dealt to Hero [As Ks]"})
        mock_match = self.create_mock_regex_match("Hero", "As Ks")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.hero, "Hero")
        hand.addHoleCards.assert_called_with(
            "PREFLOP", "Hero", closed=["As", "Ks"], shown=False, mucked=False, dealt=True
        )

    def test_deal_street_hero_cards(self) -> None:
        """Test DEAL street hero cards extraction."""
        hand = self.create_mock_hand({"DEAL": "Dealt to TestPlayer [7h 2c]"})
        mock_match = self.create_mock_regex_match("TestPlayer", "7h 2c")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.hero, "TestPlayer")
        hand.addHoleCards.assert_called_with(
            "DEAL", "TestPlayer", closed=["7h", "2c"], shown=False, mucked=False, dealt=True
        )

    def test_preflop_with_cards_keyword_skip(self) -> None:
        """Test PREFLOP with 'cards' keyword in NEWCARDS should be skipped."""
        hand = self.create_mock_hand({"PREFLOP": "Dealt to Hero [cards]"})
        mock_match = self.create_mock_regex_match("Hero", "cards")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.hero, "Hero")
        hand.addHoleCards.assert_not_called()

    def test_stud_third_street_hero_three_cards(self) -> None:
        """Test STUD THIRD street with 3 cards for hero."""
        hand = self.create_mock_hand({"THIRD": "Dealt to Hero [2s 3c] [4h]"})
        mock_match = self.create_mock_regex_match("Hero", "2s 3c 4h")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.hero, "Hero")
        self.assertIn("Hero", hand.dealt)
        hand.addHoleCards.assert_called_with(
            "THIRD", "Hero", closed=["2s", "3c"], open=["4h"], shown=False, mucked=False, dealt=False
        )

    def test_stud_third_street_non_hero_player(self) -> None:
        """Test STUD THIRD street with less than 3 cards (non-hero player)."""
        hand = self.create_mock_hand({"THIRD": "Player shows [4h]"})
        mock_match = self.create_mock_regex_match("Player", "4h")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        # Hero should not be set for non-hero player
        self.assertNotEqual(hand.hero, "Player")
        self.assertNotIn("Player", hand.dealt)
        hand.addHoleCards.assert_called_with(
            "THIRD", "Player", open=["4h"], closed=[], shown=False, mucked=False, dealt=False
        )

    def test_regular_street_with_old_and_new_cards(self) -> None:
        """Test regular street with both old and new cards."""
        hand = self.create_mock_hand({"FOURTH": "Player shows [2s 3c 4h] [5d]"})
        mock_match = self.create_mock_regex_match("Player", "5d", "2s 3c 4h")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        hand.addHoleCards.assert_called_with(
            "FOURTH", "Player", open=["5d"], closed=["2s", "3c", "4h"], shown=False, mucked=False, dealt=False
        )

    def test_regular_street_with_only_new_cards(self) -> None:
        """Test regular street with only new cards."""
        hand = self.create_mock_hand({"RIVER": "Player shows [As]"})
        mock_match = self.create_mock_regex_match("Player", "As", None)

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        hand.addHoleCards.assert_called_with(
            "RIVER", "Player", open=["As"], closed=[], shown=False, mucked=False, dealt=False
        )

    def test_empty_streets_dict(self) -> None:
        """Test with empty streets dictionary."""
        hand = self.create_mock_hand({})

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[])

        self.parser.readHoleCards(hand)

        hand.addHoleCards.assert_not_called()

    def test_no_matches_found(self) -> None:
        """Test when no regex matches are found."""
        hand = self.create_mock_hand({"PREFLOP": "Some text without cards"})

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[])

        self.parser.readHoleCards(hand)

        hand.addHoleCards.assert_not_called()

    def test_empty_street_text(self) -> None:
        """Test with empty street text."""
        hand = self.create_mock_hand({"FLOP": ""})

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock()

        self.parser.readHoleCards(hand)

        # Should skip empty streets
        self.parser.re_hero_cards.finditer.assert_not_called()
        hand.addHoleCards.assert_not_called()

    def test_multiple_players_same_street(self) -> None:
        """Test multiple players on the same street."""
        hand = self.create_mock_hand({"FOURTH": "Multiple players action"})

        mock_match1 = self.create_mock_regex_match("Player1", "As")
        mock_match2 = self.create_mock_regex_match("Player2", "Kh")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match1, mock_match2])

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.addHoleCards.call_count, 2)

        # Check first call
        first_call = hand.addHoleCards.call_args_list[0]
        self.assertEqual(first_call[0], ("FOURTH", "Player1"))
        self.assertEqual(first_call[1]["open"], ["As"])

        # Check second call
        second_call = hand.addHoleCards.call_args_list[1]
        self.assertEqual(second_call[0], ("FOURTH", "Player2"))
        self.assertEqual(second_call[1]["open"], ["Kh"])

    def test_preflop_and_other_streets_combined(self) -> None:
        """Test combination of PREFLOP and other streets."""
        streets = {"PREFLOP": "Dealt to Hero [As Ks]", "FLOP": "Player shows [Qh]"}
        hand = self.create_mock_hand(streets)

        def mock_finditer(text):
            if "Hero" in text:
                return [self.create_mock_regex_match("Hero", "As Ks")]
            elif "Player" in text:
                return [self.create_mock_regex_match("Player", "Qh")]
            return []

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = mock_finditer

        self.parser.readHoleCards(hand)

        self.assertEqual(hand.hero, "Hero")
        self.assertEqual(hand.addHoleCards.call_count, 2)

    def test_stud_hole_cards_count_constant(self) -> None:
        """Test that STUD_HOLE_CARDS_COUNT constant is used correctly."""
        # Verify the constant value
        self.assertEqual(STUD_HOLE_CARDS_COUNT, 3)

        hand = self.create_mock_hand({"THIRD": "Dealt to Hero [2s 3c 4h]"})
        mock_match = self.create_mock_regex_match("Hero", "2s 3c 4h")

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        # Should trigger stud hero logic since len(newcards) == STUD_HOLE_CARDS_COUNT
        self.assertEqual(hand.hero, "Hero")
        self.assertIn("Hero", hand.dealt)

    def test_none_values_handling(self) -> None:
        """Test handling of None values from regex groups."""
        hand = self.create_mock_hand({"TURN": "Player action"})
        mock_match = self.create_mock_regex_match("Player", None, None)

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = Mock(return_value=[mock_match])

        self.parser.readHoleCards(hand)

        hand.addHoleCards.assert_called_with(
            "TURN", "Player", open=[], closed=[], shown=False, mucked=False, dealt=False
        )

    def test_skip_preflop_deal_in_main_loop(self) -> None:
        """Test that PREFLOP and DEAL streets are skipped in main loop."""
        streets = {"PREFLOP": "Dealt to Hero [As Ks]", "DEAL": "Dealt to Hero [7h 2c]", "FLOP": "Player shows [Qh]"}
        hand = self.create_mock_hand(streets)

        call_count = 0

        def mock_finditer(text):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First two calls are for PREFLOP/DEAL
                return [self.create_mock_regex_match("Hero", "As Ks")]
            else:  # Third call should be for FLOP only
                return [self.create_mock_regex_match("Player", "Qh")]

        self.parser.re_hero_cards = Mock()
        self.parser.re_hero_cards.finditer = mock_finditer

        self.parser.readHoleCards(hand)

        # Should be called 3 times: once for PREFLOP, once for DEAL, once for FLOP
        self.assertEqual(call_count, 3)
        # addHoleCards should be called 3 times total
        self.assertEqual(hand.addHoleCards.call_count, 3)


if __name__ == "__main__":
    unittest.main()
