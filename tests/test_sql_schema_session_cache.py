"""Regression tests for session statistics cache DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_session_cache import session_cache_schema_queries


def test_session_cache_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = session_cache_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_sessions_cache_keeps_context_and_financial_columns() -> None:
    mysql = session_cache_schema_queries("mysql")["createSessionsCacheTable"]
    postgresql = session_cache_schema_queries("postgresql")["createSessionsCacheTable"]
    sqlite = session_cache_schema_queries("sqlite")["createSessionsCacheTable"]

    for ddl in (mysql, postgresql, sqlite):
        assert "sessionId" in ddl
        assert "gametypeId" in ddl
        assert "street0VPIChance" in ddl
        assert "allInEV" in ddl
    assert "startTime DATETIME NOT NULL" in mysql
    assert "startTime timestamp without time zone NOT NULL" in postgresql
    assert "startTime timestamp NOT NULL" in sqlite
    assert "REFERENCES Sessions(id)" in mysql
    assert "REFERENCES Sessions(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
