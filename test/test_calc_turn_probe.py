#!/usr/bin/env python3
"""Parity fixtures for turn-probe derivation (DerivedStats.calcCBets).

Turn probe = a NON-PFR opens the turn after the PFR checked the flop (declined
the c-bet). The first eligible non-PFR to act with no bet in front of them is
credited a chance; a bet/raise there is a done. Mirror of the delayed c-bet.
"""
from unittest.mock import Mock

import pytest

from fpdb_3_legacy.DerivedStats import DerivedStats


def _act(player, kind, amt=None):
    return (player, kind, amt, None, False)


def _hand(flop, turn):
    h = Mock()
    h.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    h.actions = {
        "PREFLOP": [_act("pfr", "raises", 200), _act("opp", "calls", 200)],
        "FLOP": flop,
        "TURN": turn,
        "RIVER": [],
    }
    return h


class TestTurnProbe:
    def setup_method(self):
        self.ds = DerivedStats()
        self.ds.handsplayers = {"pfr": {}, "opp": {}}

    def run(self, flop, turn):
        self.ds.calcCBets(_hand(flop, turn))
        return self.ds.handsplayers

    def test_oop_villain_probes_after_pfr_checks_behind(self):
        # PFR in position checks the flop behind; OOP villain leads the turn.
        hp = self.run(
            flop=[_act("opp", "checks"), _act("pfr", "checks")],
            turn=[_act("opp", "bets", 150)],
        )
        assert hp["opp"]["street2ProbeChance"] is True
        assert hp["opp"]["street2ProbeDone"] is True
        # The PFR never probes.
        assert "street2ProbeChance" not in hp["pfr"]

    def test_villain_checks_turn_chance_only(self):
        hp = self.run(
            flop=[_act("opp", "checks"), _act("pfr", "checks")],
            turn=[_act("opp", "checks"), _act("pfr", "checks")],
        )
        assert hp["opp"]["street2ProbeChance"] is True
        assert hp["opp"]["street2ProbeDone"] is False

    def test_pfr_leads_turn_is_not_a_probe(self):
        # PFR OOP checks flop then leads the turn -> delayed c-bet, no probe.
        hp = self.run(
            flop=[_act("pfr", "checks"), _act("opp", "checks")],
            turn=[_act("pfr", "bets", 150)],
        )
        assert "street2ProbeChance" not in hp["opp"]
        assert hp["pfr"].get("street2DelayedCBDone") is True

    def test_pfr_cbet_flop_no_probe(self):
        hp = self.run(
            flop=[_act("pfr", "bets", 150), _act("opp", "calls", 150)],
            turn=[_act("opp", "bets", 300)],
        )
        assert "street2ProbeChance" not in hp["opp"]

    def test_check_call_flop_no_probe(self):
        # PFR check-called a flop bet -> not a checked-through flop, no probe.
        hp = self.run(
            flop=[_act("pfr", "checks"), _act("opp", "bets", 150), _act("pfr", "calls", 150)],
            turn=[_act("opp", "bets", 300)],
        )
        assert "street2ProbeChance" not in hp["opp"]

    def test_multiway_first_prober_credited_only(self):
        self.ds.handsplayers = {"pfr": {}, "a": {}, "b": {}}
        h = Mock()
        h.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        h.actions = {
            "PREFLOP": [_act("pfr", "raises", 200), _act("a", "calls", 200), _act("b", "calls", 200)],
            "FLOP": [_act("a", "checks"), _act("b", "checks"), _act("pfr", "checks")],
            "TURN": [_act("a", "bets", 200), _act("b", "folds"), _act("pfr", "folds")],
            "RIVER": [],
        }
        self.ds.calcCBets(h)
        assert self.ds.handsplayers["a"]["street2ProbeDone"] is True
        # b faced a's bet -> not a prober.
        assert "street2ProbeChance" not in self.ds.handsplayers["b"]

    def test_facing_bet_no_probe(self):
        # If someone bets before the would-be prober, no probe chance.
        self.ds.handsplayers = {"pfr": {}, "a": {}, "b": {}}
        h = Mock()
        h.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        h.actions = {
            "PREFLOP": [_act("pfr", "raises", 200), _act("a", "calls", 200), _act("b", "calls", 200)],
            "FLOP": [_act("a", "checks"), _act("b", "checks"), _act("pfr", "checks")],
            # 'a' bets (probe), 'b' would face it.
            "TURN": [_act("a", "bets", 200), _act("b", "calls", 200)],
            "RIVER": [],
        }
        self.ds.calcCBets(h)
        assert self.ds.handsplayers["a"]["street2ProbeDone"] is True
        assert "street2ProbeChance" not in self.ds.handsplayers["b"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
