"""Comprehensive tests for PokerStars _processSplitBounty method."""

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
            "importFilters": ["holdem", "omahahi", "omahahilo", "studhi", "studlo", "razz", "27_1draw", "27_3draw", "fivedraw", "badugi", "baduci"],
            "handCount": 0,
            "fastFold": False
        }


class TestProcessSplitBounty(unittest.TestCase):
    """Comprehensive test cases for _processSplitBounty method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def _create_mock_hand(self, ko_counts=None):
        """Create a mock hand object."""
        mock_hand = Mock()
        mock_hand.koCounts = ko_counts if ko_counts is not None else {}
        return mock_hand

    def _create_mock_match(self, pnames_string):
        """Create a mock match object."""
        mock_match = Mock()
        mock_match.__getitem__ = Mock(return_value=pnames_string)
        return mock_match

    def test_split_bounty_two_players_empty_counts(self):
        """Test splitting bounty between two players with empty koCounts."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1, Player2")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["Player1"], 0.5)
        self.assertEqual(hand.koCounts["Player2"], 0.5)
        self.assertEqual(len(hand.koCounts), 2)

    def test_split_bounty_three_players_empty_counts(self):
        """Test splitting bounty between three players with empty koCounts."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1, Player2, Player3")
        
        self.parser._processSplitBounty(hand, match)
        
        expected_value = 1.0 / 3.0
        self.assertAlmostEqual(hand.koCounts["Player1"], expected_value, places=10)
        self.assertAlmostEqual(hand.koCounts["Player2"], expected_value, places=10)
        self.assertAlmostEqual(hand.koCounts["Player3"], expected_value, places=10)
        self.assertEqual(len(hand.koCounts), 3)

    def test_split_bounty_four_players_empty_counts(self):
        """Test splitting bounty between four players with empty koCounts."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1, Player2, Player3, Player4")
        
        self.parser._processSplitBounty(hand, match)
        
        expected_value = 0.25
        for player in ["Player1", "Player2", "Player3", "Player4"]:
            self.assertEqual(hand.koCounts[player], expected_value)
        self.assertEqual(len(hand.koCounts), 4)

    def test_split_bounty_two_players_existing_counts(self):
        """Test splitting bounty with existing koCounts."""
        hand = self._create_mock_hand({"Player1": 1.5, "Player2": 0.5})
        match = self._create_mock_match("Player1, Player2")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["Player1"], 2.0)  # 1.5 + 0.5
        self.assertEqual(hand.koCounts["Player2"], 1.0)  # 0.5 + 0.5

    def test_split_bounty_mixed_existing_counts(self):
        """Test splitting bounty where some players exist and some don't."""
        hand = self._create_mock_hand({"Player1": 2.0, "Player3": 1.0})
        match = self._create_mock_match("Player1, Player2, Player3")
        
        self.parser._processSplitBounty(hand, match)
        
        expected_addition = 1.0 / 3.0
        self.assertAlmostEqual(hand.koCounts["Player1"], 2.0 + expected_addition, places=10)
        self.assertAlmostEqual(hand.koCounts["Player2"], expected_addition, places=10)
        self.assertAlmostEqual(hand.koCounts["Player3"], 1.0 + expected_addition, places=10)
        self.assertEqual(len(hand.koCounts), 3)

    def test_split_bounty_single_player(self):
        """Test splitting bounty with only one player (edge case)."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["Player1"], 1.0)
        self.assertEqual(len(hand.koCounts), 1)

    def test_split_bounty_special_characters_in_names(self):
        """Test splitting bounty with special characters in player names."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player-1, Player_2, Player.3")
        
        self.parser._processSplitBounty(hand, match)
        
        expected_value = 1.0 / 3.0
        self.assertAlmostEqual(hand.koCounts["Player-1"], expected_value, places=10)
        self.assertAlmostEqual(hand.koCounts["Player_2"], expected_value, places=10)
        self.assertAlmostEqual(hand.koCounts["Player.3"], expected_value, places=10)

    def test_split_bounty_numbers_in_names(self):
        """Test splitting bounty with numbers in player names."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player123, Player456")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["Player123"], 0.5)
        self.assertEqual(hand.koCounts["Player456"], 0.5)

    def test_split_bounty_preserves_other_players(self):
        """Test that splitting bounty doesn't affect other players' counts."""
        hand = self._create_mock_hand({"OtherPlayer": 3.0, "AnotherPlayer": 1.5})
        match = self._create_mock_match("Player1, Player2")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["OtherPlayer"], 3.0)
        self.assertEqual(hand.koCounts["AnotherPlayer"], 1.5)
        self.assertEqual(hand.koCounts["Player1"], 0.5)
        self.assertEqual(hand.koCounts["Player2"], 0.5)
        self.assertEqual(len(hand.koCounts), 4)

    def test_split_bounty_zero_existing_count(self):
        """Test splitting bounty where a player has zero existing count."""
        hand = self._create_mock_hand({"Player1": 0, "Player2": 2.0})
        match = self._create_mock_match("Player1, Player2")
        
        self.parser._processSplitBounty(hand, match)
        
        self.assertEqual(hand.koCounts["Player1"], 0.5)
        self.assertEqual(hand.koCounts["Player2"], 2.5)

    def test_split_bounty_fractional_existing_counts(self):
        """Test splitting bounty with fractional existing counts."""
        hand = self._create_mock_hand({"Player1": 0.33, "Player2": 0.67})
        match = self._create_mock_match("Player1, Player2, Player3")
        
        self.parser._processSplitBounty(hand, match)
        
        expected_addition = 1.0 / 3.0
        self.assertAlmostEqual(hand.koCounts["Player1"], 0.33 + expected_addition, places=10)
        self.assertAlmostEqual(hand.koCounts["Player2"], 0.67 + expected_addition, places=10)
        self.assertAlmostEqual(hand.koCounts["Player3"], expected_addition, places=10)

    def test_split_bounty_large_number_of_players(self):
        """Test splitting bounty between many players."""
        players = [f"Player{i}" for i in range(1, 11)]  # 10 players
        hand = self._create_mock_hand()
        match = self._create_mock_match(", ".join(players))
        
        self.parser._processSplitBounty(hand, match)
        
        expected_value = 0.1
        for player in players:
            self.assertEqual(hand.koCounts[player], expected_value)
        self.assertEqual(len(hand.koCounts), 10)

    def test_split_bounty_match_group_called_correctly(self):
        """Test that match subscript access is called with correct parameter."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1, Player2")
        
        self.parser._processSplitBounty(hand, match)
        
        match.__getitem__.assert_called_once_with("PNAME")

    def test_split_bounty_precision_with_many_divisions(self):
        """Test precision when dividing by prime numbers."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("P1, P2, P3, P4, P5, P6, P7")  # 7 players
        
        self.parser._processSplitBounty(hand, match)
        
        expected_value = 1.0 / 7.0
        total = sum(hand.koCounts.values())
        
        for player in ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]:
            self.assertAlmostEqual(hand.koCounts[player], expected_value, places=10)
        
        # Total should be 1.0 (accounting for floating point precision)
        self.assertAlmostEqual(total, 1.0, places=10)

    def test_split_bounty_empty_player_name_handling(self):
        """Test handling of empty spaces in player names."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1,  Player2")  # Extra space
        
        self.parser._processSplitBounty(hand, match)
        
        # The function should handle the extra space
        self.assertTrue("Player1" in hand.koCounts)
        # Note: The actual behavior depends on how split() handles extra spaces
        # This test documents the current behavior

    def test_split_bounty_duplicate_player_names(self):
        """Test behavior with duplicate player names."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("Player1, Player1")
        
        self.parser._processSplitBounty(hand, match)
        
        # Player1 should get 0.5 + 0.5 = 1.0 (processed twice)
        self.assertEqual(hand.koCounts["Player1"], 1.0)
        self.assertEqual(len(hand.koCounts), 1)


if __name__ == '__main__':
    unittest.main()