"""Regression tests for session profit timeline queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_session_stats import session_stats_queries


def test_session_stats_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = session_stats_queries(backend)
        assert expected.keys() == {"sessionStats"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_session_stats_keeps_backend_time_and_dynamic_filters() -> None:
    mysql = session_stats_queries("mysql")["sessionStats"]
    postgresql = session_stats_queries("postgresql")["sessionStats"]
    sqlite = session_stats_queries("sqlite")["sessionStats"]

    assert "UNIX_TIMESTAMP(h.startTime)" in mysql
    assert "EXTRACT(epoch from h.startTime)" in postgresql
    assert "STRFTIME('<ampersand_s>', h.startTime)" in sqlite
    for query in (mysql, postgresql, sqlite):
        assert "hp.totalProfit" in query
        assert "<player_test>" in query
        assert "<datestest>" in query
        assert "<limit_test>" in query
        assert "<seats_test>" in query
        assert "<currency_test>" in query
