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


def test_hands_cashout_ddl_keeps_money_and_player_relations() -> None:
    mysql = hand_schema_queries("mysql")["createHandsCashoutTable"]
    postgresql = hand_schema_queries("postgresql")["createHandsCashoutTable"]
    sqlite = hand_schema_queries("sqlite")["createHandsCashoutTable"]

    assert "amount NUMERIC" in mysql
    assert "fee NUMERIC" in postgresql
    assert "amount decimal" in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Hands(id)" in ddl
        assert "REFERENCES Players(id)" in ddl
    assert "FOREIGN KEY" not in sqlite


def test_hands_showdown_ddl_keeps_card_text_and_relations() -> None:
    mysql = hand_schema_queries("mysql")["createHandsShowdownTable"]
    postgresql = hand_schema_queries("postgresql")["createHandsShowdownTable"]
    sqlite = hand_schema_queries("sqlite")["createHandsShowdownTable"]

    assert "combo VARCHAR(255)" in mysql
    assert "cards VARCHAR(64)" in postgresql
    assert "combo TEXT" in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Hands(id)" in ddl
        assert "REFERENCES Players(id)" in ddl
    assert "FOREIGN KEY" not in sqlite


def test_hands_stove_ddl_keeps_equity_and_rank_relations() -> None:
    mysql = hand_schema_queries("mysql")["createHandsStoveTable"]
    postgresql = hand_schema_queries("postgresql")["createHandsStoveTable"]
    sqlite = hand_schema_queries("sqlite")["createHandsStoveTable"]

    assert "ev NUMERIC" in mysql
    assert "ev NUMERIC" in postgresql
    assert "ev decimal" in sqlite
    assert "REFERENCES `Rank`(id)" in mysql
    assert "REFERENCES Rank(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite


def test_hands_actions_ddl_keeps_amounts_and_action_relations() -> None:
    mysql = hand_schema_queries("mysql")["createHandsActionsTable"]
    postgresql = hand_schema_queries("postgresql")["createHandsActionsTable"]
    sqlite = hand_schema_queries("sqlite")["createHandsActionsTable"]

    assert "amount BIGINT NOT NULL" in mysql
    assert "amount BIGINT" in postgresql
    assert "amount INT" in sqlite
    assert "cardsDiscarded varchar(14)" in mysql
    assert "cardsDiscarded TEXT" in sqlite
    for ddl in (mysql, postgresql):
        assert "REFERENCES Actions(id)" in ddl
    assert "FOREIGN KEY" not in sqlite
