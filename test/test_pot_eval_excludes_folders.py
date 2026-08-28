#!/usr/bin/env python3
"""Regression test: a folded player must not win a pot he paid into.

hand.pot.pots lists everyone who contributed to a pot, folders included. Feeding
all of them to the evaluator awarded the pot to whoever held the best cards --
even one who folded on the flop. The hero's cards are always known, so this fired
whenever the hero folded into a side-pot hand and happened to hold the winner.
The real winner was then credited with less than he collected and his rake came
out negative, which is how these hands were found in the wild.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import fpdb_3_legacy.DerivedStats as _derived_stats
from fpdb_3_legacy.DerivedStats import DerivedStats

# assembleHandsPots is a no-op without the native poker-eval engine (pypoker-eval),
# which isn't built in every environment, so these pot-award checks can't run there.
pytestmark = pytest.mark.skipif(
    _derived_stats.pokereval is None,
    reason="requires the native poker-eval engine (pypoker-eval)",
)

# Unibet hand 1615946806, Pot Limit Omaha. jejesat folds on the flop holding the
# best hand at the river; ASC2 wins €0.23 of a €0.25 pot, rake €0.02.
_BOARD = ["6h", "Kd", "3d", "As", "8s"]
_CARDS = {
    "ASC2": ["3s", "4d", "8d", "Kc"],
    "jejesat": ["9s", "8c", "Ac", "5d"],  # folded, yet beats ASC2 at showdown
    "papaetla": ["Ks", "Qc", "Jc", "Qh"],
}
_SAW_SHOWDOWN = {"ASC2": True, "papaetla": True, "jejesat": False}


def _hand():
    hand = MagicMock()
    hand.handid = "1615946806"
    hand.in_path = "-"
    hand.sitename = "Unibet"
    hand.gametype = {"category": "omahahi", "type": "ring", "currency": "EUR", "base": "hold"}
    hand.communityStreets = ["FLOP", "TURN", "RIVER"]
    hand.board = {"FLOP": _BOARD[:3], "TURN": [_BOARD[3]], "RIVER": [_BOARD[4]]}
    hand.runItTimes = 0
    hand.players = [[i, name, "500"] for i, name in enumerate(_CARDS, start=1)]
    hand.playerIds = {name: i for i, name in enumerate(_CARDS, start=1)}
    hand.pot.pots = [
        (Decimal("0.15"), ["ASC2", "jejesat", "papaetla"]),  # jejesat paid in, then folded
        (Decimal("0.10"), ["ASC2", "papaetla"]),
    ]
    hand.pot.common = {}
    hand.pot.stp = 0
    hand.collectees = {"ASC2": Decimal("0.23")}
    hand.collected = [["ASC2", "0.23"]]
    hand.rake = Decimal("0.02")
    hand.totalpot = Decimal("0.25")
    hand.cashedOut = False
    hand.adjustCollected = False
    hand.join_holecards = lambda p, asList=False: _CARDS[p]  # noqa: ARG005, N803
    return hand


def _stats(hand):
    stats = DerivedStats()
    for name in _CARDS:
        stats.handsplayers[name] = {
            "sawShowdown": _SAW_SHOWDOWN[name],
            "position": {"ASC2": 0, "papaetla": "B", "jejesat": "S"}[name],
            "winnings": 0,
            "rake": 0,
        }
    stats.assembleHandsPots(hand)
    return stats


def test_the_folded_player_wins_no_pot():
    stats = _stats(_hand())

    winners = {row[4] for row in stats.getHandsPots()}

    assert 2 not in winners  # playerId 2 is jejesat, who folded on the flop


def test_the_showdown_winner_takes_both_pots():
    stats = _stats(_hand())

    rows = stats.getHandsPots()

    assert {row[5] for row in rows} == {15, 10}  # main pot and side pot
    assert sum(row[6] for row in rows) == 23  # collected matches "ASC2 wins €0.23"


def test_rake_is_never_negative():
    # The winner used to be credited only with the side pot while collecting both,
    # so rake came out as the difference: negative.
    stats = _stats(_hand())

    assert sum(row[7] for row in stats.getHandsPots()) == 2  # "Rake €0.02"
    assert stats.handsplayers["ASC2"]["rake"] >= 0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
