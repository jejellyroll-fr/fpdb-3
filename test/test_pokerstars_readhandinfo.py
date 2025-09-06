#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to Python path to import fpdb modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from Exceptions import FpdbHandPartial, FpdbParseError
from PokerStarsToFpdb import PokerStars


class TestPokerStarsReadHandInfo(unittest.TestCase):
    """Comprehensive tests for PokerStars readHandInfo method."""

    def setUp(self):
        """Set up test parser instance."""
        self.config = Mock()
        self.config.get_import_parameters.return_value = {}
        self.parser = PokerStars(config=self.config, in_path="test")

        # Mock the regex patterns to avoid complex initialization
        self.parser.re_hand_info = Mock()
        self.parser.re_game_info = Mock()
        self.parser.re_cancelled = Mock()

    def create_mock_hand(self, hand_text="", hand_id="12345"):
        """Create a mock hand object."""
        mock_hand = Mock()
        mock_hand.handText = hand_text
        mock_hand.handid = hand_id
        mock_hand.gametype = {}
        mock_hand.isFast = False
        return mock_hand

    def test_readHandInfo_no_summary_raises_partial(self):
        """Test that missing SUMMARY section raises FpdbHandPartial."""
        hand = self.create_mock_hand("PokerStars Game #123: Hold'em No Limit")

        with self.assertRaises(FpdbHandPartial) as cm:
            self.parser.readHandInfo(hand)

        self.assertIn("has no SUMMARY section", str(cm.exception))
        self.assertIn("12345", str(cm.exception))

    def test_readHandInfo_single_summary_success(self):
        """Test normal case with single SUMMARY section."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Table 'TestTable' 6-max Seat #1 is the button
*** SUMMARY ***
Total pot $1.00"""

        hand = self.create_mock_hand(hand_text)

        # Mock successful regex matches
        hand_info_match = Mock()
        hand_info_match.groupdict.return_value = {"TABLE": "TestTable", "BUTTON": "1"}
        self.parser.re_hand_info.search.return_value = hand_info_match

        game_info_match = Mock()
        game_info_match.groupdict.return_value = {"HID": "123", "GAME": "Hold'em"}
        self.parser.re_game_info.search.return_value = game_info_match

        # Mock cancelled check (not cancelled)
        self.parser.re_cancelled.search.return_value = None

        # Mock helper methods
        with (
            patch.object(self.parser, "_processHandInfo") as mock_process,
            patch.object(self.parser, "_parseRakeAndPot") as mock_parse_rake,
        ):
            self.parser.readHandInfo(hand)

            # Verify helper methods were called
            mock_process.assert_called_once()
            mock_parse_rake.assert_called_once_with(hand)

    def test_readHandInfo_multiple_summaries_no_next_hand_raises_partial(self):
        """Test multiple summaries without clear next hand boundary."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
First summary
*** SUMMARY ***
Second summary without clear boundary"""

        hand = self.create_mock_hand(hand_text)

        with self.assertRaises(FpdbHandPartial) as cm:
            self.parser.readHandInfo(hand)

        self.assertIn("contains 2 SUMMARY sections", str(cm.exception))
        self.assertIn("multiple incomplete hands", str(cm.exception))

    def test_readHandInfo_regex_match_failure_raises_parse_error(self):
        """Test that failed regex matches raise FpdbParseError."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock regex failure - one returns None
        self.parser.re_hand_info.search.return_value = None
        self.parser.re_game_info.search.return_value = Mock()

        with self.assertRaises(FpdbParseError):
            self.parser.readHandInfo(hand)

    def test_readHandInfo_game_info_regex_failure_raises_parse_error(self):
        """Test that failed game info regex match raises FpdbParseError."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock regex failure - game info returns None
        hand_info_match = Mock()
        hand_info_match.groupdict.return_value = {"TABLE": "TestTable"}
        self.parser.re_hand_info.search.return_value = hand_info_match
        self.parser.re_game_info.search.return_value = None

        with self.assertRaises(FpdbParseError):
            self.parser.readHandInfo(hand)

    def test_readHandInfo_zoom_path_sets_fast_game(self):
        """Test that Zoom in path sets fast game flags."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Set up parser with Zoom path
        self.parser.in_path = "path/with/Zoom/file.txt"

        # Mock successful regex matches
        hand_info_match = Mock()
        hand_info_match.groupdict.return_value = {"TABLE": "TestTable"}
        self.parser.re_hand_info.search.return_value = hand_info_match

        game_info_match = Mock()
        game_info_match.groupdict.return_value = {"HID": "123"}
        self.parser.re_game_info.search.return_value = game_info_match

        self.parser.re_cancelled.search.return_value = None

        with patch.object(self.parser, "_processHandInfo"), patch.object(self.parser, "_parseRakeAndPot"):
            self.parser.readHandInfo(hand)

            # Verify fast game flags are set
            self.assertTrue(hand.gametype["fast"])
            self.assertTrue(hand.isFast)

    def test_readHandInfo_rush_path_sets_fast_game(self):
        """Test that Rush in path sets fast game flags."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Set up parser with Rush path
        self.parser.in_path = "path/with/Rush/file.txt"

        # Mock successful regex matches
        hand_info_match = Mock()
        hand_info_match.groupdict.return_value = {"TABLE": "TestTable"}
        self.parser.re_hand_info.search.return_value = hand_info_match

        game_info_match = Mock()
        game_info_match.groupdict.return_value = {"HID": "123"}
        self.parser.re_game_info.search.return_value = game_info_match

        self.parser.re_cancelled.search.return_value = None

        with patch.object(self.parser, "_processHandInfo"), patch.object(self.parser, "_parseRakeAndPot"):
            self.parser.readHandInfo(hand)

            # Verify fast game flags are set
            self.assertTrue(hand.gametype["fast"])
            self.assertTrue(hand.isFast)

    def test_readHandInfo_cancelled_hand_raises_partial(self):
        """Test that cancelled hands raise FpdbHandPartial."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock successful regex matches
        hand_info_match = Mock()
        hand_info_match.groupdict.return_value = {"TABLE": "TestTable"}
        self.parser.re_hand_info.search.return_value = hand_info_match

        game_info_match = Mock()
        game_info_match.groupdict.return_value = {"HID": "123"}
        self.parser.re_game_info.search.return_value = game_info_match

        # Mock cancelled match (hand was cancelled)
        cancelled_match = Mock()
        self.parser.re_cancelled.search.return_value = cancelled_match

        with patch.object(self.parser, "_processHandInfo"), patch.object(self.parser, "_parseRakeAndPot"):
            with self.assertRaises(FpdbHandPartial) as cm:
                self.parser.readHandInfo(hand)

            self.assertIn("was cancelled", str(cm.exception))
            self.assertIn("12345", str(cm.exception))

    def test_readHandInfo_info_dict_merge(self):
        """Test that hand info and game info dictionaries are properly merged."""
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock regex matches with specific return values
        hand_info_match = Mock()
        hand_info_data = {"TABLE": "TestTable", "BUTTON": "1"}
        hand_info_match.groupdict.return_value = hand_info_data
        self.parser.re_hand_info.search.return_value = hand_info_match

        game_info_match = Mock()
        game_info_data = {"HID": "123", "GAME": "Hold'em"}
        game_info_match.groupdict.return_value = game_info_data
        self.parser.re_game_info.search.return_value = game_info_match

        self.parser.re_cancelled.search.return_value = None

        expected_info = {**hand_info_data, **game_info_data}

        with (
            patch.object(self.parser, "_processHandInfo") as mock_process,
            patch.object(self.parser, "_parseRakeAndPot"),
        ):
            self.parser.readHandInfo(hand)

            # Verify _processHandInfo was called with merged info
            mock_process.assert_called_once_with(expected_info, hand)

    def test_readHandInfo_multiple_summaries_edge_cases(self):
        """Test edge cases in multiple summaries handling."""
        # Case: Multiple summaries but can't find any with finditer
        hand_text = """PokerStars Game #123: Hold'em
*** SUMMARY ***
First summary
*** SUMMARY ***
Second summary"""

        hand = self.create_mock_hand(hand_text)

        # This shouldn't happen in practice, but test the error path
        with patch("re.finditer", return_value=[]):
            with self.assertRaises(FpdbHandPartial) as cm:
                self.parser.readHandInfo(hand)

            self.assertIn("not cleanly split", str(cm.exception))

    @patch("PokerStarsToFpdb.log")
    def test_readHandInfo_logging_behavior(self, mock_log):
        """Test logging behavior in various scenarios."""
        # Test error case that definitely triggers logging
        hand_text = """PokerStars Game #123: Invalid format
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock regex failure to trigger error logging
        self.parser.re_hand_info.search.return_value = None
        self.parser.re_game_info.search.return_value = Mock()

        with self.assertRaises(FpdbParseError):
            self.parser.readHandInfo(hand)

        # Verify error log was called
        mock_log.error.assert_called_once()

    @patch("PokerStarsToFpdb.log")
    def test_readHandInfo_error_logging(self, mock_log):
        """Test error logging when regex matches fail."""
        hand_text = """PokerStars Game #123: Invalid format
*** SUMMARY ***
Valid summary"""

        hand = self.create_mock_hand(hand_text)

        # Mock regex failure
        self.parser.re_hand_info.search.return_value = None
        self.parser.re_game_info.search.return_value = Mock()

        with self.assertRaises(FpdbParseError):
            self.parser.readHandInfo(hand)

        # Verify error was logged with hand text snippet
        mock_log.error.assert_called_once()
        error_call = mock_log.error.call_args[0]
        self.assertEqual(error_call[0], "read Hand Info failed: %r")
        # The actual length depends on the hand text - just verify it's truncated to <= 200
        self.assertLessEqual(len(error_call[1]), 200)


if __name__ == "__main__":
    unittest.main()
