#!/usr/bin/env python3
"""The partial-hand diagnostic must name the actual reason.

"Hand is not cleanly split into pre and post Summary" reads like a format
problem, so an unfinished hand looked like a parser bug. Two very different
things reach this check: a hand with no summary yet -- the client writes hands as
they are dealt, and stops mid-hand when the hero leaves the table -- and a hand
carrying several summaries, which really is malformed.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.Exceptions import FpdbHandPartial
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs

# SwC hand 298240022, cut short the moment the hero left the table.
_UNFINISHED = """SwCPoker Hand #298240022:  Omaha Pot Limit (0.02/0.04) - 2026/07/17 11:43:12 UTC
Table 'No-Rake Micro Stakes PLO'(24812) 9-max (Real Money) Seat #4 is the button
Seat 3: edinapoker (1.97 in chips)
Seat 5: Slimcry (3.11 in chips)
Slimcry: posts small blind 0.02
*** HOLE CARDS ***
Dealt to edinapoker [Jc 8h 7d Qd]
edinapoker leaves the table
"""

_TWO_SUMMARIES = _UNFINISHED + "*** SUMMARY ***\nTotal pot 0.06\n*** SUMMARY ***\nTotal pot 0.06\n"


def _parser():
    return SealsWithClubs.__new__(SealsWithClubs)  # bypass the heavy __init__


def _hand(text):
    hand = MagicMock()
    hand.handid = "298240022"
    hand.handText = text
    return hand


def test_an_unfinished_hand_says_so():
    with pytest.raises(FpdbHandPartial) as excinfo:
        _parser().readPlayerStacks(_hand(_UNFINISHED))

    message = str(excinfo.value)
    assert "unfinished" in message
    assert "no result yet" in message
    assert "298240022" in message


def test_several_summaries_are_reported_as_malformed():
    with pytest.raises(FpdbHandPartial) as excinfo:
        _parser().readPlayerStacks(_hand(_TWO_SUMMARIES))

    message = str(excinfo.value)
    assert "malformed" in message
    assert "2 '*** SUMMARY ***' sections" in message


def test_the_two_reasons_do_not_share_a_message():
    def _raise(text):
        with pytest.raises(FpdbHandPartial) as excinfo:
            _parser().readPlayerStacks(_hand(text))
        return str(excinfo.value)

    assert _raise(_UNFINISHED) != _raise(_TWO_SUMMARIES)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
