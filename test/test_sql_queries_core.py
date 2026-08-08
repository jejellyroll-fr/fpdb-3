"""Regression tests for core SQL lookup queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_core import core_lookup_queries


def test_core_lookup_queries_are_installed_exactly() -> None:
    expected = core_lookup_queries()
    assert len(expected) == 8
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_core_lookup_queries_keep_expected_parameters_and_links() -> None:
    queries = core_lookup_queries()

    assert queries["get_last_hand"] == "select max(id) from Hands"
    assert queries["get_player_id"].count("%s") == 2
    assert queries["get_player_names"].count("%s") == 3
    gameinfo = queries["get_gameinfo_from_hid"]
    assert gameinfo.count("%s") == 1
    assert "h.gametypeId" in gameinfo
    assert "s.id = p.siteId" in gameinfo
