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


@pytest.mark.parametrize(
    ("small_blind", "big_blind", "expected"),
    [
        ("0.50", "1.00", ("0.50", "1.00")),
        (None, "1.00", ("0.50", "1.00")),
        ("0.50", None, ("0.50", "1.00")),
    ],
)
def test_betonline_fix_blinds_only_fills_missing_values(small_blind, big_blind, expected) -> None:
    parser = BetOnline.__new__(BetOnline)
    parser.skin = "ActionPoker"
    hand = SimpleNamespace(
        handid="123",
        gametype={"sb": small_blind, "bb": big_blind},
        sb=None,
        bb=None,
    )

    parser.fixBlinds(hand)

    assert (hand.gametype["sb"], hand.gametype["bb"]) == expected
    assert (hand.sb, hand.bb) == expected
