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
