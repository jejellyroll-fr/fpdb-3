"""Regression tests for the primary current-hand HUD query."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hud_current_stats import hud_current_stats_queries


def test_hud_current_stats_query_is_installed_with_sqlite_placeholders() -> None:
    expected = hud_current_stats_queries()
    assert set(expected) == {"get_stats_from_hand"}
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hud_current_stats_keeps_current_hand_and_style_scope() -> None:
    query = hud_current_stats_queries()["get_stats_from_hand"]

    assert "INNER JOIN HudCache hc" in query
    assert "hc.PlayerId = hp.PlayerId+0" in query
    assert "hc.gametypeId+0 = h.gametypeId+0" in query
    assert "WHERE h.id = %s" in query
    assert "hc.styleKey > %s" in query
    assert "GROUP BY hc.PlayerId, hp.seatNo, p.name" in query


def test_hud_current_stats_keeps_core_hud_aliases() -> None:
    query = hud_current_stats_queries()["get_stats_from_hand"]

    for alias in ("vpip_opp", "pfr_opp", "TB_opp_0", "steal_opp", "CB_opp_1", "f_cb_opp_1", "net", "bigblind"):
        assert f"AS {alias}" in query
