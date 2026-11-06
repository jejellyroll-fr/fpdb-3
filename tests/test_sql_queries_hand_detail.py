"""Regression tests for single-hand detail queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hand_detail import hand_detail_queries


def test_hand_detail_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = hand_detail_queries()
    assert len(expected) == 6
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hand_detail_queries_keep_draw_cards_and_table_context() -> None:
    queries = hand_detail_queries()

    cards = queries["get_cards"]
    assert "COALESCE(NULLIF(card16,0)" in cards
    assert "ORDER BY seatNo" in cards
    table = queries["get_table_name"]
    assert "gt.maxSeats" in table
    assert "gt.fast" in table
    assert "count(1) as numseats" in table
    assert "boardcard5" in queries["get_common_cards"]
