#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for calc34BetStreet0 method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing calc34BetStreet0"""
    
    def __init__(self):
        self.handid = "12345"
        self.gametype = {"base": "hold"}
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("SB", "small blind", Decimal("0.50"), False),
                ("BB", "big blind", Decimal("1.00"), False),
            ],
            "PREFLOP": [],  # Will be set in each test
        }


class TestCalc34BetStreet0:
    """Test cases for calc34BetStreet0 method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with initialized players"""
        stats = DerivedStats()
        return stats
    
    def init_players(self, stats, players):
        """Initialize handsplayers for given players"""
        for player in players:
            stats.handsplayers[player] = _INIT_STATS.copy()
            stats.handsplayers[player]["sitout"] = False
    
    def test_simple_3bet(self, stats):
        """Test simple 3-bet scenario"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "folds", False),
            ("CO", "raises", Decimal("9.00"), False),
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "folds", False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # UTG opened, should have 2B done
        assert stats.handsplayers["UTG"]["street0_2BChance"] == True
        assert stats.handsplayers["UTG"]["street0_2BDone"] == True
        
        # UTG should have fold to 3B chance
        assert stats.handsplayers["UTG"]["street0_FoldTo3BChance"] == True
        assert stats.handsplayers["UTG"]["street0_FoldTo3BDone"] == True
        
        # CO 3-bet
        assert stats.handsplayers["CO"]["street0_3BChance"] == True
        assert stats.handsplayers["CO"]["street0_3BDone"] == True
        assert stats.handsplayers["CO"]["street0_SqueezeChance"] == False
        assert stats.handsplayers["CO"]["street0_SqueezeDone"] == False
    
    def test_4bet_scenario(self, stats):
        """Test 4-bet scenario"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "folds", False),
            ("CO", "raises", Decimal("9.00"), False),
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "raises", Decimal("27.00"), False),
            ("CO", "calls", Decimal("18.00"), False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # UTG 4-bet
        assert stats.handsplayers["UTG"]["street0_4BChance"] == True
        assert stats.handsplayers["UTG"]["street0_4BDone"] == True
        
        # CO should have fold to 4B chance
        assert stats.handsplayers["CO"]["street0_FoldTo4BChance"] == True
        assert stats.handsplayers["CO"]["street0_FoldTo4BDone"] == False  # Called instead
    
    def test_squeeze_opportunity(self, stats):
        """Test squeeze opportunity"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "calls", Decimal("3.00"), False),
            ("CO", "calls", Decimal("3.00"), False),
            ("BTN", "raises", Decimal("15.00"), False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "folds", False),
            ("MP", "folds", False),
            ("CO", "folds", False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # BTN should have squeeze opportunity
        assert stats.handsplayers["BTN"]["street0_3BChance"] == True
        assert stats.handsplayers["BTN"]["street0_3BDone"] == True
        assert stats.handsplayers["BTN"]["street0_SqueezeChance"] == True
        assert stats.handsplayers["BTN"]["street0_SqueezeDone"] == True
    
    def test_cold_4bet(self, stats):
        """Test cold 4-bet (C4B)"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "raises", Decimal("9.00"), False),
            ("CO", "raises", Decimal("27.00"), False),  # Cold 4-bet
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "folds", False),
            ("MP", "folds", False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # CO should have cold 4-bet opportunity
        assert stats.handsplayers["CO"]["street0_C4BChance"] == True
        assert stats.handsplayers["CO"]["street0_C4BDone"] == True
    
    def test_all_in_stops_action(self, stats):
        """Test that all-in stops further action tracking"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "raises", Decimal("9.00"), True),  # All-in 3-bet
            ("CO", "calls", Decimal("9.00"), False),
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "calls", Decimal("6.00"), False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # MP 3-bet all-in
        assert stats.handsplayers["MP"]["street0_3BChance"] == True
        assert stats.handsplayers["MP"]["street0_3BDone"] == True
        
        # CO technically has 4B chance even after all-in (could re-raise all-in)
        assert stats.handsplayers["CO"]["street0_C4BChance"] == True
        # But CO just called, so no 4B done
        assert stats.handsplayers["CO"]["street0_C4BDone"] == False
    
    def test_stud_betting_levels(self, stats):
        """Test betting levels in stud games"""
        hand = MockHand()
        hand.gametype = {"base": "stud"}
        hand.actionStreets = ["ANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        hand.actions = {
            "ANTES": [
                ("Player1", "ante", Decimal("0.10"), False),
                ("Player2", "ante", Decimal("0.10"), False),
                ("Player3", "ante", Decimal("0.10"), False),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.25"), False),
                ("Player2", "completes", Decimal("1.00"), False),
                ("Player3", "raises", Decimal("2.00"), False),
                ("Player1", "folds", False),
                ("Player2", "raises", Decimal("3.00"), False),
                ("Player3", "calls", Decimal("1.00"), False),
            ],
        }
        
        players = ["Player1", "Player2", "Player3"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # In stud, bet_level starts at 0
        # Player2 completes (bet_level goes from 0 to 1, no 2B stats)
        assert stats.handsplayers["Player2"]["street0_2BChance"] == False
        assert stats.handsplayers["Player2"]["street0_2BDone"] == False
        
        # Player3 raises (bet_level 1, so gets 2B stats)
        assert stats.handsplayers["Player3"]["street0_2BChance"] == True
        assert stats.handsplayers["Player3"]["street0_2BDone"] == True
        
        # Player2 re-raises (bet_level 2, so gets 3B stats)
        assert stats.handsplayers["Player2"]["street0_3BChance"] == True
        assert stats.handsplayers["Player2"]["street0_3BDone"] == True
    
    def test_heads_up_aggression_chance(self, stats):
        """Test aggression chance in heads-up"""
        hand = MockHand()
        hand.actions["BLINDSANTES"] = [
            ("SB", "small blind", Decimal("0.50"), False),
            ("BB", "big blind", Decimal("1.00"), False),
        ]
        hand.actions["PREFLOP"] = [
            ("SB", "raises", Decimal("2.00"), False),
            ("BB", "raises", Decimal("6.00"), False),
            ("SB", "folds", False),
        ]
        
        players = ["SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # In HU, both players have aggression chance
        assert stats.handsplayers["SB"]["street0AggrChance"] == True
        
        # SB opens
        assert stats.handsplayers["SB"]["street0_2BChance"] == True
        assert stats.handsplayers["SB"]["street0_2BDone"] == True
        
        # BB 3-bets
        assert stats.handsplayers["BB"]["street0_3BChance"] == True
        assert stats.handsplayers["BB"]["street0_3BDone"] == True
    
    def test_sitting_out_player(self, stats):
        """Test that sitting out players are handled correctly"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "raises", Decimal("3.00"), False),
            ("MP", "raises", Decimal("9.00"), False),  # MP is sitting out
            ("CO", "folds", False),
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
            ("UTG", "folds", False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        stats.handsplayers["MP"]["sitout"] = True
        
        stats.calc34BetStreet0(hand)
        
        # Sitting out players don't get betting chances
        assert stats.handsplayers["MP"]["street0_3BChance"] == False
        assert stats.handsplayers["MP"]["street0_3BDone"] == False
    
    def test_fold_to_2bet(self, stats):
        """Test fold to 2-bet (initial raise)"""
        hand = MockHand()
        hand.actions["PREFLOP"] = [
            ("UTG", "folds", False),
            ("MP", "folds", False),
            ("CO", "raises", Decimal("3.00"), False),
            ("BTN", "folds", False),
            ("SB", "folds", False),
            ("BB", "folds", False),
        ]
        
        players = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
        self.init_players(stats, players)
        
        stats.calc34BetStreet0(hand)
        
        # Only CO raised, no one had fold to 2B chance
        assert stats.handsplayers["CO"]["street0_2BDone"] == True
        
        # No fold to 2B chances in this scenario
        for player in ["UTG", "MP", "BTN", "SB", "BB"]:
            assert stats.handsplayers[player]["street0_FoldTo2BChance"] == False


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestCalc34BetStreet0()
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