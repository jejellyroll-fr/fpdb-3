#!/usr/bin/env python3
"""Tests for Hand.addCashOutPot method."""

import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Hand import HoldemOmahaHand


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        return {"saveActions": True, "callFpdbHud": False, "cacheSessions": False}

    def get_site_id(self, sitename: str) -> int:
        return 32  # PokerStars


class TestHandCashOutPot(unittest.TestCase):
    """Test cases for Hand.addCashOutPot method."""

    def setUp(self):
        """Set up test environment."""
        self.mock_config = MockConfig()
        self.mock_hhc = Mock()

        # Create a minimal gametype
        self.gametype = {
            "type": "ring",
            "base": "hold",
            "category": "holdem",
            "limitType": "nl",
            "sb": Decimal("0.05"),
            "bb": Decimal("0.10"),
            "currency": "USD",
        }

        self.hand = HoldemOmahaHand(
            config=self.mock_config,
            hhc=self.mock_hhc,
            sitename="PokerStars",
            gametype=self.gametype,
            handText="",
            builtFrom="Test",
        )

        # Add a test player
        self.hand.addPlayer(1, "TestPlayer", "100.00")

    def test_addCashOutPot_basic_functionality(self):
        """Test basic cash out pot functionality."""
        self.hand.addCashOutPot("TestPlayer", "22.77")

        # Check that collection was recorded
        self.assertEqual(len(self.hand.collected), 1)
        self.assertEqual(self.hand.collected[0], ["TestPlayer", "22.77"])

        # Check that collectees was updated
        self.assertIn("TestPlayer", self.hand.collectees)
        self.assertEqual(self.hand.collectees["TestPlayer"], Decimal("22.77"))

        # CRITICAL: Check that totalcollected was NOT updated
        self.assertEqual(self.hand.totalcollected, Decimal("0"))

    def test_addCashOutPot_vs_addCollectPot_difference(self):
        """Test that addCashOutPot and addCollectPot behave differently."""
        # First test regular collection
        hand1 = HoldemOmahaHand(
            config=self.mock_config,
            hhc=self.mock_hhc,
            sitename="PokerStars",
            gametype=self.gametype,
            handText="",
            builtFrom="Test",
        )
        hand1.addPlayer(1, "TestPlayer", "100.00")
        hand1.addCollectPot("TestPlayer", "22.77")

        # Regular collection should update totalcollected
        self.assertEqual(hand1.totalcollected, Decimal("22.77"))

        # Now test cash out collection
        hand2 = HoldemOmahaHand(
            config=self.mock_config,
            hhc=self.mock_hhc,
            sitename="PokerStars",
            gametype=self.gametype,
            handText="",
            builtFrom="Test",
        )
        hand2.addPlayer(1, "TestPlayer", "100.00")
        hand2.addCashOutPot("TestPlayer", "22.77")

        # Cash out collection should NOT update totalcollected
        self.assertEqual(hand2.totalcollected, Decimal("0"))

        # But both should have same collected and collectees
        self.assertEqual(hand1.collected, hand2.collected)
        self.assertEqual(hand1.collectees, hand2.collectees)

    def test_multiple_cash_outs(self):
        """Test multiple cash outs from same player."""
        self.hand.addPlayer(2, "Player2", "50.00")

        # Add multiple cash outs
        self.hand.addCashOutPot("TestPlayer", "10.00")
        self.hand.addCashOutPot("TestPlayer", "12.77")
        self.hand.addCashOutPot("Player2", "5.50")

        # Check collections recorded
        self.assertEqual(len(self.hand.collected), 3)

        # Check collectees accumulated correctly
        self.assertEqual(self.hand.collectees["TestPlayer"], Decimal("22.77"))
        self.assertEqual(self.hand.collectees["Player2"], Decimal("5.50"))

        # Total collected should still be 0
        self.assertEqual(self.hand.totalcollected, Decimal("0"))

    def test_rake_calculation_with_cash_out(self):
        """Test that rake calculation works correctly with cash outs."""
        # The key test: totalcollected should not include cash outs

        # Add regular collection (affects totalcollected)
        self.hand.addCollectPot("TestPlayer", "25.00")
        self.assertEqual(self.hand.totalcollected, Decimal("25.00"))

        # Add cash out (should NOT affect totalcollected)
        self.hand.addCashOutPot("TestPlayer", "22.77")

        # totalcollected should still be 25.00, not 47.77
        self.assertEqual(self.hand.totalcollected, Decimal("25.00"))

        # Both should be recorded in collected list
        self.assertEqual(len(self.hand.collected), 2)
        self.assertEqual(self.hand.collected[0], ["TestPlayer", "25.00"])
        self.assertEqual(self.hand.collected[1], ["TestPlayer", "22.77"])

        # Both amounts should be in collectees (for display)
        self.assertEqual(self.hand.collectees["TestPlayer"], Decimal("47.77"))


if __name__ == "__main__":
    unittest.main()
