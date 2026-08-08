"""Regression tests for blind-level aggregated current-hand HUD stats."""

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
    from unittest.mock import MagicMock

    from fpdb_3_legacy.database_hud_stats import DatabaseHudStatsMixin

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
