"""Regression tests for action/rank lookup DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_lookup import lookup_schema_queries


def test_lookup_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = lookup_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_rank_ddl_keeps_backend_specific_identity_type() -> None:
    assert "AUTO_INCREMENT" in lookup_schema_queries("mysql")["createRankTable"]
    assert "SERIAL" in lookup_schema_queries("postgresql")["createRankTable"]
    assert "INTEGER PRIMARY KEY" in lookup_schema_queries("sqlite")["createRankTable"]
