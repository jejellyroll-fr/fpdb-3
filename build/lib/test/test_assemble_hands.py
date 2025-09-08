"""Test suite for assembleHands method in DerivedStats."""

import sys
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import Card
from DerivedStats import DerivedStats


class MockHand:
    """Mock Hand object for testing assembleHands."""

    def __init__(self) -> None:
        """Initialize mock hand object with test data."""
        self.handid = "12345"
        self.tablename = "Test Table"
        self.startTime = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
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

    def getStreetTotals(self) -> list[Decimal]:
        """Return street pot totals."""
        return [
            Decimal("1.50"),  # Blinds
            Decimal("7.50"),  # After preflop
            Decimal("16.50"),  # After flop
            Decimal("16.50"),  # After turn
            Decimal("16.50"),  # After river
            Decimal("16.50"),  # Final pot
        ]

    def countPlayers(self) -> int:
        """Count number of players."""
        return len(self.players)


class MockPot:
    """Mock Pot object."""

    def __init__(self) -> None:
        """Initialize MockPot with empty pot data structures."""
        self.committed = {}
        self.common = {}
        self.returned = {}
        self.pots = []
        self.stp = Decimal("0.00")
        self.contenders = []


class TestAssembleHands:
    """Test cases for assembleHands method."""

    def _assert_board_cards(self, stats: DerivedStats, expected_cards: list[str | None]) -> None:
        """Helper method to assert board card encoding.

        Args:
            stats: DerivedStats instance with assembled hands
            expected_cards: List of card strings or None for missing cards (max 5)
        """
        for i, card in enumerate(expected_cards[:5], 1):
            board_key = f"boardcard{i}"
            expected_value = Card.encodeCard(card) if card else 0
            assert stats.hands[board_key] == expected_value

    def _setup_and_assemble_hand(
        self,
        stats: DerivedStats,
        hand_modifier: Callable[[MockHand], None] | None = None,
    ) -> MockHand:
        """Helper method to create and assemble a hand with optional modifications.

        Args:
            stats: DerivedStats instance to use for assembly
            hand_modifier: Optional function to modify the hand before assembly

        Returns:
            The modified MockHand instance
        """
        hand = MockHand()
        if hand_modifier:
            hand_modifier(hand)
        stats.assembleHands(hand)
        return hand

    @pytest.fixture
    def stats(self) -> DerivedStats:
        """Create a DerivedStats instance."""
        stats = DerivedStats()

        # Mock required methods
        def mock_countPlayers(hand: MockHand) -> int:
            return len(hand.players)

        def mock_playersAtStreetX(_: MockHand) -> None:
            stats.hands["playersAtStreet1"] = 2
            stats.hands["playersAtStreet2"] = 2
            stats.hands["playersAtStreet3"] = 2
            stats.hands["playersAtStreet4"] = 2
            stats.hands["playersAtShowdown"] = 0

        def mock_streetXRaises(_: MockHand) -> None:
            stats.hands["street0Raises"] = 1
            stats.hands["street1Raises"] = 0
            stats.hands["street2Raises"] = 0
            stats.hands["street3Raises"] = 0
            stats.hands["street4Raises"] = 0

        def mock_vpip(_: MockHand) -> None:
            stats.hands["playersVpi"] = 2

        stats.countPlayers = mock_countPlayers
        stats.playersAtStreetX = mock_playersAtStreetX
        stats.streetXRaises = mock_streetXRaises
        stats.vpip = mock_vpip

        return stats

    def test_basic_hand_assembly(self, stats: DerivedStats) -> None:
        """Test basic hand assembly with standard holdem hand."""
        hand = self._setup_and_assemble_hand(stats)

        # Check basic hand properties
        assert stats.hands["tableName"] == "Test Table"
        assert stats.hands["siteHandNo"] == "12345"
        assert stats.hands["startTime"] == hand.startTime
        assert stats.hands["seats"] == 4
        assert stats.hands["tourneyId"] is None
        assert stats.hands["heroSeat"] == 1

        # Check board cards are encoded correctly
        self._assert_board_cards(stats, ["As", "Kh", "Qd", "Jc", "Ts"])

        # Check street pots
        assert stats.hands["street0Pot"] == 150  # 1.50 * 100
        assert stats.hands["street1Pot"] == 750  # 7.50 * 100
        assert stats.hands["street2Pot"] == 1650  # 16.50 * 100
        assert stats.hands["street3Pot"] == 1650
        assert stats.hands["street4Pot"] == 1650
        assert stats.hands["finalPot"] == 1650

    def test_tournament_hand(self, stats: DerivedStats) -> None:
        """Test hand assembly for tournament hand."""

        def modify_for_tournament(hand: MockHand) -> None:
            hand.gametype["type"] = "tour"
            hand.tourneyId = 999
            hand.tourneyTypeId = 10

        self._setup_and_assemble_hand(stats, modify_for_tournament)

        assert stats.hands["tourneyId"] == 999
        assert stats.hands["gametypeId"] is None  # Set later by DB

    def test_no_hero_hand(self, stats: DerivedStats) -> None:
        """Test hand assembly when no hero is present."""

        def remove_hero(hand: MockHand) -> None:
            hand.hero = None

        self._setup_and_assemble_hand(stats, remove_hero)

        assert stats.hands["heroSeat"] == 0

    def test_incomplete_board(self, stats: DerivedStats) -> None:
        """Test hand assembly with incomplete board (e.g., all-in preflop)."""

        def set_incomplete_board(hand: MockHand) -> None:
            hand.board = {
                "FLOP": ["As", "Kh", "Qd"],
                "TURN": [],
                "RIVER": [],
            }

        self._setup_and_assemble_hand(stats, set_incomplete_board)

        # Check board cards - missing cards should be encoded as 0
        self._assert_board_cards(stats, ["As", "Kh", "Qd", None, None])

    def test_run_it_twice(self, stats: DerivedStats) -> None:
        """Test hand assembly for run it twice scenario."""

        def setup_run_it_twice(hand: MockHand) -> None:
            hand.runItTimes = 2
            hand.board["FLOP2"] = ["2s", "2h", "2d"]
            hand.board["TURN2"] = ["2c"]
            hand.board["RIVER2"] = ["3s"]

        self._setup_and_assemble_hand(stats, setup_run_it_twice)

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

    def test_split_pot_game(self, stats: DerivedStats) -> None:
        """Test hand assembly for split pot games."""

        def setup_split_pot(hand: MockHand) -> None:
            hand.gametype["split"] = True
            hand.gametype["category"] = "omaha8"

        self._setup_and_assemble_hand(stats, setup_split_pot)

        # In split games, boards are handled differently
        assert stats.hands["runItTwice"] == False
        assert len(stats.hands["boards"]) == 1

    def test_empty_actions(self, stats: DerivedStats) -> None:
        """Test hand assembly with no actions."""

        def clear_actions(hand: MockHand) -> None:
            hand.actions = {
                "BLINDSANTES": [],
                "PREFLOP": [],
                "FLOP": [],
                "TURN": [],
                "RIVER": [],
            }

        self._setup_and_assemble_hand(stats, clear_actions)

        # Should still assemble basic hand info
        assert stats.hands["tableName"] == "Test Table"
        assert stats.hands["siteHandNo"] == "12345"
        assert stats.hands["seats"] == 4

    def test_special_board_cards(self, stats: DerivedStats) -> None:
        """Test encoding of special board situations."""

        def setup_special_board(hand: MockHand) -> None:
            hand.board = {
                "FLOPET": ["As", "Kh"],  # Special flop key
                "FLOP": ["Qd"],
                "TURN": ["Jc"],
                "RIVER": ["Ts"],
            }

        self._setup_and_assemble_hand(stats, setup_special_board)

        # FLOPET cards should be included first
        self._assert_board_cards(stats, ["As", "Kh", "Qd", "Jc", "Ts"])

    def test_max_position_initialization(self, stats: DerivedStats) -> None:
        """Test that maxPosition is properly initialized."""
        self._setup_and_assemble_hand(stats)

        assert stats.hands["maxPosition"] == -1
        assert stats.hands["texture"] is None
