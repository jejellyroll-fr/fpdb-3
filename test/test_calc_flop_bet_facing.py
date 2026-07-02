#!/usr/bin/env python3
"""Tests for flop bet-faced sizing (DerivedStats.calcPostflopRaiseFacing).

PT4 convention: the bet faced is recorded as a pot-odds price,
to_call / pot_at_decision (the pot already includes the bet). The running pot is
accumulated from the blinds + preflop + flop actions, so the tests include a
preflop that seeds a known pot.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal as D
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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


# Heads-up limped pot: SB 1 / BB 2, P1 (SB) completes, P2 (BB) checks.
# Pot entering the flop = 4.
def _limped_preflop():
    return {
        "BLINDSANTES": [("P1", "small blind", D(1), False), ("P2", "big blind", D(2), False)],
        "PREFLOP": [("P1", "calls", D(1), False), ("P2", "checks")],
    }


def test_half_pot_bet_faced():
    streets = _limped_preflop()
    # P2 bets 4 into the pot of 4; P1 faces to_call 4 into pot 8 -> 50%.
    streets["FLOP"] = [("P1", "checks"), ("P2", "bets", D(4), False), ("P1", "calls", D(4), False)]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    assert ds.handsplayers["P1"]["cnt_f_bet_facing"] == 1
    assert ds.handsplayers["P1"]["val_f_bet_facing_bp"] == 5000  # 4 / (4 + 4)
    # The bettor does not face its own bet.
    assert not ds.handsplayers["P2"].get("cnt_f_bet_facing")


def test_pot_sized_bet_faced():
    streets = _limped_preflop()
    # P2 bets 8 (2x pot) into pot 4; P1 faces 8 into pot 12 -> 66.7%.
    streets["FLOP"] = [("P1", "checks"), ("P2", "bets", D(8), False), ("P1", "folds")]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    assert ds.handsplayers["P1"]["val_f_bet_facing_bp"] == 6666  # 8 / 12


def test_check_around_records_nothing():
    streets = _limped_preflop()
    streets["FLOP"] = [("P1", "checks"), ("P2", "checks")]
    ds = _ds(streets)
    ds.calcPostflopRaiseFacing(_hand(streets))
    assert not ds.handsplayers["P1"].get("cnt_f_bet_facing")
    assert not ds.handsplayers["P2"].get("cnt_f_bet_facing")


def test_no_handsplayers_is_noop():
    ds = DerivedStats()
    ds.calcPostflopRaiseFacing(_hand({"FLOP": [("P1", "bets", D(4), False)]}))  # must not raise
