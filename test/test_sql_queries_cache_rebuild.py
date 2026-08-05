"""Regression tests for HUD cache rebuild queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_cache_rebuild import cache_rebuild_queries


def test_cache_rebuild_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = cache_rebuild_queries(backend)
        assert expected.keys() == {"rebuildCache"}
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_cache_rebuild_keeps_stats_and_composition_placeholders() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        query = cache_rebuild_queries(backend)["rebuildCache"]
        assert "street0VPIChance" in query
        assert "street0VPI" in query
        assert "totalProfit" in query
        assert "allInEV" in query
        for placeholder in (
            "<insert>",
            "<select>",
            "<group>",
            "<where_clause>",
            "<hero_join>",
            "<sessions_join_clause>",
            "<tourney_join_clause>",
        ):
            assert placeholder in query
