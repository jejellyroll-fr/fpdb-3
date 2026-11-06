"""Regression tests for detailed tournament-player queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_tournament_player import (
    tournament_player_detailed_queries,
)


def test_tournament_player_detailed_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = tournament_player_detailed_queries(backend)
        assert expected.keys() == {"tourneyPlayerDetailedStats"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_tournament_player_query_keeps_results_and_filters() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        query = tournament_player_detailed_queries(backend)["tourneyPlayerDetailedStats"]
        assert "tt.buyIn" in query
        assert "tp.winnings" in query
        assert "tp.koCount" in query
        assert "profitPerTourney" in query
        assert "<nametest>" in query
        assert "<sitetest>" in query
        assert "<startdate_test>" in query
        assert "<enddate_test>" in query


def test_mysql_quotes_rank_in_tournament_report() -> None:
    query = tournament_player_detailed_queries("mysql")["tourneyPlayerDetailedStats"]
    assert "tp.`rank`" in query
    assert "tp.rank" not in query


def test_tournament_rates_protect_zero_denominators() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        query = tournament_player_detailed_queries(backend)["tourneyPlayerDetailedStats"]
        assert "NULLIF(COUNT(1), 0)" in query
        assert "NULLIF(SUM(tt.buyin+tt.fee), 0)" in query
        assert query.count("NULLIF(") == 3


def test_postgresql_rates_use_decimal_not_integer_division() -> None:
    query = tournament_player_detailed_queries("postgresql")["tourneyPlayerDetailedStats"]
    assert "100.0 * SUM(CASE WHEN winnings > 0 THEN 1 ELSE 0 END)" in query
    assert "100.0 * SUM(tp.winnings" in query
    assert "AS BIGINT" not in query


def test_profit_per_tourney_excludes_unknown_ranks() -> None:
    mysql = tournament_player_detailed_queries("mysql")["tourneyPlayerDetailedStats"]
    postgresql = tournament_player_detailed_queries("postgresql")["tourneyPlayerDetailedStats"]
    sqlite = tournament_player_detailed_queries("sqlite")["tourneyPlayerDetailedStats"]

    assert "CASE WHEN tp.`rank` > 0 THEN 0 ELSE 1 END" in mysql
    assert "CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END" in postgresql
    assert "CASE WHEN tp.rank > 0 THEN 0 ELSE 1 END" in sqlite
