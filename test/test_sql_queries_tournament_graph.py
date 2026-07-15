"""Regression tests for tournament result and graph queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_tournament_graph import tournament_graph_queries


def test_tournament_graph_queries_are_installed_exactly() -> None:
    expected = tournament_graph_queries()
    assert len(expected) == 5
    for backend in ("mysql", "postgresql", "sqlite"):
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_tournament_graph_queries_keep_profit_and_chipev_contracts() -> None:
    queries = tournament_graph_queries()

    for key in ("tourneyResults", "tourneyGraph", "tourneyGraphType"):
        query = queries[key]
        assert "tp.winnings" in query
        assert "tt.buyIn" in query
        assert "tp.koCount" in query
        assert "<player_test>" in query
    assert "<tourney_buyin>" in queries["tourneyGraphType"]
    assert "<tourney_cat>" in queries["tourneyGraphType"]
    assert "<tourney_lim>" in queries["tourneyGraphType"]
    for key in ("tourneyChipEVByPosition", "tourneyChipEVByPositionGrid"):
        assert "<chipev_columns>" in queries[key]
