"""Tests for PokerStars progressive bounties processing."""

import unittest
from unittest.mock import Mock

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


class TestProgressiveBounties(unittest.TestCase):
    """Test cases for _processProgressiveBounties method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def test_no_progressive_bounties(self):
        """Test when no progressive bounties are found."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 0
        mock_hand.handText = "Standard hand text without bounties"

        self.parser._processProgressiveBounties(mock_hand)

        self.assertEqual(len(mock_hand.endBounty), 0)
        self.assertFalse(mock_hand.isProgressive)
        self.assertEqual(len(mock_hand.koCounts), 0)

    def test_single_progressive_bounty(self):
        """Test single progressive bounty processing."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 10.0
        mock_hand.handText = """
Player1 wins $5.00 for eliminating Player2 and their own bounty increases by $2.50 to $12.50
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 1250)  # 12.50 * 100
        self.assertEqual(mock_hand.koCounts["Player1"], 50.0)  # 500 / 10.0

    def test_multiple_progressive_bounties_same_player(self):
        """Test multiple progressive bounties for same player."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 20.0
        mock_hand.handText = """
Player1 wins $3.00 for eliminating Player2 and their own bounty increases by $1.50 to $8.50
Player1 wins $4.00 for eliminating Player3 and their own bounty increases by $2.00 to $10.50
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 1050)  # Last endamt: 10.50 * 100
        self.assertEqual(mock_hand.koCounts["Player1"], 35.0)  # (300+400) / 20.0

    def test_multiple_progressive_bounties_different_players(self):
        """Test multiple progressive bounties for different players."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 15.0
        mock_hand.handText = """
Player1 wins $3.00 for eliminating Player3 and their own bounty increases by $1.50 to $8.50
Player2 wins $4.00 for eliminating Player4 and their own bounty increases by $2.00 to $9.00
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 850)  # 8.50 * 100
        self.assertEqual(mock_hand.endBounty["Player2"], 900)  # 9.00 * 100
        self.assertEqual(mock_hand.koCounts["Player1"], 20.0)  # 300 / 15.0
        self.assertAlmostEqual(mock_hand.koCounts["Player2"], 26.67, places=1)  # 400 / 15.0

    def test_tournament_winner_bonus(self):
        """Test tournament winner gets end bounty added."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 10.0
        mock_hand.handText = """
Player1 wins $5.00 for eliminating Player2 and their own bounty increases by $2.50 to $12.50
Player1 wins the tournament and receives $230.36 - congratulations!
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 1250)  # 12.50 * 100
        # Winner gets ko_amount + endBounty: (500 + 1250) / 10.0 = 175.0
        self.assertEqual(mock_hand.koCounts["Player1"], 175.0)

    def test_splitting_elimination(self):
        """Test splitting elimination scenario."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 8.0
        mock_hand.handText = """
Player1 wins $2.00 for splitting the elimination of Player3 and their own bounty increases by $1.00 to $6.00
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 600)  # 6.00 * 100
        self.assertEqual(mock_hand.koCounts["Player1"], 25.0)  # 200 / 8.0

    def test_zero_ko_bounty(self):
        """Test when koBounty is zero, koCounts should not be set."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 0
        mock_hand.handText = """
Player1 wins $5.00 for eliminating Player2 and their own bounty increases by $2.50 to $12.50
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 1250)  # 12.50 * 100
        self.assertEqual(len(mock_hand.koCounts), 0)  # No koCounts when koBounty is 0

    def test_decimal_amounts(self):
        """Test handling of decimal amounts."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 12.5
        mock_hand.handText = """
Player1 wins $3.75 for eliminating Player2 and their own bounty increases by $1.25 to $8.75
*** SUMMARY ***
"""

        self.parser._processProgressiveBounties(mock_hand)

        self.assertTrue(mock_hand.isProgressive)
        self.assertEqual(mock_hand.endBounty["Player1"], 875)  # 8.75 * 100
        self.assertEqual(mock_hand.koCounts["Player1"], 30.0)  # 375 / 12.5

    def test_comma_in_amt_fails(self):
        """Test that comma in AMT fails due to float() conversion."""
        mock_hand = Mock()
        mock_hand.endBounty = {}
        mock_hand.isProgressive = False
        mock_hand.koCounts = {}
        mock_hand.koBounty = 50.0
        mock_hand.handText = """
Player1 wins $1,250.50 for eliminating Player2 and their own bounty increases by $625.25 to $2500.75
*** SUMMARY ***
"""

        # Test that method raises ValueError due to comma in AMT
        with self.assertRaises(ValueError):
            self.parser._processProgressiveBounties(mock_hand)


if __name__ == "__main__":
    unittest.main()
