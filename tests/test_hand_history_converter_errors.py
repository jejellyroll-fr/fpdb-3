from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
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
