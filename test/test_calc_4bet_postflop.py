#!/usr/bin/env python3
"""Tests for DerivedStats.calc4BetPostflop."""

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


def test_flop_4bet_made_and_fold_to_4bet():
    ds = _ds(["p1", "p2"])
    ds.calc4BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p1", "raises", 90, None, False),
                    ("p2", "raises", 210, None, False),
                    ("p1", "folds", 0, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p2"]["street1_4BChance"] is True
    assert ds.handsplayers["p2"]["street1_4BDone"] is True
    assert ds.handsplayers["p1"]["street1_FoldTo4BChance"] is True
    assert ds.handsplayers["p1"]["street1_FoldTo4BDone"] is True


def test_flop_4bet_chance_not_taken():
    ds = _ds(["p1", "p2"])
    ds.calc4BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p1", "raises", 90, None, False),
                    ("p2", "calls", 60, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p2"]["street1_4BChance"] is True
    assert ds.handsplayers["p2"].get("street1_4BDone", False) is False
    assert "street1_FoldTo4BChance" not in ds.handsplayers["p1"]


def test_no_4bet_when_only_3bet_lands():
    ds = _ds(["p1", "p2"])
    ds.calc4BetPostflop(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p1", "raises", 90, None, False),
                ],
            },
        ),
    )

    assert "street1_4BChance" not in ds.handsplayers["p1"]
    assert "street1_4BChance" not in ds.handsplayers["p2"]


def test_turn_and_river_independent():
    ds = _ds(["p1", "p2"])
    war = [
        ("p1", "bets", 10, None, False),
        ("p2", "raises", 30, None, False),
        ("p1", "raises", 90, None, False),
        ("p2", "raises", 210, None, False),
    ]
    ds.calc4BetPostflop(_hand({"TURN": war, "RIVER": war}))

    assert ds.handsplayers["p2"]["street2_4BDone"] is True
    assert ds.handsplayers["p2"]["street3_4BDone"] is True
    assert "street1_4BDone" not in ds.handsplayers["p2"]


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calc4BetPostflop(_hand({"FLOP": [("p1", "bets", 10, None, False)]}))
