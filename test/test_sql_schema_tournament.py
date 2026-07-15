"""Regression tests for tournament-domain DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_tournament import tournament_schema_queries


def test_tournament_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = tournament_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_backings_ddl_keeps_backend_specific_constraints() -> None:
    mysql = tournament_schema_queries("mysql")["createBackingsTable"]
    postgresql = tournament_schema_queries("postgresql")["createBackingsTable"]
    sqlite = tournament_schema_queries("sqlite")["createBackingsTable"]

    assert "BIGINT UNSIGNED" in mysql
    assert "BIGSERIAL" in postgresql
    assert "FOREIGN KEY" not in sqlite
