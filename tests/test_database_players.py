"""Unit tests for DatabasePlayersMixin and player resolution methods."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_players import DatabasePlayersMixin


class DummyPlayerDB(DatabasePlayersMixin):
    def __init__(self):
        self.config = SimpleNamespace(
            supported_sites={"PokerStars": SimpleNamespace(screen_name="HeroStars")},
            get_hero_aliases=lambda site: ["HeroStars", "HeroAlias"] if site == "PokerStars" else [],
            get_supported_sites=lambda: ["PokerStars"],
        )
        self.sql = SimpleNamespace(query={"placeholder": "%s", "get_player_id": "get_player_id_sql", "get_player_names": "get_player_names_sql"})
        self.connection = MagicMock()
        self.backend = 4
        self.MYSQL_INNODB = 2
        self.pcache = None

    def get_site_id(self, site):
        if site == "PokerStars":
            return [[1]]
        return []

    def get_cursor(self, connect: bool = False):
        return self.connection.cursor()


def test_hero_aliases_resolution() -> None:
    db = DummyPlayerDB()
    aliases = db._hero_aliases("PokerStars")
    assert aliases == ["HeroStars", "HeroAlias"]

    empty_aliases = db._hero_aliases("UnknownSite")
    assert empty_aliases == []


def test_resolve_alias_ids() -> None:
    db = DummyPlayerDB()
    cursor_mock = db.connection.cursor.return_value
    cursor_mock.fetchall.return_value = [[101], [102]]

    res = db._resolve_alias_ids("PokerStars", ["HeroStars", "HeroAlias"])
    assert res == {101, 102}
    cursor_mock.execute.assert_called_once()


def test_get_hero_player_ids() -> None:
    db = DummyPlayerDB()
    cursor_mock = db.connection.cursor.return_value
    cursor_mock.fetchall.return_value = [[101]]

    ids = db.get_hero_player_ids("PokerStars")
    assert ids == [101]


def test_get_player_id_found() -> None:
    db = DummyPlayerDB()
    cursor_mock = db.connection.cursor.return_value
    cursor_mock.fetchone.return_value = [42]

    player_id = db.get_player_id(db.config, "PokerStars", "HeroStars")
    assert player_id == 42


def test_get_player_id_fallback_single() -> None:
    db = DummyPlayerDB()
    cursor_mock = db.connection.cursor.return_value
    # First fetchone on get_player_id returns None
    cursor_mock.fetchone.return_value = None
    # Fallback fetchall returns single match
    cursor_mock.fetchall.return_value = [[99]]

    player_id = db.get_player_id(db.config, "PokerStars", "UnknownOnSite")
    assert player_id == 99


def test_get_player_name_by_id() -> None:
    db = DummyPlayerDB()
    cursor_mock = db.connection.cursor.return_value
    cursor_mock.fetchone.return_value = ["Alice"]

    name = db.get_player_name_by_id(50)
    assert name == "Alice"


def test_database_inherits_players_mixin() -> None:
    assert issubclass(Database, DatabasePlayersMixin)
