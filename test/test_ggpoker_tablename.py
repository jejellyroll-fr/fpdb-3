#!/usr/bin/env python3
"""Regression tests for reading a GGPoker hand's table name.

re_hand_info has always captured the name off "Table 'PLOWhite4' 6-max", but
_process_hand_info had no branch for it, so hand.tablename kept its empty default
on every hand: 26205 of 26215 stored hands carried "", and the completeness check
warned about all of them. Tournament hands showed it plainly -- Hand prefixes the
tournament number, leaving a bare "249773363 ".
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.GGPokerToFpdb import GGPoker


def test_the_parsed_table_name_reaches_the_hand():
    hand = MagicMock()
    hand.tablename = ""
    hand.tourNo = None
    hand.gametype = {}
    # _process_hand_info goes on to scan the text for rake and a cancellation;
    # an empty one lets it run without pulling in a whole hand.
    hand.handText = ""
    parser = GGPoker.__new__(GGPoker)

    parser._process_hand_info(hand, {"TABLE": "PLOWhite4"})

    assert hand.tablename == "PLOWhite4"


def test_the_pattern_captures_the_table_name():
    text = "Table 'PLOWhite4' 6-max Seat #4 is the button"

    match = GGPoker.re_hand_info.search(text)

    assert match is not None
    assert match.group("TABLE") == "PLOWhite4"


def test_a_table_name_holding_spaces_and_symbols_is_kept_whole():
    text = "Table 'NLH - $.50 / $1' 9-max Seat #7 is the button"

    assert GGPoker.re_hand_info.search(text).group("TABLE") == "NLH - $.50 / $1"


def test_a_tournament_table_is_a_bare_number():
    text = "Table '20654' 3-max Seat #1 is the button"

    assert GGPoker.re_hand_info.search(text).group("TABLE") == "20654"


@pytest.mark.parametrize(
    ("text", "expected_max"),
    [
        ("Table 'PLOWhite4' 6-max Seat #4 is the button", "6"),
        ("Table '20654' 3-max Seat #1 is the button", "3"),
    ],
)
def test_max_seats_still_reads_alongside(text, expected_max):
    assert GGPoker.re_hand_info.search(text).group("MAX") == expected_max


def test_the_pattern_is_searched_from_the_start_of_the_hand():
    # search()'s second argument is pos, not flags. Passing re.DOTALL (16) skipped
    # the first 16 characters, which a short header would hide behind.
    text = "Table 'X' 2-max Seat #1 is the button"

    assert GGPoker.re_hand_info.search(text).group("TABLE") == "X"
    assert GGPoker.re_hand_info.search(text, 16) is None  # what the bug did


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
