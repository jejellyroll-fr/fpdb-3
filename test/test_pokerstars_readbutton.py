"""Comprehensive tests for PokerStarsToFpdb.readButton method."""

import unittest
from unittest.mock import Mock, patch

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


class TestPokerStarsReadButton(unittest.TestCase):
    """Test cases for readButton method in PokerStarsToFpdb."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def test_readButton_basic_case(self):
        """Test readButton with basic button position."""
        hand = Mock()
        hand.handText = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #3 is the button
Seat 1: Player1 ($10.00 in chips)
Seat 3: Hero ($10.00 in chips)"""

        self.parser.readButton(hand)
        self.assertEqual(hand.buttonpos, 3)

    def test_readButton_different_positions(self):
        """Test readButton with different button positions."""
        test_cases = [
            (1, "Seat #1 is the button"),
            (2, "Seat #2 is the button"),
            (6, "Seat #6 is the button"),
            (9, "Seat #9 is the button"),
        ]

        for expected_pos, button_text in test_cases:
            with self.subTest(position=expected_pos):
                hand = Mock()
                hand.handText = f"PokerStars Game #123: Hold'em No Limit\nTable 'Test' 6-max {button_text}\n"

                self.parser.readButton(hand)
                self.assertEqual(hand.buttonpos, expected_pos)

    def test_readButton_multiline_text(self):
        """Test readButton with multiline hand text."""
        hand = Mock()
        hand.handText = """PokerStars Game #123456789: Hold'em No Limit ($0.01/$0.02 USD)
Table 'Caesium IV' 6-max Seat #4 is the button
Seat 1: Player1 ($2.00 in chips)
Seat 2: Player2 ($2.00 in chips)
Seat 4: Hero ($2.00 in chips)
Seat 5: Player5 ($2.00 in chips)
Hero: posts small blind $0.01"""

        self.parser.readButton(hand)
        self.assertEqual(hand.buttonpos, 4)

    def test_readButton_with_extra_spaces(self):
        """Test readButton with extra spaces around button text."""
        hand = Mock()
        hand.handText = "Table 'Test'   Seat #5 is the button   "

        self.parser.readButton(hand)
        self.assertEqual(hand.buttonpos, 5)

    def test_readButton_button_not_found(self):
        """Test readButton when button information is not found."""
        hand = Mock()
        hand.handText = "No button information in this text"

        with patch("PokerStarsToFpdb.log") as mock_log:
            self.parser.readButton(hand)
            mock_log.info.assert_called_once_with("readButton: not found")

        # buttonpos should not be set when button is not found
        # Since Mock objects auto-create attributes when accessed, we check if buttonpos was actually set by readButton
        buttonpos_value = getattr(hand, "buttonpos", "NOT_SET")
        self.assertNotIsInstance(buttonpos_value, int)

    def test_readButton_empty_hand_text(self):
        """Test readButton with empty hand text."""
        hand = Mock()
        hand.handText = ""

        with patch("PokerStarsToFpdb.log") as mock_log:
            self.parser.readButton(hand)
            mock_log.info.assert_called_once_with("readButton: not found")

    def test_readButton_malformed_button_text(self):
        """Test readButton with malformed button text."""
        test_cases = [
            "Seat # is the button",  # Missing number
            "Seat #X is the button",  # Non-numeric
            "Seat is the button",  # Missing #
            "Seat #10 is not the button",  # Different text
        ]

        for malformed_text in test_cases:
            with self.subTest(text=malformed_text):
                hand = Mock()
                hand.handText = malformed_text

                with patch("PokerStarsToFpdb.log") as mock_log:
                    self.parser.readButton(hand)
                    mock_log.info.assert_called_once_with("readButton: not found")

    def test_readButton_multiple_button_references(self):
        """Test readButton when there are multiple button references."""
        hand = Mock()
        hand.handText = """PokerStars Game #123: Hold'em No Limit
Table 'Test' 6-max Seat #2 is the button
Previous hand: Seat #1 was the button
Seat #2 is the button"""

        self.parser.readButton(hand)
        # Should match the first occurrence
        self.assertEqual(hand.buttonpos, 2)

    def test_readButton_case_sensitivity(self):
        """Test readButton with different case variations."""
        test_cases = [
            "Seat #3 is the button",
            "SEAT #3 IS THE BUTTON",
            "seat #3 is the button",
        ]

        for button_text in test_cases:
            with self.subTest(text=button_text):
                hand = Mock()
                hand.handText = button_text

                # The regex is case-sensitive, so only the first should work
                if button_text == "Seat #3 is the button":
                    self.parser.readButton(hand)
                    self.assertEqual(hand.buttonpos, 3)
                else:
                    with patch("PokerStarsToFpdb.log"):
                        self.parser.readButton(hand)
                        # For non-matching cases, buttonpos shouldn't be set to an integer
                        buttonpos_value = getattr(hand, "buttonpos", "NOT_SET")
                        self.assertNotIsInstance(buttonpos_value, int)

    def test_readButton_tournament_format(self):
        """Test readButton with tournament hand format."""
        hand = Mock()
        hand.handText = """PokerStars Game #123456789: Tournament #987654321, $10+$1 USD Hold'em No Limit
Level I (10/20) - 2023/01/01 12:00:00 ET
Table '987654321 1' 9-max Seat #7 is the button
Seat 1: Player1 (1500 in chips)
Seat 7: Hero (1500 in chips)"""

        self.parser.readButton(hand)
        self.assertEqual(hand.buttonpos, 7)

    def test_readButton_cash_game_format(self):
        """Test readButton with cash game format."""
        hand = Mock()
        hand.handText = """PokerStars Game #123456789: Hold'em No Limit ($0.25/$0.50 USD)
Table 'Procyon V' 6-max Seat #8 is the button
Seat 2: Player2 ($50.00 in chips)
Seat 8: Hero ($100.00 in chips)"""

        self.parser.readButton(hand)
        self.assertEqual(hand.buttonpos, 8)

    def test_readButton_regex_pattern(self):
        """Test that the regex pattern is correctly compiled."""
        # Verify the regex pattern exists and is compiled
        self.assertTrue(hasattr(self.parser, "re_button"))
        self.assertIsNotNone(self.parser.re_button)

        # Test the pattern directly
        pattern = r"Seat #(?P<BUTTON>\d+) is the button"
        test_text = "Seat #5 is the button"
        match = self.parser.re_button.search(test_text)

        self.assertIsNotNone(match)
        self.assertEqual(match.group("BUTTON"), "5")

    def test_readButton_preserves_hand_object(self):
        """Test that readButton doesn't modify other hand attributes."""
        hand = Mock()
        hand.handText = "Table 'Test' Seat #2 is the button"
        hand.existing_attr = "preserved_value"

        self.parser.readButton(hand)

        self.assertEqual(hand.buttonpos, 2)
        self.assertEqual(hand.existing_attr, "preserved_value")


if __name__ == "__main__":
    unittest.main()
