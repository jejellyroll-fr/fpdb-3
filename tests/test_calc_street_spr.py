#!/usr/bin/env python3
"""Tests for DerivedStats.calcStreetSPR and the {f,t,r}_spr HUD stats.

SPR = effective stack / pot entering a street. The pot entering a street is the
chips committed so far; remaining = startCash - committed; effective stack =
min(own remaining, deepest active opponent). Stored as count + SPR*100.
"""

from __future__ import annotations

from decimal import Decimal as D
from unittest.mock import Mock

import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _run(streets, start_cash):
    ds = DerivedStats()
    ds.handsplayers = {p: {"startCash": int(100 * start_cash[p])} for p in start_cash}
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: [] for s in STREETS}
    for k, v in streets.items():
        hand.actions[k] = v
    ds.calcStreetSPR(hand)
    return ds.handsplayers


def test_flop_and_turn_spr_heads_up():
    # P1 stack 50, P2 stack 100. SB 1 / BB 2.
    streets = {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        # P1 completes (calls 1 more -> 2 total), P2 checks. Pot entering flop = 4.
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
        # P2 bets 3, P1 calls 3. Pot entering turn = 4 + 6 = 10.
        "FLOP": [("P1", "checks"), ("P2", "bets", D(3), False), ("P1", "calls", D(3), False)],
        "TURN": [("P1", "checks"), ("P2", "checks")],
    }
    hp = _run(streets, {"P1": D(50), "P2": D(100)})
    # Flop: remaining P1=48, P2=98 -> eff 48; pot 4 -> SPR 12.0 -> 1200.
    assert hp["P1"]["cnt_f_spr"] == 1
    assert hp["P1"]["val_f_spr"] == 1200
    assert hp["P2"]["val_f_spr"] == 1200
    # Turn: remaining P1=45, P2=95 -> eff 45; pot 10 -> SPR 4.5 -> 450.
    assert hp["P1"]["val_t_spr"] == 450
    assert hp["P2"]["val_t_spr"] == 450


def test_effective_stack_is_capped_by_shorter():
    # Short stack caps the effective stack / SPR.
    streets = {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
        "FLOP": [("P1", "checks"), ("P2", "checks")],
    }
    # P1 only 10 deep, P2 100. Pot entering flop = 4. remaining P1=8, P2=98 -> eff 8 -> SPR 2.0.
    hp = _run(streets, {"P1": D(10), "P2": D(100)})
    assert hp["P1"]["val_f_spr"] == 200
    assert hp["P2"]["val_f_spr"] == 200  # symmetric: deepest opponent for P2 is P1=8


def test_no_flop_no_spr():
    streets = {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "folds")],
    }
    hp = _run(streets, {"P1": D(50), "P2": D(100)})
    assert not hp["P1"].get("cnt_f_spr")
    assert not hp["P2"].get("cnt_f_spr")


def test_single_active_player_skipped():
    # Only one player acts on the flop -> no opponent -> no SPR.
    streets = {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
        "FLOP": [("P1", "bets", D(3), False)],
    }
    hp = _run(streets, {"P1": D(50), "P2": D(100)})
    assert not hp["P1"].get("cnt_f_spr")


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {"FLOP": [("P1", "bets", D(3), False)]}
    ds.calcStreetSPR(hand)  # must not raise


def test_spr_stats():
    sd = {0: {"f_spr_cnt": "2", "f_spr_val": "700"}}  # (700/2)/100 = 3.5
    res = Stats.f_spr(sd, 0)
    assert res[1] == "3.5"
    assert res[2] == "fSPR=3.5"
    assert res[5] == "avg flop SPR"


def test_spr_no_data():
    for fn in ("f_spr", "t_spr", "r_spr"):
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
        assert fn in Stats.STATLIST
