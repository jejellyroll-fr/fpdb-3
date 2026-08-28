#!/usr/bin/env python3
"""The partial-hand diagnostic must name the actual reason.

"Hand is not cleanly split into pre and post Summary" reads like a format
problem, so an unfinished hand looked like a parser bug. Two very different
things reach this check: a hand with no summary yet -- clients write hands as
they are dealt, and stop mid-hand when the hero leaves the table -- and a hand
carrying several summaries, which really is malformed.

Six parsers shared that wording, each with its own summary marker, and all now
report through HandHistoryConverter.raise_summary_partial().
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Exceptions import FpdbHandPartial
from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
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


def _hand(text, handid="298240022"):
    hand = MagicMock()
    hand.handid = handid
    hand.handText = text
    return hand


def _raise(text, marker="*** SUMMARY ***", handid="298240022"):
    converter = HandHistoryConverter.__new__(SealsWithClubs)  # bypass the heavy __init__
    with pytest.raises(FpdbHandPartial) as excinfo:
        converter.raise_summary_partial(_hand(text, handid), marker)
    return str(excinfo.value)


def test_an_unfinished_hand_says_so():
    message = _raise(_UNFINISHED)

    assert "unfinished" in message
    assert "no result yet" in message
    assert "298240022" in message


def test_several_summaries_are_reported_as_malformed():
    message = _raise(_TWO_SUMMARIES)

    assert "malformed" in message
    assert "2 '*** SUMMARY ***' sections" in message


def test_the_two_reasons_do_not_share_a_message():
    assert _raise(_UNFINISHED) != _raise(_TWO_SUMMARIES)


@pytest.mark.parametrize("marker", ["*** SUMMARY ***", "------ Summary ------", "*** SUMMARY *"])
def test_the_message_quotes_the_marker_of_the_site(marker):
    # Winning writes "------ Summary ------" in one of its formats and KingsClub
    # "*** SUMMARY *": a shared message must not name a marker the file lacks.
    assert marker in _raise("no summary here", marker)


def test_an_unparsed_handid_does_not_leak_a_zero():
    # readHandInfo() runs this check before the id is read, leaving handid at 0.
    message = _raise(_UNFINISHED, handid=0)

    assert "Hand ? is unfinished" in message
    assert "Hand 0" not in message


def test_swc_still_reports_one_unfinished_hand_in_a_real_file():
    parser = SealsWithClubs.__new__(SealsWithClubs)
    with pytest.raises(FpdbHandPartial) as excinfo:
        parser.readPlayerStacks(_hand(_UNFINISHED))

    assert "unfinished" in str(excinfo.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
