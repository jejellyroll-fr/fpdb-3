"""Tests for PokerStars regular bounties processing."""

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


class TestRegularBounties(unittest.TestCase):
    """Test cases for _processRegularBounties method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def test_no_regular_bounties(self):
        """Test when no regular bounties are found."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = "Standard hand text without bounties"

        self.parser._processRegularBounties(mock_hand)

        self.assertEqual(len(mock_hand.koCounts), 0)

    def test_single_regular_bounty(self):
        """Test single regular bounty processing."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = "APTEM-89 wins the $0.27 bounty for eliminating Hero"

        with patch.object(self.parser, "_processSingleBounty") as mock_single:
            self.parser._processRegularBounties(mock_hand)
            mock_single.assert_called_once()

    def test_split_regular_bounty(self):
        """Test split regular bounty processing."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = "JKuzja, vecenta split the $50 bounty for eliminating ODYSSES"

        with patch.object(self.parser, "_processSplitBounty") as mock_split:
            self.parser._processRegularBounties(mock_hand)
            mock_split.assert_called_once()

    def test_multiple_regular_bounties_mixed(self):
        """Test multiple regular bounties with both single and split."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = """
APTEM-89 wins the $0.27 bounty for eliminating Hero
JKuzja, vecenta split the $50 bounty for eliminating ODYSSES
ChazDazzle wins the 22000 bounty for eliminating berkovich609
"""

        with (
            patch.object(self.parser, "_processSingleBounty") as mock_single,
            patch.object(self.parser, "_processSplitBounty") as mock_split,
        ):
            self.parser._processRegularBounties(mock_hand)
            self.assertEqual(mock_single.call_count, 2)  # APTEM-89 and ChazDazzle
            self.assertEqual(mock_split.call_count, 1)  # JKuzja, vecenta

    def test_process_single_bounty(self):
        """Test _processSingleBounty method."""
        mock_hand = Mock()
        mock_hand.koCounts = {}

        # Mock match object
        mock_match = Mock()
        mock_match.__getitem__ = Mock(side_effect=lambda x: {"PNAME": "TestPlayer"}.get(x))

        self.parser._processSingleBounty(mock_hand, mock_match)

        self.assertEqual(mock_hand.koCounts["TestPlayer"], 1)
        mock_match.__getitem__.assert_called_with("PNAME")

    def test_process_single_bounty_existing_player(self):
        """Test _processSingleBounty method with existing player."""
        mock_hand = Mock()
        mock_hand.koCounts = {"TestPlayer": 2}

        # Mock match object
        mock_match = Mock()
        mock_match.__getitem__ = Mock(side_effect=lambda x: {"PNAME": "TestPlayer"}.get(x))

        self.parser._processSingleBounty(mock_hand, mock_match)

        self.assertEqual(mock_hand.koCounts["TestPlayer"], 3)

    def test_process_split_bounty_two_players(self):
        """Test _processSplitBounty method with two players."""
        mock_hand = Mock()
        mock_hand.koCounts = {}

        # Mock match object
        mock_match = Mock()
        mock_match.__getitem__ = Mock(return_value="Player1, Player2")

        self.parser._processSplitBounty(mock_hand, mock_match)

        self.assertEqual(mock_hand.koCounts["Player1"], 0.5)
        self.assertEqual(mock_hand.koCounts["Player2"], 0.5)
        mock_match.__getitem__.assert_called_with("PNAME")

    def test_process_split_bounty_three_players(self):
        """Test _processSplitBounty method with three players."""
        mock_hand = Mock()
        mock_hand.koCounts = {}

        # Mock match object
        mock_match = Mock()
        mock_match.__getitem__ = Mock(return_value="Player1, Player2, Player3")

        self.parser._processSplitBounty(mock_hand, mock_match)

        expected_value = 1.0 / 3.0
        self.assertAlmostEqual(mock_hand.koCounts["Player1"], expected_value, places=6)
        self.assertAlmostEqual(mock_hand.koCounts["Player2"], expected_value, places=6)
        self.assertAlmostEqual(mock_hand.koCounts["Player3"], expected_value, places=6)

    def test_process_split_bounty_existing_players(self):
        """Test _processSplitBounty method with existing players."""
        mock_hand = Mock()
        mock_hand.koCounts = {"Player1": 1.0, "Player2": 0.5}

        # Mock match object
        mock_match = Mock()
        mock_match.__getitem__ = Mock(return_value="Player1, Player2")

        self.parser._processSplitBounty(mock_hand, mock_match)

        self.assertEqual(mock_hand.koCounts["Player1"], 1.5)  # 1.0 + 0.5
        self.assertEqual(mock_hand.koCounts["Player2"], 1.0)  # 0.5 + 0.5

    def test_regular_bounty_regex_patterns(self):
        """Test that the regex correctly identifies bounty patterns."""
        test_cases = [
            ("APTEM-89 wins the $0.27 bounty for eliminating Hero", False),  # single
            ("ChazDazzle wins the 22000 bounty for eliminating berkovich609", False),  # single, no currency
            ("JKuzja, vecenta split the $50 bounty for eliminating ODYSSES", True),  # split
            ("Player1, Player2, Player3 split the €25.50 bounty for eliminating Target", True),  # split with euro
        ]

        for hand_text, is_split in test_cases:
            matches = list(self.parser.re_bounty.finditer(hand_text))
            self.assertEqual(len(matches), 1, f"Should find exactly one match in: {hand_text}")

            match = matches[0]
            split_group = match.group("SPLIT")
            if is_split:
                self.assertEqual(split_group, "split", f"Should be split bounty: {hand_text}")
            else:
                self.assertEqual(split_group, "wins", f"Should be single bounty: {hand_text}")

    def test_integration_with_read_tourney_results(self):
        """Test integration with readTourneyResults method."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = "APTEM-89 wins the $0.27 bounty for eliminating Hero"

        # Mock the methods directly since we can't mock re.Pattern.search
        with (
            patch.object(self.parser, "_processRegularBounties") as mock_regular,
            patch.object(self.parser, "_processProgressiveBounties") as mock_progressive,
        ):
            self.parser.readTourneyResults(mock_hand)

            # Since the handText contains regular bounty pattern, it should call _processRegularBounties
            mock_regular.assert_called_once_with(mock_hand)
            mock_progressive.assert_not_called()

    def test_integration_no_bounties_triggers_progressive(self):
        """Test that no regular bounties triggers progressive bounty processing."""
        mock_hand = Mock()
        mock_hand.koCounts = {}
        mock_hand.handText = "No bounty text here"

        # Mock the methods directly since we can't mock re.Pattern.search
        with (
            patch.object(self.parser, "_processRegularBounties") as mock_regular,
            patch.object(self.parser, "_processProgressiveBounties") as mock_progressive,
        ):
            self.parser.readTourneyResults(mock_hand)

            # Since the handText contains no regular bounty pattern, it should call _processProgressiveBounties
            mock_regular.assert_not_called()
            mock_progressive.assert_called_once_with(mock_hand)


if __name__ == "__main__":
    unittest.main()
