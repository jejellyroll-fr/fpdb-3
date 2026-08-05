"""Regression tests for HUD cache maintenance queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_cache_maintenance import cache_maintenance_queries


def test_cache_maintenance_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = cache_maintenance_queries()
    assert len(expected) == 17
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_cache_maintenance_keeps_all_cache_contexts() -> None:
    queries = cache_maintenance_queries()

    assert queries["clearHudCache"] == "DELETE FROM HudCache"
    assert queries["clearCardsCache"] == "DELETE FROM CardsCache"
    assert queries["clearPositionsCache"] == "DELETE FROM PositionsCache"
    assert "TourneyTypes" in queries["fetchNewHudCacheTourneyTypeIds"]
    assert "Sessions" in queries["fetchNewCardsCacheWeeksMonths"]
    assert "Sessions" in queries["fetchNewPositionsCacheWeeksMonths"]
    assert queries["clearCardsCacheWeeksMonths"].count("%s") == 2
