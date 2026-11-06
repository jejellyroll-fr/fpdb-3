"""Regression tests for primary and starting-card HUD cache DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_cards_cache import cards_cache_schema_queries
from fpdb_3_legacy.sql_schema_hud_cache import hud_cache_schema_queries


def test_hud_cache_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = hud_cache_schema_queries(backend) | cards_cache_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_hud_cache_keeps_position_and_modern_turn_columns() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        ddl = hud_cache_schema_queries(backend)["createHudCacheTable"]
        assert "street2DelayedCBChance" in ddl
        assert "street2DelayedCBDone" in ddl
        assert "street2ProbeChance" in ddl
        assert "street2ProbeDone" in ddl
        assert "position" in ddl


def test_cards_cache_keeps_period_and_starting_card_context() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        ddl = cards_cache_schema_queries(backend)["createCardsCacheTable"]
        assert "weekId" in ddl
        assert "monthId" in ddl
        assert "startCards" in ddl
        assert "street0VPIChance" in ddl
