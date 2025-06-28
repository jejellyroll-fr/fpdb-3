#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for setPositions method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing setPositions"""
    
    def __init__(self):
        self.handid = "12345"
        self.gametype = {"base": "hold"}
        self.holeStreets = ["PREFLOP"]
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "calls", Decimal("1.00")),
                ("Player4", "raises", Decimal("3.00")),
                ("Player5", "calls", Decimal("3.00")),
                ("Player6", "folds"),
                ("Player1", "folds"),
                ("Player2", "calls", Decimal("2.00")),
                ("Player3", "calls", Decimal("2.00")),
            ],
        }
        self.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
            (4, "Player4", Decimal("100.00"), None, None),
            (5, "Player5", Decimal("100.00"), None, None),
            (6, "Player6", Decimal("100.00"), None, None),
        ]


class TestSetPositions:
    """Test cases for setPositions method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with mocked pfbao"""
        stats = DerivedStats()
        
        def mock_pfbao(actions):
            """Mock method to get players by action order"""
            players = []
            for action in actions:
                if action[0] not in players:
                    players.append(action[0])
            return players
        
        stats.pfbao = mock_pfbao
        return stats
    
    def test_basic_6max_positions(self, stats):
        """Test basic position assignment in 6-max game"""
        hand = MockHand()
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # Check blind positions
        assert stats.handsplayers["Player1"]["position"] == "S"  # Small blind
        assert stats.handsplayers["Player2"]["position"] == "B"  # Big blind
        
        # Check other positions (0 = button, increasing counter-clockwise)
        assert stats.handsplayers["Player6"]["position"] == 0  # Button
        assert stats.handsplayers["Player5"]["position"] == 1  # Cutoff
        assert stats.handsplayers["Player4"]["position"] == 2  # Hijack
        assert stats.handsplayers["Player3"]["position"] == 3  # UTG
        
        # Check maxPosition
        assert stats.hands["maxPosition"] == 3
        
        # Check street0FirstToAct and street0InPosition
        assert stats.handsplayers["Player1"]["street0FirstToAct"] == True  # SB acts first
        assert stats.handsplayers["Player2"]["street0InPosition"] == True  # BB is in position preflop
    
    def test_heads_up_positions(self, stats):
        """Test position assignment in heads-up"""
        hand = MockHand()
        hand.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
        ]
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player1", "raises", Decimal("2.00")),
                ("Player2", "calls", Decimal("1.00")),
            ],
        }
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # In HU, both positions should be negative
        assert stats.handsplayers["Player1"]["position"] == "S"  # SB/Button
        assert stats.handsplayers["Player2"]["position"] == "B"  # BB
        
        # SB is first to act preflop in HU
        assert stats.handsplayers["Player1"]["street0FirstToAct"] == True
        assert stats.handsplayers["Player2"]["street0InPosition"] == True
    
    def test_stud_positions(self, stats):
        """Test position assignment in stud games"""
        hand = MockHand()
        hand.gametype = {"base": "stud"}
        hand.holeStreets = ["THIRD"]
        hand.actionStreets = ["ANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.actions = {
            "ANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.25")),  # Bring-in
                ("Player2", "completes", Decimal("1.00")),
                ("Player3", "calls", Decimal("1.00")),
                ("Player1", "calls", Decimal("0.75")),
            ],
        }
        hand.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
        ]
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # In stud, bring-in gets position "S"
        assert stats.handsplayers["Player1"]["position"] == "S"
        assert stats.handsplayers["Player1"]["street0FirstToAct"] == True
        
        # Last to act gets position 0 and is in position
        assert stats.handsplayers["Player3"]["position"] == 0
        assert stats.handsplayers["Player3"]["street0InPosition"] == True
        
        # Middle player
        assert stats.handsplayers["Player2"]["position"] == 1
    
    def test_button_blind_position(self, stats):
        """Test position with button blind (like in some tournament situations)"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "button blind", Decimal("1.00")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player2", "checks"),
                ("Player1", "checks"),
            ],
        }
        hand.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
        ]
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # Button blind should be in position
        assert stats.handsplayers["Player1"]["street0InPosition"] == True
        assert stats.handsplayers["Player2"]["position"] == "B"
    
    def test_straddle_position(self, stats):
        """Test position assignment with straddle"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
                ("Player3", "straddle", Decimal("2.00")),
            ],
            "PREFLOP": [
                ("Player4", "calls", Decimal("2.00")),
                ("Player5", "folds"),
                ("Player1", "folds"),
                ("Player2", "folds"),
                ("Player3", "checks"),
            ],
        }
        hand.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
            (4, "Player4", Decimal("100.00"), None, None),
            (5, "Player5", Decimal("100.00"), None, None),
        ]
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # Straddle affects position order by moving last player to beginning
        # But Player3 (straddle) keeps position 2 in this implementation
        assert stats.handsplayers["Player3"]["position"] == 2
        assert stats.handsplayers["Player5"]["position"] == 0  # Button (was last, moved to 0)
        assert stats.handsplayers["Player4"]["position"] == 1  # Next position
    
    def test_missing_small_blind(self, stats):
        """Test position assignment when small blind is missing"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "calls", Decimal("1.00")),
                ("Player4", "raises", Decimal("3.00")),
                ("Player2", "folds"),
                ("Player3", "calls", Decimal("2.00")),
            ],
        }
        hand.players = [
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
            (4, "Player4", Decimal("100.00"), None, None),
        ]
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # Big blind should still get position "B"
        assert stats.handsplayers["Player2"]["position"] == "B"
        assert stats.handsplayers["Player2"]["street0InPosition"] == True
        
        # Other positions
        assert stats.handsplayers["Player4"]["position"] == 0  # Button
        assert stats.handsplayers["Player3"]["position"] == 1  # Cutoff
    
    def test_all_fold_to_bb(self, stats):
        """Test when everyone folds to big blind"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "folds"),
                ("Player4", "folds"),
                ("Player1", "folds"),
            ],
        }
        
        # Initialize handsplayers and hands
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        stats.hands = {"maxPosition": -1}
        
        stats.setPositions(hand)
        
        # BB should still have correct position even if not in pfbao list
        assert stats.handsplayers["Player2"]["position"] == "B"
        assert stats.handsplayers["Player2"]["street0InPosition"] == True


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestSetPositions()
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