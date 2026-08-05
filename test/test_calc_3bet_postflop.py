#!/usr/bin/env python3
"""Tests for DerivedStats.calc3BetPostflop — postflop per-street 3-bet.

A postflop 3-bet is the third level of aggression on a street
(bet -> raise -> re-raise), mirroring PT4's flg_f/t/r_3bet. These tests lock in
the chance/done and fold-to-3bet bookkeeping for flop (street1), turn (street2)
and river (street3).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(actions):
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: actions.get(s, []) for s in STREETS}
    return hand


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in players}
    return ds


def test_flop_3bet_made_and_fold_to_3bet():
    # p1 bets, p2 raises, p1 re-raises (3-bet), p2 folds.
    ds = _ds(["p1", "p2"])
    ds.calc3BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p1", "raises", 90, None, False),
                    ("p2", "folds", 0, None, False),
                ],
            },
        ),
    )
    # p1 faced p2's raise and re-raised => 3-bet done.
    assert ds.handsplayers["p1"]["street1_3BChance"] is True
    assert ds.handsplayers["p1"]["street1_3BDone"] is True
    # p2 (the level-2 raiser) faced the re-raise and folded.
    assert ds.handsplayers["p2"]["street1_FoldTo3BChance"] is True
    assert ds.handsplayers["p2"]["street1_FoldTo3BDone"] is True
    # p2 never had a 3-bet chance itself (it made the raise, not a re-raise).
    assert "street1_3BChance" not in ds.handsplayers["p2"]


def test_flop_3bet_chance_not_taken():
    # p1 bets, p2 raises, p1 just calls => chance but not done.
    ds = _ds(["p1", "p2"])
    ds.calc3BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p1", "calls", 20, None, False),
                ],
            },
        ),
    )
    assert ds.handsplayers["p1"]["street1_3BChance"] is True
    assert ds.handsplayers["p1"].get("street1_3BDone", False) is False
    # No re-raise landed, so p2 never faced fold-to-3bet.
    assert "street1_FoldTo3BChance" not in ds.handsplayers["p2"]


def test_no_3bet_when_only_bet_and_call():
    ds = _ds(["p1", "p2"])
    ds.calc3BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "calls", 10, None, False),
                ],
            },
        ),
    )
    assert "street1_3BChance" not in ds.handsplayers["p1"]
    assert "street1_3BChance" not in ds.handsplayers["p2"]


def test_turn_and_river_independent():
    # 3-bet on the turn (street2) and river (street3), nothing on the flop.
    ds = _ds(["p1", "p2"])
    war = [
        ("p1", "bets", 10, None, False),
        ("p2", "raises", 30, None, False),
        ("p1", "raises", 90, None, False),
        ("p2", "calls", 60, None, False),
    ]
    ds.calc3BetPostflop(_hand({"TURN": war, "RIVER": war}))
    assert ds.handsplayers["p1"]["street2_3BDone"] is True
    assert ds.handsplayers["p1"]["street3_3BDone"] is True
    # Flop saw no action.
    assert "street1_3BDone" not in ds.handsplayers["p1"]


def test_no_handsplayers_is_noop():
    ds = DerivedStats()  # no handsplayers attribute
    ds.calc3BetPostflop(_hand({"FLOP": [("p1", "bets", 10, None, False)]}))  # must not raise
