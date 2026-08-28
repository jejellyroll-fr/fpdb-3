#!/usr/bin/env python3
"""Regression test for GitHub issue #137 — Total Profit for 5_omaha8 hands.

A 5 Card Omaha Hi/Lo (category ``5_omaha8``) hand that Hero wins must report a
positive Total Profit, not a loss / zero winnings. This locks in the correct
parser + DerivedStats output for the hand attached to issue #137.

Player6 wins the pot uncontested:
  - committed $2.53  (preflop call $0.85 + flop bet $1.68; river bet returned)
  - collected $5.75  (Total pot $6.01 - Rake $0.26)
  - net profit $3.22
"""

import os

import pytest

from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars


class MockConfig:
    """Minimal configuration stub for parser tests."""

    def get_import_parameters(self) -> dict:
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [],
            "handCount": 0,
            "fastFold": False,
            "ringFilter": True,
            "tourneyFilter": True,
        }

    def get_site_id(self, sitename: str) -> int:
        return 32  # PokerStars.COM


HAND_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "regression-test-files",
    "cash",
    "Stars",
    "Flop",
    "PLO5-Hi-Lo-USD-0.10-0.25-issue137.txt",
)


class TestFiveCardOmaha8ProfitIssue137:
    """5 Card Omaha Hi/Lo profit must be computed correctly for a winning hand."""

    def setup_method(self) -> None:
        with open(HAND_FILE, encoding="utf-8-sig") as fh:
            hand_text = fh.read()
        self.parser = PokerStars(config=MockConfig())

        def mock_read_file() -> bool:
            self.parser.obs = hand_text
            self.parser.index = 0
            return True

        self.parser.readFile = mock_read_file

    def _hand(self):
        hands = self.parser.allHandsAsList()
        assert len(hands) == 1
        return self.parser.processHand(hands[0])

    def test_category_is_5omaha8(self) -> None:
        assert self._hand().gametype["category"] == "5_omaha8"

    def test_parser_collects_pot_for_winner(self) -> None:
        """The parser must register Player6's $5.75 pot collection."""
        hand = self._hand()
        assert hand.collectees.get("Player6") is not None
        assert str(hand.collectees["Player6"]) == "5.75"

    def test_derived_stats_winner_profit(self) -> None:
        """Player6 wins: winnings $5.75, committed $2.53, profit $3.22 (in cents)."""
        hand = self._hand()
        stats = DerivedStats()
        stats.getStats(hand)
        hp = stats.handsplayers["Player6"]

        assert hp["winnings"] == 575
        assert hp["committed"] == 253
        assert hp["totalProfit"] == 322
        assert hp["flg_won_hand"] is True

    def test_derived_stats_loser_profit(self) -> None:
        """Player2 loses what they committed; winnings stay 0."""
        hand = self._hand()
        stats = DerivedStats()
        stats.getStats(hand)
        hp = stats.handsplayers["Player2"]

        assert hp["winnings"] == 0
        assert hp["committed"] == 253
        assert hp["totalProfit"] == -253


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
