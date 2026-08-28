#!/usr/bin/env python3
"""Regression test for GitHub issue #98 — PokerStars cash-out double-counting.

When a player cashes out a hand they *would* have won, PokerStars still prints
a SUMMARY line "showed [...] and won ($X) ... (pot not awarded as player cashed
out)". The parser used to count both that $X and the cash-out amount, inflating
winnings (won 35.71 instead of 15.82, net 25.29 instead of 5.40).
"""

from decimal import Decimal

import pytest

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


# Hand from issue #98: Hero wins the showdown but cashes out for $15.82.
# Hero committed $10.42 (BB $0.10 -> raise to $1.15 -> call $9.27).
# Expected: winnings = 15.82, net profit = 15.82 - 10.42 = 5.40.
HAND_TEXT = """PokerStars Hand #198361245189: Hold'em No Limit ($0.05/$0.10 USD) - 2024/11/15 18:22:15 ET
Table 'Humboldt IV' 6-max Seat #5 is the button
Seat 1: Player1 ($10.42 in chips)
Seat 3: Player3 ($11.44 in chips)
Seat 4: Player4 ($10.24 in chips)
Seat 5: Hero ($10.79 in chips)
Seat 6: Player6 ($13.28 in chips)
Player4: posts small blind $0.05
Hero: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [Ad As]
Player6: folds
Player1: raises $0.20 to $0.30
Player3: folds
Player4: folds
Hero: raises $0.85 to $1.15
Player1: raises $9.27 to $10.42 and is all-in
Hero: calls $9.27
*** FLOP *** [7c 3s Ac]
*** TURN *** [7c 3s Ac] [Jh]
*** RIVER *** [7c 3s Ac Jh] [Jd]
*** SHOW DOWN ***
Hero: shows [Ad As] (a full house, Aces full of Jacks)
Player1: shows [8d 8s] (two pair, Jacks and Eights)
Hero cashed out the hand for $15.82 | Cash Out Fee $0.32
*** SUMMARY ***
Total pot $20.89 | Rake $1
Board [7c 3s Ac Jh Jd]
Seat 1: Player1 showed [8d 8s] and lost with two pair, Jacks and Eights
Seat 3: Player3 folded before Flop (didn't bet)
Seat 4: Player4 (small blind) folded before Flop
Seat 5: Hero (big blind) showed [Ad As] and won ($19.89) with a full house, Aces full of Jacks (pot not awarded as player cashed out)
Seat 6: Player6 folded before Flop (didn't bet)"""


class TestPokerStarsCashOutIssue98:
    """Hero wins the showdown but cashes out — winnings must not be double-counted."""

    def setup_method(self) -> None:
        self.parser = PokerStars(config=MockConfig())

        def mock_read_file() -> bool:
            self.parser.obs = HAND_TEXT
            self.parser.index = 0
            return True

        self.parser.readFile = mock_read_file

    def _process(self):
        hands = self.parser.allHandsAsList()
        assert len(hands) == 1
        return self.parser.processHand(hands[0])

    def test_cash_out_detected(self) -> None:
        hand = self._process()
        assert hand.cashedOut is True

    def test_hero_winnings_not_double_counted(self) -> None:
        """Hero's winnings must be the cash-out amount only ($15.82), not $35.71."""
        hand = self._process()

        hero_entries = [Decimal(amount) for player, amount in hand.collected if player == "Hero"]
        assert hero_entries == [Decimal("15.82")], (
            f"Hero should collect only the $15.82 cash-out, got {hero_entries}"
        )
        assert hand.collectees["Hero"] == Decimal("15.82")

    def test_cash_out_fee_recorded(self) -> None:
        hand = self._process()
        assert hand.cashOutFees["Hero"] == Decimal("0.32")

    def test_net_profit_is_5_40(self) -> None:
        """Net profit = winnings (15.82) - committed (10.42) = 5.40."""
        hand = self._process()
        committed = Decimal("10.42")
        winnings = hand.collectees["Hero"]
        assert winnings - committed == Decimal("5.40")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
