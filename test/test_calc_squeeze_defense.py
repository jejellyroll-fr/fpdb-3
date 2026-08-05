#!/usr/bin/env python3
"""Tests for DerivedStats.calcSqueezeDefense and calcFaceLimpers (preflop).

A squeeze is a preflop 3-bet made after an open-raise *and* at least one
cold-call; the raiser and caller(s) then face the squeeze (PT4
flg_p_squeeze_def_opp). cnt_p_face_limpers counts the limpers a player faced
before their first preflop action.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(preflop, base="hold"):
    hand = Mock()
    hand.actionStreets = STREETS
    hand.gametype = {"base": base}
    hand.actions = {s: [] for s in STREETS}
    hand.actions["PREFLOP"] = preflop
    return hand


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in players}
    return ds


# ---------------------------------------------------------------------------
# calcFaceLimpers
# ---------------------------------------------------------------------------
def test_face_limpers_counts_limps_before_first_action():
    # p1 limps, p2 limps, p3 raises, p4 cold-calls, p5 folds.
    ds = _ds(["p1", "p2", "p3", "p4", "p5"])
    ds.calcFaceLimpers(
        _hand(
            [
                ("p1", "calls", 10),
                ("p2", "calls", 10),
                ("p3", "raises", 40),
                ("p4", "calls", 40),
                ("p5", "folds", 0),
            ],
        ),
    )
    faced = [ds.handsplayers[p].get("street0_FaceLimpers", 0) for p in ["p1", "p2", "p3", "p4", "p5"]]
    # PT4: limpers are only counted while the pot is unraised at your turn.
    # p4/p5 first act after p3's raise -> they faced a raise, not limpers (0).
    assert faced == [0, 1, 2, 0, 0]


def test_face_limpers_zero_when_pot_opened_with_raise():
    ds = _ds(["p1", "p2"])
    ds.calcFaceLimpers(_hand([("p1", "raises", 30), ("p2", "calls", 30)]))
    assert ds.handsplayers["p1"].get("street0_FaceLimpers", 0) == 0
    assert ds.handsplayers["p2"].get("street0_FaceLimpers", 0) == 0


# ---------------------------------------------------------------------------
# calcSqueezeDefense
# ---------------------------------------------------------------------------
def test_squeeze_defense_opp_and_fold():
    # p1 raises, p2 cold-calls, p3 squeezes (3-bet), p1 folds, p2 calls.
    ds = _ds(["p1", "p2", "p3"])
    ds.calcSqueezeDefense(
        _hand(
            [
                ("p1", "raises", 30),
                ("p2", "calls", 30),
                ("p3", "raises", 120),
                ("p1", "folds", 0),
                ("p2", "calls", 90),
            ],
        ),
    )
    # Original raiser folded to the squeeze.
    assert ds.handsplayers["p1"]["street0_FoldToSqueezeChance"] is True
    assert ds.handsplayers["p1"]["street0_FoldToSqueezeDone"] is True
    # Cold-caller faced the squeeze but defended (called) -> no fold.
    assert ds.handsplayers["p2"]["street0_FoldToSqueezeChance"] is True
    assert ds.handsplayers["p2"].get("street0_FoldToSqueezeDone", False) is False
    # The squeezer itself is not a defender.
    assert "street0_FoldToSqueezeChance" not in ds.handsplayers["p3"]


def test_three_bet_without_caller_is_not_a_squeeze():
    # p1 raises, p2 3-bets immediately (no cold-caller) -> not a squeeze.
    ds = _ds(["p1", "p2"])
    ds.calcSqueezeDefense(_hand([("p1", "raises", 30), ("p2", "raises", 90), ("p1", "folds", 0)]))
    assert "street0_FoldToSqueezeChance" not in ds.handsplayers["p1"]
    assert "street0_FoldToSqueezeChance" not in ds.handsplayers["p2"]


def test_squeeze_chance_recorded_once_per_defender():
    # Defender acts twice after the squeeze; chance/done captured on first only.
    ds = _ds(["p1", "p2", "p3"])
    ds.calcSqueezeDefense(
        _hand(
            [
                ("p1", "raises", 30),
                ("p2", "calls", 30),
                ("p3", "raises", 120),
                ("p1", "calls", 90),  # defends first
                ("p2", "folds", 0),
                ("p1", "raises", 300),  # later re-raise must not flip done
            ],
        ),
    )
    assert ds.handsplayers["p1"]["street0_FoldToSqueezeChance"] is True
    assert ds.handsplayers["p1"].get("street0_FoldToSqueezeDone", False) is False


def test_no_handsplayers_is_noop():
    ds = DerivedStats()  # no handsplayers attribute
    ds.calcSqueezeDefense(_hand([("p1", "raises", 30)]))  # must not raise
    ds.calcFaceLimpers(_hand([("p1", "calls", 10)]))  # must not raise
