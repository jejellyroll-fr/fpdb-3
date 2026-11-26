"""Regression tests for cash-game profit graph queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_cash_profit import cash_profit_queries, period_results_queries


def test_cash_profit_queries_are_installed_exactly() -> None:
    expected = cash_profit_queries() | period_results_queries()
    assert len(expected) == 4
    for backend in ("mysql", "postgresql", "sqlite"):
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_cash_profit_queries_keep_units_equity_and_filters() -> None:
    queries = cash_profit_queries()
    big_blinds = queries["getRingProfitAllHandsPlayerIdSiteInBB"]
    dollars = queries["getRingProfitAllHandsPlayerIdSiteInDollars"]

    assert "hp.allInEV" in big_blinds
    assert "gt.bigBlind" in big_blinds
    assert "hp.allInEV" in dollars
    assert "COALESCE(hp.splashWinnings, 0)" in big_blinds
    assert "COALESCE(hp.splashWinnings, 0)" in dollars
    assert "hp.splashWinnings" in queries["getRingProfitAllHandsPlayerIdSite"]
    assert "gt.bigBlind" in big_blinds
    # A hand without an all-in EV plots its result as its EV (#827).
    assert "COALESCE(hp.allInEV, hp.totalProfit)" in big_blinds
    assert "COALESCE(hp.allInEV, hp.totalProfit)" in dollars
    assert len(queries) == 3
    for query in queries.values():
        assert "<player_test>" in query
        assert "<site_test>" in query
        assert "<startdate_test>" in query
        assert "<enddate_test>" in query
        assert "ORDER BY h.startTime, hp.handId" in query


def test_period_results_query_reads_cash_hands_with_their_ev_and_blind() -> None:
    query = period_results_queries()["periodResultsHands"]

    assert "h.startTime" in query
    assert "COALESCE(hp.allInEV, hp.totalProfit)" in query
    assert "hp.sawShowdown" in query
    assert "gt.bigBlind" in query
    assert "gt.currency" in query
    assert "hp.street0VPIChance" in query
    assert "hp.street0VPI" in query
    assert "hp.street0AggrChance" in query
    assert "hp.street0Aggr" in query
    assert "gt.type = 'ring'" in query
    assert "hp.tourneysPlayersId IS NULL" in query
    for placeholder in (
        "<player_test>",
        "<startdate_test>",
        "<enddate_test>",
        "<limit_test>",
        "<game_test>",
        "<currency_test>",
        "<seats_test>",
    ):
        assert placeholder in query
    assert "hp.playerId" in query
    assert "ORDER BY h.startTime, h.id" in query
