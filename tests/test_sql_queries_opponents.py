"""Regression tests for opponent report queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_opponents import opponent_report_queries


def test_opponent_report_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = opponent_report_queries(backend)
        assert expected.keys() == {"opponentsReport"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_opponent_report_keeps_aggregates_and_backend_dates() -> None:
    mysql = opponent_report_queries("mysql")["opponentsReport"]
    postgresql = opponent_report_queries("postgresql")["opponentsReport"]
    sqlite = opponent_report_queries("sqlite")["opponentsReport"]

    for query in (mysql, postgresql, sqlite):
        assert "AS hero_net_bb" in query
        assert "AS river_aggr" in query
        assert "<minhands>" in query
        assert "<maxopponents>" in query
        assert "<player_test>" in query
    assert "date_format(h.startTime" in mysql
    assert "to_char(h.startTime" in postgresql
    assert "datetime(h.startTime)" in sqlite
