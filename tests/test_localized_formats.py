"""Locale-sensitive formatting contracts."""

import time
from collections.abc import Iterator
from datetime import date, datetime, timezone

import pytest

from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
from fpdb_3_legacy.localized_formats import (
    currency_symbol,
    format_currency,
    format_date,
    format_datetime,
    format_number,
    format_utc_datetime,
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


@pytest.fixture
def paris_time(monkeypatch) -> Iterator[None]:
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset to switch the process zone")
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_hand_history_datetime_follows_active_locale(paris_time) -> None:
    set_format_locale("fr_FR")
    # Stored in UTC; 12:30 UTC is 14:30 in Paris in July.
    hand = type("Hand", (), {"startTime": datetime(2026, 7, 16, 12, 30)})()

    assert GuiHandViewer._format_datetime(object(), hand) == "16/07/2026 14:30"


def test_stored_utc_times_show_in_local_time_and_the_ui_languages_pattern(paris_time) -> None:
    # A hand played at 00:55 in Paris on 7 November is stored 23:55 UTC on the 6th.
    stored = datetime(2026, 11, 6, 23, 55)

    set_format_locale("fr_FR")
    assert format_utc_datetime(stored) == "07/11/2026 00:55"
    set_format_locale("en_US")
    assert format_utc_datetime(stored) == "11/7/26 12:55 AM"
    assert format_utc_datetime(stored.replace(tzinfo=timezone.utc)) == "11/7/26 12:55 AM"
