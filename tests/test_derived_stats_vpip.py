"""VPIP of a blind who folds preflop (#691).

A blind who called or raised has voluntarily put money in, whatever they do next. Only
a blind who folds without having done so stays out of the opportunity.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpdb_3_legacy.DerivedStats import DerivedStats, _buildStatsInitializer


class _Hand:
    handid = "1"
    actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    gametype = {"category": "holdem", "base": "hold"}

    def __init__(self, preflop: list[tuple]) -> None:
        self.actions = {
            "BLINDSANTES": [("sb", "small blind", 1), ("bb", "big blind", 2)],
            "PREFLOP": preflop,
        }


def _vpip(preflop: list[tuple]) -> tuple[dict[str, Any], Any]:
    derived = DerivedStats()
    derived.handsplayers = {name: _buildStatsInitializer() for name in ("utg", "sb", "bb")}
    derived.hands = {}
    derived.vpip(_Hand(preflop))
    stats = {name: (row["street0VPIChance"], row["street0VPI"]) for name, row in derived.handsplayers.items()}
    return stats, derived.hands["playersVpi"]


@pytest.mark.parametrize(
    ("label", "sb_action"),
    [
        ("completes the small blind, then folds to the raise", ("sb", "calls", 1, 2, False)),
        ("raises, then folds to the shove", ("sb", "raises", 4, 6, 2, False)),
    ],
)
def test_a_blind_who_put_money_in_keeps_vpip_after_folding(label, sb_action) -> None:
    stats, players_vpi = _vpip([("utg", "folds"), sb_action, ("bb", "raises", 20, 22, 2, True), ("sb", "folds")])

    assert stats["sb"] == (True, True), label
    assert stats["bb"] == (True, True)
    assert players_vpi == 2


def test_a_blind_who_only_folds_stays_out_of_the_opportunity() -> None:
    stats, players_vpi = _vpip([("utg", "raises", 6, 6, 4, False), ("sb", "folds"), ("bb", "folds")])

    assert stats["sb"] == (False, False)
    assert stats["bb"] == (False, False)
    assert stats["utg"] == (True, True)
    assert players_vpi == 1


def test_a_big_blind_who_checks_then_folds_later_streets_is_unchanged() -> None:
    stats, players_vpi = _vpip([("utg", "calls", 2, 2, False), ("sb", "calls", 1, 2, False), ("bb", "checks")])

    assert stats["bb"] == (True, False)
    assert players_vpi == 2


def test_an_all_in_blind_stays_out_of_the_opportunity() -> None:
    derived = DerivedStats()
    derived.handsplayers = {name: _buildStatsInitializer() for name in ("utg", "sb")}
    derived.hands = {}
    hand = _Hand([("utg", "calls", 2, 2, False)])
    hand.actions["BLINDSANTES"] = [("sb", "small blind", "allin")]
    derived.vpip(hand)

    assert derived.handsplayers["sb"]["street0VPIChance"] is False
    assert derived.handsplayers["sb"]["street0VPI"] is False
