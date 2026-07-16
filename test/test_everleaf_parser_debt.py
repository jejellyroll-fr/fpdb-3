from __future__ import annotations

import pytest

from fpdb_3_legacy.EverleafToFpdb import Everleaf
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError


@pytest.mark.parametrize(
    ("header", "currency", "game_type"),
    [
        ("Blinds $0.05/$0.10 NL Hold'em", "USD", "ring"),
        ("Blinds €0.05/€0.10 NL Hold'em", "EUR", "ring"),
        ("Blinds ˆ0.05/ˆ0.10 NL Hold'em", "EUR", "ring"),
        ("Blinds 10/20 NL Hold'em", "T$", "tour"),
    ],
)
def test_determine_game_type_accepts_decoded_currency_symbols(
    header: str,
    currency: str,
    game_type: str,
) -> None:
    result = Everleaf.determineGameType(Everleaf.__new__(Everleaf), header)

    assert result["currency"] == currency
    assert result["type"] == game_type


@pytest.mark.parametrize("symbol", ["|", "\x80"])
def test_determine_game_type_rejects_non_unicode_currency_artifacts(symbol: str) -> None:
    header = f"Blinds {symbol}0.05/{symbol}0.10 NL Hold'em"

    with pytest.raises(FpdbParseError):
        Everleaf.determineGameType(Everleaf.__new__(Everleaf), header)
