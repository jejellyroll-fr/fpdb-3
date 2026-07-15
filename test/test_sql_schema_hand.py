"""Regression tests for poker hand-domain DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries


def test_hand_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = hand_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_boards_ddl_keeps_backend_specific_hand_relation() -> None:
    mysql = hand_schema_queries("mysql")["createBoardsTable"]
    postgresql = hand_schema_queries("postgresql")["createBoardsTable"]
    sqlite = hand_schema_queries("sqlite")["createBoardsTable"]

    assert "BIGINT UNSIGNED AUTO_INCREMENT" in mysql
    assert "BIGSERIAL" in postgresql
    assert "INTEGER PRIMARY KEY" in sqlite
    assert "FOREIGN KEY (handId) REFERENCES Hands(id)" in mysql
    assert "FOREIGN KEY (handId) REFERENCES Hands(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
