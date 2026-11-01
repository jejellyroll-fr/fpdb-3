"""Regression tests for extracted core schema DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_core import core_schema_queries


def test_core_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = core_schema_queries(backend)
        actual = Sql(db_server=backend).query
        assert expected.items() <= actual.items()


def test_insert_lock_remains_mysql_only() -> None:
    assert "createLockTable" in core_schema_queries("mysql")
    assert "createLockTable" not in core_schema_queries("postgresql")
    assert "createLockTable" not in core_schema_queries("sqlite")
