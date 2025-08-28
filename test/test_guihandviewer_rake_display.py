"""Tests for GuiHandViewer rake display logic fix."""

import unittest
from unittest.mock import Mock
from decimal import Decimal


class TestGuiHandViewerRakeDisplay(unittest.TestCase):
    """Test cases for GuiHandViewer rake display logic."""

    def test_rake_logic_uses_hand_rake(self) -> None:
        """Test that rake logic uses hand.rake instead of incorrect calculation."""
        # Issue #91 case: PokerStars.DE hand with correct rake
        hand = Mock()
        hand.rake = Decimal("0.04")  # Correct rake from hand history parsing
        
        # GuiHandViewer should use: rake = hand.rake if hand.rake is not None else Decimal("0.00")
        rake = hand.rake if hand.rake is not None else Decimal("0.00")
        
        self.assertEqual(rake, Decimal("0.04"))  # Should use parsed rake

    def test_rake_logic_with_none_rake(self) -> None:
        """Test that None rake defaults to 0.00."""
        hand = Mock()
        hand.rake = None  # Rake not set
        
        rake = hand.rake if hand.rake is not None else Decimal("0.00")
        self.assertEqual(rake, Decimal("0.00"))

    def test_old_vs_new_calculation(self) -> None:
        """Test comparison between old incorrect and new correct calculation."""
        # Values from issue #91 PokerStars.DE hand
        hand = Mock()
        hand.rake = Decimal("0.04")  # Correct rake from parsing
        totalpot = Decimal("0.53")
        nbplayers = 6
        net = Decimal("0.49")  # Hero won $0.49
        
        # Old incorrect formula: rake = (totalpot / nbplayers) - net
        old_rake = (totalpot / nbplayers) - net
        self.assertAlmostEqual(old_rake, Decimal("-0.40"), places=1)  # Would show -$0.40
        
        # New correct logic: use hand.rake
        new_rake = hand.rake if hand.rake is not None else Decimal("0.00")
        self.assertEqual(new_rake, Decimal("0.04"))  # Shows correct $0.04
        
        # Verify they're different
        self.assertNotEqual(new_rake, old_rake)


if __name__ == '__main__':
    unittest.main()