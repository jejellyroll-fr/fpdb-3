"""Regression tests for primary HUD cache write queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hud_cache_write import hud_cache_write_queries


def test_hud_cache_write_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = hud_cache_write_queries()
    assert len(expected) == 5
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hud_cache_write_keeps_position_and_turn_extension_columns() -> None:
    queries = hud_cache_write_queries()
    insert = queries["insert_hudcache"]
    update = queries["update_hudcache"]

    for column in (
        "street2DelayedCBChance",
        "street2DelayedCBDone",
        "street2ProbeChance",
        "street2ProbeDone",
    ):
        assert column in insert
        assert column in update
    for key in ("select_hudcache_ring", "select_hudcache_tour"):
        assert "position=%s" in queries[key]
        assert "styleKey = %s" in queries[key]
