#!/usr/bin/env python3
"""Tests for postflop "bet made" sizing (DerivedStats.calcBetFacing).

The first bettor on a street records their own bet size as basis points of the
pot before the bet (PT4 amt_{f,t,r}_bet_made / val_*_bet_made_pct), alongside the
"bet faced" recorded for the players who act after.
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
    def __init__(self, by_street):
        self._by_street = by_street

    def getTotalAtStreet(self, street):
        return D(self._by_street.get(street, 0))


def _hand(streets, pots):
    hand = Mock()
    hand.actionStreets = STREETS
    hand.actions = {s: [] for s in STREETS}
    for k, v in streets.items():
        hand.actions[k] = v
    hand.pot = _Pot(pots)
    return hand


def _ds(streets):
    ds = DerivedStats()
    ds.handsplayers = {p: {} for p in {a[0] for v in streets.values() for a in v}}
    return ds


def test_flop_bet_made_records_bettor():
    streets = {"FLOP": [("P1", "bets", D(50), False), ("P2", "folds"), ("P3", "calls", D(50), False)]}
    ds = _ds(streets)
    ds.calcBetFacing(_hand(streets, {"PREFLOP": 100}))
    # Bettor P1: bet made = 50/100 = 5000 bp (sizing convention, bet/pot_before).
    assert ds.handsplayers["P1"]["cnt_f_bet_made"] == 1
    assert ds.handsplayers["P1"]["val_f_bet_made_bp"] == 5000
    # Only the bettor records bet_made (facing is handled elsewhere).
    assert not ds.handsplayers["P2"].get("cnt_f_bet_made")
    assert not ds.handsplayers["P3"].get("cnt_f_bet_made")


def test_turn_and_river_bet_made():
    streets = {
        "TURN": [("P1", "bets", D(150), False), ("P2", "calls", D(150), False)],
        "RIVER": [("P1", "bets", D(100), False), ("P2", "folds")],
    }
    ds = _ds(streets)
    ds.calcBetFacing(_hand(streets, {"FLOP": 150, "TURN": 400}))
    assert ds.handsplayers["P1"]["val_t_bet_made_bp"] == 10000  # 150/150 pot-sized
    assert ds.handsplayers["P1"]["val_r_bet_made_bp"] == 2500  # 100/400


def test_check_around_no_bet_made():
    streets = {"FLOP": [("P1", "checks"), ("P2", "checks")]}
    ds = _ds(streets)
    ds.calcBetFacing(_hand(streets, {"PREFLOP": 100}))
    assert not ds.handsplayers["P1"].get("cnt_f_bet_made")
    assert not ds.handsplayers["P2"].get("cnt_f_bet_made")


def test_bet_made_stats():
    sd = {0: {"f_bet_made_cnt": "2", "f_bet_made_bp": "15000"}}
    res = Stats.f_bet_made(sd, 0)
    assert res[1] == "75.0"
    assert res[2] == "FBet=75.0%"
    assert res[5] == "avg flop bet made (% pot)"


def test_bet_made_no_data():
    for fn in ("f_bet_made", "t_bet_made", "r_bet_made"):
        assert getattr(Stats, fn)({0: {}}, 0)[1] in ("-", "NA")
        assert fn in Stats.STATLIST
