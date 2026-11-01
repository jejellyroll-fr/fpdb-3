#!/usr/bin/env python3
"""Tests for DerivedStats.calcSpecialBlinds and the straddle HUD stat.

Maps fpdb blind actions to PT4 flags: ``straddle`` -> flg_blind_k,
``secondsb``/``both`` -> flg_blind_ds. fpdb has no standalone dead-big-blind
action, so flg_blind_db is never set here.
"""

from __future__ import annotations

from unittest.mock import Mock

import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(blinds):
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: [] for s in STREETS}
    hand.actions["BLINDSANTES"] = blinds
    return hand


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in players}
    return ds


def test_straddle_flag_set():
    ds = _ds(["p1", "p2", "p3"])
    ds.calcSpecialBlinds(
        _hand([("p1", "small blind", 1), ("p2", "big blind", 2), ("p3", "straddle", 4)]),
    )
    assert ds.handsplayers["p3"]["flg_blind_k"] is True
    assert ds.handsplayers["p3"].get("flg_blind_ds", False) is False
    # Regular blinds are not special.
    assert ds.handsplayers["p1"].get("flg_blind_k", False) is False
    assert ds.handsplayers["p2"].get("flg_blind_k", False) is False


def test_dead_small_blind_secondsb_and_returning_both():
    # secondsb is always a dead SB; a "both" after a live BB is a returning
    # player posting a dead SB + live BB.
    ds = _ds(["SB", "BB", "p1", "p2"])
    ds.calcSpecialBlinds(
        _hand([("SB", "small blind", 1), ("BB", "big blind", 2),
               ("p1", "secondsb", 1), ("p2", "both", 3)]),
    )
    assert ds.handsplayers["p1"]["flg_blind_ds"] is True
    assert ds.handsplayers["p2"]["flg_blind_ds"] is True  # "both" after a BB


def test_both_that_is_just_the_bb_is_not_a_dead_sb():
    # Some converters tag a plain BB as "both"; with no prior BB it is the live
    # BB, not a dead small blind.
    ds = _ds(["p1", "p2"])
    ds.calcSpecialBlinds(_hand([("p1", "small blind", 1), ("p2", "both", 2)]))
    assert ds.handsplayers["p2"].get("flg_blind_ds", False) is False


def test_dead_big_blind_from_second_big_blind():
    # A second big blind (returning player) is a dead big blind.
    ds = _ds(["SB", "BB", "p3"])
    ds.calcSpecialBlinds(
        _hand([("SB", "small blind", 1), ("BB", "big blind", 2), ("p3", "big blind", 2)]),
    )
    assert ds.handsplayers["p3"]["flg_blind_db"] is True
    assert ds.handsplayers["BB"].get("flg_blind_db", False) is False  # first BB is live


def test_no_handsplayers_is_noop():
    ds = DerivedStats()  # no handsplayers attribute
    ds.calcSpecialBlinds(_hand([("p1", "straddle", 4)]))  # must not raise


def test_straddle_stat_percentage():
    sd = {0: {"n": "100", "straddle_done": "5"}}
    res = Stats.straddle(sd, 0)
    assert res[1] == "5.0"
    assert res[2] == "Str=5.0%"
    assert res[4] == "(5/100)"
    assert res[5] == "% straddle"


def test_straddle_stat_no_data():
    assert Stats.straddle({0: {"n": "0", "straddle_done": "0"}}, 0)[1] in ("-", "NA")
    assert Stats.straddle({0: {}}, 0)[1] in ("-", "NA")
    assert "straddle" in Stats.STATLIST
