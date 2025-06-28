#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for calcEffectiveStack method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing calcEffectiveStack"""
    
    def __init__(self):
        self.handid = "12345"
        self.players = [
            (1, "ShortStack", Decimal("20.00"), None, None),
            (2, "MidStack", Decimal("50.00"), None, None),
            (3, "BigStack", Decimal("100.00"), None, None),
            (4, "DeepStack", Decimal("200.00"), None, None),
        ]
        self.sitout = []  # No one sitting out by default
        self.holeStreets = ["PREFLOP"]
        self.actions = {
            "PREFLOP": [
                ("ShortStack", "calls", Decimal("1.00")),
                ("MidStack", "raises", Decimal("3.00")),
                ("BigStack", "calls", Decimal("3.00")),
                ("DeepStack", "raises", Decimal("10.00")),
                ("ShortStack", "folds"),
                ("MidStack", "calls", Decimal("7.00")),
                ("BigStack", "calls", Decimal("7.00")),
            ],
        }


class TestEffectiveStack:
    """Test cases for calcEffectiveStack method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with initialized players"""
        stats = DerivedStats()
        return stats
    
    def test_basic_effective_stack(self, stats):
        """Test basic effective stack calculation"""
        hand = MockHand()
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # ShortStack (20) faces opponents with 50, 100, 200
        # Effective stack = min(20, max(50, 100, 200)) = 20 (own stack)
        assert stats.handsplayers["ShortStack"]["effStack"] == 2000
        
        # MidStack (50) faces opponents with 20, 100, 200
        # Effective stack = min(50, max(20, 100, 200)) = 50 (own stack)
        assert stats.handsplayers["MidStack"]["effStack"] == 5000
        
        # BigStack (100) faces opponents with 20, 50, 200
        # Effective stack = min(100, max(20, 50, 200)) = 100 (own stack)
        assert stats.handsplayers["BigStack"]["effStack"] == 10000
        
        # DeepStack (200) faces opponents with 20, 50, 100
        # Effective stack = min(200, max(20, 50, 100)) = 100 (limited by biggest opponent)
        assert stats.handsplayers["DeepStack"]["effStack"] == 10000
    
    def test_heads_up_effective_stack(self, stats):
        """Test effective stack in heads-up scenario"""
        hand = MockHand()
        hand.players = [
            (1, "Player1", Decimal("75.00"), None, None),
            (2, "Player2", Decimal("125.00"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("Player1", "raises", Decimal("3.00")),
                ("Player2", "calls", Decimal("3.00")),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # Player1 (75) faces Player2 (125)
        # Effective stack = min(75, 125) = 75
        assert stats.handsplayers["Player1"]["effStack"] == 7500
        
        # Player2 (125) faces Player1 (75)
        # Effective stack = min(125, 75) = 75
        assert stats.handsplayers["Player2"]["effStack"] == 7500
    
    def test_folded_player_excluded(self, stats):
        """Test that folded players are excluded from future calculations"""
        hand = MockHand()
        hand.players = [
            (1, "Folder", Decimal("30.00"), None, None),
            (2, "Caller", Decimal("80.00"), None, None),
            (3, "Raiser", Decimal("120.00"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("Folder", "folds"),  # Folds immediately
                ("Caller", "calls", Decimal("1.00")),
                ("Raiser", "raises", Decimal("4.00")),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # Folder's stack is set to 0 after folding
        # Effective stack against Caller (80) and Raiser (120) = 30
        assert stats.handsplayers["Folder"]["effStack"] == 3000
        
        # Caller faces Folder (0 after fold) and Raiser (120)
        # Effective stack = min(80, max(0, 120)) = 80
        assert stats.handsplayers["Caller"]["effStack"] == 8000
        
        # Raiser faces Folder (0 after fold) and Caller (80)
        # Effective stack = min(120, max(0, 80)) = 80
        assert stats.handsplayers["Raiser"]["effStack"] == 8000
    
    def test_sitting_out_players_excluded(self, stats):
        """Test that sitting out players are excluded"""
        hand = MockHand()
        hand.sitout = ["SitoutPlayer"]
        hand.players = [
            (1, "ActivePlayer", Decimal("50.00"), None, None),
            (2, "SitoutPlayer", Decimal("100.00"), None, None),
            (3, "BigStack", Decimal("150.00"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("ActivePlayer", "raises", Decimal("3.00")),
                ("BigStack", "calls", Decimal("3.00")),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # ActivePlayer (50) faces only BigStack (150), SitoutPlayer excluded
        # Effective stack = min(50, 150) = 50
        assert stats.handsplayers["ActivePlayer"]["effStack"] == 5000
        
        # BigStack (150) faces only ActivePlayer (50)
        # Effective stack = min(150, 50) = 50
        assert stats.handsplayers["BigStack"]["effStack"] == 5000
        
        # SitoutPlayer should not have effStack calculated (remains 0)
        assert stats.handsplayers["SitoutPlayer"]["effStack"] == 0
    
    def test_all_equal_stacks(self, stats):
        """Test when all players have equal stacks"""
        hand = MockHand()
        hand.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
            (4, "Player4", Decimal("100.00"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("Player1", "raises", Decimal("3.00")),
                ("Player2", "calls", Decimal("3.00")),
                ("Player3", "calls", Decimal("3.00")),
                ("Player4", "calls", Decimal("3.00")),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # All players should have effective stack of 100
        assert stats.handsplayers["Player1"]["effStack"] == 10000
        assert stats.handsplayers["Player2"]["effStack"] == 10000
        assert stats.handsplayers["Player3"]["effStack"] == 10000
        assert stats.handsplayers["Player4"]["effStack"] == 10000
    
    def test_single_player_action(self, stats):
        """Test when only one player acts (others fold)"""
        hand = MockHand()
        hand.players = [
            (1, "Winner", Decimal("100.00"), None, None),
            (2, "Folder1", Decimal("50.00"), None, None),
            (3, "Folder2", Decimal("75.00"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("Winner", "raises", Decimal("3.00")),
                ("Folder1", "folds"),
                ("Folder2", "folds"),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # Winner faces Folder1 (50) and Folder2 (75)
        # Effective stack = min(100, max(50, 75)) = 75
        assert stats.handsplayers["Winner"]["effStack"] == 7500
        
        # Folders' effective stacks before folding
        assert stats.handsplayers["Folder1"]["effStack"] == 5000
        assert stats.handsplayers["Folder2"]["effStack"] == 7500
    
    def test_no_actions(self, stats):
        """Test when there are no preflop actions"""
        hand = MockHand()
        hand.actions = {
            "PREFLOP": [],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # All players should have default effStack of 0
        for player in hand.players:
            assert stats.handsplayers[player[1]]["effStack"] == 0
    
    def test_decimal_stacks(self, stats):
        """Test with decimal stack sizes"""
        hand = MockHand()
        hand.players = [
            (1, "Player1", Decimal("25.50"), None, None),
            (2, "Player2", Decimal("100.75"), None, None),
            (3, "Player3", Decimal("200.25"), None, None),
        ]
        hand.actions = {
            "PREFLOP": [
                ("Player1", "calls", Decimal("1.00")),
                ("Player2", "raises", Decimal("3.50")),
                ("Player3", "calls", Decimal("3.50")),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.calcEffectiveStack(hand)
        
        # Values should be converted to cents (multiplied by 100)
        assert stats.handsplayers["Player1"]["effStack"] == 2550  # 25.50 * 100
        assert stats.handsplayers["Player2"]["effStack"] == 10075  # 100.75 * 100
        assert stats.handsplayers["Player3"]["effStack"] == 10075  # Limited by Player2


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestEffectiveStack()
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