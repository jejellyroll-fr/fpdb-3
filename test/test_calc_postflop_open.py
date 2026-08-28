#!/usr/bin/env python3
"""Tests for DerivedStats.calcPostflopOpen."""

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


def test_flop_open_after_checks():
    ds = _ds(["bb", "btn", "co"])
    ds.calcPostflopOpen(
        _hand(
            {
                "FLOP": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 10, None, False),
                    ("co", "folds", 0, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["bb"]["street1OpenChance"] is True
    assert ds.handsplayers["bb"].get("street1OpenDone", False) is False
    assert ds.handsplayers["btn"]["street1OpenChance"] is True
    assert ds.handsplayers["btn"]["street1OpenDone"] is True
    assert "street1OpenChance" not in ds.handsplayers["co"]


def test_all_checks_get_open_chances_without_done():
    ds = _ds(["bb", "btn"])
    ds.calcPostflopOpen(
        _hand(
            {
                "FLOP": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "checks", 0, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["bb"]["street1OpenChance"] is True
    assert ds.handsplayers["btn"]["street1OpenChance"] is True
    assert ds.handsplayers["bb"].get("street1OpenDone", False) is False
    assert ds.handsplayers["btn"].get("street1OpenDone", False) is False


def test_turn_and_river_open_are_independent():
    ds = _ds(["p1", "p2"])
    ds.calcPostflopOpen(
        _hand(
            {
                "TURN": [("p1", "bets", 10, None, False)],
                "RIVER": [
                    ("p1", "checks", 0, None, False),
                    ("p2", "bets", 20, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p1"]["street2OpenDone"] is True
    assert ds.handsplayers["p1"]["street3OpenChance"] is True
    assert ds.handsplayers["p2"]["street3OpenDone"] is True
    assert "street1OpenChance" not in ds.handsplayers["p1"]


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcPostflopOpen(_hand({"FLOP": [("p1", "bets", 10, None, False)]}))
