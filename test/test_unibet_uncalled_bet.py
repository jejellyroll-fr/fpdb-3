#!/usr/bin/env python3
"""Regression tests for giving a Unibet player back the bet nobody called.

re_Uncalled expected PokerStars' shape, "Uncalled bet (€0.10) returned to
venomjr", while Unibet writes "Uncalled bet returned to venomjr: €0.10". It
matched none of the hands on hand -- and nothing ever called it either, so the
money was never taken back out of the pot. A hand whose "Total pot" reads €0.35
was assembled as €0.45, its main pot went unattributed, and the winner's rake
came out negative.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.UnibetToFpdb import Unibet


def _uncalled(line: str) -> tuple[str, str] | None:
    match = Unibet.re_Uncalled.search(line)
    return (match.group("PNAME"), match.group("BET")) if match else None


def test_reads_the_returned_bet_and_its_owner():
    assert _uncalled("Uncalled bet returned to venomjr: €0.10") == ("venomjr", "0.10")


def test_a_bracketed_account_name_is_kept_whole():
    line = "Uncalled bet returned to jejesat[Unibet_28204e083c0fb55a]: €0.29"

    assert _uncalled(line) == ("jejesat[Unibet_28204e083c0fb55a]", "0.29")


def test_tournament_chips_have_no_currency_symbol():
    line = "Uncalled bet returned to jejesat[Unibet_28204e083c0fb55a]: 690"

    assert _uncalled(line) == ("jejesat[Unibet_28204e083c0fb55a]", "690")


def test_the_pokerstars_shape_is_not_what_unibet_writes():
    # The pattern this replaces. Kept as a test so the old shape cannot creep back
    # in unnoticed: no Unibet hand is written this way.
    assert _uncalled("Uncalled bet (€0.10) returned to venomjr") is None


@pytest.mark.parametrize(
    "line",
    [
        "venomjr: bets €0.10",
        "venomjr wins €0.33",
        "Seat 3: venomjr: bet €0.20 and won €0.43, net result: €0.23",
    ],
)
def test_ordinary_lines_are_not_a_returned_bet(line):
    assert _uncalled(line) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
