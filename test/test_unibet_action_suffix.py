#!/usr/bin/env python3
"""Regression tests for actions Unibet annotates with a reason.

Unibet appends why the site acted for a player: "jejesat[...] folds  (timed out)".
re_Action allowed for "(disconnect)" and nothing else, so a timed-out fold was
not read at all. The consequences ran deep: the player stayed in the hand, was
counted among those reaching a showdown that never happened, and -- his cards
being the hero's, hence known -- could be handed the pot by the evaluator. The
real winner was then credited with less than he collected and his rake went
negative.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.UnibetToFpdb import Unibet


def _action(line: str) -> tuple[str, str] | None:
    match = Unibet.re_Action.search(line)
    return (match.group("PNAME"), match.group("ATYPE").strip()) if match else None


def test_a_timed_out_fold_is_read():
    # Two spaces before the note, as Unibet writes it.
    line = "jejesat[Unibet_28204e083c0fb55a] folds  (timed out)"

    assert _action(line) == ("jejesat[Unibet_28204e083c0fb55a]", "folds")


def test_a_disconnected_fold_is_still_read():
    assert _action("jejesat folds (disconnect)") == ("jejesat", "folds")


def test_an_unannotated_action_is_unaffected():
    assert _action("venomjr: checks") == ("venomjr", "checks")


@pytest.mark.parametrize(
    ("line", "expected_bet"),
    [
        ("venomjr: bets €0.10", "0.10"),
        # The pattern takes the comma of ", and is all-in" into BET; clearMoneyString
        # drops it downstream. Asserted through it so this documents the pipeline
        # rather than the quirk.
        ("Slimcry: bets €0.90, and is all-in", "0.90"),
    ],
)
def test_amounts_are_still_captured(line, expected_bet):
    match = Unibet.re_Action.search(line)

    assert match is not None
    assert Unibet.clearMoneyString(match.group("BET")) == expected_bet


def test_an_unknown_note_does_not_break_the_action():
    # The point of matching any parenthesised note rather than listing them: the
    # site can add one without silently dropping the action.
    assert _action("someone folds  (sitting out)") == ("someone", "folds")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
