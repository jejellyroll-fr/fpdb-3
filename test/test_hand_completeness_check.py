#!/usr/bin/env python3
"""Tests for the "no betting actions" completeness warning.

The check flags a parsed hand that holds no action outside the blinds, on the
assumption that a hold'em hand always has one. A blind posted all-in breaks that
assumption: the short stack is already covered, nobody has anything left to act
on, and the board just runs out. Winamax hand 4933326270864822 is such a hand --
jejellyroll posts a big blind of 20 all-in against a small blind of 40 -- and
warning about it reported a parser failure that had not happened.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
from fpdb_3_legacy.WinamaxToFpdb import Winamax


def _converter():
    converter = HandHistoryConverter.__new__(Winamax)  # bypass the heavy __init__
    converter.sitename = "Winamax"
    converter.parsing_issues = []
    return converter


def _hand(blind_actions, other_actions=None):
    hand = MagicMock()
    hand.handid = "4933326270864822"
    hand.gametype = {"base": "hold", "type": "tour", "sb": "40", "bb": "80"}
    hand.tourNo = "1148629531"
    hand.players = [[1, "Benjouille__", "880"], [3, "jejellyroll", "20"]]
    hand.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    hand.actions = {"BLINDSANTES": blind_actions, "PREFLOP": other_actions or []}
    hand.handText = ""
    hand.board = {}
    return hand


def _issues(hand) -> list[str]:
    converter = _converter()
    converter._warn_if_hand_missing_expected_data(hand)
    return converter.parsing_issues


# jejellyroll's 20-chip big blind leaves him with nothing: the fourth element is True.
_BLIND_ALL_IN = [
    ("Benjouille__", "small blind", Decimal("40"), False),
    ("jejellyroll", "big blind", Decimal("20"), True),
]
_BLIND_NORMAL = [
    ("Benjouille__", "small blind", Decimal("40"), False),
    ("jejellyroll", "big blind", Decimal("80"), False),
]


def test_a_blind_posted_all_in_is_not_a_missing_action():
    assert _issues(_hand(_BLIND_ALL_IN)) == []


def test_a_hand_with_neither_action_nor_all_in_is_still_flagged():
    # The warning must keep its teeth: this one has no reason to be actionless.
    issues = _issues(_hand(_BLIND_NORMAL))

    assert any("no betting actions" in issue for issue in issues)


def test_an_all_in_blind_followed_by_action_is_not_flagged():
    hand = _hand(_BLIND_ALL_IN, other_actions=[("Benjouille__", "calls", Decimal("40"), False)])

    assert _issues(hand) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
