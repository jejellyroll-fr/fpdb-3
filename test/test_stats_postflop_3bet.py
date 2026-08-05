#!/usr/bin/env python3
"""Tests for the postflop per-street 3-bet HUD stats (three_B_flop/turn/river)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fpdb_3_legacy.Stats as Stats


def test_flop_3bet_percentage():
    sd = {7: {"fl3b_opp": "8", "fl3b": "2"}}
    res = Stats.three_B_flop(sd, 7)
    assert abs(res[0] - 0.25) < 1e-9
    assert res[1] == "25.0"
    assert res[2] == "F3B=25.0%"
    assert res[4] == "(2/8)"
    assert res[5] == "% 3 bet flop"


def test_turn_and_river_use_their_keys():
    sd = {1: {"tn3b_opp": "4", "tn3b": "1", "rv3b_opp": "2", "rv3b": "2"}}
    assert Stats.three_B_turn(sd, 1)[1] == "25.0"
    assert Stats.three_B_river(sd, 1)[1] == "100.0"


def test_no_opportunity_returns_no_data():
    sd = {1: {"fl3b_opp": "0", "fl3b": "0"}}
    # format_no_data_stat returns the dash sentinel in the formatted slot.
    assert Stats.three_B_flop(sd, 1)[1] in ("-", "NA")


def test_missing_keys_do_not_raise():
    assert Stats.three_B_flop({1: {}}, 1)[1] in ("-", "NA")


def test_fold_to_3bet_percentage():
    sd = {3: {"ff3b_opp": "5", "ff3b": "2", "ft3b_opp": "4", "ft3b": "1", "fr3b_opp": "0", "fr3b": "0"}}
    assert Stats.fold_to_three_B_flop(sd, 3)[2] == "FF3B=40.0%"
    assert Stats.fold_to_three_B_turn(sd, 3)[1] == "25.0"
    assert Stats.fold_to_three_B_river(sd, 3)[1] in ("-", "NA")  # no opportunity


def test_discovered_as_valid_hud_stats():
    valid = Stats.get_valid_stats()
    for name in (
        "three_B_flop",
        "three_B_turn",
        "three_B_river",
        "fold_to_three_B_flop",
        "fold_to_three_B_turn",
        "fold_to_three_B_river",
    ):
        assert name in valid
    assert "_postflop_3bet" not in Stats.STATLIST  # helper stays private
