from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.EverleafToFpdb import Everleaf
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError

ROOT = Path(__file__).resolve().parents[1]
EVERLEAF_TOURNEYS = ROOT / "regression-test-files" / "tour" / "Everleaf"


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


@pytest.mark.parametrize(
    ("filename", "tournament_number"),
    [
        ("TID_1337923-1.txt", "1337923"),
        ("NLHE-NA-0-0-201901.Grand.Tour.txt", "2768325"),
    ],
)
def test_tournament_identity_is_resolved_offline(
    filename: str,
    tournament_number: str,
) -> None:
    parser = Everleaf(Config(), str(EVERLEAF_TOURNEYS / filename), autostart=True)
    hands = parser.getProcessedHands()

    assert hands
    assert {hand.tourNo for hand in hands} == {tournament_number}
    assert {hand.tablename for hand in hands} == {f"{tournament_number} 1"}
    assert {(hand.buyin, hand.fee, hand.buyinCurrency) for hand in hands} == {(0, 0, "NA")}
