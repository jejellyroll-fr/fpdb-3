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


def test_tourneys_ddl_keeps_backend_specific_relations_and_times() -> None:
    mysql = tournament_schema_queries("mysql")["createTourneysTable"]
    postgresql = tournament_schema_queries("postgresql")["createTourneysTable"]
    sqlite = tournament_schema_queries("sqlite")["createTourneysTable"]

    assert "INT UNSIGNED AUTO_INCREMENT" in mysql
    assert "id SERIAL" in postgresql
    assert "id INTEGER PRIMARY KEY" in sqlite
    assert "startTime DATETIME" in mysql
    assert "startTime timestamp without time zone" in postgresql
    assert "FOREIGN KEY" not in sqlite


def test_tourney_types_ddl_keeps_backend_specific_money_and_site_link() -> None:
    mysql = tournament_schema_queries("mysql")["createTourneyTypesTable"]
    postgresql = tournament_schema_queries("postgresql")["createTourneyTypesTable"]
    sqlite = tournament_schema_queries("sqlite")["createTourneyTypesTable"]

    assert "SMALLINT UNSIGNED AUTO_INCREMENT" in mysql
    assert "id SERIAL" in postgresql
    assert "id INTEGER PRIMARY KEY" in sqlite
    assert "guaranteeAmt BIGINT" in mysql
    assert "guaranteeAmt BIGINT" in postgresql
    assert "guaranteeAmt INT" in sqlite
    assert "REFERENCES Sites(id)" in mysql
    assert "REFERENCES Sites(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
