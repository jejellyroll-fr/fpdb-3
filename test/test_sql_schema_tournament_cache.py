"""Regression tests for tournament statistics cache DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_tournament_cache import tournament_cache_schema_queries


def test_tournament_cache_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = tournament_cache_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_tourneys_cache_keeps_context_and_financial_columns() -> None:
    mysql = tournament_cache_schema_queries("mysql")["createTourneysCacheTable"]
    postgresql = tournament_cache_schema_queries("postgresql")["createTourneysCacheTable"]
    sqlite = tournament_cache_schema_queries("sqlite")["createTourneysCacheTable"]

    for ddl in (mysql, postgresql, sqlite):
        assert "sessionId" in ddl
        assert "tourneyId" in ddl
        assert "street0VPIChance" in ddl
        assert "allInEV" in ddl
    assert "startTime DATETIME NOT NULL" in mysql
    assert "startTime timestamp without time zone NOT NULL" in postgresql
    assert "startTime timestamp NOT NULL" in sqlite
    assert "REFERENCES Tourneys(id)" in mysql
    assert "REFERENCES Tourneys(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
