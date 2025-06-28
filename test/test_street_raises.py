#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for streetXRaises method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats


class MockHand:
    """Mock Hand object for testing streetXRaises"""
    
    def __init__(self):
        self.handid = "12345"
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "raises", Decimal("3.00")),
                ("Player4", "calls", Decimal("3.00")),
                ("Player1", "raises", Decimal("9.00")),
                ("Player2", "folds"),
                ("Player3", "raises", Decimal("27.00")),
                ("Player4", "folds"),
                ("Player1", "calls", Decimal("18.00")),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player3", "bets", Decimal("30.00")),
                ("Player1", "raises", Decimal("90.00")),
                ("Player3", "calls", Decimal("60.00")),
            ],
            "TURN": [
                ("Player1", "bets", Decimal("100.00")),
                ("Player3", "calls", Decimal("100.00")),
            ],
            "RIVER": [
                ("Player1", "checks"),
                ("Player3", "checks"),
            ],
        }


class TestStreetRaises:
    """Test cases for streetXRaises method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance"""
        stats = DerivedStats()
        stats.hands = {}
        return stats
    
    def test_basic_raise_counting(self, stats):
        """Test basic counting of raises, bets, and completes"""
        hand = MockHand()
        
        stats.streetXRaises(hand)
        
        # Street 0 (PREFLOP): 3 raises
        assert stats.hands["street0Raises"] == 3
        
        # Street 1 (FLOP): 1 bet + 1 raise = 2
        assert stats.hands["street1Raises"] == 2
        
        # Street 2 (TURN): 1 bet
        assert stats.hands["street2Raises"] == 1
        
        # Street 3 (RIVER): 0 (only checks)
        assert stats.hands["street3Raises"] == 0
        
        # Street 4: Should be 0 (no street4 in holdem)
        assert stats.hands["street4Raises"] == 0
    
    def test_no_betting_streets(self, stats):
        """Test when there's no betting on any street"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "calls", Decimal("1.00")),
                ("Player4", "calls", Decimal("1.00")),
                ("Player1", "calls", Decimal("0.50")),
                ("Player2", "checks"),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player2", "checks"),
                ("Player3", "checks"),
                ("Player4", "checks"),
            ],
            "TURN": [
                ("Player1", "checks"),
                ("Player2", "checks"),
                ("Player3", "checks"),
                ("Player4", "checks"),
            ],
            "RIVER": [
                ("Player1", "checks"),
                ("Player2", "checks"),
                ("Player3", "checks"),
                ("Player4", "checks"),
            ],
        }
        
        stats.streetXRaises(hand)
        
        # All streets should have 0 raises
        assert stats.hands["street0Raises"] == 0
        assert stats.hands["street1Raises"] == 0
        assert stats.hands["street2Raises"] == 0
        assert stats.hands["street3Raises"] == 0
        assert stats.hands["street4Raises"] == 0
    
    def test_completes_counted(self, stats):
        """Test that completes are counted as raises"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "calls", Decimal("1.00")),
                ("Player4", "calls", Decimal("1.00")),
                ("Player1", "completes", Decimal("0.50")),  # Complete from SB
                ("Player2", "checks"),
            ],
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }
        
        stats.streetXRaises(hand)
        
        # Preflop should have 1 "raise" (the complete)
        assert stats.hands["street0Raises"] == 1
    
    def test_multiple_bets_same_street(self, stats):
        """Test multiple bets on the same street"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [],
            "PREFLOP": [
                ("Player1", "bets", Decimal("1.00")),
                ("Player2", "raises", Decimal("3.00")),
                ("Player3", "raises", Decimal("9.00")),
                ("Player4", "raises", Decimal("27.00")),
                ("Player1", "calls", Decimal("26.00")),
            ],
            "FLOP": [
                ("Player1", "bets", Decimal("30.00")),
                ("Player4", "raises", Decimal("90.00")),
                ("Player1", "raises", Decimal("270.00")),
                ("Player4", "calls", Decimal("180.00")),
            ],
            "TURN": [],
            "RIVER": [],
        }
        
        stats.streetXRaises(hand)
        
        # Preflop: 1 bet + 3 raises = 4
        assert stats.hands["street0Raises"] == 4
        
        # Flop: 1 bet + 2 raises = 3
        assert stats.hands["street1Raises"] == 3
    
    def test_empty_streets(self, stats):
        """Test handling of empty action streets"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal("3.00")),
                ("Player2", "folds"),
                ("Player3", "folds"),
                ("Player4", "folds"),
            ],
            "FLOP": [],  # Empty
            "TURN": [],  # Empty
            "RIVER": [],  # Empty
        }
        
        stats.streetXRaises(hand)
        
        # Only preflop should have a raise
        assert stats.hands["street0Raises"] == 1
        assert stats.hands["street1Raises"] == 0
        assert stats.hands["street2Raises"] == 0
        assert stats.hands["street3Raises"] == 0
    
    def test_all_in_not_counted(self, stats):
        """Test that all-in actions are not counted as raises"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal("3.00")),
                ("Player2", "allin", Decimal("50.00")),  # All-in should not count
                ("Player3", "folds"),
                ("Player1", "calls", Decimal("47.00")),
            ],
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }
        
        stats.streetXRaises(hand)
        
        # Only the initial raise should count, not the all-in
        assert stats.hands["street0Raises"] == 1
    
    def test_stud_streets(self, stats):
        """Test with different street names (like in Stud games)"""
        hand = MockHand()
        hand.actionStreets = ["ANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.actions = {
            "ANTES": [],
            "THIRD": [
                ("Player1", "bets", Decimal("2.00")),
                ("Player2", "raises", Decimal("4.00")),
                ("Player3", "calls", Decimal("4.00")),
            ],
            "FOURTH": [
                ("Player1", "bets", Decimal("4.00")),
                ("Player2", "calls", Decimal("4.00")),
            ],
            "FIFTH": [
                ("Player1", "bets", Decimal("8.00")),
                ("Player2", "raises", Decimal("16.00")),
                ("Player1", "raises", Decimal("24.00")),
                ("Player2", "calls", Decimal("8.00")),
            ],
            "SIXTH": [],
            "SEVENTH": [],
        }
        
        stats.streetXRaises(hand)
        
        # Street 0 (THIRD): 1 bet + 1 raise = 2
        assert stats.hands["street0Raises"] == 2
        
        # Street 1 (FOURTH): 1 bet
        assert stats.hands["street1Raises"] == 1
        
        # Street 2 (FIFTH): 1 bet + 2 raises = 3
        assert stats.hands["street2Raises"] == 3
        
        # Street 3 (SIXTH): 0
        assert stats.hands["street3Raises"] == 0
        
        # Street 4 (SEVENTH): 0
        assert stats.hands["street4Raises"] == 0


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestStreetRaises()
        stats = test_instance.stats()
        
        test_methods = [method for method in dir(test_instance) if method.startswith("test_")]
        
        for method_name in test_methods:
            try:
                print(f"\nRunning {method_name}...")
                # Create fresh stats instance for each test
                fresh_stats = test_instance.stats()
                method = getattr(test_instance, method_name)
                method(fresh_stats)
                print(f"✓ {method_name} passed")
            except AssertionError as e:
                print(f"✗ {method_name} failed: {e}")
            except Exception as e:
                print(f"✗ {method_name} error: {e}")
        
        print("\nBasic tests completed!")