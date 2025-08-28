"""
Comprehensive tests for PokerStarsToFpdb.readPlayerStacks method.
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        }


class TestReadPlayerStacks(unittest.TestCase):
    """Test cases for readPlayerStacks method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)

    def test_basic_player_stacks(self):
        """Test basic player stack parsing."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Seat 1: Player1 ($10.50 in chips)
Seat 2: Hero ($25.75 in chips)
Seat 3: Player3 ($15.25 in chips)
*** SUMMARY ***
Total pot $5.00
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 3)
        
        # Check calls
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player1", "10.50", None, None, None))
        self.assertEqual(calls[1][0], (2, "Hero", "25.75", None, None, None))
        self.assertEqual(calls[2][0], (3, "Player3", "15.25", None, None, None))

    def test_player_with_bounty(self):
        """Test parsing players with bounties."""
        hand_text = """PokerStars Game #123: Tournament #123456, $1.00+$0.10 USD
Seat 1: Player1 ($1000 in chips, $0.50 bounty)
Seat 2: Hero ($2000 in chips, $1.00 bounty)
*** SUMMARY ***
Total pot $100
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 2)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player1", "1000", None, None, "0.50"))
        self.assertEqual(calls[1][0], (2, "Hero", "2000", None, None, "1.00"))

    def test_sitting_out_player(self):
        """Test parsing players sitting out."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Seat 1: Player1 ($10.50 in chips)
Seat 2: Hero ($25.75 in chips) is sitting out
Seat 3: Player3 ($15.25 in chips)
*** SUMMARY ***
Total pot $5.00
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 3)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player1", "10.50", None, None, None))
        self.assertEqual(calls[1][0], (2, "Hero", "25.75", None, " is sitting out", None))
        self.assertEqual(calls[2][0], (3, "Player3", "15.25", None, None, None))

    def test_mixed_currencies_and_formats(self):
        """Test parsing with different currency formats."""
        hand_text = """PokerStars Game #123: Hold'em No Limit (€0.05/€0.10 EUR)
Seat 1: Player1 (€10.50 in chips)
Seat 2: Hero (€25.75 in chips, €2.50 bounty)
Seat 3: Player3 (€15.25 in chips) is sitting out
*** SUMMARY ***
Total pot €5.00
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 3)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player1", "10.50", None, None, None))
        self.assertEqual(calls[1][0], (2, "Hero", "25.75", None, None, "2.50"))
        self.assertEqual(calls[2][0], (3, "Player3", "15.25", None, " is sitting out", None))

    def test_no_summary_section(self):
        """Test handling when no SUMMARY section exists."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Seat 1: Player1 ($10.50 in chips)
Seat 2: Hero ($25.75 in chips)
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        with self.assertRaises(ValueError):
            self.parser.readPlayerStacks(hand)

    def test_empty_hand_text(self):
        """Test handling empty hand text."""
        hand_text = ""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        with self.assertRaises(ValueError):
            self.parser.readPlayerStacks(hand)

    def test_no_players_found(self):
        """Test when no players are found in pre-summary section."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
*** SUMMARY ***
Total pot $5.00
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 0)

    def test_large_stacks(self):
        """Test parsing very large stack amounts."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($500/$1000 USD)
Seat 1: HighRoller ($1000000.00 in chips)
Seat 2: BigStack ($999999.99 in chips)
*** SUMMARY ***
Total pot $50000
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 2)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "HighRoller", "1000000.00", None, None, None))
        self.assertEqual(calls[1][0], (2, "BigStack", "999999.99", None, None, None))

    def test_special_characters_in_names(self):
        """Test parsing player names with special characters."""
        hand_text = """PokerStars Game #123: Hold'em No Limit ($0.05/$0.10 USD)
Seat 1: Player-123 ($10.50 in chips)
Seat 2: Hero_999 ($25.75 in chips)
Seat 3: Плеер3 ($15.25 in chips)
*** SUMMARY ***
Total pot $5.00
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 3)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player-123", "10.50", None, None, None))
        self.assertEqual(calls[1][0], (2, "Hero_999", "25.75", None, None, None))
        self.assertEqual(calls[2][0], (3, "Плеер3", "15.25", None, None, None))

    def test_tournament_with_bounties_and_sitting_out(self):
        """Test complex tournament scenario with bounties and sitting out."""
        hand_text = """PokerStars Game #123: Tournament #987654, $5.00+$0.50 USD
Seat 1: Player1 ($1500 in chips, $2.50 bounty)
Seat 2: Hero ($3000 in chips, $5.00 bounty) is sitting out
Seat 3: Player3 ($2000 in chips)
Seat 4: Player4 ($1000 in chips, $1.25 bounty) is sitting out
*** SUMMARY ***
Total pot $200
"""
        hand = Mock()
        hand.handText = hand_text
        hand.addPlayer = Mock()
        
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x if x else None)
        
        self.parser.readPlayerStacks(hand)
        
        self.assertEqual(hand.addPlayer.call_count, 4)
        
        calls = hand.addPlayer.call_args_list
        self.assertEqual(calls[0][0], (1, "Player1", "1500", None, None, "2.50"))
        self.assertEqual(calls[1][0], (2, "Hero", "3000", None, " is sitting out", "5.00"))
        self.assertEqual(calls[2][0], (3, "Player3", "2000", None, None, None))
        self.assertEqual(calls[3][0], (4, "Player4", "1000", None, " is sitting out", "1.25"))


if __name__ == "__main__":
    unittest.main()