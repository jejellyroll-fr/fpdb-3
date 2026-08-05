#!/usr/bin/env python3
"""Parity fixtures for delayed-turn-cbet derivation (DerivedStats.calcCBets).

Delayed turn c-bet = the preflop aggressor CHECKED the flop (declined the c-bet
and did not face+call a bet), then OPENS the turn (bets/raises when no bet has
occurred). These exercise the in-position and out-of-position lines plus the
edge cases that must NOT count (c-bet flop, check-call flop, facing a turn bet,
folding the flop, no turn).
"""
import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.DerivedStats import DerivedStats

CHECK = ("checks", None, None, False)
RAISE_PF = ("raises", 200, None, False)


def hand_with(actions, streets=None):
    h = Mock()
    h.actionStreets = streets or ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    h.actions = actions
    return h


def _act(player, kind, amt=None):
    return (player, kind, amt, None, False)


class TestDelayedTurnCBet:
    def setup_method(self):
        self.ds = DerivedStats()
        self.ds.handsplayers = {"pfr": {}, "opp": {}}

    def run(self, flop, turn):
        hand = hand_with({
            "PREFLOP": [_act("pfr", "raises", 200), _act("opp", "calls", 200)],
            "FLOP": flop,
            "TURN": turn,
            "RIVER": [],
        })
        self.ds.calcCBets(hand)
        return self.ds.handsplayers["pfr"]

    def test_checked_flop_then_opens_turn_oop(self):
        # PFR out of position: checks flop, leads turn.
        hp = self.run(
            flop=[_act("pfr", "checks"), _act("opp", "checks")],
            turn=[_act("pfr", "bets", 150), _act("opp", "folds")],
        )
        assert hp["street2DelayedCBChance"] is True
        assert hp["street2DelayedCBDone"] is True

    def test_checked_flop_then_opens_turn_ip(self):
        # PFR in position: opp checks turn to PFR who bets.
        hp = self.run(
            flop=[_act("opp", "checks"), _act("pfr", "checks")],
            turn=[_act("opp", "checks"), _act("pfr", "bets", 150)],
        )
        assert hp["street2DelayedCBChance"] is True
        assert hp["street2DelayedCBDone"] is True

    def test_checked_flop_checks_turn_chance_only(self):
        hp = self.run(
            flop=[_act("pfr", "checks"), _act("opp", "checks")],
            turn=[_act("pfr", "checks"), _act("opp", "checks")],
        )
        assert hp["street2DelayedCBChance"] is True
        assert hp["street2DelayedCBDone"] is False

    def test_cbet_flop_is_not_delayed(self):
        hp = self.run(
            flop=[_act("pfr", "bets", 150), _act("opp", "calls", 150)],
            turn=[_act("pfr", "bets", 300)],
        )
        assert hp["street2DelayedCBChance"] is False
        assert hp["street2DelayedCBDone"] is False

    def test_check_call_flop_is_not_delayed(self):
        # PFR check-called a flop bet -> faced a bet, not a delayed setup.
        hp = self.run(
            flop=[_act("pfr", "checks"), _act("opp", "bets", 150), _act("pfr", "calls", 150)],
            turn=[_act("pfr", "bets", 300)],
        )
        assert hp["street2DelayedCBChance"] is False

    def test_facing_turn_bet_no_chance(self):
        # PFR checked flop but opp bets the turn before PFR can open.
        hp = self.run(
            flop=[_act("opp", "checks"), _act("pfr", "checks")],
            turn=[_act("opp", "bets", 150), _act("pfr", "calls", 150)],
        )
        assert hp["street2DelayedCBChance"] is False

    def test_fold_flop_no_chance(self):
        hp = self.run(
            flop=[_act("opp", "bets", 150), _act("pfr", "folds")],
            turn=[_act("opp", "bets", 300)],
        )
        assert hp["street2DelayedCBChance"] is False
        assert hp["street2DelayedCBDone"] is False

    def test_no_turn_street_is_safe(self):
        hand = hand_with(
            {"PREFLOP": [_act("pfr", "raises", 200)], "FLOP": [_act("pfr", "checks")]},
            streets=["BLINDSANTES", "PREFLOP", "FLOP"],
        )
        self.ds.calcCBets(hand)
        assert self.ds.handsplayers["pfr"]["street2DelayedCBChance"] is False

    def test_multiway_checked_through_then_lead(self):
        self.ds.handsplayers = {"pfr": {}, "a": {}, "b": {}}
        hand = hand_with({
            "PREFLOP": [_act("pfr", "raises", 200), _act("a", "calls", 200), _act("b", "calls", 200)],
            "FLOP": [_act("pfr", "checks"), _act("a", "checks"), _act("b", "checks")],
            "TURN": [_act("pfr", "bets", 200)],
            "RIVER": [],
        })
        self.ds.calcCBets(hand)
        assert self.ds.handsplayers["pfr"]["street2DelayedCBDone"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
