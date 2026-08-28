#!/usr/bin/env python3
"""Tests for DerivedStats.calcFaceRaise."""

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


def test_preflop_face_raise_after_raise():
    ds = _ds(["utg", "btn", "bb"])
    ds.calcFaceRaise(
        _hand(
            {
                "PREFLOP": [
                    ("utg", "raises", 30, None, False),
                    ("btn", "calls", 30, None, False),
                    ("bb", "folds", 0, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["btn"]["street0FaceRaise"] is True
    assert ds.handsplayers["bb"]["street0FaceRaise"] is True
    assert ds.handsplayers["utg"].get("street0FaceRaise", False) is False


def test_postflop_face_raise_only_after_raise_not_bet():
    ds = _ds(["p1", "p2", "p3"])
    ds.calcFaceRaise(
        _hand(
            {
                "FLOP": [
                    ("p1", "bets", 10, None, False),
                    ("p2", "calls", 10, None, False),
                    ("p3", "raises", 40, None, False),
                    ("p1", "calls", 30, None, False),
                ],
            },
        ),
    )

    assert ds.handsplayers["p1"]["street1FaceRaise"] is True
    assert ds.handsplayers["p2"].get("street1FaceRaise", False) is False
    assert ds.handsplayers["p3"].get("street1FaceRaise", False) is False


def test_turn_and_river_are_independent():
    ds = _ds(["p1", "p2"])
    ds.calcFaceRaise(
        _hand(
            {
                "TURN": [("p1", "raises", 20, None, False), ("p2", "calls", 20, None, False)],
                "RIVER": [("p2", "raises", 40, None, False), ("p1", "folds", 0, None, False)],
            },
        ),
    )

    assert ds.handsplayers["p2"]["street2FaceRaise"] is True
    assert ds.handsplayers["p1"]["street3FaceRaise"] is True
    assert "street1FaceRaise" not in ds.handsplayers["p1"]


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcFaceRaise(_hand({"FLOP": [("p1", "raises", 10, None, False)]}))
