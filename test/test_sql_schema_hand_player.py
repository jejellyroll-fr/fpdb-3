"""Regression tests for per-player poker-hand DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_hand_player import hand_player_schema_queries


def test_hand_player_schema_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = hand_player_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_hands_players_ddl_keeps_hud_and_tournament_columns() -> None:
    mysql = hand_player_schema_queries("mysql")["createHandsPlayersTable"]
    postgresql = hand_player_schema_queries("postgresql")["createHandsPlayersTable"]
    sqlite = hand_player_schema_queries("sqlite")["createHandsPlayersTable"]

    for ddl in (mysql, postgresql, sqlite):
        assert "street0VPIChance" in ddl
        assert "raiseToStealChance" in ddl
        assert "tourneysPlayersId" in ddl
        assert "allInEV" in ddl
    assert "position CHAR(1)" in mysql
    assert "position CHAR(1)" in postgresql
    assert "position TEXT" in sqlite
    assert "REFERENCES TourneysPlayers(id)" in mysql
    assert "REFERENCES TourneysPlayers(id)" in postgresql
    assert "FOREIGN KEY" not in sqlite
