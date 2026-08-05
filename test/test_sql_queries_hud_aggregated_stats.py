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
