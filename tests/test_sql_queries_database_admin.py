"""Regression tests for backend-specific database administration queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_database_admin import database_admin_queries


def test_database_admin_queries_are_installed_with_sqlite_placeholders() -> None:
    for backend in ("mysql", "postgresql"):
        expected = database_admin_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {
        key: value.replace("%s", "?")
        for key, value in database_admin_queries("sqlite").items()
    }
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_database_admin_queries_keep_backend_contracts() -> None:
    mysql = database_admin_queries("mysql")
    assert set(mysql) == {"analyze", "vacuum", "switchLockOn", "switchLockOff", "lockForInsert"}
    assert "analyze table" in mysql["analyze"]
    assert "optimize table" in mysql["vacuum"]
    assert "lock tables Hands write" in mysql["lockForInsert"]

    for backend in ("postgresql", "sqlite"):
        queries = database_admin_queries(backend)
        assert queries == {"analyze": "analyze", "vacuum": " vacuum ", "lockForInsert": ""}
