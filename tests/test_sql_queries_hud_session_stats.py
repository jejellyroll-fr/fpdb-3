"""Regression tests for backend-specific HUD session queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hud_session_stats import hud_session_stats_queries


def test_hud_session_stats_query_is_installed_with_sqlite_placeholders() -> None:
    for backend in ("mysql", "postgresql"):
        expected = hud_session_stats_queries(backend)
        assert set(expected) == {"get_stats_from_hand_session"}
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {
        key: value.replace("%s", "?")
        for key, value in hud_session_stats_queries("sqlite").items()
    }
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hud_session_stats_keeps_backend_casts() -> None:
    mysql = hud_session_stats_queries("mysql")["get_stats_from_hand_session"]
    postgres = hud_session_stats_queries("postgresql")["get_stats_from_hand_session"]
    sqlite = hud_session_stats_queries("sqlite")["get_stats_from_hand_session"]

    assert "cast(hp2.street0VPIChance as SIGNED)" in mysql
    assert "cast(hp2.street0VPIChance as <signed>integer)" in postgres
    assert "cast(hp2.street0VPIChance as <signed>integer)" in sqlite


def test_hud_session_stats_keeps_order_and_session_scope() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        query = hud_session_stats_queries(backend)["get_stats_from_hand_session"]
        if backend == "mysql":
            aliases = ("AS player_id,", "AS seats,", "AS hand_id,", "AS seat,", "AS screen_name,")
        else:
            aliases = ("AS player_id,", "AS hand_id,", "AS seat,", "AS screen_name,", "AS seats,")
        indexes = [query.index(alias) for alias in aliases]
        assert indexes == sorted(indexes)
        assert "h2.tableName = h.tableName" in query
        assert query.count("h2.seats between %s and %s") == 2
        assert "hp2.playerId != %s" in query
        assert "hp2.playerId = %s" in query
        assert "ORDER BY h.startTime desc, hp2.PlayerId" in query
