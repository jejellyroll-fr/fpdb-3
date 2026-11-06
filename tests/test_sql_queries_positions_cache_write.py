"""Regression tests for primary PositionsCache write queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_positions_cache_write import positions_cache_write_queries


def test_positions_cache_write_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = positions_cache_write_queries()
    assert len(expected) == 4
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_positions_cache_write_keeps_full_positional_context() -> None:
    queries = positions_cache_write_queries()
    insert = queries["insert_positionscache"]
    update = queries["update_positionscache"]

    assert insert.index("playerId") < insert.index("seats") < insert.index("maxPosition") < insert.index("position")
    # The update used to set street0Limp, street0OpenLimpChance and
    # street0OpenLimp, which no variant of PositionsCache declares, so every
    # update raised "no such column". The statistics stop at street3Discards,
    # the last column the table actually has.
    assert update.index("street3Discards") < update.index("WHERE id=%s")
    for absent in ("street0Limp", "street0OpenLimpChance", "street0OpenLimp"):
        assert absent not in update
    assert update.rstrip().endswith("WHERE id=%s")
    for key in ("select_positionscache_ring", "select_positionscache_tour"):
        for condition in ("playerId=%s", "seats=%s", "maxPosition=%s", "position=%s"):
            assert condition in queries[key]
