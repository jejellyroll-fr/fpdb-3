"""Regression tests for session and tournament cache write queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_session_cache_write import session_cache_write_queries


def test_session_cache_write_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = session_cache_write_queries()
    assert len(expected) == 34
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_session_cache_write_keeps_session_and_tournament_linkage() -> None:
    queries = session_cache_write_queries()

    assert queries["clear_S_H"] == "UPDATE Hands SET sessionId = NULL"
    for key, table in (
        ("update_S_SC", "SessionsCache"),
        ("update_S_TC", "TourneysCache"),
        ("update_S_T", "Tourneys"),
        ("update_S_H", "Hands"),
    ):
        assert f"UPDATE {table} SET" in queries[key]
        assert "sessionId=%s" in queries[key]
    assert "UPDATE Tourneys SET" in queries["updateTourneysSessions"]
    assert "sessionId=%s" in queries["updateTourneysSessions"]
    assert "WHERE id=%s" in queries["updateTourneysSessions"]


def test_session_cache_write_keeps_financial_aggregates() -> None:
    queries = session_cache_write_queries()

    for key in ("insert_SC", "insert_TC", "update_SC", "update_TC"):
        assert "totalProfit" in queries[key]
        assert "allInEV" in queries[key]
        assert "rake" in queries[key]
