#!/usr/bin/env python3
"""Tests for DerivedStats.calcFacedAllin and the fold-to-all-in HUD stat.

A player faces an all-in when an opponent's all-in bet/raise puts them to a
decision (PT4 enum_face_allin), modelled as a chance/done boolean pair.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(streets):
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: [] for s in STREETS}
    for k, v in streets.items():
        hand.actions[k] = v
    return hand


def _ds(streets):
    players = {a[0] for acts in streets.values() for a in acts}
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in players}
    return ds


def test_fold_and_call_facing_preflop_shove():
    streets = {"PREFLOP": [("P1", "raises", 100, True), ("P2", "folds"), ("P3", "calls", 100, True)]}
    ds = _ds(streets)
    ds.calcFacedAllin(_hand(streets))
    assert ds.handsplayers["P2"]["flg_faced_allin"] is True
    assert ds.handsplayers["P2"]["flg_fold_to_allin"] is True
    # P3 faced the shove but called -> chance without a fold.
    assert ds.handsplayers["P3"]["flg_faced_allin"] is True
    assert ds.handsplayers["P3"].get("flg_fold_to_allin", False) is False
    # The shover itself did not "face" an all-in.
    assert ds.handsplayers["P1"].get("flg_faced_allin", False) is False


def test_no_allin_means_no_flags():
    streets = {"PREFLOP": [("P1", "raises", 10, False), ("P2", "calls", 10, False)]}
    ds = _ds(streets)
    ds.calcFacedAllin(_hand(streets))
    assert ds.handsplayers["P1"].get("flg_faced_allin", False) is False
    assert ds.handsplayers["P2"].get("flg_faced_allin", False) is False


def test_allin_on_a_later_street():
    streets = {
        "PREFLOP": [("P1", "raises", 10, False), ("P2", "calls", 10, False)],
        "TURN": [("P1", "bets", 50, True), ("P2", "folds")],
    }
    ds = _ds(streets)
    ds.calcFacedAllin(_hand(streets))
    assert ds.handsplayers["P2"]["flg_faced_allin"] is True
    assert ds.handsplayers["P2"]["flg_fold_to_allin"] is True


def test_only_aggressive_allin_creates_a_facing_spot():
    # P2's all-in is a *call*, not aggression -> P1 (who acted first) and the
    # caller do not record a faced-all-in from a mere call.
    streets = {"PREFLOP": [("P1", "raises", 10, False), ("P2", "calls", 10, True)]}
    ds = _ds(streets)
    ds.calcFacedAllin(_hand(streets))
    assert ds.handsplayers["P1"].get("flg_faced_allin", False) is False
    assert ds.handsplayers["P2"].get("flg_faced_allin", False) is False


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcFacedAllin(_hand({"PREFLOP": [("P1", "raises", 100, True)]}))  # must not raise


def test_fold_to_allin_stat():
    sd = {0: {"faced_allin": "6", "fold_allin": "4"}}
    res = Stats.fold_to_allin(sd, 0)
    assert res[1] == "66.7"
    assert res[2] == "FvAI=66.7%"
    assert res[4] == "(4/6)"
    assert res[5] == "% fold to all-in"


def test_fold_to_allin_no_data():
    assert Stats.fold_to_allin({0: {"faced_allin": "0", "fold_allin": "0"}}, 0)[1] in ("-", "NA")
    assert Stats.fold_to_allin({0: {}}, 0)[1] in ("-", "NA")
    assert "fold_to_allin" in Stats.STATLIST
