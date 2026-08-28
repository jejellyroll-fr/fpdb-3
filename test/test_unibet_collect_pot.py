#!/usr/bin/env python3
"""Regression tests for what a Unibet player takes out of the pot.

Unibet's summary line states two figures, neither of which is the pot:

    venomjr wins €0.33                                            <- the pot
    Total pot €0.35 Rake €0.02
    Uncalled bet returned to venomjr: €0.10
    Seat 3: venomjr: bet €0.20 and won €0.43, net result: €0.23

"net result" is profit: using it charged the bet twice and understated winnings.
"won" counts the player's own uncalled bet back in (0.33 + 0.10 = 0.43), so it
can exceed the pot and drive the computed rake negative. Only the "wins" lines
add up to the pot, and they are what re_CollectPot reads.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.UnibetToFpdb import Unibet


def _collected(line: str) -> tuple[str, str] | None:
    match = Unibet.re_CollectPot.search(line)
    return (match.group("PNAME"), match.group("POT")) if match else None


def test_reads_the_pot_won_not_the_inflated_summary():
    assert _collected("venomjr wins €0.33") == ("venomjr", "0.33")


def test_tournament_chip_counts_have_no_currency_symbol():
    assert _collected("DrikC79 wins 380") == ("DrikC79", "380")


def test_a_split_pot_names_the_pot_it_came_from():
    assert _collected("cla17 wins €0.07 from main pot") == ("cla17", "0.07")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("jejesat[Unibet_28204e083c0fb55a] wins main pot, 150", ("jejesat[Unibet_28204e083c0fb55a]", "150")),
        ("jejesat[Unibet_28204e083c0fb55a] wins side pot #1, 660", ("jejesat[Unibet_28204e083c0fb55a]", "660")),
    ],
)
def test_tournament_side_pots_put_the_amount_last(line, expected):
    assert _collected(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        # None of these is a pot, and each contains " wins " or " won ".
        "Hero wins the tournament and receives €12.50 - congratulations!",
        "APTEM-89 wins the $0.27 bounty for eliminating Hero",
        "Amsterdam71 wins $19.90 for eliminating MuKoJla and their own bounty increases by $19.89 to $155.32",
        "jejesat[Unibet_28204e083c0fb55a] finished the tournament in 1st place, and won €4",
        # The summary line itself: its "won" is the figure that broke the rake.
        "Seat 3: venomjr: bet €0.20 and won €0.43, net result: €0.23",
    ],
)
def test_lines_that_are_not_a_collected_pot(line):
    assert _collected(line) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
