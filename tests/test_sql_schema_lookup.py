"""Regression tests for poker lookup-table DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_lookup import lookup_schema_queries


def test_lookup_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = lookup_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_lookup_ddl_keeps_backend_specific_identity_types() -> None:
    keys = (
        "createActionsTable",
        "createRankTable",
        "createStartCardsTable",
        "createSitesTable",
    )
    for key in keys:
        assert "AUTO_INCREMENT" in lookup_schema_queries("mysql")[key]
        assert "SERIAL" in lookup_schema_queries("postgresql")[key]
        assert "INTEGER PRIMARY KEY" in lookup_schema_queries("sqlite")[key]


def test_mysql_quotes_reserved_rank_table_name() -> None:
    mysql = lookup_schema_queries("mysql")["createRankTable"]
    assert "CREATE TABLE `Rank`" in mysql
    assert "CREATE TABLE Rank" not in mysql
    assert "`rank` SMALLINT" in lookup_schema_queries("mysql")["createStartCardsTable"]
