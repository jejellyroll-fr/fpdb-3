"""Regression tests for hand-history import DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_import import import_schema_queries


def test_import_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = import_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_files_ddl_keeps_backend_specific_identity_and_times() -> None:
    mysql = import_schema_queries("mysql")["createFilesTable"]
    postgresql = import_schema_queries("postgresql")["createFilesTable"]
    sqlite = import_schema_queries("sqlite")["createFilesTable"]

    assert "INT(10) UNSIGNED AUTO_INCREMENT" in mysql
    assert "id BIGSERIAL" in postgresql
    assert "id INTEGER PRIMARY KEY" in sqlite
    assert "startTime DATETIME NOT NULL" in mysql
    assert "startTime timestamp without time zone NOT NULL" in postgresql
    assert "startTime timestamp NOT NULL" in sqlite
    for ddl in (mysql, postgresql, sqlite):
        assert "storedHands INT" in ddl
        assert "finished BOOLEAN" in ddl
