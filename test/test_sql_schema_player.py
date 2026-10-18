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


#: ``Players.name`` compares byte for byte (#417): case, accents and ligatures are distinct, so
#: two players whose names differ there are two rows and their actions stay apart.
def test_players_name_is_declared_with_a_binary_collation() -> None:
    mysql = player_schema_queries("mysql")["createPlayersTable"]
    postgresql = player_schema_queries("postgresql")["createPlayersTable"]
    sqlite = player_schema_queries("sqlite")["createPlayersTable"]

    assert "name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL" in mysql
    assert 'name VARCHAR(32) COLLATE "C"' in postgresql
    assert "name TEXT COLLATE BINARY" in sqlite


def test_autorates_ddl_keeps_backend_specific_relations() -> None:
    mysql = player_schema_queries("mysql")["createAutoratesTable"]
    postgresql = player_schema_queries("postgresql")["createAutoratesTable"]
    sqlite = player_schema_queries("sqlite")["createAutoratesTable"]

    assert "BIGINT UNSIGNED AUTO_INCREMENT" in mysql
    assert "BIGSERIAL" in postgresql
    assert "FOREIGN KEY" not in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Players(id)" in ddl
        assert "REFERENCES Gametypes(id)" in ddl


def test_player_auto_notes_ddl_keeps_unique_rule_hits_and_times() -> None:
    mysql = player_schema_queries("mysql")["createPlayerAutoNotesTable"]
    postgresql = player_schema_queries("postgresql")["createPlayerAutoNotesTable"]
    sqlite = player_schema_queries("sqlite")["createPlayerAutoNotesTable"]

    columns = "(playerId, handId, ruleId, ruleVersion)"
    assert f"UNIQUE KEY player_auto_note_rule_hit {columns}" in mysql
    assert f"UNIQUE {columns}" in postgresql
    assert f"UNIQUE {columns}" in sqlite
    assert "createdTs DATETIME DEFAULT CURRENT_TIMESTAMP" in mysql
    assert "timestamp without time zone DEFAULT CURRENT_TIMESTAMP" in postgresql
    assert "FOREIGN KEY" not in sqlite
