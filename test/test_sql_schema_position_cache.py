"""Regression tests for position-based HUD cache DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_position_cache import position_cache_schema_queries


def test_position_cache_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = position_cache_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_positions_cache_keeps_hud_identity_and_position_columns() -> None:
    mysql = position_cache_schema_queries("mysql")["createPositionsCacheTable"]
    postgresql = position_cache_schema_queries("postgresql")["createPositionsCacheTable"]
    sqlite = position_cache_schema_queries("sqlite")["createPositionsCacheTable"]

    for ddl in (mysql, postgresql, sqlite):
        assert "street0VPIChance" in ddl
        assert "raiseToStealChance" in ddl
        assert "tourneyTypeId" in ddl
    assert "position CHAR(1)" in mysql
    assert "position CHAR(1)" in postgresql
    assert "position TEXT" in sqlite
    assert "REFERENCES TourneyTypes(id)" in mysql
    assert "REFERENCES TourneyTypes(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
