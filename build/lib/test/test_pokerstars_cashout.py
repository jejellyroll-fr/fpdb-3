#!/usr/bin/env python3
"""Test cash out functionality for PokerStars parser."""

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PokerStarsToFpdb import PokerStars


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return import parameters for testing."""
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [],  # Empty list means no filters - import everything
            "handCount": 0,
            "fastFold": False,
            "ringFilter": True,
            "tourneyFilter": True,
        }

    def get_site_id(self, sitename: str) -> int:
        """Return the site ID for the given site name."""
        return 32  # PokerStars.COM


class TestPokerStarsCashOut:
    """Test cases for PokerStars cash out functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.config = MockConfig()
        # Set the file path using relative path
        self.cashout_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            "regression-test-files",
            "cash",
            "Stars",
            "Flop",
            "2025-NL-6max-USD-0.05-0.10.cashout.txt",
        )
        # Initialize parser without automatic processing
        self.parser = PokerStars(config=self.config)

        # Test hand text with cash out
        self.hand_text = """PokerStars Hand #257180854570: Hold'em No Limit ($0.05/$0.10 USD) - 2025/08/02 11:24:53 CET [2025/08/02 5:24:53 ET]
Table 'Wezen' 6-max Seat #3 is the button
Seat 1: Player1 ($13.53 in chips)
Seat 2: Player2 ($10 in chips)
Seat 3: Player3 ($18.39 in chips)
Seat 4: Hero ($15.35 in chips)
Seat 5: Player5 ($3.67 in chips)
Seat 6: Player6 ($2.76 in chips)
Hero: posts small blind $0.05
Player5: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [9s 6s]
Player6: folds
Player1: raises $0.20 to $0.30
Player2: folds
Player3: raises $0.60 to $0.90
Hero: folds
Player5: folds
Player1: calls $0.60
*** FLOP *** [Qh Ad Ts]
Player1: bets $0.93
Player3: calls $0.93
*** TURN *** [Qh Ad Ts] [As]
Player1: bets $3.62
Player3: raises $3.78 to $7.40
Player1: raises $3.78 to $11.18
Player3: raises $3.78 to $14.96
Player1: calls $0.52 and is all-in
Uncalled bet ($3.26) returned to Player3
*** RIVER *** [Qh Ad Ts As] [Qd]
*** SHOW DOWN ***
Player1: shows [Qs Js] (a full house, Queens full of Aces)
Player3: shows [Th Tc] (a full house, Tens full of Aces)
Player1 collected $25.96 from pot
Player3 cashed out the hand for $22.77 | Cash Out Fee $0.46
*** SUMMARY ***
Total pot $27.21 | Rake $1.25
Board [Qh Ad Ts As Qd]
Seat 1: Player1 showed [Qs Js] and won ($25.96) with a full house, Queens full of Aces
Seat 2: Player2 folded before Flop (didn't bet)
Seat 3: Player3 (button) showed [Th Tc] and lost with a full house, Tens full of Aces (cashed out)
Seat 4: Hero (small blind) folded before Flop
Seat 5: Player5 (big blind) folded before Flop
Seat 6: Player6 folded before Flop (didn't bet)"""

        # Override readFile to avoid file system access
        def mock_readFile():
            self.parser.obs = self.hand_text
            self.parser.index = 0
            return True

        self.parser.readFile = mock_readFile

    def test_cash_out_detection(self):
        """Test that cash out hands are correctly detected."""
        hands = self.parser.allHandsAsList()
        assert len(hands) == 1, f"Expected 1 hand, got {len(hands)}"

        hand = self.parser.processHand(hands[0])

        # Verify cash out detection
        assert hand.cashedOut is True, "Hand should be detected as cashed out"

    def test_cash_out_pot_collection(self):
        """Test that cash out pot collection works correctly."""
        hands = self.parser.allHandsAsList()
        hand = self.parser.processHand(hands[0])

        # Check collected amounts - direct assertions for known values
        collected = hand.collected

        # Create a dictionary for easier lookup - collected is a list of [player, amount] pairs
        collected_dict = {entry[0]: Decimal(entry[1]) for entry in collected}

        # Player1 collected $25.96 from pot
        assert collected_dict["Player1"] == Decimal(
            "25.96"
        ), f"Player1 should collect 25.96, got {collected_dict.get('Player1')}"

        # Player3 cashed out for $22.77 (also counted as a collection)
        assert collected_dict["Player3"] == Decimal(
            "22.77"
        ), f"Player3 should collect 22.77, got {collected_dict.get('Player3')}"

        # Check that cash out fee is captured
        assert hasattr(hand, "cashOutFees"), "Hand should have cashOutFees attribute"
        assert "Player3" in hand.cashOutFees, "Player3 should have a cash out fee recorded"
        assert hand.cashOutFees["Player3"] == Decimal(
            "0.46"
        ), f"Player3 cash out fee should be 0.46, got {hand.cashOutFees['Player3']}"

    def test_cash_out_regex_pattern(self):
        """Test the cash out regex patterns work correctly."""
        # Test basic cash out detection
        test_text = "Player3 cashed out the hand"
        assert self.parser.re_cashed_out.search(test_text) is not None

        # Test cash out with fee pattern
        test_text = "Player3 cashed out the hand for $22.77 | Cash Out Fee $0.46"
        match = self.parser.re_collect_pot3.search(test_text)

        assert match is not None
        assert match.group("PNAME") == "Player3"
        assert match.group("POT") == "22.77"
        assert match.group("FEE") == "0.46"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
