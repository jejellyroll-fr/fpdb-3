#!/usr/bin/env python3
"""Tests for postflop raise-faced sizing (DerivedStats.calcPostflopRaiseFacing).

PT4 pot-odds convention: to_call / pot_at_decision. A bet is level 1, a raise
level 2 (2-bet), a re-raise level 3, etc. Running pot carried across streets.
"""

from __future__ import annotations

from decimal import Decimal as D
from unittest.mock import Mock

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
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in {a[0] for v in streets.values() for a in v}}
    return ds


def _limped():
    # Pot entering the flop = 4.
    return {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
    }


def test_flop_raise_war_levels():
    streets = _limped()
    # Pot 4. P1 bets 4, P2 raises to 16, P1 re-raises to 60, P2 calls.
    streets["FLOP"] = [
        ("P1", "bets", D(4), False),
        ("P2", "raises", D(12), D(16), D(4), False),
        ("P1", "raises", D(44), D(60), D(12), False),  # C=12 (to-call 16 over own 4)
        ("P2", "calls", D(44), False),
    ]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    # P2 faces the bet (level 1): 4 / (4+4) = 50%.
    assert ds.handsplayers["P2"]["val_f_bet_facing_bp"] == 5000
    # P1 faces the 2-bet: to_call 12 / pot 24 = 50%.
    assert ds.handsplayers["P1"]["cnt_f_2bet_facing"] == 1
    assert ds.handsplayers["P1"]["val_f_2bet_facing_bp"] == 5000
    # P2 faces the 3-bet: to_call 44 / pot 80 = 55%.
    assert ds.handsplayers["P2"]["cnt_f_3bet_facing"] == 1
    assert ds.handsplayers["P2"]["val_f_3bet_facing_bp"] == 5500


def test_turn_level_independent_from_flop():
    streets = _limped()
    streets["FLOP"] = [("P1", "checks"), ("P2", "checks")]
    # Turn pot 4: P1 bets 4, P2 raises to 16, P1 folds.
    streets["TURN"] = [
        ("P1", "bets", D(4), False),
        ("P2", "raises", D(12), D(16), D(4), False),
        ("P1", "folds"),
    ]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    # P1 faces the turn 2-bet: to_call 12 / pot 24 = 50%.
    assert ds.handsplayers["P1"]["cnt_t_2bet_facing"] == 1
    assert ds.handsplayers["P1"]["val_t_2bet_facing_bp"] == 5000
    assert not ds.handsplayers["P1"].get("cnt_f_2bet_facing")


def test_postflop_raise_facing_stats():
    sd = {0: {"f_2bet_facing_cnt": "2", "f_2bet_facing_bp": "10000"}}
    res = Stats.f_2bet_facing(sd, 0)
    assert res[1] == "50.0"
    assert res[5] == "avg flop 2bet faced (% pot)"


def test_postflop_raise_facing_no_data():
    for fn in ("f_2bet_facing", "f_3bet_facing", "f_4bet_facing",
               "t_2bet_facing", "t_3bet_facing", "t_4bet_facing",
               "r_2bet_facing", "r_3bet_facing", "r_4bet_facing"):
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
        assert fn in Stats.STATLIST
