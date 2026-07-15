"""Regression tests for position-grouped player statistics queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_player_position import player_position_stats_queries


def test_player_position_stats_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = player_position_stats_queries(backend)
        assert expected.keys() == {"playerStatsByPosition"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_player_position_stats_keeps_grouping_and_filters() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        query = player_position_stats_queries(backend)["playerStatsByPosition"]
        assert "PlPosition" in query
        assert "hc.position" in query
        assert "hp.position" in query
        assert "street0VPIChance" in query
        assert "totalProfit" in query
        assert "<player_test>" in query
        assert "<seats_test>" in query
        assert "<datestest>" in query
