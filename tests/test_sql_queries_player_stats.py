"""Regression tests for general player statistics queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_player_stats import player_stats_queries


def test_player_stats_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = player_stats_queries(backend)
        assert expected.keys() == {"playerStats"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_player_stats_query_keeps_aggregates_and_dynamic_filters() -> None:
    mysql = player_stats_queries("mysql")["playerStats"]
    postgresql = player_stats_queries("postgresql")["playerStats"]
    sqlite = player_stats_queries("sqlite")["playerStats"]

    for query in (mysql, postgresql, sqlite):
        assert "street0VPIChance" in query
        assert "totalProfit" in query
        assert "<player_test>" in query
        assert "<seats_test>" in query
        assert "<datestest>" in query
        assert "<orderbyseats>" in query
    assert "format(100.0*sum(street0VPI)" in mysql
    assert "round(100.0*sum(street0VPI)" in sqlite
    assert "to_char(100.0*sum(street0VPI)" in postgresql
