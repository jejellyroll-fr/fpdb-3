"""Locale-aware number, currency, and date formatting for UI text."""

from __future__ import annotations

from datetime import date, datetime
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
    formatted = _locale_copy().toCurrencyString(float(value), symbol, decimals)
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
