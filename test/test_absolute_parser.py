"""Regression tests for the legacy Absolute/Cereus parser."""

from decimal import Decimal

import pytest

from fpdb_3_legacy.AbsoluteToFpdb import Absolute


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
