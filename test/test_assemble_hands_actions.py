"""Test suite for assembleHandsActions method in DerivedStats."""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from DerivedStats import DerivedStats


class TestAssembleHandsActions:
    """Test cases for assembleHandsActions method."""

    def setup_method(self) -> None:
        """Set up test fixtures before each test method."""
        self.derived_stats = DerivedStats()
        self.mock_hand = Mock()

        # Initialize handsplayers
        self.derived_stats.handsplayers = {
            "Player1": {"street0Discards": 0, "street1Discards": 0, "street2Discards": 0, "wentAllIn": False},
            "Player2": {"street0Discards": 0, "street1Discards": 0, "street2Discards": 0, "wentAllIn": False},
            "Player3": {"street0Discards": 0, "street1Discards": 0, "street2Discards": 0, "wentAllIn": False},
        }

        # Mock ACTION dictionary (from Hand.py)
        self.mock_hand.ACTION = {
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

    def test_basic_actions_assembly(self) -> None:
        """Test basic assembly of actions from a simple hand."""
        # Setup
        self.mock_hand.handid = "12345"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal(10), Decimal(10), Decimal(5), False),
                ("Player2", "calls", Decimal(10), False),
                ("Player3", "folds"),
            ],
            "FLOP": [
                ("Player1", "bets", Decimal(15), False),
                ("Player2", "calls", Decimal(15), False),
            ],
            "TURN": [
                ("Player1", "checks"),
                ("Player2", "bets", Decimal(30), False),
                ("Player1", "calls", Decimal(30), False),
            ],
            "RIVER": [
                ("Player1", "checks"),
                ("Player2", "checks"),
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert len(self.derived_stats.handsactions) == 10  # Total number of actions

        # Check first action (Player1 raises)
        assert self.derived_stats.handsactions[1]["player"] == "Player1"
        assert self.derived_stats.handsactions[1]["street"] == 0  # PREFLOP is street 0
        assert self.derived_stats.handsactions[1]["actionNo"] == 1
        assert self.derived_stats.handsactions[1]["streetActionNo"] == 1
        assert self.derived_stats.handsactions[1]["actionId"] == 7  # raises
        assert self.derived_stats.handsactions[1]["amount"] == 1000  # 10 * 100
        assert self.derived_stats.handsactions[1]["raiseTo"] == 1000
        assert self.derived_stats.handsactions[1]["amountCalled"] == 500
        assert self.derived_stats.handsactions[1]["allIn"] == False

    def test_all_in_action(self) -> None:
        """Test handling of all-in actions."""
        # Setup
        self.mock_hand.handid = "12346"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal(100), Decimal(100), Decimal(2), True),  # All-in
                ("Player2", "calls", Decimal(100), True),  # All-in call
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert self.derived_stats.handsactions[1]["allIn"] == True
        assert self.derived_stats.handsactions[2]["allIn"] == True
        assert self.derived_stats.handsplayers["Player1"]["wentAllIn"] == True
        assert self.derived_stats.handsplayers["Player1"]["street0AllIn"] == True
        assert self.derived_stats.handsplayers["Player2"]["wentAllIn"] == True

    def test_discard_actions(self) -> None:
        """Test handling of discard actions in draw games."""
        # Setup
        self.mock_hand.handid = "12347"
        self.mock_hand.actionStreets = ["BLINDS", "DEAL", "DRAWONE"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "DEAL": [
                ("Player1", "checks"),
                ("Player2", "bets", Decimal(5), False),
            ],
            "DRAWONE": [
                ("Player1", "discards", 3, ["Ah", "Kh", "Qh"]),
                ("Player2", "discards", 1, ["2c"]),
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify discard actions
        assert self.derived_stats.handsactions[3]["actionId"] == 12  # discards
        assert self.derived_stats.handsactions[3]["numDiscarded"] == 3
        assert self.derived_stats.handsactions[3]["cardsDiscarded"] == ["Ah", "Kh", "Qh"]
        assert self.derived_stats.handsplayers["Player1"]["street1Discards"] == 3

        assert self.derived_stats.handsactions[4]["numDiscarded"] == 1
        assert self.derived_stats.handsactions[4]["cardsDiscarded"] == ["2c"]
        assert self.derived_stats.handsplayers["Player2"]["street1Discards"] == 1

    def test_empty_streets(self) -> None:
        """Test handling of streets with no actions."""
        # Setup
        self.mock_hand.handid = "12348"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP", "FLOP", "TURN", "RIVER"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal(10), Decimal(10), Decimal(0), False),
                ("Player2", "calls", Decimal(10), False),
            ],
            "FLOP": [],  # No actions on flop
            "TURN": [],  # No actions on turn
            "RIVER": [],  # No actions on river
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert len(self.derived_stats.handsactions) == 2  # Only preflop actions

    def test_complete_action(self) -> None:
        """Test handling of complete actions in limit games."""
        # Setup
        self.mock_hand.handid = "12349"
        self.mock_hand.actionStreets = ["BLINDS", "THIRD", "FOURTH"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "THIRD": [
                ("Player1", "bets", Decimal(2), False),
                ("Player2", "completes", Decimal(4), Decimal(4), Decimal(2), False),
            ],
            "FOURTH": [],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert self.derived_stats.handsactions[2]["actionId"] == 14  # completes
        assert self.derived_stats.handsactions[2]["amount"] == 400
        assert self.derived_stats.handsactions[2]["raiseTo"] == 400
        assert self.derived_stats.handsactions[2]["amountCalled"] == 200

    def test_unknown_action_type(self) -> None:
        """Test handling of unknown action types."""
        # Setup
        self.mock_hand.handid = "12350"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "unknown_action", Decimal(10), False),
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert self.derived_stats.handsactions[1]["actionId"] is None
        assert self.derived_stats.handsactions[1]["player"] == "Player1"

    def test_street_action_numbering(self) -> None:
        """Test correct numbering of actions within streets."""
        # Setup
        self.mock_hand.handid = "12351"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP", "FLOP"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal(10), Decimal(10), Decimal(0), False),
                ("Player2", "calls", Decimal(10), False),
                ("Player3", "raises", Decimal(30), Decimal(30), Decimal(10), False),
            ],
            "FLOP": [
                ("Player1", "checks"),
                ("Player2", "bets", Decimal(20), False),
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify street action numbering
        assert self.derived_stats.handsactions[1]["streetActionNo"] == 1
        assert self.derived_stats.handsactions[2]["streetActionNo"] == 2
        assert self.derived_stats.handsactions[3]["streetActionNo"] == 3
        assert self.derived_stats.handsactions[4]["streetActionNo"] == 1  # Reset for new street
        assert self.derived_stats.handsactions[5]["streetActionNo"] == 2

    def test_decimal_amounts(self) -> None:
        """Test handling of decimal amounts in actions."""
        # Setup
        self.mock_hand.handid = "12352"
        self.mock_hand.actionStreets = ["BLINDS", "PREFLOP"]
        self.mock_hand.actions = {
            "BLINDS": [],
            "PREFLOP": [
                ("Player1", "raises", Decimal("2.50"), Decimal("2.50"), Decimal("1.00"), False),
                ("Player2", "calls", Decimal("2.50"), False),
            ],
        }

        # Execute
        self.derived_stats.assembleHandsActions(self.mock_hand)

        # Verify
        assert self.derived_stats.handsactions[1]["amount"] == 250  # 2.50 * 100
        assert self.derived_stats.handsactions[1]["raiseTo"] == 250
        assert self.derived_stats.handsactions[1]["amountCalled"] == 100
