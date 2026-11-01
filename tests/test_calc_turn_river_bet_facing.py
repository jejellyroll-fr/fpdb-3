#!/usr/bin/env python3
"""Tests for turn/river bet-faced sizing (DerivedStats.calcPostflopRaiseFacing).

PT4 pot-odds convention: to_call / pot_at_decision, with the running pot carried
across all streets.
"""

from __future__ import annotations

from decimal import Decimal as D
from unittest.mock import Mock

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


def _base():
    # Pot entering the flop = 4 (limped). Flop checks through (pot still 4 -> turn).
    return {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
        "FLOP": [("P1", "checks"), ("P2", "checks")],
    }


def test_turn_and_river_bet_facing():
    streets = _base()
    # Turn: P2 bets 4 into pot 4; P1 faces 4 into pot 8 -> 50%. P1 calls (pot 12).
    streets["TURN"] = [("P1", "checks"), ("P2", "bets", D(4), False), ("P1", "calls", D(4), False)]
    # River: P2 bets 6 into pot 12; P1 faces 6 into pot 18 -> 33.3%.
    streets["RIVER"] = [("P1", "checks"), ("P2", "bets", D(6), False), ("P1", "folds")]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    assert ds.handsplayers["P1"]["val_t_bet_facing_bp"] == 5000  # 4 / 8
    assert ds.handsplayers["P1"]["val_r_bet_facing_bp"] == 3333  # 6 / 18
    # No flop bet was faced (checked through).
    assert not ds.handsplayers["P1"].get("cnt_f_bet_facing")


def test_streets_independent():
    streets = _base()
    streets["TURN"] = [("P1", "checks"), ("P2", "checks")]
    streets["RIVER"] = [("P1", "bets", D(4), False), ("P2", "folds")]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    # P2 faces a river bet only.
    assert ds.handsplayers["P2"]["cnt_r_bet_facing"] == 1
    assert not ds.handsplayers["P2"].get("cnt_t_bet_facing")
