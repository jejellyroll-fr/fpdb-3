#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test script to verify street0Aggr is properly set for preflop aggressive actions"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from DerivedStats import DerivedStats
from decimal import Decimal

# Mock the missing methods
def countPlayers(self, hand):
    return len(hand.players)

def playersAtStreetX(self, hand):
    self.hands["playersAtStreet1"] = 0
    self.hands["playersAtStreet2"] = 0
    self.hands["playersAtStreet3"] = 0
    self.hands["playersAtStreet4"] = 0
    self.hands["playersAtShowdown"] = 0

def streetXRaises(self, hand):
    self.hands["street0Raises"] = 0
    self.hands["street1Raises"] = 0
    self.hands["street2Raises"] = 0
    self.hands["street3Raises"] = 0
    self.hands["street4Raises"] = 0

def pfba(self, actions, f=None, limit_actions=None):
    return set()

def calcCBets(self, hand):
    pass

def calcCheckCallRaise(self, hand):
    pass

def calc34BetStreet0(self, hand):
    pass

def calcSteals(self, hand):
    pass

def calcCalledRaiseStreet0(self, hand):
    pass

def calcEffectiveStack(self, hand):
    pass

def setPositions(self, hand):
    pass

# Add the methods to DerivedStats
DerivedStats.countPlayers = countPlayers
DerivedStats.playersAtStreetX = playersAtStreetX
DerivedStats.streetXRaises = streetXRaises
DerivedStats.pfba = pfba
DerivedStats.calcCBets = calcCBets
DerivedStats.calcCheckCallRaise = calcCheckCallRaise
DerivedStats.calc34BetStreet0 = calc34BetStreet0
DerivedStats.calcSteals = calcSteals
DerivedStats.calcCalledRaiseStreet0 = calcCalledRaiseStreet0
DerivedStats.calcEffectiveStack = calcEffectiveStack
DerivedStats.setPositions = setPositions

# Create a mock hand object with preflop actions
class MockHand:
    def __init__(self):
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
            "bb": "1.00"
        }
        self.players = [
            (1, "Hero", Decimal("100.00"), None, None),
            (2, "Villain1", Decimal("100.00"), None, None),
            (3, "Villain2", Decimal("100.00"), None, None)
        ]
        self.board = {
            "FLOP": [],
            "TURN": [],
            "RIVER": []
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
            "folds": 7
        }
        self.actions = {
            "BLINDSANTES": [
                ("Villain1", "small blind", Decimal("0.50")),
                ("Villain2", "big blind", Decimal("1.00"))
            ],
            "PREFLOP": [
                ("Hero", "raises", Decimal("3.00"), Decimal("3.00"), Decimal("0.00")),
                ("Villain1", "calls", Decimal("2.50")),
                ("Villain2", "raises", Decimal("9.00"), Decimal("12.00"), Decimal("3.00")),
                ("Hero", "calls", Decimal("9.00"))
            ],
            "FLOP": [],
            "TURN": [],
            "RIVER": []
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
        
    def getStreetTotals(self):
        return [Decimal("0"), Decimal("24.50"), Decimal("24.50"), 
                Decimal("24.50"), Decimal("24.50"), Decimal("24.50")]
    
    def join_holecards(self, player, asList=False):
        if asList:
            return ["As", "Kh"]
        return "AsKh"

class MockPot:
    def __init__(self):
        self.committed = {
            "Hero": Decimal("12.00"),
            "Villain1": Decimal("3.00"),
            "Villain2": Decimal("12.00")
        }
        self.common = {}
        self.returned = {}
        self.pots = [(Decimal("24.50"), ["Hero", "Villain1", "Villain2"])]
        self.stp = Decimal("0.00")
        self.contenders = ["Hero", "Villain1", "Villain2"]

def test_street0_aggr():
    """Test that street0Aggr is properly set for preflop aggressive actions"""
    
    # Create mock hand
    hand = MockHand()
    
    # Create DerivedStats instance
    stats = DerivedStats()
    
    # Add debug to check if vpip is called
    original_vpip = stats.vpip
    def debug_vpip(self, hand):
        print("\n[DEBUG] vpip function called!")
        result = original_vpip(hand)
        print(f"[DEBUG] vpip completed, playersVpi = {self.hands.get('playersVpi', 'NOT SET')}")
        return result
    
    stats.vpip = lambda h: debug_vpip(stats, h)
    
    # Process the hand
    stats.getStats(hand)
    
    # Check results
    print("Testing street0Aggr calculation...")
    print("-" * 50)
    
    handsplayers = stats.getHandsPlayers()
    
    for player_name, player_stats in handsplayers.items():
        print(f"\nPlayer: {player_name}")
        print(f"  street0VPI: {player_stats.get('street0VPI', False)}")
        print(f"  street0Aggr: {player_stats.get('street0Aggr', False)}")
        print(f"  street0AggrChance: {player_stats.get('street0AggrChance', True)}")
        print(f"  street0Calls: {player_stats.get('street0Calls', 0)}")
        print(f"  street0Raises: {player_stats.get('street0Raises', 0)}")
        
        # Verify expected results
        if player_name == "Hero":
            assert player_stats.get('street0VPI', False) == True, "Hero should have VPIP"
            assert player_stats.get('street0Aggr', False) == True, "Hero should have street0Aggr (raised preflop)"
            assert player_stats.get('street0Raises', 0) == 1, "Hero should have 1 raise"
            assert player_stats.get('street0Calls', 0) == 1, "Hero should have 1 call"
            print("  ✓ Hero stats correct")
            
        elif player_name == "Villain1":
            assert player_stats.get('street0VPI', False) == True, "Villain1 should have VPIP"
            assert player_stats.get('street0Aggr', False) == False, "Villain1 should NOT have street0Aggr (only called)"
            assert player_stats.get('street0Calls', 0) == 1, "Villain1 should have 1 call"
            assert player_stats.get('street0Raises', 0) == 0, "Villain1 should have 0 raises"
            print("  ✓ Villain1 stats correct")
            
        elif player_name == "Villain2":
            assert player_stats.get('street0VPI', False) == True, "Villain2 should have VPIP"
            assert player_stats.get('street0Aggr', False) == True, "Villain2 should have street0Aggr (3-bet preflop)"
            assert player_stats.get('street0Raises', 0) == 1, "Villain2 should have 1 raise"
            print("  ✓ Villain2 stats correct")
    
    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("street0Aggr is now correctly set for preflop aggressive actions.")

if __name__ == "__main__":
    test_street0_aggr()