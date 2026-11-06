"""Regression tests for primary CardsCache write queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_cards_cache_write import cards_cache_write_queries


def test_cards_cache_write_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = cards_cache_write_queries()
    assert len(expected) == 4
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_cards_cache_write_keeps_starting_card_context_and_value_order() -> None:
    queries = cards_cache_write_queries()
    insert = queries["insert_cardscache"]
    update = queries["update_cardscache"]

    assert insert.index("playerId") < insert.index("startCards") < insert.index("street0VPIChance")
    assert update.index("n=n+%s") < update.index("street0VPIChance=street0VPIChance+%s")
    assert update.rstrip().endswith("WHERE     id=%s")
    for key in ("select_cardscache_ring", "select_cardscache_tour"):
        assert "playerId=%s" in queries[key]
        assert "startCards=%s" in queries[key]
