"""Locale-aware number, currency, and date formatting for UI text."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from threading import RLock

from PySide6.QtCore import QDate, QDateTime, QLocale, QTime

Number = int | float | Decimal

_lock = RLock()
_locale = QLocale("en_US")
_CURRENCY_SYMBOLS = {
    "CAD": "C$",
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "JPY": "¥",
    "MBTC": "ⓑ",
    "RSD": "РСД",
    "SEK": "kr.",
    "USD": "$",
}


def set_format_locale(language: str | None) -> str:
    """Select the locale used by display helpers and return its resolved name."""
    global _locale
    selected = QLocale.system() if not language or language == "system" else QLocale(language)
    if selected.language() == QLocale.Language.C:
        selected = QLocale("en_US")
    with _lock:
        _locale = selected
        return _locale.name()


def get_format_locale() -> str:
    """Return the currently selected locale name."""
    with _lock:
        return _locale.name()


def _locale_copy(grouping: bool = True) -> QLocale:
    with _lock:
        selected = QLocale(_locale)
    if not grouping:
        selected.setNumberOptions(selected.numberOptions() | QLocale.NumberOption.OmitGroupSeparator)
    return selected


def format_number(value: Number, decimals: int = 2, *, grouping: bool = True, show_plus: bool = False) -> str:
    """Format a numeric UI value using the active decimal and grouping marks."""
    formatted = _locale_copy(grouping).toString(float(value), "f", decimals)
    return f"+{formatted}" if show_plus and value > 0 else formatted


def format_currency(value: Number, currency: str = "USD", decimals: int = 2, *, show_plus: bool = False) -> str:
    """Format money using locale placement and the requested ISO currency symbol."""
    code = currency.upper()
    symbol = _CURRENCY_SYMBOLS.get(code, code)
    locale = _locale_copy()
    # A loss is written with a minus sign. Qt's en_US currency pattern is the
    # accounting one, "($55.59)", which read as a typo next to "+$4.81".
    formatted = locale.toCurrencyString(abs(float(value)), symbol, decimals)
    if value < 0 and round(abs(float(value)), decimals) > 0:
        return f"{locale.negativeSign()}{formatted}"
    return f"+{formatted}" if show_plus and value > 0 else formatted


def currency_symbol(currency: str = "USD") -> str:
    """Return the compact symbol used for an ISO currency code."""
    code = currency.upper()
    return _CURRENCY_SYMBOLS.get(code, code)


def format_date(value: date | datetime, *, long: bool = False) -> str:
    """Format a calendar date using the active locale's short or long pattern."""
    qdate = QDate(value.year, value.month, value.day)
    format_type = QLocale.FormatType.LongFormat if long else QLocale.FormatType.ShortFormat
    return _locale_copy().toString(qdate, format_type)


def format_datetime(value: datetime, *, long: bool = False) -> str:
    """Format a local date and time using the active locale's display pattern."""
    qdatetime = QDateTime(
        QDate(value.year, value.month, value.day),
        QTime(value.hour, value.minute, value.second),
    )
    format_type = QLocale.FormatType.LongFormat if long else QLocale.FormatType.ShortFormat
    return _locale_copy().toString(qdatetime, format_type)


def format_utc_datetime(value: datetime, *, long: bool = False) -> str:
    """Format a time the database stores in UTC as this computer's local time.

    Hand and tournament start times are stored as naive UTC. Shown as they are,
    a hand played at 18:59 in Paris read 17:59 -- or the wrong day near midnight.
    The pattern (day/month order, 12 or 24 hours) still follows the UI language.
    """
    utc = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        local = utc.astimezone()
    except (OverflowError, OSError, ValueError):
        # Outside the platform's time range (before 1970 on Windows).
        local = utc
    return format_datetime(local, long=long)
