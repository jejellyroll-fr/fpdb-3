"""Regression tests for player identity DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_player import player_schema_queries


def test_player_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = player_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_players_ddl_keeps_backend_specific_identity_and_site_link() -> None:
    mysql = player_schema_queries("mysql")["createPlayersTable"]
    postgresql = player_schema_queries("postgresql")["createPlayersTable"]
    sqlite = player_schema_queries("sqlite")["createPlayersTable"]

    assert "INT UNSIGNED AUTO_INCREMENT" in mysql
    assert "id SERIAL" in postgresql
    assert "id INTEGER PRIMARY KEY" in sqlite
    assert "REFERENCES Sites(id)" in mysql
    assert "REFERENCES Sites(id)" in postgresql
    assert "REFERENCES Sites(id) ON DELETE CASCADE" in sqlite
