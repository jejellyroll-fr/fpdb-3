#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for calcSteals method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing calcSteals"""
    
    def __init__(self):
        self.handid = "12345"
        self.gametype = {"base": "hold"}
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("SB", "small blind", Decimal("0.50")),
                ("BB", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [],  # Will be set in each test
        }


class TestCalcSteals:
    """Test cases for calcSteals method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with initialized players"""
        stats = DerivedStats()
        return stats
    
    def init_players(self, stats, positions):
        """Initialize handsplayers with given positions"""
        for player, pos in positions.items():
            stats.handsplayers[player] = _INIT_STATS.copy()
            stats.handsplayers[player]["position"] = pos
            stats.handsplayers[player]["sitout"] = False
    
    def test_button_steal_success(self, stats):
        """Test successful steal from button"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "raises", Decimal("3.00")),
            ("SB", "folds"),
            ("BB", "folds"),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # Button should have steal opportunity and success
        assert stats.handsplayers["BTN"]["raiseFirstInChance"] == True
        assert stats.handsplayers["BTN"]["stealChance"] == True
        assert stats.handsplayers["BTN"]["raisedFirstIn"] == True
        assert stats.handsplayers["BTN"]["stealDone"] == True
        assert stats.handsplayers["BTN"]["success_Steal"] == True
        
        # Blinds should have fold to steal chances
        assert stats.handsplayers["SB"]["foldSbToStealChance"] == True
        assert stats.handsplayers["SB"]["foldedSbToSteal"] == True
        assert stats.handsplayers["BB"]["foldBbToStealChance"] == True
        assert stats.handsplayers["BB"]["foldedBbToSteal"] == True
    
    def test_cutoff_steal_called_by_bb(self, stats):
        """Test steal attempt from cutoff called by big blind"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "raises", Decimal("3.00")),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "calls", Decimal("2.00")),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # Cutoff should have steal attempt but not success
        assert stats.handsplayers["CO"]["stealChance"] == True
        assert stats.handsplayers["CO"]["stealDone"] == True
        assert stats.handsplayers["CO"]["success_Steal"] == False
        
        # SB folded to steal
        assert stats.handsplayers["SB"]["foldSbToStealChance"] == True
        assert stats.handsplayers["SB"]["foldedSbToSteal"] == True
        
        # BB defended
        assert stats.handsplayers["BB"]["foldBbToStealChance"] == True
        assert stats.handsplayers["BB"]["foldedBbToSteal"] == False
    
    def test_sb_steal_in_full_ring(self, stats):
        """Test steal from small blind"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "raises", Decimal("3.00")),
            ("BB", "folds"),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # SB should have steal opportunity and success
        assert stats.handsplayers["SB"]["stealChance"] == True
        assert stats.handsplayers["SB"]["stealDone"] == True
        # SB's steal is successful because BB folded
        assert stats.handsplayers["SB"]["success_Steal"] == True
        
        # BB should have fold to steal
        assert stats.handsplayers["BB"]["foldBbToStealChance"] == True
        assert stats.handsplayers["BB"]["foldedBbToSteal"] == True
    
    def test_no_steal_opportunity_early_position(self, stats):
        """Test raise from early position is not a steal"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00")),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # UTG should have raise first in but not steal
        assert stats.handsplayers["UTG"]["raiseFirstInChance"] == True
        assert stats.handsplayers["UTG"]["raisedFirstIn"] == True
        assert stats.handsplayers["UTG"]["stealChance"] == False
        assert stats.handsplayers["UTG"]["stealDone"] == False
        
        # Blinds should not have fold to steal chances
        assert stats.handsplayers["SB"]["foldSbToStealChance"] == False
        assert stats.handsplayers["BB"]["foldBbToStealChance"] == False
    
    def test_limp_then_raise_not_steal(self, stats):
        """Test that raise after limp is not a steal"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "calls", Decimal("1.00")),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "raises", Decimal("4.00")),
            ("SB", "folds"),
            ("BB", "folds"),
            ("UTG", "folds"),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # Button raised but not first in, so no steal
        assert stats.handsplayers["BTN"]["raiseFirstInChance"] == False
        assert stats.handsplayers["BTN"]["stealChance"] == False
        assert stats.handsplayers["BTN"]["stealDone"] == False
        
        # UTG had raise first in chance but called
        assert stats.handsplayers["UTG"]["raiseFirstInChance"] == True
        assert stats.handsplayers["UTG"]["raisedFirstIn"] == False
    
    def test_bb_reraise_steal_attempt(self, stats):
        """Test BB re-raising a steal attempt"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "folds"),
            ("BTN", "raises", Decimal("3.00")),
            ("SB", "folds"),
            ("BB", "raises", Decimal("9.00")),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # Button attempted steal
        assert stats.handsplayers["BTN"]["stealDone"] == True
        assert stats.handsplayers["BTN"]["success_Steal"] == False
        
        # BB re-raised the steal
        assert stats.handsplayers["BB"]["foldBbToStealChance"] == True
        assert stats.handsplayers["BB"]["foldedBbToSteal"] == False
        assert stats.handsplayers["BB"]["raiseToStealChance"] == True
        assert stats.handsplayers["BB"]["raiseToStealDone"] == True
    
    def test_stud_steal_positions(self, stats):
        """Test steal positions in stud games"""
        hand = MockHand()
        hand.gametype = {"base": "stud"}
        hand.actionStreets = ["ANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.actions = {
            "ANTES": [],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.25")),
                ("Player2", "folds"),
                ("Player3", "folds"),
                ("Player4", "completes", Decimal("1.00")),
                ("Player5", "folds"),
                ("Player1", "folds"),
            ],
        }
        
        positions = {
            "Player1": "S",  # Bring-in
            "Player2": 3,
            "Player3": 2,
            "Player4": 1,    # Steal position in stud
            "Player5": 0,
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # Player4 (position 1) should have steal opportunity in stud
        assert stats.handsplayers["Player4"]["stealChance"] == True
        assert stats.handsplayers["Player4"]["stealDone"] == True
        assert stats.handsplayers["Player4"]["success_Steal"] == True
        
        # Bring-in folded to steal
        assert stats.handsplayers["Player1"]["foldSbToStealChance"] == True
        assert stats.handsplayers["Player1"]["foldedSbToSteal"] == True
    
    def test_button_blind_steal_positions(self, stats):
        """Test steal positions with button blind"""
        hand = MockHand()
        hand.actions["BLINDSANTES"] = [
            ("BTN", "button blind", Decimal("1.00")),
            ("BB", "big blind", Decimal("1.00")),
        ]
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "folds"),
            ("CO", "raises", Decimal("3.00")),
            ("BTN", "folds"),
            ("BB", "folds"),
        ]
        
        positions = {
            "UTG": 4,
            "MP": 3,
            "CO": 2,    # Different steal position with button blind
            "BTN": 1,
            "BB": "B",
        }
        self.init_players(stats, positions)
        
        stats.calcSteals(hand)
        
        # CO (position 2) should have steal opportunity with button blind
        assert stats.handsplayers["CO"]["stealChance"] == True
        assert stats.handsplayers["CO"]["stealDone"] == True
    
    def test_sitout_player_ignored(self, stats):
        """Test that sitting out players are ignored"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds"),
            ("MP", "raises", Decimal("3.00")),  # MP is sitting out
            ("CO", "folds"),
            ("BTN", "folds"),
            ("SB", "folds"),
            ("BB", "folds"),
        ]
        
        positions = {
            "UTG": 3,
            "MP": 2,
            "CO": 1,
            "BTN": 0,
            "SB": "S",
            "BB": "B",
        }
        self.init_players(stats, positions)
        stats.handsplayers["MP"]["sitout"] = True  # MP is sitting out
        
        stats.calcSteals(hand)
        
        # Sitting out player should not have any steal stats set
        assert stats.handsplayers["MP"]["raiseFirstInChance"] == False
        assert stats.handsplayers["MP"]["stealChance"] == False


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestCalcSteals()
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