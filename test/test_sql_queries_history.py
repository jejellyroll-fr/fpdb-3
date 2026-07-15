"""Regression tests for hand-history window queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_history import history_window_queries


def test_history_window_queries_are_installed_per_backend() -> None:
    for backend in ("mysql", "postgresql"):
        expected = history_window_queries(backend)
        assert len(expected) == 2
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite = history_window_queries("sqlite")
    sqlite_expected = {key: value.replace("%s", "?") for key, value in sqlite.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_history_window_queries_keep_backend_date_functions() -> None:
    mysql = history_window_queries("mysql")
    postgresql = history_window_queries("postgresql")
    sqlite = history_window_queries("sqlite")

    assert "date_sub(utc_timestamp()" in mysql["get_hand_1day_ago"]
    assert "now() at time zone 'UTC'" in postgresql["get_hand_1day_ago"]
    assert "strftime('%J', 'now')" in sqlite["get_hand_1day_ago"]
    assert mysql["get_date_nhands_ago"].count("%s") == 2
    assert postgresql["get_date_nhands_ago"].count("%s") == 2
    assert sqlite["get_date_nhands_ago"].count("%s") == 2
