"""Regression tests for poker game-definition DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_game import game_schema_queries


def test_game_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = game_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_gametypes_ddl_keeps_backend_specific_constraints() -> None:
    mysql = game_schema_queries("mysql")["createGametypesTable"]
    postgresql = game_schema_queries("postgresql")["createGametypesTable"]
    sqlite = game_schema_queries("sqlite")["createGametypesTable"]

    assert "maxSeats TINYINT" in mysql
    assert "maxSeats SMALLINT" in postgresql
    assert "ON DELETE CASCADE" in sqlite
