#!/usr/bin/env python3
"""Tests for DerivedStats.calcGpStats and the GP HUD stats.

The "GenerationPoker" pack buckets a player's open (first-in raise) by size:
an open committing >= 40% of the player's own stack is an open-shove ("OS"),
otherwise a normal open ("2X"); a limp is the first voluntary preflop action
being a call in an unraised pot. The denominator is the open opportunity.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal as D
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(preflop):
    h = Mock()
    h.actionStreets = STREETS
    h.actions = {s: [] for s in STREETS}
    h.actions["PREFLOP"] = preflop
    return h


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {p: dict(v) for p, v in players.items()}
    return ds


def test_normal_open_is_2x():
    # raise to 3 with a 100-stack -> 3% of stack -> normal open (2X), not a shove.
    ds = _ds({"p1": {"startCash": 10000, "raiseFirstInChance": True, "raisedFirstIn": True}})
    ds.calcGpStats(_hand([("p1", "raises", D(2), D(3), D(1), False)]))
    p1 = ds.handsplayers["p1"]
    assert p1["cnt_gp_open_opp"] == 1
    assert p1["cnt_gp_2x"] == 1
    assert p1.get("cnt_gp_os", 0) == 0


def test_open_shove_is_os():
    # raise to 5 with a 10-stack -> 50% of stack -> open-shove (OS).
    ds = _ds({"p1": {"startCash": 1000, "raiseFirstInChance": True, "raisedFirstIn": True}})
    ds.calcGpStats(_hand([("p1", "raises", D(3), D(5), D(2), True)]))
    p1 = ds.handsplayers["p1"]
    assert p1["cnt_gp_os"] == 1
    assert p1.get("cnt_gp_2x", 0) == 0


def test_exactly_40pct_is_shove():
    # raise to 4 with a 10-stack -> exactly 40% -> shove (>= threshold).
    ds = _ds({"p1": {"startCash": 1000, "raiseFirstInChance": True, "raisedFirstIn": True}})
    ds.calcGpStats(_hand([("p1", "raises", D(2), D(4), D(2), False)]))
    assert ds.handsplayers["p1"]["cnt_gp_os"] == 1


def test_limp_first_call_in_unraised_pot():
    ds = _ds({"p1": {"startCash": 5000, "raiseFirstInChance": True}})
    ds.calcGpStats(_hand([("p1", "calls", D(2), False)]))
    p1 = ds.handsplayers["p1"]
    assert p1["cnt_gp_limp"] == 1
    assert p1.get("cnt_gp_2x", 0) == 0


def test_call_after_a_raise_is_not_a_limp():
    ds = _ds({
        "p1": {"startCash": 5000, "raiseFirstInChance": True, "raisedFirstIn": True},
        "p2": {"startCash": 5000},
    })
    ds.calcGpStats(_hand([("p1", "raises", D(2), D(3), D(1), False), ("p2", "calls", D(3), False)]))
    assert ds.handsplayers["p2"].get("cnt_gp_limp", 0) == 0  # cold-call, not a limp


def test_open_opp_without_acting():
    # had the chance to open (RFI) but folded -> opp counted, no open/limp.
    ds = _ds({"p1": {"startCash": 5000, "raiseFirstInChance": True}})
    ds.calcGpStats(_hand([("p1", "folds", 0)]))
    p1 = ds.handsplayers["p1"]
    assert p1["cnt_gp_open_opp"] == 1
    assert p1.get("cnt_gp_2x", 0) == 0
    assert p1.get("cnt_gp_limp", 0) == 0


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcGpStats(_hand([("p1", "raises", D(2), D(3), D(1), False)]))  # must not raise


def test_gp_hud_stats_format_and_registration():
    sd = {0: {"gp_open_opp": "20", "gp_2x": "12", "gp_os": "3", "gp_limp": "5"}}
    assert Stats.gp_2x(sd, 0)[1] == "60.0"
    assert Stats.gp_os(sd, 0)[1] == "15.0"
    assert Stats.gp_limp(sd, 0)[1] == "25.0"
    for fn in ("gp_2x", "gp_os", "gp_limp"):
        assert fn in Stats.STATLIST
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
