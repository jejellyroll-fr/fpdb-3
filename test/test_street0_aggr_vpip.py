#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for street0Aggr and street0VPI calculations in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats


class MockHand:
    """Mock Hand object for testing"""
    
    def __init__(self, actions_preflop=None):
        self.handid = "12345"
        self.tablename = "Test Table"
        self.startTime = "2024-01-01 12:00:00"
        self.tourneyId = None
        self.hero = "Hero"
        self.gametype = {
            "category": "holdem",
            "type": "ring",
            "base": "hold",
            "currency": "USD",
            "sb": "0.50",
            "bb": "1.00",
        }
        self.players = [
            (1, "Hero", Decimal("100.00"), None, None),
            (2, "Villain1", Decimal("100.00"), None, None),
            (3, "Villain2", Decimal("100.00"), None, None),
            (4, "Villain3", Decimal("100.00"), None, None),
        ]
        self.board = {
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }
        self.communityStreets = ["FLOP", "TURN", "RIVER"]
        self.allStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.holeStreets = ["PREFLOP"]
        self.ACTION = {
            "small blind": 1,
            "big blind": 2,
            "raises": 3,
            "calls": 4,
            "bets": 5,
            "completes": 6,
            "folds": 7,
        }
        
        # Default actions - can be overridden
        self.actions = {
            "BLINDSANTES": [
                ("Villain1", "small blind", Decimal("0.50")),
                ("Villain2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": actions_preflop or [],
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }
        
        self.pot = MockPot()
        self.collectees = {}
        self.rake = Decimal("0.00")
        self.totalpot = Decimal("24.50")
        self.shown = []
        self.sitout = []
        self.endBounty = {}
        self.runItTimes = 1
        self.net_collected = {}
        self.dbid_hands = 1
        self.dbid_pids = {"Hero": 1, "Villain1": 2, "Villain2": 3, "Villain3": 4}
        self.in_path = "test_hand.txt"
        self.publicDB = False
        self.cashedOut = False
        
    def getStreetTotals(self):
        return [Decimal("0"), Decimal("24.50"), Decimal("24.50"), 
                Decimal("24.50"), Decimal("24.50"), Decimal("24.50")]
    
    def join_holecards(self, player, asList=False):
        if asList:
            return ["As", "Kh"]
        return "AsKh"


class MockPot:
    """Mock Pot object for testing"""
    
    def __init__(self):
        self.committed = {
            "Hero": Decimal("12.00"),
            "Villain1": Decimal("3.00"),
            "Villain2": Decimal("12.00"),
            "Villain3": Decimal("0.00"),
        }
        self.common = {}
        self.returned = {}
        self.pots = [(Decimal("24.50"), ["Hero", "Villain1", "Villain2"])]
        self.stp = Decimal("0.00")
        self.contenders = ["Hero", "Villain1", "Villain2"]


class TestStreet0AggrVPIP:
    """Test cases for street0Aggr and street0VPI calculations"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with mocked methods"""
        stats = DerivedStats()
        
        # Mock methods that are not relevant for our tests
        def mock_countPlayers(self, hand):
            return len(hand.players)
        
        def mock_playersAtStreetX(self, hand):
            self.hands["playersAtStreet1"] = 0
            self.hands["playersAtStreet2"] = 0
            self.hands["playersAtStreet3"] = 0
            self.hands["playersAtStreet4"] = 0
            self.hands["playersAtShowdown"] = 0
        
        def mock_streetXRaises(self, hand):
            self.hands["street0Raises"] = 0
            self.hands["street1Raises"] = 0
            self.hands["street2Raises"] = 0
            self.hands["street3Raises"] = 0
            self.hands["street4Raises"] = 0
        
        def mock_pfba(self, actions, f=None, limit_actions=None):
            return set()
        
        def mock_empty(self, hand):
            pass
        
        stats.countPlayers = mock_countPlayers.__get__(stats, DerivedStats)
        stats.playersAtStreetX = mock_playersAtStreetX.__get__(stats, DerivedStats)
        stats.streetXRaises = mock_streetXRaises.__get__(stats, DerivedStats)
        stats.pfba = mock_pfba.__get__(stats, DerivedStats)
        stats.calcCBets = mock_empty.__get__(stats, DerivedStats)
        stats.calcCheckCallRaise = mock_empty.__get__(stats, DerivedStats)
        stats.calc34BetStreet0 = mock_empty.__get__(stats, DerivedStats)
        stats.calcSteals = mock_empty.__get__(stats, DerivedStats)
        stats.calcCalledRaiseStreet0 = mock_empty.__get__(stats, DerivedStats)
        stats.calcEffectiveStack = mock_empty.__get__(stats, DerivedStats)
        stats.setPositions = mock_empty.__get__(stats, DerivedStats)
        
        return stats
    
    def test_vpip_basic_raise_call(self, stats):
        """Test VPIP is set correctly for basic raise/call scenario"""
        actions = [
            ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
            ("Villain1", "calls", Decimal("2.50")),
            ("Villain2", "folds"),
            ("Villain3", "folds"),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        assert stats.handsplayers["Hero"]["street0VPI"] == True
        assert stats.handsplayers["Villain1"]["street0VPI"] == True
        assert stats.handsplayers["Villain2"]["street0VPI"] == False
        assert stats.handsplayers["Villain3"]["street0VPI"] == False
        assert stats.hands["playersVpi"] == 2
    
    def test_street0_aggr_raise(self, stats):
        """Test street0Aggr is set for players who raise"""
        actions = [
            ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
            ("Villain1", "calls", Decimal("2.50")),
            ("Villain2", "raises", Decimal("9.00"), Decimal("12.00"), Decimal("3.00")),
            ("Hero", "calls", Decimal("9.00")),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        # Hero raised first, so should have street0Aggr
        assert stats.handsplayers["Hero"]["street0Aggr"] == True
        assert stats.handsplayers["Hero"]["street0Raises"] == 1
        
        # Villain1 only called, should NOT have street0Aggr
        assert stats.handsplayers["Villain1"]["street0Aggr"] == False
        assert stats.handsplayers["Villain1"]["street0Calls"] == 1
        assert stats.handsplayers["Villain1"]["street0Raises"] == 0
        
        # Villain2 3-bet, should have street0Aggr
        assert stats.handsplayers["Villain2"]["street0Aggr"] == True
        assert stats.handsplayers["Villain2"]["street0Raises"] == 1
    
    def test_street0_aggr_bet(self, stats):
        """Test street0Aggr is set for players who bet"""
        actions = [
            ("Hero", "bets", Decimal("3.00")),
            ("Villain1", "calls", Decimal("3.00")),
            ("Villain2", "folds"),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        assert stats.handsplayers["Hero"]["street0Aggr"] == True
        assert stats.handsplayers["Villain1"]["street0Aggr"] == False
    
    def test_street0_aggr_complete(self, stats):
        """Test street0Aggr is set for players who complete"""
        actions = [
            ("Hero", "completes", Decimal("1.00")),
            ("Villain1", "calls", Decimal("0.50")),
            ("Villain2", "folds"),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        assert stats.handsplayers["Hero"]["street0Aggr"] == True
        assert stats.handsplayers["Villain1"]["street0Aggr"] == False
    
    def test_street0_aggr_allin(self, stats):
        """Test street0Aggr is set for players who go all-in"""
        actions = [
            ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
            ("Villain1", "allin", Decimal("100.00"), None, None, True),
            ("Hero", "calls", Decimal("97.00")),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        assert stats.handsplayers["Hero"]["street0Aggr"] == True
        assert stats.handsplayers["Villain1"]["street0Aggr"] == True
        assert stats.handsplayers["Villain1"]["street0AllIn"] == True
    
    def test_vpip_limp_scenario(self, stats):
        """Test VPIP in a limp pot scenario"""
        actions = [
            ("Hero", "calls", Decimal("1.00")),
            ("Villain1", "calls", Decimal("1.00")),
            ("Villain2", "calls", Decimal("0.50")),
            ("Villain3", "checks"),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        # All players who called should have VPIP
        assert stats.handsplayers["Hero"]["street0VPI"] == True
        assert stats.handsplayers["Villain1"]["street0VPI"] == True
        assert stats.handsplayers["Villain2"]["street0VPI"] == True
        
        # BB who checked should NOT have VPIP
        assert stats.handsplayers["Villain3"]["street0VPI"] == False
        
        # No one should have street0Aggr in a limp pot
        assert stats.handsplayers["Hero"]["street0Aggr"] == False
        assert stats.handsplayers["Villain1"]["street0Aggr"] == False
        assert stats.handsplayers["Villain2"]["street0Aggr"] == False
        assert stats.handsplayers["Villain3"]["street0Aggr"] == False
    
    def test_multiple_raises(self, stats):
        """Test counting multiple raises from same player"""
        actions = [
            ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
            ("Villain1", "raises", Decimal("9.00"), Decimal("12.00"), Decimal("3.00")),
            ("Hero", "raises", Decimal("27.00"), Decimal("36.00"), Decimal("12.00")),
            ("Villain1", "calls", Decimal("24.00")),
        ]
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        # Hero raised twice
        assert stats.handsplayers["Hero"]["street0Raises"] == 2
        assert stats.handsplayers["Hero"]["street0Aggr"] == True
        
        # Villain1 raised once then called
        assert stats.handsplayers["Villain1"]["street0Raises"] == 1
        assert stats.handsplayers["Villain1"]["street0Calls"] == 1
        assert stats.handsplayers["Villain1"]["street0Aggr"] == True
    
    def test_no_preflop_action(self, stats):
        """Test when there's no preflop action (walk scenario)"""
        actions = []
        hand = MockHand(actions_preflop=actions)
        
        stats.getStats(hand)
        
        # No one should have VPIP or street0Aggr
        for player_name in ["Hero", "Villain1", "Villain2", "Villain3"]:
            assert stats.handsplayers[player_name]["street0VPI"] == False
            assert stats.handsplayers[player_name]["street0Aggr"] == False
            assert stats.handsplayers[player_name]["street0Calls"] == 0
            assert stats.handsplayers[player_name]["street0Raises"] == 0
    
    def test_sitout_player(self, stats):
        """Test that sitting out players don't get VPIP chance"""
        actions = [
            ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
            ("Villain1", "calls", Decimal("2.50")),
        ]
        hand = MockHand(actions_preflop=actions)
        hand.sitout = ["Villain3"]  # Villain3 is sitting out
        
        stats.getStats(hand)
        
        # Sitting out player should have VPIChance = False
        assert stats.handsplayers["Villain3"]["street0VPIChance"] == False
        assert stats.handsplayers["Villain3"]["street0AggrChance"] == False


if __name__ == "__main__":
    # Run tests with pytest if available, otherwise run basic tests
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner without pytest
        test_instance = TestStreet0AggrVPIP()
        stats = test_instance.stats()
        
        # Run each test method
        test_methods = [method for method in dir(test_instance) if method.startswith("test_")]
        
        for method_name in test_methods:
            try:
                print(f"\nRunning {method_name}...")
                method = getattr(test_instance, method_name)
                method(stats())
                print(f"✓ {method_name} passed")
            except AssertionError as e:
                print(f"✗ {method_name} failed: {e}")
            except Exception as e:
                print(f"✗ {method_name} error: {e}")
        
        print("\nBasic tests completed!")