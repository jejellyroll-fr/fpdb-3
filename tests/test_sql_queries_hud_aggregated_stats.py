"""Regression tests for blind-level aggregated current-hand HUD stats."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fpdb_3_legacy.database_hud_stats import DatabaseHudStatsMixin
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hud_aggregated_stats import hud_aggregated_stats_queries


def test_hud_aggregated_stats_query_is_installed_with_sqlite_placeholders() -> None:
    expected = hud_aggregated_stats_queries()
    assert set(expected) == {"get_stats_from_hand_aggregated"}
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hud_aggregated_stats_keeps_current_seat_and_blind_band() -> None:
    query = hud_aggregated_stats_queries()["get_stats_from_hand_aggregated"]

    assert "max(case when hc.gametypeId = h.gametypeId" in query
    assert "then hp.seatNo" in query
    assert "gt1.bigblind <= gt2.bigblind * %s" in query
    assert "gt1.bigblind >= gt2.bigblind / %s" in query
    assert query.count("hc.seats between %s and %s") == 2


def test_hud_aggregated_stats_keeps_hero_and_opponent_scopes() -> None:
    query = hud_aggregated_stats_queries()["get_stats_from_hand_aggregated"]

    assert "hp.playerId != %s" in query
    assert "hp.playerId = %s" in query
    assert query.count("hc.styleKey > %s") == 2
    assert "GROUP BY hc.PlayerId, p.name" in query
    assert "ORDER BY hc.PlayerId, p.name" in query


def _rewritten_for_players(backend: str, placeholder: str, player_count: int = 3) -> str:
    """The aggregate re-keyed on a player set, as get_stats_for_players runs it."""
    mixin = DatabaseHudStatsMixin()
    mixin.sql = MagicMock()
    mixin.sql.query = {"placeholder": placeholder}

    sql_text = Sql(db_server=backend).query["get_stats_from_hand_aggregated"]
    for original, replacement in mixin._live_player_rewrites(placeholder, player_count):
        assert original in sql_text, f"anchor no longer in the query: {original!r}"
        sql_text = sql_text.replace(original, replacement, 1)
    return sql_text


def test_live_player_rewrite_anchors_still_match_the_query() -> None:
    """Fast-Fold stats silently vanish if the aggregate drifts from these anchors."""
    for backend, placeholder in (("sqlite", "?"), ("postgresql", "%s"), ("mysql", "%s")):
        _rewritten_for_players(backend, placeholder)


def test_live_player_rewrite_drops_every_hand_dependency() -> None:
    """No hand exists for these players, so Hands/HandsPlayers must be gone."""
    import re

    sql_text = _rewritten_for_players("sqlite", "?")

    assert "Hands" not in sql_text
    assert "HandsPlayers" not in sql_text
    assert not re.findall(r"\bh\.\w+", sql_text)
    assert not re.findall(r"\bhp\.\w+", sql_text)
    assert "WHERE hc.playerId IN (?, ?, ?)" in sql_text
    # 3 player ids + the 14 range/stake parameters the caller binds.
    assert sql_text.count("?") == 17


def _player_stats_mixin() -> tuple[DatabaseHudStatsMixin, MagicMock, MagicMock]:
    mixin = DatabaseHudStatsMixin()
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value = cursor
    mixin.connection = connection
    mixin.sql = SimpleNamespace(query=Sql(db_server="sqlite").query)
    mixin._hud_chipev_clause = ""
    mixin._merge_aof_profile_stats = MagicMock()
    return mixin, cursor, mixin._merge_aof_profile_stats


def test_get_stats_for_players_maps_rows_and_binds_ranges() -> None:
    """The live path returns the same row shape and filters as the hand path."""
    mixin, cursor, merge_profiles = _player_stats_mixin()
    cursor.description = [("player_id",), ("screen_name",), ("N",)]
    cursor.fetchall.return_value = [(11, "Alice", 23), (12, "Bob", 7)]

    result = mixin.get_stats_for_players([11, "12"], gametype_id=7, hero_id=11, num_seats=5)

    assert result == {
        11: {"player_id": 11, "screen_name": "Alice", "n": 23},
        12: {"player_id": 12, "screen_name": "Bob", "n": 7},
    }
    sql_text, subs = cursor.execute.call_args.args
    assert "WHERE hc.playerId IN (?, ?)" in sql_text
    assert "HandsPlayers" not in sql_text
    assert subs == (
        11,
        12,
        11,
        "0000000",
        1000,
        1000,
        7,
        0,
        10,
        11,
        "0000000",
        1000,
        1000,
        7,
        0,
        10,
    )
    merge_profiles.assert_called_once_with(result, None)


def test_get_stats_for_players_short_circuits_without_players() -> None:
    mixin, cursor, merge_profiles = _player_stats_mixin()

    assert mixin.get_stats_for_players([], gametype_id=7) == {}
    cursor.execute.assert_not_called()
    merge_profiles.assert_not_called()


def test_get_stats_for_players_rejects_query_drift() -> None:
    """A changed aggregate must fail closed instead of executing partial SQL."""
    mixin, cursor, merge_profiles = _player_stats_mixin()
    mixin.sql.query["get_stats_from_hand_aggregated"] = "SELECT 1"

    assert mixin.get_stats_for_players([11], gametype_id=7) == {}
    cursor.execute.assert_not_called()
    merge_profiles.assert_not_called()
