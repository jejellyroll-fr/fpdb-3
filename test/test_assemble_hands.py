#!/usr/bin/env python

"""Test suite for assembleHands method in DerivedStats."""

import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Card
from DerivedStats import DerivedStats


class MockHand:
    """Mock Hand object for testing assembleHands."""

    def __init__(self) -> None:
        self.handid = "12345"
        self.tablename = "Test Table"
        self.startTime = datetime(2024, 1, 1, 12, 0, 0)
        self.tourneyId = None
        self.tourneyTypeId = None
        self.hero = "Hero"
        self.sitename = "PokerStars"
        self.gametype = {
            "category": "holdem",
            "type": "ring",
            "base": "hold",
            "currency": "USD",
            "sb": "0.50",
            "bb": "1.00",
            "split": False,
        }
        self.players = [
            (1, "Hero", Decimal("100.00"), None, None),
            (2, "Villain1", Decimal("100.00"), None, None),
            (3, "Villain2", Decimal("100.00"), None, None),
            (4, "Villain3", Decimal("100.00"), None, None),
        ]
        self.board = {
            "FLOP": ["As", "Kh", "Qd"],
            "TURN": ["Jc"],
            "RIVER": ["Ts"],
        }
        self.communityStreets = ["FLOP", "TURN", "RIVER"]
        self.allStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.runItTimes = 1
        self.actions = {
            "BLINDSANTES": [],
            "PREFLOP": [
                ("Hero", "raises", Decimal("3.00")),
                ("Villain1", "calls", Decimal("3.00")),
            ],
            "FLOP": [
                ("Hero", "bets", Decimal("4.50")),
                ("Villain1", "calls", Decimal("4.50")),
            ],
            "TURN": [],
            "RIVER": [],
        }
        self.pot = MockPot()

    def getStreetTotals(self):
        """Return street pot totals."""
        return [
            Decimal("1.50"),   # Blinds
            Decimal("7.50"),   # After preflop
            Decimal("16.50"),  # After flop
            Decimal("16.50"),  # After turn
            Decimal("16.50"),  # After river
            Decimal("16.50"),   # Final pot
        ]

    def countPlayers(self):
        """Count number of players."""
        return len(self.players)


class MockPot:
    """Mock Pot object."""

    def __init__(self) -> None:
        self.committed = {}
        self.common = {}
        self.returned = {}
        self.pots = []
        self.stp = Decimal("0.00")
        self.contenders = []


class TestAssembleHands:
    """Test cases for assembleHands method."""

    @pytest.fixture
    def stats(self):
        """Create a DerivedStats instance."""
        stats = DerivedStats()

        # Mock required methods
        def mock_countPlayers(hand):
            return len(hand.players)

        def mock_playersAtStreetX(hand) -> None:
            stats.hands["playersAtStreet1"] = 2
            stats.hands["playersAtStreet2"] = 2
            stats.hands["playersAtStreet3"] = 2
            stats.hands["playersAtStreet4"] = 2
            stats.hands["playersAtShowdown"] = 0

        def mock_streetXRaises(hand) -> None:
            stats.hands["street0Raises"] = 1
            stats.hands["street1Raises"] = 0
            stats.hands["street2Raises"] = 0
            stats.hands["street3Raises"] = 0
            stats.hands["street4Raises"] = 0

        def mock_vpip(hand) -> None:
            stats.hands["playersVpi"] = 2

        stats.countPlayers = mock_countPlayers
        stats.playersAtStreetX = mock_playersAtStreetX
        stats.streetXRaises = mock_streetXRaises
        stats.vpip = mock_vpip

        return stats

    def test_basic_hand_assembly(self, stats) -> None:
        """Test basic hand assembly with standard holdem hand."""
        hand = MockHand()

        stats.assembleHands(hand)

        # Check basic hand properties
        assert stats.hands["tableName"] == "Test Table"
        assert stats.hands["siteHandNo"] == "12345"
        assert stats.hands["startTime"] == hand.startTime
        assert stats.hands["seats"] == 4
        assert stats.hands["tourneyId"] is None
        assert stats.hands["heroSeat"] == 1

        # Check board cards are encoded correctly
        assert stats.hands["boardcard1"] == Card.encodeCard("As")
        assert stats.hands["boardcard2"] == Card.encodeCard("Kh")
        assert stats.hands["boardcard3"] == Card.encodeCard("Qd")
        assert stats.hands["boardcard4"] == Card.encodeCard("Jc")
        assert stats.hands["boardcard5"] == Card.encodeCard("Ts")

        # Check street pots
        assert stats.hands["street0Pot"] == 150  # 1.50 * 100
        assert stats.hands["street1Pot"] == 750  # 7.50 * 100
        assert stats.hands["street2Pot"] == 1650  # 16.50 * 100
        assert stats.hands["street3Pot"] == 1650
        assert stats.hands["street4Pot"] == 1650
        assert stats.hands["finalPot"] == 1650

    def test_tournament_hand(self, stats) -> None:
        """Test hand assembly for tournament hand."""
        hand = MockHand()
        hand.gametype["type"] = "tour"
        hand.tourneyId = 999
        hand.tourneyTypeId = 10

        stats.assembleHands(hand)

        assert stats.hands["tourneyId"] == 999
        assert stats.hands["gametypeId"] is None  # Set later by DB

    def test_no_hero_hand(self, stats) -> None:
        """Test hand assembly when no hero is present."""
        hand = MockHand()
        hand.hero = None

        stats.assembleHands(hand)

        assert stats.hands["heroSeat"] == 0

    def test_incomplete_board(self, stats) -> None:
        """Test hand assembly with incomplete board (e.g., all-in preflop)."""
        hand = MockHand()
        hand.board = {
            "FLOP": ["As", "Kh", "Qd"],
            "TURN": [],
            "RIVER": [],
        }

        stats.assembleHands(hand)

        # Check board cards - missing cards should be encoded as 0
        assert stats.hands["boardcard1"] == Card.encodeCard("As")
        assert stats.hands["boardcard2"] == Card.encodeCard("Kh")
        assert stats.hands["boardcard3"] == Card.encodeCard("Qd")
        assert stats.hands["boardcard4"] == 0  # No turn card
        assert stats.hands["boardcard5"] == 0  # No river card

    def test_run_it_twice(self, stats) -> None:
        """Test hand assembly for run it twice scenario."""
        hand = MockHand()
        hand.runItTimes = 2
        hand.board["FLOP2"] = ["2s", "2h", "2d"]
        hand.board["TURN2"] = ["2c"]
        hand.board["RIVER2"] = ["3s"]

        stats.assembleHands(hand)

        assert stats.hands["runItTwice"] == True
        assert len(stats.hands["boards"]) == 2

        # Check first board
        board1 = stats.hands["boards"][0]
        assert board1[0] == 1  # Board ID
        assert len(board1) == 6  # Board ID + 5 cards

        # Check second board
        board2 = stats.hands["boards"][1]
        assert board2[0] == 2  # Board ID
        assert len(board2) == 6  # Board ID + 5 cards

    def test_split_pot_game(self, stats) -> None:
        """Test hand assembly for split pot games."""
        hand = MockHand()
        hand.gametype["split"] = True
        hand.gametype["category"] = "omaha8"

        stats.assembleHands(hand)

        # In split games, boards are handled differently
        assert stats.hands["runItTwice"] == False
        assert len(stats.hands["boards"]) == 1

    def test_empty_actions(self, stats) -> None:
        """Test hand assembly with no actions."""
        hand = MockHand()
        hand.actions = {
            "BLINDSANTES": [],
            "PREFLOP": [],
            "FLOP": [],
            "TURN": [],
            "RIVER": [],
        }

        stats.assembleHands(hand)

        # Should still assemble basic hand info
        assert stats.hands["tableName"] == "Test Table"
        assert stats.hands["siteHandNo"] == "12345"
        assert stats.hands["seats"] == 4

    def test_special_board_cards(self, stats) -> None:
        """Test encoding of special board situations."""
        hand = MockHand()
        hand.board = {
            "FLOPET": ["As", "Kh"],  # Special flop key
            "FLOP": ["Qd"],
            "TURN": ["Jc"],
            "RIVER": ["Ts"],
        }

        stats.assembleHands(hand)

        # FLOPET cards should be included first
        assert stats.hands["boardcard1"] == Card.encodeCard("As")
        assert stats.hands["boardcard2"] == Card.encodeCard("Kh")
        assert stats.hands["boardcard3"] == Card.encodeCard("Qd")
        assert stats.hands["boardcard4"] == Card.encodeCard("Jc")
        assert stats.hands["boardcard5"] == Card.encodeCard("Ts")

    def test_max_position_initialization(self, stats) -> None:
        """Test that maxPosition is properly initialized."""
        hand = MockHand()

        stats.assembleHands(hand)

        assert stats.hands["maxPosition"] == -1
        assert stats.hands["texture"] is None


if __name__ == "__main__":
    # Run tests with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:

        # Basic test runner
        test_instance = TestAssembleHands()
        stats = test_instance.stats()

        test_methods = [method for method in dir(test_instance) if method.startswith("test_")]

        for method_name in test_methods:
            try:
                # Create fresh stats instance for each test
                fresh_stats = test_instance.stats()
                method = getattr(test_instance, method_name)
                method(fresh_stats)
            except AssertionError:
                pass
            except Exception:
                pass

