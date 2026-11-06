"""Regression tests for calendar-period DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_time import time_schema_queries


def test_time_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = time_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_week_and_month_tables_share_backend_identity_and_time_types() -> None:
    for key, column in (
        ("createWeeksTable", "weekStart"),
        ("createMonthsTable", "monthStart"),
    ):
        mysql = time_schema_queries("mysql")[key]
        postgresql = time_schema_queries("postgresql")[key]
        sqlite = time_schema_queries("sqlite")[key]

        assert "INT UNSIGNED AUTO_INCREMENT" in mysql
        assert f"{column} DATETIME NOT NULL" in mysql
        assert "id SERIAL" in postgresql
        assert f"{column} timestamp without time zone NOT NULL" in postgresql
        assert "id INTEGER PRIMARY KEY" in sqlite
        assert f"{column} timestamp NOT NULL" in sqlite


def test_sessions_ddl_keeps_period_relations_and_time_types() -> None:
    mysql = time_schema_queries("mysql")["createSessionsTable"]
    postgresql = time_schema_queries("postgresql")["createSessionsTable"]
    sqlite = time_schema_queries("sqlite")["createSessionsTable"]

    assert "sessionStart DATETIME NOT NULL" in mysql
    assert "sessionEnd timestamp without time zone NOT NULL" in postgresql
    assert "sessionStart timestamp NOT NULL" in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Weeks(id)" in ddl
        assert "REFERENCES Months(id)" in ddl
    assert "FOREIGN KEY" not in sqlite
