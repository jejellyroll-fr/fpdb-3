#!/usr/bin/env python3
"""Tests for the bet-sizing completion stats.

Covers DerivedStats.calcBetAmounts (PT4 amt_blind/amt_bet_*), the generic
raise-faced and second-raise-made added to calcPreflop/PostflopRaiseFacing /
calcRaiseMade, and preflop 5-bet faced.
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


class _Pot:
    def __init__(self, total):
        self._t = total

    def getTotalAtStreet(self, _s):
        return D(self._t)


def _hand(streets, total_after=0):
    h = Mock()
    h.actionStreets = STREETS
    h.actions = {s: [] for s in STREETS}
    for k, v in streets.items():
        h.actions[k] = v
    h.pot = _Pot(total_after)
    return h


def _ds(streets, start=1000):
    ds = DerivedStats()
    ds.handsplayers = {p: {"startCash": int(100 * start)} for p in {a[0] for v in streets.values() for a in v}}
    return ds


# --- amounts ---
def test_amt_bet_per_street_and_total():
    streets = {
        "BLINDSANTES": [("P1", "small blind", D("0.5"), False), ("P2", "big blind", D(1), False)],
        # P1 (SB) raises to 3: C=0.5 to call the BB, Rb=2 -> chips 2.5, total 3.0.
        "PREFLOP": [("P1", "raises", D(2), D(3), D("0.5"), False), ("P2", "calls", D(2), False)],
        "FLOP": [("P1", "bets", D(4), False), ("P2", "calls", D(4), False)],
    }
    ds = _ds(streets)
    ds.calcBetAmounts(_hand(streets))
    p1 = ds.handsplayers["P1"]
    assert p1["amt_blind"] == 50  # 0.5
    assert p1["amt_bet_p"] == 300  # PT4 incl. blind: SB 0.5 + raise chips 2.5 = 3.0
    assert p1["amt_bet_f"] == 400  # bet 4
    # Both players matched (3 + 4 = 7 each), so no uncalled bet -> ttl = 700.
    assert p1["amt_bet_ttl"] == 700


# --- raise_made_2 ---
def test_second_raise_made_recorded():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),  # open (raise_made)
            ("P2", "raises", D(6), D(9), D(2), False),
            ("P1", "raises", D(18), D(27), D(6), False),  # 4-bet (raise_made_2)
        ],
    }
    ds = _ds(streets)
    ds.calcRaiseMade(_hand(streets))
    assert ds.handsplayers["P1"]["cnt_p_raise_made"] == 1
    assert ds.handsplayers["P1"]["val_p_raise_made_bp"] == 20000  # 3 / 1.5
    assert ds.handsplayers["P1"]["cnt_p_raise_made_2"] == 1
    assert ds.handsplayers["P1"]["val_p_raise_made_2_bp"] == 21600  # 27 / 12.5


# --- generic raise faced + 5-bet preflop ---
def test_generic_raise_facing_and_5bet():
    streets = {
        "BLINDSANTES": [("SB", "small blind", D("0.5"), False), ("BB", "big blind", D(1), False)],
        "PREFLOP": [
            ("P1", "raises", D(2), D(3), D(1), False),  # open (2-bet)
            ("P2", "raises", D(6), D(9), D(2), False),  # 3-bet
            ("P1", "raises", D(18), D(27), D(6), False),  # 4-bet
            ("P2", "raises", D(54), D(81), D(18), False),  # 5-bet
            ("P1", "calls", D(54), False),
        ],
    }
    ds = _ds(streets)
    ds.calcPreflopRaiseFacing(_hand(streets, total_after=999))
    # Generic raise_facing = first raise faced (the open, 2-bet) for P2.
    assert ds.handsplayers["P2"]["cnt_p_raise_facing"] == 1
    # P1 faces the 5-bet.
    assert ds.handsplayers["P1"]["cnt_p_5bet_facing"] == 1


def test_postflop_generic_raise_facing():
    streets = {
        "PREFLOP": [("P1", "calls", D(5), False), ("P2", "calls", D(5), False)],
        "FLOP": [
            ("P1", "bets", D(5), False),
            ("P2", "raises", D(15), D(20), D(5), False),
            ("P1", "calls", D(15), False),
        ],
    }
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    assert ds.handsplayers["P1"]["cnt_f_raise_facing"] == 1
    assert ds.handsplayers["P1"]["cnt_f_2bet_facing"] == 1  # both still recorded


# --- stats ---
def test_extra_stats_registered_and_format():
    assert Stats.p_raise_facing({0: {"p_raise_facing_cnt": "2", "p_raise_facing_bp": "30000"}}, 0)[1] == "150.0"
    assert Stats.amt_bet_ttl({0: {"n": "10", "amt_bet_ttl": "5000"}}, 0)[1] == "5.00"  # 50.00/10
    for fn in ("p_raise_facing", "f_raise_facing", "t_raise_facing", "r_raise_facing",
               "p_raise_made_2", "f_raise_made_2", "t_raise_made_2", "r_raise_made_2",
               "p_5bet_facing", "amt_blind", "amt_bet_p", "amt_bet_f", "amt_bet_t",
               "amt_bet_r", "amt_bet_ttl"):
        assert fn in Stats.STATLIST, fn
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
