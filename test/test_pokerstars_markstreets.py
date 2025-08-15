"""
Comprehensive tests for PokerStarsToFpdb.markStreets() method.

Tests all branches and edge cases of the markStreets method including:
- Draw games (27_1draw, fivedraw, multi-draw)
- Hold'em games (regular, Bovada, run-it-twice)
- Stud games
- Edge cases and error conditions
"""

import re
import unittest
from unittest.mock import Mock, patch

from PokerStarsToFpdb import PokerStars


class TestPokerStarsMarkStreets(unittest.TestCase):
    """Test suite for PokerStars markStreets method."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock the config to avoid file reading errors
        mock_config = Mock()
        
        # Create parser with dummy path to avoid None path error
        self.parser = PokerStars(config=mock_config, in_path='dummy_test_file.txt')
        
        # Set site_id (not siteId - it's a property)
        self.parser.site_id = 32  # Default PokerStars site ID
        
    def _create_mock_hand(self, game_type=None, hand_text=""):
        """Create a mock hand object with specified properties."""
        hand = Mock()
        hand.handText = hand_text
        hand.gametype = game_type or {"base": "hold", "split": False, "category": "holdem"}
        hand.addStreets = Mock()
        return hand

    def test_markstreets_27_1draw_with_discard(self):
        """Test markStreets for 27_1draw with discard action."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [As Ks Qh Jh Ts]
Player1: discards 2 cards
Hero: stands pat
Player2: discards 1 card
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "27_1draw", "base": "draw", "split": False},
            hand_text
        )
        
        self.parser.markStreets(hand)
        
        # Should add DRAW marker
        self.assertIn("*** DRAW ***", hand.handText)
        hand.addStreets.assert_called_once()
        
    def test_markstreets_27_1draw_no_discard(self):
        """Test markStreets for 27_1draw without discard action."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [As Ks Qh Jh Ts]
All players fold
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "27_1draw", "base": "draw", "split": False},
            hand_text
        )
        
        original_text = hand_text
        self.parser.markStreets(hand)
        
        # Should not modify hand text if no discard pattern found
        self.assertEqual(hand.handText, original_text)
        hand.addStreets.assert_called_once()

    def test_markstreets_fivedraw_with_discard(self):
        """Test markStreets for fivedraw with discard action."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [2s 3h 4d 5c 6s]
Player1: discards 3 cards [2h 7d 8c]
Hero: discards 1 card [6s]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "fivedraw", "base": "draw", "split": False},
            hand_text
        )
        
        self.parser.markStreets(hand)
        
        # Should add DRAW marker
        self.assertIn("*** DRAW ***", hand.handText)
        hand.addStreets.assert_called_once()

    def test_markstreets_run_it_twice(self):
        """Test markStreets for run-it-twice scenarios."""
        hand_text = """*** HOLE CARDS ***
Dealt to Hero [As Ks]
*** FLOP *** [Qh Jh Ts]
*** FIRST TURN *** [Qh Jh Ts] [9h]
*** SECOND TURN *** [Qh Jh Ts] [8h]
*** FIRST RIVER *** [Qh Jh Ts 9h] [7h]
*** SECOND RIVER *** [Qh Jh Ts 8h] [6h]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "hold", "split": True, "category": "holdem"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_holdem_regular(self):
        """Test markStreets for regular Hold'em games."""
        hand_text = """*** HOLE CARDS ***
Dealt to Hero [As Ks]
*** FLOP *** [Qh Jh Ts]
*** TURN *** [Qh Jh Ts] [9h]
*** RIVER *** [Qh Jh Ts 9h] [8s]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "hold", "split": False, "category": "holdem"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_holdem_bovada(self):
        """Test markStreets for Bovada Hold'em games."""
        hand_text = """*** HOLE CARDS ***
Dealt to Hero [As Ks]
*** FLOP *** [Qh Jh Ts]
*** TURN *** [Qh Jh Ts] [9h]
*** RIVER *** [Qh Jh Ts 9h] [8s]
*** SUMMARY ***"""
        
        # Mock SITE_BOVADA constant
        with patch('PokerStarsToFpdb.SITE_BOVADA', 12):
            self.parser.site_id = 12  # SITE_BOVADA
            
            hand = self._create_mock_hand(
                {"base": "hold", "split": False, "category": "holdem"},
                hand_text
            )
            
            self.parser.markStreets(hand)
            hand.addStreets.assert_called_once()

    def test_markstreets_stud_complete(self):
        """Test markStreets for complete Stud game."""
        hand_text = """Player1: posts the ante $0.01
Hero: posts the ante $0.01
*** 3rd STREET ***
Dealt to Player1 [Xx Xx] [3c]
Dealt to Hero [As Ks] [Qh]
*** 4th STREET ***
Dealt to Player1 [3c] [7h]
Dealt to Hero [Qh] [Jh]
*** 5th STREET ***
Dealt to Player1 [3c 7h] [Ts]
Dealt to Hero [Qh Jh] [9h]
*** 6th STREET ***
Dealt to Player1 [3c 7h Ts] [8s]
Dealt to Hero [Qh Jh 9h] [Th]
*** RIVER ***
Dealt to Player1 [8s]
Dealt to Hero [Kh]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "stud", "split": False, "category": "studhi"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_stud_incomplete(self):
        """Test markStreets for incomplete Stud game (missing streets)."""
        hand_text = """Player1: posts the ante $0.01
*** 3rd STREET ***
Dealt to Player1 [Xx Xx] [3c]
*** 4th STREET ***
Dealt to Player1 [3c] [7h]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "stud", "split": False, "category": "studhi"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_draw_multiple_draws(self):
        """Test markStreets for multi-draw games (not 27_1draw or fivedraw)."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [2s 3h 4d 5c 6s]
*** FIRST DRAW ***
Player1: discards 3 cards
Hero: discards 1 card
*** SECOND DRAW ***
Player1: discards 2 cards
Hero: stands pat
*** THIRD DRAW ***
Player1: stands pat
Hero: stands pat
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "draw", "split": False, "category": "triple_draw"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_draw_missing_streets(self):
        """Test markStreets for draw game with missing streets."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [2s 3h 4d 5c 6s]
*** FIRST DRAW ***
Player1: discards 3 cards
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "draw", "split": False, "category": "triple_draw"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_holdem_missing_streets(self):
        """Test markStreets for Hold'em game with missing streets."""
        hand_text = """*** HOLE CARDS ***
Dealt to Hero [As Ks]
*** FLOP *** [Qh Jh Ts]
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"base": "hold", "split": False, "category": "holdem"},
            hand_text
        )
        
        self.parser.markStreets(hand)
        hand.addStreets.assert_called_once()

    def test_markstreets_stands_pat_pattern(self):
        """Test markStreets with 'stands pat' pattern in draw games."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [As Ks Qh Jh Ts]
Player1: stands pat
Hero: discards 1 card
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "27_1draw", "base": "draw", "split": False},
            hand_text
        )
        
        self.parser.markStreets(hand)
        
        # Should add DRAW marker
        self.assertIn("*** DRAW ***", hand.handText)
        hand.addStreets.assert_called_once()

    def test_markstreets_empty_hand_text(self):
        """Test markStreets with empty hand text."""
        hand = self._create_mock_hand(
            {"base": "hold", "split": False, "category": "holdem"},
            ""
        )
        
        # Empty text will cause regex to return None, expect this to raise an error
        with self.assertRaises(AttributeError):
            self.parser.markStreets(hand)

    def test_markstreets_unknown_game_type(self):
        """Test markStreets with unknown game type."""
        hand_text = """Some unknown game format"""
        
        hand = self._create_mock_hand(
            {"base": "unknown", "split": False, "category": "unknown"},
            hand_text
        )
        
        # Unknown game type will cause 'm' to be undefined, expect error
        with self.assertRaises(UnboundLocalError):
            self.parser.markStreets(hand)

    def test_markstreets_regex_patterns_called(self):
        """Test that appropriate regex patterns are used based on game type."""
        # Test different game types to ensure correct patterns are applied
        # Use realistic hand texts that will match the patterns
        test_cases = [
            ({"base": "hold", "split": False, "category": "holdem"}, 
             "*** HOLE CARDS ***\nTest\n*** SUMMARY ***"),
            ({"base": "hold", "split": True, "category": "holdem"}, 
             "*** HOLE CARDS ***\nTest\n*** SUMMARY ***"),
            ({"base": "stud", "split": False, "category": "studhi"}, 
             "*** 3rd STREET ***\nTest\n*** SUMMARY ***"),
            ({"base": "draw", "split": False, "category": "27_1draw"}, 
             "*** DEALING HANDS ***\nTest\n*** SUMMARY ***"),
            ({"base": "draw", "split": False, "category": "fivedraw"}, 
             "*** DEALING HANDS ***\nTest\n*** SUMMARY ***"),
            ({"base": "draw", "split": False, "category": "triple_draw"}, 
             "*** DEALING HANDS ***\nTest\n*** SUMMARY ***"),
        ]
        
        for game_type, hand_text in test_cases:
            with self.subTest(game_type=game_type):
                hand = self._create_mock_hand(game_type, hand_text)
                self.parser.markStreets(hand)
                hand.addStreets.assert_called_once()
                hand.addStreets.reset_mock()

    def test_markstreets_carriage_return_handling(self):
        """Test that DRAW marker is added with proper line ending."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [As Ks Qh Jh Ts]
Player1: discards 2 cards
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "27_1draw", "base": "draw", "split": False},
            hand_text
        )
        
        self.parser.markStreets(hand)
        
        # Should add DRAW marker with \r\n
        self.assertIn("*** DRAW ***\r\n", hand.handText)

    def test_markstreets_reassemble_split_text(self):
        """Test that split text is properly reassembled in draw games."""
        hand_text = """*** DEALING HANDS ***
Dealt to Hero [As Ks Qh Jh Ts]
Player1: discards 2 cards
More text after discard
*** SUMMARY ***"""
        
        hand = self._create_mock_hand(
            {"category": "27_1draw", "base": "draw", "split": False},
            hand_text
        )
        
        original_length = len(hand_text)
        self.parser.markStreets(hand)
        
        # Text should be longer due to added DRAW marker
        self.assertGreater(len(hand.handText), original_length)
        # Should contain all original text
        self.assertIn("More text after discard", hand.handText)


if __name__ == '__main__':
    unittest.main()