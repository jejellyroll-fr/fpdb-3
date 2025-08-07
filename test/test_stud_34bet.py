#!/usr/bin/env python
"""Test suite for Stud 3/4-bet functionality in DerivedStats."""

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
        self.hero = "Hero"

        # Game type
        self.gametype = {
            "base": "stud",
            "category": "7stud",
            "type": "ring",
            "limitType": "fl",
            "currency": "USD",
        }

        # Players
        self.players = [
            [1, "Player1", Decimal("100.00"), None, None],
            [2, "Player2", Decimal("100.00"), None, None],
            [3, "Player3", Decimal("100.00"), None, None],
            [4, "Hero", Decimal("100.00"), None, None],
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
        self.pot.common = {
            "Player1": Decimal(0),
            "Player2": Decimal(0),
            "Player3": Decimal(0),
            "Hero": Decimal(0),
        }
        self.pot.committed = {
            "Player1": Decimal("2.50"),
            "Player2": Decimal("2.50"),
            "Player3": Decimal("2.50"),
            "Hero": Decimal("2.50"),
        }
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
        return [Decimal("1.00"), Decimal("2.00"), Decimal("4.00"), Decimal("6.00"), Decimal("8.00"), Decimal("10.00")]

    def join_holecards(self, player, asList=False):
        if asList:
            return self.holecards.get(player, [])
        return " ".join(self.holecards.get(player, []))


class TestStud34Bet:
    """Test Stud 3/4-bet calculations."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.hand = MockHand()
        self.stats = DerivedStats()

    def test_basic_stud_34bet(self) -> None:
        """Test basic 3-bet and 4-bet scenario in Stud."""
        # Set up actions - typical Stud betting pattern
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),  # Bring-in (not counted)
                ("Player2", "completes", Decimal("0.25")),  # Complete = 1-bet
                ("Player3", "raises", Decimal("0.50")),  # Raise = 2-bet
                ("Hero", "raises", Decimal("0.75")),  # Re-raise = 3-bet
                ("Player1", "folds"),
                ("Player2", "raises", Decimal("1.00")),  # Re-re-raise = 4-bet
                ("Player3", "folds"),
                ("Hero", "calls", Decimal("0.25")),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        # Process stats
        self.stats.getStats(self.hand)

        # Debug output
        for player in ["Player1", "Player2", "Player3", "Hero"]:
            for key in self.stats.handsplayers[player]:
                if "2B" in key or "3B" in key or "4B" in key:
                    pass

        # In Stud: complete = 1-bet, first raise = 2-bet, re-raise = 3-bet, re-re-raise = 4-bet

        # Player2 completes (1-bet) - no 2B flags
        assert self.stats.handsplayers["Player2"]["street0_2BChance"] == False
        assert self.stats.handsplayers["Player2"]["street0_2BDone"] == False

        # Player3 raises after complete (2-bet)
        assert self.stats.handsplayers["Player3"]["street0_2BChance"] == True
        assert self.stats.handsplayers["Player3"]["street0_2BDone"] == True

        # Hero re-raises (3-bet)
        assert self.stats.handsplayers["Hero"]["street0_3BChance"] == True
        assert self.stats.handsplayers["Hero"]["street0_3BDone"] == True

        # Player2 re-re-raises (4-bet)
        assert self.stats.handsplayers["Player2"]["street0_4BChance"] == True
        assert self.stats.handsplayers["Player2"]["street0_4BDone"] == True

        # Verify fold to 3-bet
        assert self.stats.handsplayers["Player2"]["street0_FoldTo3BChance"] == True
        assert self.stats.handsplayers["Player2"]["street0_FoldTo3BDone"] == False  # Didn't fold

        # Verify fold to 4-bet
        assert self.stats.handsplayers["Hero"]["street0_FoldTo4BChance"] == True
        assert self.stats.handsplayers["Hero"]["street0_FoldTo4BDone"] == False  # Called

    def test_stud_bring_in_not_counted(self) -> None:
        """Test that bring-in is not counted as a bet level."""
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),  # Not counted
                ("Player2", "raises", Decimal("0.25")),  # This is 1-bet in Stud
                ("Player1", "calls", Decimal("0.15")),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Player2's raise after bring-in is the first bet level (1-bet)
        # So no 2B flags should be set
        assert self.stats.handsplayers["Player2"]["street0_2BChance"] == False
        assert self.stats.handsplayers["Player2"]["street0_2BDone"] == False

    def test_stud_complete_counts_as_aggressive(self) -> None:
        """Test that complete action is treated as aggressive."""
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "completes", Decimal("0.25")),  # Should count as aggressive
                ("Player3", "calls", Decimal("0.25")),
                ("Player1", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Complete is the first bet level (1-bet) in Stud, not 2-bet
        assert self.stats.handsplayers["Player2"]["street0_2BChance"] == False
        assert self.stats.handsplayers["Player2"]["street0_2BDone"] == False

        # Complete should count for VPIP
        assert self.stats.handsplayers["Player2"]["street0VPI"] == True

        # Complete should count as aggressive action
        assert self.stats.handsplayers["Player2"]["street0Aggr"] == True

    def test_stud_cold_4bet(self) -> None:
        """Test cold 4-bet scenario."""
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "completes", Decimal("0.25")),  # 1-bet
                ("Player3", "raises", Decimal("0.50")),  # 2-bet
                ("Hero", "raises", Decimal("0.75")),  # 3-bet
                ("Player1", "raises", Decimal("1.00")),  # Cold 4-bet
                ("Player2", "folds"),
                ("Player3", "folds"),
                ("Hero", "calls", Decimal("0.25")),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Verify cold 4-bet
        assert self.stats.handsplayers["Player1"]["street0_C4BChance"] == True
        assert self.stats.handsplayers["Player1"]["street0_C4BDone"] == True

    def test_stud_squeeze(self) -> None:
        """Test squeeze scenario in Stud."""
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "completes", Decimal("0.25")),  # 1-bet
                ("Player3", "calls", Decimal("0.25")),  # Call creates squeeze opportunity
                ("Hero", "raises", Decimal("0.50")),  # This is 2-bet, not 3-bet
                ("Player1", "folds"),
                ("Player2", "folds"),
                ("Player3", "folds"),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # Hero's raise is a 2-bet, not a 3-bet, so no squeeze opportunity
        # Squeeze only happens when there's a raise (2-bet) and a call, then a re-raise (3-bet)
        assert self.stats.handsplayers["Hero"]["street0_2BChance"] == True
        assert self.stats.handsplayers["Hero"]["street0_2BDone"] == True
        assert self.stats.handsplayers["Hero"]["street0_SqueezeChance"] == False
        assert self.stats.handsplayers["Hero"]["street0_SqueezeDone"] == False

    def test_stud_vpip_with_completes(self) -> None:
        """Test VPIP calculation includes completes for Stud."""
        self.hand.actions = {
            "BLINDSANTES": [
                ("Player1", "ante", Decimal("0.10")),
                ("Player2", "ante", Decimal("0.10")),
                ("Player3", "ante", Decimal("0.10")),
                ("Hero", "ante", Decimal("0.10")),
            ],
            "THIRD": [
                ("Player1", "bringin", Decimal("0.10")),
                ("Player2", "completes", Decimal("0.25")),
                ("Player3", "calls", Decimal("0.25")),
                ("Hero", "raises", Decimal("0.50")),
                ("Player1", "folds"),
                ("Player2", "calls", Decimal("0.25")),
                ("Player3", "calls", Decimal("0.25")),
            ],
            "FOURTH": [],
            "FIFTH": [],
            "SIXTH": [],
            "SEVENTH": [],
        }

        self.stats.getStats(self.hand)

        # All players except Player1 (who only did bring-in) should have VPIP
        assert self.stats.handsplayers["Player1"]["street0VPI"] == False  # Only bring-in
        assert self.stats.handsplayers["Player2"]["street0VPI"] == True  # Complete
        assert self.stats.handsplayers["Player3"]["street0VPI"] == True  # Call
        assert self.stats.handsplayers["Hero"]["street0VPI"] == True  # Raise

        # VPIP count should be 3
        assert self.stats.hands["playersVpi"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
