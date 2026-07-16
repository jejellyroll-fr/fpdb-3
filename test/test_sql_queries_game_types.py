"""Regression tests for game and tournament type persistence queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_game_types import game_type_queries


def test_game_type_queries_are_installed_with_sqlite_placeholders() -> None:
    for backend in ("mysql", "postgresql"):
        expected = game_type_queries(backend)
        assert len(expected) == 10
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {
        key: value.replace("%s", "?") for key, value in game_type_queries("sqlite").items()
    }
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_game_type_queries_keep_backend_tourney_remapping() -> None:
    sqlite = game_type_queries("sqlite")["updateTourneyTypeId"]
    postgres = game_type_queries("postgresql")["updateTourneyTypeId"]
    mysql = game_type_queries("mysql")["updateTourneyTypeId"]

    assert "tourneyTypeId in (SELECT id FROM TourneyTypes" in sqlite
    assert "UPDATE Tourneys t" in postgres and "FROM TourneyTypes tt" in postgres
    assert "UPDATE Tourneys t INNER JOIN TourneyTypes tt" in mysql


def test_game_type_queries_keep_full_type_dimensions() -> None:
    queries = game_type_queries("postgresql")

    for column in ("buyinType", "fast", "newToGame", "homeGame", "split"):
        assert column in queries["getGametypeNL"]
        assert column in queries["insertGameTypes"]
    for column in ("progressive", "multiEntry", "reEntry", "flighted", "guarantee", "lottery", "multiplier"):
        assert column in queries["getTourneyTypeId"]
        assert column in queries["insertTourneyType"]


def test_game_type_lookups_distinguish_limit_variants() -> None:
    queries = game_type_queries("postgresql")

    assert queries["getGametypeFL"].count("limitType=%s") == 1
    assert queries["getGametypeNL"].count("limitType=%s") == 1
