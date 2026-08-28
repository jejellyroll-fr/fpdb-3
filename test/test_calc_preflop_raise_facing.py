#!/usr/bin/env python3
"""Tests for DerivedStats.calcPreflopRaiseFacing (PT4 pot-odds convention).

The raise faced is recorded as to_call / pot_at_decision, where the pot already
includes the raise; running pot + per-player investment are tracked across the
blinds and preflop actions.
"""

from __future__ import annotations

from decimal import Decimal as D
from unittest.mock import Mock

import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.DerivedStats import DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _run(streets):
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in {a[0] for v in streets.values() for a in v}}
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: [] for s in STREETS}
    for k, v in streets.items():
        hand.actions[k] = v
    ds.calcPreflopRaiseFacing(hand)
    return ds.handsplayers


def test_three_bet_four_bet_war():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),  # open to 3 (C=1, Rb=2)
            ("P2", "raises", D(6), D(9), D(3), False),  # 3-bet to 9 (C=3, Rb=6)
            ("P1", "raises", D(18), D(27), D(6), False),  # 4-bet to 27 (C=6, Rb=18)
        ],
    }
    hp = _run(streets)
    # P2 faces the open (2-bet): to_call 3 / pot 4.5 = 66.66%.
    assert hp["P2"]["cnt_p_2bet_facing"] == 1
    assert hp["P2"]["val_p_2bet_facing_bp"] == 6666
    # P1 faces the 3-bet: to_call 6 / pot 13.5 = 44.44%.
    assert hp["P1"]["cnt_p_3bet_facing"] == 1
    assert hp["P1"]["val_p_3bet_facing_bp"] == 4444
    # Generic raise_facing = most recent raise faced.
    assert hp["P1"]["val_p_raise_facing_bp"] == 4444
    assert hp["P2"]["val_p_raise_facing_bp"] == 6666


def test_limp_then_open():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D(1), False), ("BB", "big blind", D(2), False)],
        "PREFLOP": [
            ("P3", "calls", D(2), False),  # limp (not a raise -> no facing)
            ("P4", "raises", D(6), D(8), D(2), False),  # open to 8
            ("P3", "calls", D(6), False),  # faces the open
        ],
    }
    hp = _run(streets)
    # P3 faces the open: to_call 8-2 = 6 / pot 13 = 46.15%.
    assert hp["P3"]["cnt_p_2bet_facing"] == 1
    assert hp["P3"]["val_p_2bet_facing_bp"] == 4615
    # The limp itself is not a raise faced.
    assert hp["P4"].get("cnt_p_2bet_facing", 0) == 0


def test_no_raise_records_nothing():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D(1), False), ("BB", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(2), False), ("P2", "checks")],
    }
    hp = _run(streets)
    assert not hp["P1"].get("cnt_p_2bet_facing")
    assert not hp["P2"].get("cnt_p_raise_facing")


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {"PREFLOP": [("P1", "raises", D(2), D(3), D(1), False)]}
    ds.calcPreflopRaiseFacing(hand)  # must not raise


def test_preflop_facing_stats():
    sd = {0: {"p_3bet_facing_cnt": "2", "p_3bet_facing_bp": "10000"}}
    assert Stats.p_3bet_facing(sd, 0)[1] == "50.0"


def test_preflop_facing_no_data():
    for fn in ("p_2bet_facing", "p_3bet_facing", "p_4bet_facing", "p_5bet_facing", "p_raise_facing"):
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
        assert fn in Stats.STATLIST
