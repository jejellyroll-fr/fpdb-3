"""Regression tests for detailed cash-player report queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_player_detailed import player_detailed_report_queries


def test_player_detailed_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = player_detailed_report_queries(backend)
        assert expected.keys() == {"playerDetailedStats"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_player_detailed_query_keeps_position_and_dynamic_filters() -> None:
    mysql = player_detailed_report_queries("mysql")["playerDetailedStats"]
    postgresql = player_detailed_report_queries("postgresql")["playerDetailedStats"]
    sqlite = player_detailed_report_queries("sqlite")["playerDetailedStats"]

    for query in (mysql, postgresql, sqlite):
        assert "<position>" in query
        assert "<game_test>" in query
        assert "<site_test>" in query
        assert "street0VPIChance" in query
        assert "totalProfit" in query
    assert "cast(hp.street0VPIChance as SIGNED)" in mysql
    assert "'Z'||<position>" in postgresql
    assert "'Z'||<position>" in sqlite


def test_player_detailed_bet_stats_include_tournament_linked_hands() -> None:
    aliases = ("pf3", "fl3", "tn3", "rv3", "pf4", "fl4", "tn4", "rv4", "pff3", "pff4")
    for backend in ("mysql", "postgresql", "sqlite"):
        query = player_detailed_report_queries(backend)["playerDetailedStats"]
        normalized = query.lower()

        assert "tourneysplayersid is null" not in normalized
        for alias in aliases:
            assert f"as {alias}" in normalized
