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
        query = tournament_player_detailed_queries(backend)[
            "tourneyPlayerDetailedStats"
        ]
        assert "tt.buyIn" in query
        assert "tp.winnings" in query
        assert "tp.koCount" in query
        assert "profitPerTourney" in query
        assert "<nametest>" in query
        assert "<sitetest>" in query
        assert "<startdate_test>" in query
        assert "<enddate_test>" in query
