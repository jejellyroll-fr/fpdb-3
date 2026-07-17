#!/usr/bin/env python3
"""Regression tests for what a Unibet seat collects from the pot.

Unibet states both figures on one summary line:

    Seat 2: cla17: bet €0.15 and won €0.33, net result: €0.18

re_CollectPot captured the net result -- the profit -- as the pot collected. That
charged the bet twice, once by the site and once again by fpdb, so winnings came
out understated (0.18 instead of 0.33) and rake absurd (0.17 instead of 0.02).
The line also went unmatched whenever the net was negative, because the leading
"-" is outside the captured character class, silently dropping the collect of any
player who won a pot smaller than their own bet.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.UnibetToFpdb import Unibet


def _pot(line: str) -> str | None:
    match = Unibet.re_CollectPot.search(line)
    return match.group("POT") if match else None


def test_captures_the_pot_won_not_the_net_result():
    line = "Seat 2: cla17: bet €0.15 and won €0.33, net result: €0.18"

    assert _pot(line) == "0.33"


def test_captures_a_pot_smaller_than_the_bet():
    # Net result is negative here; the old pattern could not match it at all, so a
    # real winner collected nothing.
    line = "Seat 1: joueur: bet €0.20 and won €0.05, net result: €-0.15"

    assert _pot(line) == "0.05"


def test_tournament_chip_counts_have_no_currency_symbol():
    line = "Seat 5: jejesat: bet 150 and won 300, net result: 150"

    assert _pot(line) == "300"


@pytest.mark.parametrize(
    "line",
    [
        "Seat 3: Savy-95: bet €0.05 and won €0, net result: €-0.05",
        "Seat 4: jejesat[Unibet_28204e083c0fb55a]: bet €0.15 and won €0, net result: €-0.15",
    ],
)
def test_a_seat_that_won_nothing_reports_a_zero_pot(line):
    # readCollectPot drops these rather than putting a zero collectee on the hand.
    assert _pot(line) == "0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
