"""Regression tests for the root poker-hand DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_hand_root import root_hand_schema_queries


def test_root_hand_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = root_hand_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_hands_ddl_keeps_backend_specific_links_and_pot_types() -> None:
    mysql = root_hand_schema_queries("mysql")["createHandsTable"]
    postgresql = root_hand_schema_queries("postgresql")["createHandsTable"]
    sqlite = root_hand_schema_queries("sqlite")["createHandsTable"]

    assert "id BIGINT UNSIGNED AUTO_INCREMENT" in mysql
    assert "id BIGSERIAL" in postgresql
    assert "id INTEGER PRIMARY KEY" in sqlite
    assert "finalPot   BIGINT" in mysql
    assert "finalPot   BIGINT" in postgresql
    assert "finalPot INT" in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Gametypes(id)" in ddl
        assert "REFERENCES Files(id)" in ddl
    assert "FOREIGN KEY" not in sqlite
