"""Focused regressions for Entraction parser debt removal."""

import pytest

from fpdb_3_legacy.EntractionToFpdb import Entraction


@pytest.mark.parametrize(
    ("buyin", "header_currency", "expected"),
    [
        ("10+1", "EUR", "EUR"),
        ("100.5+10.5", "Fun", "play"),
        ("$10+$1", None, "USD"),
        ("£10+£1", None, "GBP"),
        ("10.50+1.50", None, "play"),
    ],
)
def test_entraction_tournament_currency_uses_header_symbol_or_play_money(buyin, header_currency, expected) -> None:
    info = {"BUYIN": buyin, "CURRENCY": header_currency}

    assert Entraction.tournamentCurrency(info) == expected
