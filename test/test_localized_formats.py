"""Locale-sensitive formatting contracts."""

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
from fpdb_3_legacy.localized_formats import (
    currency_symbol,
    format_currency,
    format_date,
    format_datetime,
    format_number,
    get_format_locale,
    set_format_locale,
)
from fpdb_3_legacy.stats_financial import totalprofit
from fpdb_3_legacy.stats_formatting import stat_override


@pytest.fixture(autouse=True)
def restore_format_locale() -> Iterator[None]:
    previous = get_format_locale()
    yield
    set_format_locale(previous)


def test_french_formats_numbers_money_and_dates() -> None:
    assert set_format_locale("fr_FR") == "fr_FR"
    assert format_number(1234.5) == "1\u202f234,50"
    assert format_number(12.5, 1, show_plus=True) == "+12,5"
    assert format_currency(1234.5, "EUR") == "1\u202f234,50\u00a0€"
    assert format_currency(12.5, "EUR", show_plus=True) == "+12,50\u00a0€"
    assert format_date(date(2026, 7, 16)) == "16/07/2026"
    assert format_datetime(datetime(2026, 7, 16, 14, 30)) == "16/07/2026 14:30"
    assert currency_symbol("EUR") == "€"


def test_english_default_style_and_grouping_control() -> None:
    set_format_locale("en_US")
    assert format_number(1234.5) == "1,234.50"
    assert format_number(1234.5, 1, grouping=False) == "1234.5"
    assert format_currency(-12.5, "USD") == "($12.50)"
    assert format_date(date(2026, 7, 16)) == "7/16/26"


def test_financial_stat_and_override_follow_active_locale() -> None:
    set_format_locale("fr_FR")
    profit = totalprofit({1: {"net": 123450, "currency": "EUR"}}, 1)
    overridden = stat_override(1, (0.125, "", "a", "b", "c", "d"))

    assert profit[1] == "1\u202f234,50\u00a0€"
    assert profit[2] == "tp=1\u202f234,50\u00a0€"
    assert overridden[1] == "12,5"


def test_hand_history_datetime_follows_active_locale() -> None:
    set_format_locale("fr_FR")
    hand = type("Hand", (), {"startTime": datetime(2026, 7, 16, 14, 30)})()

    assert GuiHandViewer._format_datetime(object(), hand) == "16/07/2026 14:30"
