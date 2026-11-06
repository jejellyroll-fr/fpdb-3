#!/usr/bin/env python3
"""Tests for DerivedStats.calcPostflopFirstRaise."""

from __future__ import annotations

from unittest.mock import Mock

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


def test_first_flop_raise_only_marks_first_raiser():
    ds = _ds(["p1", "p2", "p3"])
    ds.calcPostflopFirstRaise(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                    ("p3", "raises", 90, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p2"]["street1FirstRaise"] is True
    assert ds.handsplayers["p1"].get("street1FirstRaise", False) is False
    assert ds.handsplayers["p3"].get("street1FirstRaise", False) is False


def test_turn_and_river_are_independent():
    ds = _ds(["p1", "p2", "p3"])
    ds.calcPostflopFirstRaise(
        _hand(
            {
                "TURN": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "raises", 30, None, False),
                ],
                "RIVER": [
                    ("p1", "bets", 20, None, False),
                    ("p3", "raises", 60, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p2"]["street2FirstRaise"] is True
    assert ds.handsplayers["p3"]["street3FirstRaise"] is True
    assert "street1FirstRaise" not in ds.handsplayers["p2"]


def test_no_raise_leaves_flags_unset():
    ds = _ds(["p1", "p2"])
    ds.calcPostflopFirstRaise(
        _hand({"FLOP": [("p1", "bets", 10, None, False), ("p2", "calls", 10, None, False)]}),
    )

    assert "street1FirstRaise" not in ds.handsplayers["p1"]
    assert "street1FirstRaise" not in ds.handsplayers["p2"]


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcPostflopFirstRaise(_hand({"FLOP": [("p1", "raises", 10, None, False)]}))
