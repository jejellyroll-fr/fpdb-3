import re
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars


def test_unmatched_game_type_raises_once_without_mutating_error_count() -> None:
    converter = PokerStars.__new__(PokerStars)
    converter.sitename = "PokerStars"
    converter.copyGameHeader = False
    converter.numErrors = 0
    converter.isPartial = lambda _hand_text: False
    converter.determineGameType = lambda _hand_text: None

    with pytest.raises(FpdbParseError, match="Could not determine game type for PokerStars hand"):
        converter.processHand("PokerStars Hand #invalid\nunknown game")

    assert converter.numErrors == 0


def test_missing_required_hand_metadata_is_reported_non_fatally() -> None:
    converter = PokerStars.__new__(PokerStars)
    converter.parsing_issues = []
    hand = SimpleNamespace(
        handid=None,
        startTime=None,
        tablename="",
        tourNo=None,
        gametype={"type": "tour", "base": None},
        players=[(1, "alice"), (2, "bob")],
        actions={},
        actionStreets=[],
        handText="",
        board={},
    )

    converter._warn_if_hand_missing_expected_data(hand)

    warning = converter.parsing_issues[-1]
    assert "missing required handid" in warning
    assert "missing required startTime" in warning
    assert "missing required tablename" in warning
    assert "missing required tourNo" in warning


def test_failed_hand_capture_uses_only_session_header_and_snake_case_flag() -> None:
    captured = []
    converter = SimpleNamespace(
        failed_hand_callback=lambda **values: captured.append(values),
        copyGameHeader=False,
        copy_game_header=True,
        whole_file='<gametype>holdem</gametype>\n<game gamecode="1">first hand</game>',
        re_identify=re.compile(r'<game gamecode="\d+">'),
    )

    HandHistoryConverter._capture_failed_hand(
        converter,
        1,
        '<game gamecode="2">failed hand</game>',
        "error",
        "bad",
        Exception(),
    )

    assert captured[0]["shared_header"] == "<gametype>holdem</gametype>"
