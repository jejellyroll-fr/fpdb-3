#!/usr/bin/env python
"""Test suite for Stud steal functionality in DerivedStats."""

import os
import sys
from decimal import Decimal
from unittest.mock import Mock

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Card
from DerivedStats import DerivedStats


class MockHand:
    """Mock hand object for testing."""

    def __init__(self) -> None:
        self.handid = "12345"
        self.tablename = "Test Table"
        self.startTime = "2024-01-01 12:00:00"
        self.maxseats = 8
        self.hero = "Hero"
        self.dbid_hands = 1
        self.dbid_pids = {}
        self.tourneyId = None
        self.tourneyTypeId = None
        self.buyinCurrency = "USD"
        self.buyin = 0
        self.fee = 0
        self.totalpot = Decimal("10.00")
        self.rake = Decimal("0.50")
        self.totalcollected = Decimal("9.50")

        # Game type
        self.gametype = {
            "base": "stud",
            "category": "7stud",
            "type": "ring",
            "limitType": "fl",
            "currency": "USD",
        }

        # Players - 6 players for full ring test
        self.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Player2", Decimal("100.00"), None, None],
            [3, "Player3", Decimal("100.00"), None, None],
            [4, "Player4", Decimal("100.00"), None, None],
            [5, "Player5", Decimal("100.00"), None, None],
            [6, "Hero", Decimal("100.00"), None, None],
        ]

        # Streets
        self.allStreets = ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        self.actionStreets = ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        self.holeStreets = ["THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        self.communityStreets = []

        # Default empty attributes
        self.board = {}
        self.holecards = {}
        self.discards = {}
        self.shown = set()
        self.folded = set()
        self.collected = []
        self.collectees = {}
        self.pot = Mock()
        self.pot.pots = [(Decimal("10.00"), ["Hero"])]
        self.pot.common = {p[1]: Decimal("0") for p in self.players}
        self.pot.committed = {p[1]: Decimal("1.67") for p in self.players}
        self.pot.stp = 0
        self.sitout = set()
        self.actions = {}
        self.stacks = {}
        self.endBounty = {}
        self.tourneysPlayersIds = {}
        self.showdownStrings = {}
        self.cashedOut = False
        self.runItTimes = 0

        # Initialize Card module if needed
        if not hasattr(Card, "card_map"):
            Card.card_map = {}

        # ACTION dictionary
        self.ACTION = {
            "ante": 1,
            "small blind": 2,
            "secondsb": 3,
            "big blind": 4,
            "both": 5,
            "calls": 6,
            "raises": 7,
            "bets": 8,
            "stands pat": 9,
            "folds": 10,
            "checks": 11,
            "discards": 12,
            "bringin": 13,
            "completes": 14,
            "straddle": 15,
            "button blind": 16,
            "cashout": 17,
        }

    def getStreetTotals(self):
        return [Decimal("1.00"), Decimal("2.00"), Decimal("4.00"),
                Decimal("6.00"), Decimal("8.00"), Decimal("10.00")]

    def join_holecards(self, player, asList=False):
        if asList:
            return self.holecards.get(player, [])
        return " ".join(self.holecards.get(player, []))


class TestStudSteals:
    """Test Stud steal calculations."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.hand = MockHand()
        self.stats = DerivedStats()

    def test_steal_from_late_position(self) -> None:
        """Test steal attempt from late position (position 2) in Stud."""
        # Set up actions - Player1 bring-in, everyone folds to Player4 who raises
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
                ("Player5", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),    # Bring-in
                ("Player2", "folds"),
                ("Player3", "folds"),
                ("Player4", "raises", Decimal("0.25")),     # Steal attempt from position 2
                ("Player5", "folds"),
                ("Hero", "folds"),
                ("Player1", "folds"),                        # Bring-in folds
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        # Process stats
        self.stats.getStats(self.hand)

        # Player4 should have steal opportunity and execution
        assert self.stats.handsplayers["Player4"]["stealChance"] == True
        assert self.stats.handsplayers["Player4"]["stealDone"] == True
        assert self.stats.handsplayers["Player4"]["success_Steal"] == True

        # Player1 (bring-in) should have fold to steal stats
        # Note: In current implementation, bring-in position is 'S', not 'B'
        assert self.stats.handsplayers["Player1"]["foldSbToStealChance"] == True
        assert self.stats.handsplayers["Player1"]["foldedSbToSteal"] == True

    def test_steal_defended(self) -> None:
        """Test steal attempt that gets defended."""
        # Create new hand with 4 players
        self.hand = MockHand()
        self.hand.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Player2", Decimal("100.00"), None, None],
            [3, "Player3", Decimal("100.00"), None, None],
            [4, "Player4", Decimal("100.00"), None, None],
        ]
        self.hand.pot.common = {p[1]: Decimal("0") for p in self.hand.players}
        self.hand.pot.committed = {p[1]: Decimal("1.67") for p in self.hand.players}

        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "folds"),
                ("Player3", "raises", Decimal("0.25")),     # Steal attempt
                ("Player4", "folds"),
                ("Player1", "calls", Decimal("0.15")),       # Bring-in defends
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Player3 should have steal attempt but not successful
        assert self.stats.handsplayers["Player3"]["stealChance"] == True
        assert self.stats.handsplayers["Player3"]["stealDone"] == True
        assert self.stats.handsplayers["Player3"]["success_Steal"] == False

        # Player1 should have fold to steal chance but didn't fold
        assert self.stats.handsplayers["Player1"]["foldSbToStealChance"] == True
        assert self.stats.handsplayers["Player1"]["foldedSbToSteal"] == False

    def test_complete_as_steal(self) -> None:
        """Test that complete can be a steal attempt in Stud."""
        # Create new hand with 4 players
        self.hand = MockHand()
        self.hand.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Player2", Decimal("100.00"), None, None],
            [3, "Player3", Decimal("100.00"), None, None],
            [4, "Player4", Decimal("100.00"), None, None],
        ]
        self.hand.pot.common = {p[1]: Decimal("0") for p in self.hand.players}
        self.hand.pot.committed = {p[1]: Decimal("1.67") for p in self.hand.players}

        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "folds"),
                ("Player3", "completes", Decimal("0.25")),  # Complete as steal
                ("Player4", "folds"),
                ("Player1", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Player3's complete should count as a steal
        assert self.stats.handsplayers["Player3"]["stealChance"] == True
        assert self.stats.handsplayers["Player3"]["stealDone"] == True
        assert self.stats.handsplayers["Player3"]["success_Steal"] == True

    def test_non_steal_position_raise(self) -> None:
        """Test raise from non-steal position (early position)."""
        # Already has 6 players by default, just need to update actions
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
                ("Player5", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "raises", Decimal("0.25")),     # Early position raise
                ("Player3", "folds"),
                ("Player4", "folds"),
                ("Player5", "folds"),
                ("Hero", "folds"),
                ("Player1", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Player2 is not in steal position (position would be 4 or 5)
        # Should have raiseFirstIn but not steal
        assert self.stats.handsplayers["Player2"]["raiseFirstInChance"] == True
        assert self.stats.handsplayers["Player2"]["raisedFirstIn"] == True
        assert self.stats.handsplayers["Player2"]["stealChance"] == False
        assert self.stats.handsplayers["Player2"]["stealDone"] == False

    def test_heads_up_steal(self) -> None:
        """Test steal in heads-up Stud."""
        # Create new hand with 2 players
        self.hand = MockHand()
        self.hand.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Hero", Decimal("100.00"), None, None],
        ]
        self.hand.hero = "Hero"
        self.hand.pot.common = {p[1]: Decimal("0") for p in self.hand.players}
        self.hand.pot.committed = {p[1]: Decimal("5.00") for p in self.hand.players}

        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Hero", "raises", Decimal("0.25")),        # HU steal attempt
                ("Player1", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # In HU, the non-bring-in player should have steal opportunity
        assert self.stats.handsplayers["Hero"]["stealChance"] == True
        assert self.stats.handsplayers["Hero"]["stealDone"] == True
        assert self.stats.handsplayers["Hero"]["success_Steal"] == True

    def test_steal_positions_calculation(self) -> None:
        """Test that steal positions are correctly identified in Stud."""
        # 6-player game to test position calculations
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
                ("Player5", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "folds"),
                ("Player3", "folds"),
                ("Player4", "folds"),
                ("Player5", "folds"),
                ("Hero", "raises", Decimal("0.25")),        # Last position steal
                ("Player1", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Hero in last position (position 0) should have steal opportunity
        assert self.stats.handsplayers["Hero"]["position"] == 0
        assert self.stats.handsplayers["Hero"]["stealChance"] == True
        assert self.stats.handsplayers["Hero"]["stealDone"] == True

    def test_raise_to_steal_after_steal_attempt(self) -> None:
        """Test re-steal scenario."""
        # Create new hand with 4 players
        self.hand = MockHand()
        self.hand.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Player2", Decimal("100.00"), None, None],
            [3, "Player3", Decimal("100.00"), None, None],
            [4, "Player4", Decimal("100.00"), None, None],
        ]
        self.hand.pot.common = {p[1]: Decimal("0") for p in self.hand.players}
        self.hand.pot.committed = {p[1]: Decimal("1.67") for p in self.hand.players}

        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Player4", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "folds"),
                ("Player3", "raises", Decimal("0.25")),     # Steal attempt
                ("Player4", "folds"),
                ("Player1", "raises", Decimal("0.50")),     # Re-steal from bring-in
                ("Player3", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Player1 should have raiseToSteal stats
        assert self.stats.handsplayers["Player1"]["raiseToStealChance"] == True
        assert self.stats.handsplayers["Player1"]["raiseToStealDone"] == True

        # Player3's steal should fail
        assert self.stats.handsplayers["Player3"]["success_Steal"] == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
