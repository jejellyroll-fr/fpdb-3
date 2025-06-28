#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test suite for playersAtStreetX method in DerivedStats"""

import pytest
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DerivedStats import DerivedStats, _INIT_STATS


class MockHand:
    """Mock Hand object for testing playersAtStreetX"""
    
    def __init__(self):
        self.handid = "12345"
        self.players = [
            (1, "Player1", Decimal("100.00"), None, None),
            (2, "Player2", Decimal("100.00"), None, None),
            (3, "Player3", Decimal("100.00"), None, None),
            (4, "Player4", Decimal("100.00"), None, None),
        ]
        self.gametype = {"category": "holdem", "base": "hold"}
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "raises", Decimal("3.00")),
                ("Player4", "calls", Decimal("3.00")),
                ("Player1", "calls", Decimal("2.50")),
                ("Player2", "calls", Decimal("2.00")),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player2", "bets", Decimal("6.00")),
                ("Player3", "calls", Decimal("6.00")),
                ("Player4", "folds"),
                ("Player1", "folds"),
            ],
            "TURN": [
                ("Player2", "checks"),
                ("Player3", "bets", Decimal("12.00")),
                ("Player2", "calls", Decimal("12.00")),
            ],
            "RIVER": [
                ("Player2", "checks"),
                ("Player3", "checks"),
            ],
        }
        self.pot = MockPot()


class MockPot:
    """Mock Pot object"""
    def __init__(self):
        self.pots = []  # Empty by default


class TestPlayersAtStreet:
    """Test cases for playersAtStreetX method"""
    
    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance with initialized players"""
        stats = DerivedStats()
        
        # Mock pfba and pfbao methods
        def mock_pfba(actions, limit_actions):
            """Mock method to find players who performed specific actions"""
            result = set()
            for action in actions:
                if action[1] in limit_actions:
                    result.add(action[0])
            return result
        
        def mock_pfbao(actions, f=None):
            """Mock method to find players who performed actions (ordered)"""
            result = []
            for action in actions:
                if f is None or action[1] not in f:
                    if action[0] not in result:
                        result.append(action[0])
            return result
        
        stats.pfba = mock_pfba
        stats.pfbao = mock_pfbao
        
        return stats
    
    def test_basic_players_at_street(self, stats):
        """Test basic counting of players at each street"""
        hand = MockHand()
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        # Initialize hands dict
        stats.hands = {}
        
        stats.playersAtStreetX(hand)
        
        # All 4 players saw the flop (street1)
        assert stats.hands["playersAtStreet1"] == 4
        assert stats.handsplayers["Player1"]["street1Seen"] == True
        assert stats.handsplayers["Player2"]["street1Seen"] == True
        assert stats.handsplayers["Player3"]["street1Seen"] == True
        assert stats.handsplayers["Player4"]["street1Seen"] == True
        
        # Only 2 players saw the turn (street2) - Player3 and Player2
        assert stats.hands["playersAtStreet2"] == 2
        assert stats.handsplayers["Player2"]["street2Seen"] == True
        assert stats.handsplayers["Player3"]["street2Seen"] == True
        assert stats.handsplayers["Player1"]["street2Seen"] == False
        assert stats.handsplayers["Player4"]["street2Seen"] == False
        
        # Same 2 players saw the river (street3)
        assert stats.hands["playersAtStreet3"] == 2
        assert stats.handsplayers["Player2"]["street3Seen"] == True
        assert stats.handsplayers["Player3"]["street3Seen"] == True
        
        # 2 players reached showdown
        assert stats.hands["playersAtShowdown"] == 2
        assert stats.handsplayers["Player2"]["sawShowdown"] == True
        assert stats.handsplayers["Player3"]["sawShowdown"] == True
        assert stats.handsplayers["Player1"]["sawShowdown"] == False
        assert stats.handsplayers["Player4"]["sawShowdown"] == False
    
    def test_all_fold_preflop(self, stats):
        """Test when all players fold to one player preflop"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "raises", Decimal("3.00")),
                ("Player4", "folds"),
                ("Player1", "folds"),
                ("Player2", "folds"),
            ],
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # No one saw the flop
        assert stats.hands["playersAtStreet1"] == 0
        assert stats.hands["playersAtStreet2"] == 0
        assert stats.hands["playersAtStreet3"] == 0
        assert stats.hands["playersAtStreet4"] == 0
        assert stats.hands["playersAtShowdown"] == 0
    
    def test_heads_up(self, stats):
        """Test heads-up scenario"""
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
            "FLOP": [
                ("Player2", "checks"),
                ("Player1", "bets", Decimal("3.00")),
                ("Player2", "calls", Decimal("3.00")),
            ],
            "TURN": [
                ("Player2", "checks"),
                ("Player1", "checks"),
            ],
            "RIVER": [
                ("Player2", "bets", Decimal("6.00")),
                ("Player1", "folds"),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # Both players saw all streets except showdown
        assert stats.hands["playersAtStreet1"] == 2
        assert stats.hands["playersAtStreet2"] == 2
        assert stats.hands["playersAtStreet3"] == 2
        
        # When only one player remains (Player1 folded on river), 
        # the method returns early and doesn't set playersAtShowdown
        assert stats.hands["playersAtShowdown"] == 0
        assert stats.handsplayers["Player2"]["sawShowdown"] == False
        assert stats.handsplayers["Player1"]["sawShowdown"] == False
    
    def test_position_tracking(self, stats):
        """Test that first to act and in position are tracked correctly"""
        hand = MockHand()
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # On flop, Player1 is first to act (checks first)
        assert stats.handsplayers["Player1"]["street1FirstToAct"] == True
        # Player4 is in position on flop (last to act, even though he folds)
        assert stats.handsplayers["Player4"]["street1InPosition"] == True
        
        # On turn, Player2 is first to act
        assert stats.handsplayers["Player2"]["street2FirstToAct"] == True
        # Player3 is in position on turn
        assert stats.handsplayers["Player3"]["street2InPosition"] == True
    
    def test_all_in_blind(self, stats):
        """Test handling of all-in blind players"""
        hand = MockHand()
        hand.pot.pots = [(Decimal("10.00"), ["Player1", "Player2", "Player3"])]
        
        # Simulate a scenario where Player3 is all-in blind
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player1", "calls", Decimal("0.50")),
                ("Player2", "checks"),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player2", "checks"),
            ],
            "TURN": [
                ("Player1", "checks"),
                ("Player2", "checks"),
            ],
            "RIVER": [
                ("Player1", "checks"),
                ("Player2", "checks"),
            ],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # All 3 players (including all-in Player3) should be counted
        assert stats.hands["playersAtStreet1"] == 3
        assert stats.hands["playersAtShowdown"] == 3
        assert stats.handsplayers["Player3"]["sawShowdown"] == True
    
    def test_no_flop_action(self, stats):
        """Test when there's no action on certain streets"""
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
            "FLOP": [],  # No action on flop
            "TURN": [],  # No action on turn
            "RIVER": [],  # No action on river
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # All 4 players saw all streets and showdown (no one folded)
        assert stats.hands["playersAtStreet1"] == 4
        assert stats.hands["playersAtStreet2"] == 4
        assert stats.hands["playersAtStreet3"] == 4
        assert stats.hands["playersAtShowdown"] == 4
    
    def test_multiway_fold_to_last_aggressor(self, stats):
        """Test position assignment when everyone folds to last aggressor"""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [
                ("Player1", "small blind", Decimal("0.50")),
                ("Player2", "big blind", Decimal("1.00")),
            ],
            "PREFLOP": [
                ("Player3", "raises", Decimal("3.00")),
                ("Player4", "calls", Decimal("3.00")),
                ("Player1", "calls", Decimal("2.50")),
                ("Player2", "calls", Decimal("2.00")),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player2", "checks"),
                ("Player3", "checks"),
                ("Player4", "bets", Decimal("8.00")),
                ("Player1", "folds"),
                ("Player2", "folds"),
                ("Player3", "folds"),
            ],
            "TURN": [],
            "RIVER": [],
        }
        
        # Initialize handsplayers
        for player in hand.players:
            stats.handsplayers[player[1]] = _INIT_STATS.copy()
        
        stats.hands = {}
        stats.playersAtStreetX(hand)
        
        # Player4 should be marked as in position on flop
        assert stats.handsplayers["Player4"]["street1InPosition"] == True
        
        # Only Player4 continues past flop
        assert stats.hands["playersAtStreet2"] == 0
        assert stats.hands["playersAtShowdown"] == 0


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        test_instance = TestPlayersAtStreet()
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