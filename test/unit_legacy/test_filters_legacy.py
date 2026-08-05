from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QDate, QDateTime, QTime

from fpdb_3_legacy.Filters import Filters, parse_tourney_buyin_key, tourney_buyin_key


def test_get_dates_builds_qdatetime_from_qdate() -> None:
    filters = Filters.__new__(Filters)
    filters.day_start = 0
    filters.start_date = SimpleNamespace(date=lambda: QDate(2026, 6, 5))
    filters.end_date = SimpleNamespace(date=lambda: QDate(2026, 6, 5))

    expected_start = QDateTime(QDate(2026, 6, 5), QTime(0, 0, 0)).toUTC().toString("yyyy-MM-dd HH:mm:ss")
    expected_end = QDateTime(QDate(2026, 6, 5), QTime(23, 59, 59)).toUTC().toString("yyyy-MM-dd HH:mm:ss")

    assert Filters.getDates(filters) == (expected_start, expected_end)


def test_get_dates_applies_day_start_offset() -> None:
    filters = Filters.__new__(Filters)
    filters.day_start = 6
    filters.start_date = SimpleNamespace(date=lambda: QDate(2026, 6, 5))
    filters.end_date = SimpleNamespace(date=lambda: QDate(2026, 6, 5))

    offset = 6 * 3600
    expected_start = QDateTime(QDate(2026, 6, 5), QTime(0, 0, 0)).addSecs(offset).toUTC().toString("yyyy-MM-dd HH:mm:ss")
    expected_end = QDateTime(QDate(2026, 6, 5), QTime(0, 0, 0)).addSecs(offset + 24 * 3600 - 1).toUTC().toString("yyyy-MM-dd HH:mm:ss")

    assert Filters.getDates(filters) == (expected_start, expected_end)


def test_tourney_buyin_keys_preserve_currency_and_legacy_compatibility() -> None:
    assert tourney_buyin_key(1000, 100, "EUR") == "1000,100,EUR"
    assert parse_tourney_buyin_key("1000,100,EUR") == (1000, 100, "EUR")
    assert parse_tourney_buyin_key("1000,100") == (1000, 100, "")


def test_get_buyin_accepts_currency_aware_keys() -> None:
    filters = Filters.__new__(Filters)
    filters.cbTourneyBuyin = {
        "1000,100,EUR": SimpleNamespace(isChecked=lambda: True),
        "2000,200,USD": SimpleNamespace(isChecked=lambda: False),
    }

    assert Filters.getBuyIn(filters) == [1100]
