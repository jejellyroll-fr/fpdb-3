#!/usr/bin/env python3
"""Regression tests for DerivedStats.getBoardsList().

A board is a whole run of community cards, not a street. getBoardsList used to
return one entry per street, so assembleHandsPots handed poker-eval a one-card
"board" for the turn and again for the river -- "pyenum returned error code 1005"
(wrong # of board cards) -- and evaluated the pot on the flop alone. It also
divided the pot by the number of streets rather than the number of runs.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.DerivedStats import DerivedStats


def _hand(board, run_it_times=0, base="hold"):
    hand = MagicMock()
    hand.handid = "1558008046"
    hand.gametype = {"base": base}
    hand.communityStreets = ["FLOP", "TURN", "RIVER"]
    hand.board = board
    hand.runItTimes = run_it_times
    return hand


def _boards(hand):
    return DerivedStats.getBoardsList(DerivedStats.__new__(DerivedStats), hand)


def test_full_board_is_one_entry_of_five_cards():
    # Unibet hand 1558008046, a PLO pot whose board ran out to the river.
    hand = _hand({"FLOP": ["5h", "5d", "4d"], "TURN": ["Kd"], "RIVER": ["4s"]})

    assert _boards(hand) == [["5h", "5d", "4d", "Kd", "4s"]]


def test_board_stopping_at_the_flop_stays_one_entry():
    hand = _hand({"FLOP": ["5h", "5d", "4d"]})

    assert _boards(hand) == [["5h", "5d", "4d"]]


def test_run_it_twice_yields_one_board_per_run():
    # Each run is dealt onto its own streets; the pot is split across the runs.
    hand = _hand(
        {
            "FLOP1": ["5h", "5d", "4d"],
            "TURN1": ["Kd"],
            "RIVER1": ["4s"],
            "FLOP2": ["2c", "7h", "9d"],
            "TURN2": ["Ts"],
            "RIVER2": ["Jc"],
        },
        run_it_times=2,
    )

    assert _boards(hand) == [
        ["5h", "5d", "4d", "Kd", "4s"],
        ["2c", "7h", "9d", "Ts", "Jc"],
    ]


def test_run_it_twice_after_the_flop_reuses_the_shared_flop():
    """FTP archive hands agree to run it twice once the flop is out.

    Only the streets dealt twice are numbered, so FLOP1/FLOP2 stay empty and the
    flop lives in FLOP. Ignoring it left each run a two-card board that poker-eval
    rejected (error 1005), so the pot split was lost for the whole hand.
    """
    # FTP hand 26063988000 (PLO-6max-USD-25-50.201012.Run.it.Twice.Archive.Shallow).
    hand = _hand(
        {
            "FLOP": ["6c", "Qh", "3c"],
            "TURN": [],
            "RIVER": [],
            "FLOP1": [],
            "TURN1": ["3d"],
            "RIVER1": ["Th"],
            "FLOP2": [],
            "TURN2": ["9h"],
            "RIVER2": ["6h"],
        },
        run_it_times=2,
    )

    assert _boards(hand) == [
        ["6c", "Qh", "3c", "3d", "Th"],
        ["6c", "Qh", "3c", "9h", "6h"],
    ]


def test_non_hold_games_have_no_board():
    assert _boards(_hand({}, base="stud")) == []


def test_every_board_is_evaluable_by_poker_eval():
    # The point of the fix: poker-eval rejects a board of fewer than three cards.
    hand = _hand({"FLOP": ["5h", "5d", "4d"], "TURN": ["Kd"], "RIVER": ["4s"]})

    for board in _boards(hand):
        assert 3 <= len(board) <= 5


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
