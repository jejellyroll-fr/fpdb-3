#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for calcCalledRaiseStreet0 method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing calcCalledRaiseStreet0"""
    
    def __init__(self):
        self.handid = "12345"
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("SB", "small blind", Decimal("0.50")),
                ("BB", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [],  # Will be set in each test
        }


class TestCalcCalledRaiseStreet0:
    """Test cases for calcCalledRaiseStreet0 method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with initialized players"""
        stats = DerivedStats()
        return stats
    
    def init_players(self, stats, players):
        """Initialize handsplayers for given players"""
        for player in players:
            stats.handsplayers[player] = _INIT_STATS.copy()
    
    def test_simple_call_of_raise(self, stats):
        """Test simple scenario where player calls a raise"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00")),
            ("MP", "calls", Decimal("3.00")),
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # UTG raised first, no chance to call raise
        assert stats.handsplayers["UTG"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["UTG"]["street0CalledRaiseDone"] == 0
        
        # MP called the raise
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["MP"]["street0CalledRaiseDone"] == 1
        
        # Others folded after MP called - no chance to call raise
        # (fast_forward is True again after MP's call)
        assert stats.handsplayers["CO"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["CO"]["street0CalledRaiseDone"] == 0
        
        assert stats.handsplayers["BTN"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["BTN"]["street0CalledRaiseDone"] == 0
    
    def test_multiple_raises_and_calls(self, stats):
        """Test scenario with multiple raises and calls"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00")),
            ("MP", "calls", Decimal("3.00")),
            ("CO", "raises", Decimal("9.00")),
            ("BTN", "calls", Decimal("9.00")),
            ("SB", "folds"),
            ("BB", "raises", Decimal("27.00")),
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "calls", Decimal("18.00")),
            ("BTN", "folds"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # MP called first raise, then had another chance after BB's 3-bet
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 2
        assert stats.handsplayers["MP"]["street0CalledRaiseDone"] == 1
        
        # CO re-raised instead of calling UTG's raise, then called BB's 3-bet
        assert stats.handsplayers["CO"]["street0CalledRaiseChance"] == 1  # Only after BB's raise
        assert stats.handsplayers["CO"]["street0CalledRaiseDone"] == 1
        
        # BTN called CO's re-raise
        assert stats.handsplayers["BTN"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["BTN"]["street0CalledRaiseDone"] == 1
        
        # UTG had chance to call BB's 3-bet but folded
        assert stats.handsplayers["UTG"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["UTG"]["street0CalledRaiseDone"] == 0
    
    def test_complete_counts_as_raise(self, stats):
        """Test that complete action counts as a raise"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "calls", Decimal("1.00")),
            ("MP", "calls", Decimal("1.00")),
            ("CO", "completes", Decimal("2.00")),
            ("BTN", "calls", Decimal("2.00")),
            ("SB", "folds"),
            ("BB", "folds"),
            ("UTG", "calls", Decimal("1.00")),
            ("MP", "folds"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # BTN called the complete
        assert stats.handsplayers["BTN"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["BTN"]["street0CalledRaiseDone"] == 1
        
        # After BTN called, fast_forward is True again
        # UTG and MP don't get CalledRaiseChance
        assert stats.handsplayers["UTG"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["UTG"]["street0CalledRaiseDone"] == 0
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 0
    
    def test_no_raises_no_chances(self, stats):
        """Test that no raises means no call raise chances"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "calls", Decimal("1.00")),
            ("MP", "calls", Decimal("1.00")),
            ("CO", "calls", Decimal("1.00")),
            ("BTN", "folds"),
            ("SB", "calls", Decimal("0.50")),
            ("BB", "checks"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # No raises, so no one has call raise chances
        for player in players:
            assert stats.handsplayers[player]["street0CalledRaiseChance"] == 0
            assert stats.handsplayers[player]["street0CalledRaiseDone"] == 0
    
    def test_all_fold_to_raise(self, stats):
        """Test when everyone folds to a raise"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00")),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # Everyone had chance but no one called
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["MP"]["street0CalledRaiseDone"] == 0
        
        assert stats.handsplayers["CO"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["CO"]["street0CalledRaiseDone"] == 0
        
        assert stats.handsplayers["BB"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["BB"]["street0CalledRaiseDone"] == 0
    
    def test_reraise_resets_tracking(self, stats):
        """Test that re-raise resets the tracking"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00")),
            ("MP", "raises", Decimal("9.00")),  # Re-raise, resets tracking
            ("CO", "calls", Decimal("9.00")),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
            ("UTG", "folds"),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # MP re-raised instead of calling
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["MP"]["street0CalledRaiseDone"] == 0
        
        # CO called MP's raise
        assert stats.handsplayers["CO"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["CO"]["street0CalledRaiseDone"] == 1
        
        # After CO called, fast_forward is True again
        # UTG doesn't get CalledRaiseChance
        assert stats.handsplayers["UTG"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["UTG"]["street0CalledRaiseDone"] == 0
    
    def test_heads_up_scenario(self, stats):
        """Test heads-up scenario"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("SB", "raises", Decimal("3.00")),
            ("BB", "calls", Decimal("2.00")),
        ]
        
        players = ["SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # SB raised, no chance
        assert stats.handsplayers["SB"]["street0CalledRaiseChance"] == 0
        assert stats.handsplayers["SB"]["street0CalledRaiseDone"] == 0
        
        # BB called the raise
        assert stats.handsplayers["BB"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["BB"]["street0CalledRaiseDone"] == 1
    
    def test_limp_reraise_scenario(self, stats):
        """Test limp-reraise scenario"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "calls", Decimal("1.00")),
            ("MP", "raises", Decimal("4.00")),
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
            ("UTG", "raises", Decimal("12.00")),  # Limp-reraise
            ("MP", "calls", Decimal("8.00")),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calcCalledRaiseStreet0(hand)
        
        # UTG had chance to call MP's raise but re-raised
        assert stats.handsplayers["UTG"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["UTG"]["street0CalledRaiseDone"] == 0
        
        # MP called UTG's re-raise
        assert stats.handsplayers["MP"]["street0CalledRaiseChance"] == 1
        assert stats.handsplayers["MP"]["street0CalledRaiseDone"] == 1


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestCalcCalledRaiseStreet0()
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