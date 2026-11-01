#!/usr/bin/env python3
"""Tests for DerivedStats.calcRaiseMade and the {p,f,t,r}_raise_made HUD stats.

Records the player's first raise per street as basis points of the pot before
that raise (running pot across the hand). A plain bet (first chips on a street)
is not a raise and is not counted (PT4 amt_*_raise_made / val_*_raise_made_pct).
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
    ds.calcRaiseMade(hand)
    return ds.handsplayers


def test_preflop_open_and_3bet_sizing():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),  # open to 3, pot before = 1.5
            ("P2", "raises", D(6), D(9), D(2), False),  # 3-bet to 9, pot before = 4.5
            ("P1", "calls", D(6), False),
        ],
    }
    hp = _run(streets)
    assert hp["P1"]["cnt_p_raise_made"] == 1
    assert hp["P1"]["val_p_raise_made_bp"] == 20000  # 3 / 1.5
    assert hp["P2"]["val_p_raise_made_bp"] == 20000  # 9 / 4.5


def test_flop_raise_made_but_not_bet():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),
            ("P2", "raises", D(6), D(9), D(2), False),
            ("P1", "calls", D(6), False),
        ],
        # Pot entering flop = 1.5 + (3 + 8 + 6) = 18.5. P2 bets 5 -> pot 23.5, P1 raises to 15.
        "FLOP": [("P2", "bets", D(5), False), ("P1", "raises", D(10), D(15), D(5), False)],
    }
    hp = _run(streets)
    # P1 raised on the flop: 15 / 23.5 = 6382 bp.
    assert hp["P1"]["cnt_f_raise_made"] == 1
    assert hp["P1"]["val_f_raise_made_bp"] == 6382
    # P2 only bet (not a raise) -> not counted as raise made.
    assert not hp["P2"].get("cnt_f_raise_made")


def test_only_first_raise_per_street_counted():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        # P1 opens, P2 4-bets after a 3-bet; P1's first raise (the open) is the one recorded.
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),  # open to 3 (recorded)
            ("P2", "raises", D(6), D(9), D(2), False),
            ("P1", "raises", D(18), D(27), D(6), False),  # P1's 2nd raise -> not recorded
        ],
    }
    hp = _run(streets)
    assert hp["P1"]["val_p_raise_made_bp"] == 20000  # the open, not the 4-bet


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {"PREFLOP": [("P1", "raises", D(2), D(3), D(1), False)]}
    ds.calcRaiseMade(hand)  # must not raise


def test_raise_made_stats():
    sd = {0: {"f_raise_made_cnt": "2", "f_raise_made_bp": "20000"}}
    res = Stats.f_raise_made(sd, 0)
    assert res[1] == "100.0"
    assert res[2] == "FRz=100.0%"
    assert res[5] == "avg flop raise made (% pot)"


def test_raise_made_no_data():
    for fn in ("p_raise_made", "f_raise_made", "t_raise_made", "r_raise_made"):
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
        assert fn in Stats.STATLIST
