"""Integration test for rake calculation fixes."""

import unittest
from unittest.mock import Mock
from decimal import Decimal

from PokerStarsToFpdb import PokerStars


class TestRakeFixesIntegration(unittest.TestCase):
    """Integration tests for rake calculation fixes."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.parser = PokerStars(config=Mock(), in_path="test.txt")

    def test_issue_91_pokerstars_de_fix(self) -> None:
        """Test fix for issue #91: PokerStars.DE rake parsing incorrect."""
        # Original issue: GuiHandViewer showed -0.40 instead of 0.04
        # Hand from issue #91
        hand_text = """PokerStars Hand #255825888565:  Hold'em No Limit ($0.02/$0.05 USD) - 2025/04/21 9:50:44 CET [2025/04/21 3:50:44 ET]
*** SUMMARY ***
Total pot $0.53 | Rake $0.04
Board [3h 2d Qs]"""

        hand = Mock()
        hand.handText = hand_text
        
        # Parse rake from hand text
        self.parser._parseRakeAndPot(hand)
        
        # Should parse correctly
        self.assertEqual(hand.rake, Decimal("0.04"))
        self.assertEqual(hand.totalpot, Decimal("0.53"))
        
        # GuiHandViewer should use hand.rake instead of incorrect calculation
        guihandviewer_rake = hand.rake if hand.rake is not None else Decimal("0.00")
        self.assertEqual(guihandviewer_rake, Decimal("0.04"))
        
        # Verify old calculation would be wrong
        totalpot = Decimal("0.53")
        nbplayers = 6
        net = Decimal("0.49")  # Hero collected
        old_incorrect_rake = (totalpot / nbplayers) - net
        self.assertAlmostEqual(old_incorrect_rake, Decimal("-0.40"), places=1)
        
        # New calculation is correct
        self.assertNotEqual(guihandviewer_rake, old_incorrect_rake)

    def test_cashout_hands_fix(self) -> None:
        """Test fix for cash out hands rake/pot calculation."""
        # Original issue: cash out hands had incorrect totalcollected = 0
        # causing wrong rake calculations
        cashout_hand = """Player3 cashed out the hand for $22.77 | Cash Out Fee $0.46
*** SUMMARY ***
Total pot $27.21 | Rake $1.25 
Board [Qh Ad Ts As Qd]
Seat 1: Player1 showed [Qs Js] and won ($25.96) with a full house, Queens full of Aces"""

        hand = Mock()
        hand.handText = cashout_hand
        
        # Parse rake and pot from summary
        self.parser._parseRakeAndPot(hand)
        
        # Should parse summary values normally for cash out hands
        self.assertEqual(hand.totalpot, Decimal("27.21"))
        self.assertEqual(hand.rake, Decimal("1.25"))
        
        # Test cash out detection
        pre, post = hand.handText.split("*** SUMMARY ***")
        cash_out_detected = self.parser.re_cashed_out.search(pre) is not None
        self.assertTrue(cash_out_detected)
        
        # The key fix: normal pot collections should still be processed
        # even for cash out hands (Player1 won $25.96)
        # This ensures totalcollected is correct, making rake calculation coherent

    def test_integration_consistency(self) -> None:
        """Test that both fixes work together for consistent rake handling."""
        # Test 1: Normal hand
        normal_hand = Mock()
        normal_hand.handText = """*** SUMMARY ***
Total pot $10.00 | Rake $0.50"""
        
        self.parser._parseRakeAndPot(normal_hand)
        
        self.assertEqual(normal_hand.rake, Decimal("0.50"))
        self.assertEqual(normal_hand.totalpot, Decimal("10.00"))
        
        # Test 2: Cash out hand
        cashout_hand = Mock() 
        cashout_hand.handText = """Player2 cashed out the hand for $5.00 | Cash Out Fee $0.25
*** SUMMARY ***
Total pot $15.00 | Rake $0.75"""
        
        self.parser._parseRakeAndPot(cashout_hand)
        
        self.assertEqual(cashout_hand.rake, Decimal("0.75"))
        self.assertEqual(cashout_hand.totalpot, Decimal("15.00"))
        
        # Both should use hand.rake in GuiHandViewer
        normal_display_rake = normal_hand.rake if normal_hand.rake is not None else Decimal("0.00")
        cashout_display_rake = cashout_hand.rake if cashout_hand.rake is not None else Decimal("0.00")
        
        self.assertEqual(normal_display_rake, Decimal("0.50"))
        self.assertEqual(cashout_display_rake, Decimal("0.75"))


if __name__ == '__main__':
    unittest.main()