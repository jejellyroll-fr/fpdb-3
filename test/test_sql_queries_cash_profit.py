"""Regression tests for cash-game profit graph queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_cash_profit import cash_profit_queries


def test_cash_profit_queries_are_installed_exactly() -> None:
    expected = cash_profit_queries()
    assert len(expected) == 3
    for backend in ("mysql", "postgresql", "sqlite"):
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_cash_profit_queries_keep_units_equity_and_filters() -> None:
    queries = cash_profit_queries()
    big_blinds = queries["getRingProfitAllHandsPlayerIdSiteInBB"]
    dollars = queries["getRingProfitAllHandsPlayerIdSiteInDollars"]

    assert "hp.allInEV" in big_blinds
    assert "gt.bigBlind" in big_blinds
    assert "hp.allInEV" in dollars
    for query in queries.values():
        assert "<player_test>" in query
        assert "<site_test>" in query
        assert "<startdate_test>" in query
        assert "<enddate_test>" in query
        assert "ORDER BY h.startTime" in query
