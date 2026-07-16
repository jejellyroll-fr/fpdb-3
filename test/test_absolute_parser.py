"""Regression tests for the legacy Absolute/Cereus parser."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.AbsoluteToFpdb import Absolute, FpdbParseError


@pytest.mark.parametrize(
    ("stakes", "expected_currency", "expected_type"),
    [
        ("$0.02", "USD", "ring"),
        ("€0.02", "EUR", "ring"),
        ("0.02", "T$", "tour"),
    ],
)
def test_absolute_header_currency_is_explicit(stakes, expected_currency, expected_type) -> None:
    parser = Absolute.__new__(Absolute)
    hand_text = f"Stage #1571362962: Holdem No Limit {stakes} - 2009-08-05 15:24:06 (ET)"

    game = parser.determineGameType(hand_text)

    assert game["currency"] == expected_currency
    assert game["type"] == expected_type
    assert Decimal(game["sb"]) == Decimal("0.01")
    assert Decimal(game["bb"]) == Decimal("0.02")


@pytest.mark.parametrize("dealer_text", ["Seat #6 is the dealer", "Seat #6 is the dead dealer"])
def test_absolute_button_accepts_live_and_dead_dealer(dealer_text) -> None:
    hand = SimpleNamespace(handText=dealer_text, buttonpos=None)

    Absolute.__new__(Absolute).readButton(hand)

    assert hand.buttonpos == 6


@pytest.mark.parametrize("dealer_text", ["Seat #6 is the d dealer", "Seat #6 is the added dealer"])
def test_absolute_button_rejects_partial_dead_words(dealer_text) -> None:
    hand = SimpleNamespace(handText=dealer_text, buttonpos=None)

    with pytest.raises(FpdbParseError, match="button position"):
        Absolute.__new__(Absolute).readButton(hand)


def test_absolute_incoming_player_post_is_one_big_blind() -> None:
    calls = []
    hand = SimpleNamespace(
        handText="New Player - Posts $0.02\n*** POCKET CARDS ***",
        handid="123",
        players=[(3, "New Player", "1.00")],
        addBlind=lambda *args: calls.append(args),
        setUncalledBets=lambda _value: None,
    )
    parser = Absolute.__new__(Absolute)
    parser.compiledPlayers = set()
    parser.compilePlayerRegexs(hand)

    parser.readBlinds(hand)

    assert calls == [(None, None, None), ("New Player", "big blind", "0.02")]
