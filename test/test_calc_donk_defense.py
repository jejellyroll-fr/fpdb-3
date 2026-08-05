#!/usr/bin/env python3
"""Tests for postflop donk defense opportunities."""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.DerivedStats import _INIT_STATS, DerivedStats

STREETS = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def _hand(actions):
    hand = Mock()
    hand.handid = 1
    hand.actionStreets = STREETS
    hand.actions = {street: actions.get(street, []) for street in STREETS}
    players = []
    for street in STREETS:
        for action in hand.actions[street]:
            player = action[0]
            if player not in players:
                players.append(player)
    hand.players = [(idx + 1, player, 100) for idx, player in enumerate(players)]
    return hand


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {player: _INIT_STATS.copy() for player in players}
    return ds


def test_flop_donk_sets_defense_opportunity_for_preflop_aggressor():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street1Seen"] = True
    ds.handsplayers["btn"]["street1Seen"] = True

    ds.calcFlopStats(
        _hand(
            {
                "PREFLOP": [
                    ("btn", "raises", 30, None, False),
                    ("bb", "calls", 30, None, False),
                ],
                "FLOP": [
                    ("bb", "bets", 40, None, False),
                    ("btn", "calls", 40, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["bb"]["flg_f_donk_opp"] is True
    assert ds.handsplayers["bb"]["flg_f_donk"] is True
    assert ds.handsplayers["btn"]["flg_f_donk_def_opp"] is True


def test_turn_donk_sets_defense_opportunity_for_previous_aggressor():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street2Seen"] = True
    ds.handsplayers["btn"]["street2Seen"] = True

    ds.calcTurnStats(
        _hand(
            {
                "PREFLOP": [
                    ("btn", "raises", 30, None, False),
                    ("bb", "calls", 30, None, False),
                ],
                "FLOP": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 40, None, False),
                    ("bb", "calls", 40, None, False),
                ],
                "TURN": [
                    ("bb", "bets", 90, None, False),
                    ("btn", "calls", 90, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["bb"]["flg_t_donk_opp"] is True
    assert ds.handsplayers["bb"]["flg_t_donk"] is True
    assert ds.handsplayers["btn"]["flg_t_donk_def_opp"] is True


def test_river_donk_sets_defense_opportunity_for_previous_aggressor():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street3Seen"] = True
    ds.handsplayers["btn"]["street3Seen"] = True

    ds.calcRiverStats(
        _hand(
            {
                "FLOP": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 40, None, False),
                    ("bb", "calls", 40, None, False),
                ],
                "TURN": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 90, None, False),
                    ("bb", "calls", 90, None, False),
                ],
                "RIVER": [
                    ("bb", "bets", 160, None, False),
                    ("btn", "calls", 160, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["bb"]["flg_r_donk_opp"] is True
    assert ds.handsplayers["bb"]["flg_r_donk"] is True
    assert ds.handsplayers["btn"]["flg_r_donk_def_opp"] is True
