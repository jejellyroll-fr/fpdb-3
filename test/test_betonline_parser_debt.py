"""Focused regressions for BetOnline parser debt removal."""

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.BetOnlineToFpdb import BetOnline


@pytest.mark.parametrize(
    ("buyin", "expected"),
    [
        ("$10+$1", "USD"),
        ("€10+€1", "EUR"),
        ("£10+£1", "GBP"),
        ("10.50+1.50", "play"),
    ],
)
def test_betonline_buyin_currency_matches_supported_symbols(buyin, expected) -> None:
    hand = SimpleNamespace(handid="123", buyinCurrency=None)

    BetOnline.__new__(BetOnline)._detect_buyin_currency(hand, {"BUYIN": buyin})

    assert hand.buyinCurrency == expected
