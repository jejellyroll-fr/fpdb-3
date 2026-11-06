"""Focused regressions for Enet parser debt removal."""

import pytest

from fpdb_3_legacy.EnetToFpdb import Enet


@pytest.mark.parametrize(
    ("buyin", "iso_code", "expected"),
    [
        ("10+1 USD", "USD", "USD"),
        ("10+1 CAD", "CAD", "CAD"),
        ("100+10 FPP", "FPP", "play"),
        ("£10+£1", None, "GBP"),
        ("10.50+1.50", None, "play"),
    ],
)
def test_enet_tournament_currency_uses_iso_symbol_or_play_money(buyin, iso_code, expected) -> None:
    info = {"BUYIN": buyin, "TOUR_ISO": iso_code}

    assert Enet.tournamentCurrency(info) == expected
