#!/usr/bin/env python3
"""Tests for turn and river float stat derivation."""

from __future__ import annotations

from unittest.mock import Mock

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
            if action[0] not in players:
                players.append(action[0])
    hand.players = [(idx + 1, player, 100) for idx, player in enumerate(players)]
    return hand


def _ds(players):
    ds = DerivedStats()
    ds.handsplayers = {player: _INIT_STATS.copy() for player in players}
    return ds


def test_turn_float_done_sets_defense_opportunity():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street2Seen"] = True
    ds.handsplayers["btn"]["street2Seen"] = True

    ds.calcTurnStats(
        _hand(
            {
                "FLOP": [
                    ("bb", "bets", 40, None, False),
                    ("btn", "calls", 40, None, False),
                ],
                "TURN": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 90, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["btn"]["flg_t_float_opp"] is True
    assert ds.handsplayers["btn"]["flg_t_float"] is True
    assert ds.handsplayers["bb"]["flg_t_float_def_opp"] is True


def test_turn_float_opportunity_without_bet_does_not_set_defense_opportunity():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street2Seen"] = True
    ds.handsplayers["btn"]["street2Seen"] = True

    ds.calcTurnStats(
        _hand(
            {
                "FLOP": [
                    ("bb", "bets", 40, None, False),
                    ("btn", "calls", 40, None, False),
                ],
                "TURN": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "checks", 0, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["btn"]["flg_t_float_opp"] is True
    assert ds.handsplayers["btn"]["flg_t_float"] is False
    assert ds.handsplayers["bb"]["flg_t_float_def_opp"] is False


def test_river_float_done_sets_defense_opportunity():
    ds = _ds(["bb", "btn"])
    ds.handsplayers["bb"]["street3Seen"] = True
    ds.handsplayers["btn"]["street3Seen"] = True

    ds.calcRiverStats(
        _hand(
            {
                "TURN": [
                    ("bb", "bets", 90, None, False),
                    ("btn", "calls", 90, None, False),
                ],
                "RIVER": [
                    ("bb", "checks", 0, None, False),
                    ("btn", "bets", 160, None, False),
                ],
            }
        )
    )

    assert ds.handsplayers["btn"]["flg_r_float_opp"] is True
    assert ds.handsplayers["btn"]["flg_r_float"] is True
    assert ds.handsplayers["bb"]["flg_r_float_def_opp"] is True
