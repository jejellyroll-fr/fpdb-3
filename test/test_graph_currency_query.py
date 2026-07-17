"""Regression test for the cash-game graph query selection.

getRingProfitGraph() must pick its SQL query based on BB-vs-currency mode, not
on the literal "$". A localized currency symbol ("€", "£", ...) previously
matched neither branch and left the query variable unbound (UnboundLocalError),
so the graph rendered nothing for any non-USD currency.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.GuiGraphViewer import GuiGraphViewer


def _make_viewer(executed: list[str]) -> GuiGraphViewer:
    viewer = GuiGraphViewer.__new__(GuiGraphViewer)
    # Query templates carry a unique marker so the test can tell which was used.
    viewer.sql = SimpleNamespace(
        query={
            "getRingProfitAllHandsPlayerIdSiteInDollars": "DOLLARS <game_test> <player_test> "
            "<site_test> <startdate_test> <enddate_test> <limit_test> <currency_test>",
            "getRingProfitAllHandsPlayerIdSiteInBB": "BB <game_test> <player_test> "
            "<site_test> <startdate_test> <enddate_test> <limit_test> <currency_test>",
        },
    )
    viewer.filters = SimpleNamespace(
        getDates=lambda: ("2020-01-01", "2020-12-31"),
        display={"Games": False},
        get_limits_where_clause=lambda limits: "",
        getType=lambda: "ring",
    )
    cursor = SimpleNamespace(
        execute=lambda tmp: executed.append(tmp),
        fetchall=lambda: [],
    )
    viewer.db = SimpleNamespace(cursor=cursor, rollback=lambda: None)
    return viewer


def _run(units: str) -> str:
    executed: list[str] = []
    viewer = _make_viewer(executed)
    result = viewer.getRingProfitGraph([1], [2], [], [], ["USD"], units)
    # Empty result set -> (None, None, None, None), but the query still ran.
    assert result == (None, None, None, None)
    assert executed, "no SQL query was executed"
    return executed[0].split(" ", 1)[0]  # the marker token


def test_bb_mode_uses_bb_query() -> None:
    assert _run("BB") == "BB"


def test_dollar_symbol_uses_dollars_query() -> None:
    assert _run("$") == "DOLLARS"


def test_localized_currency_symbols_use_dollars_query() -> None:
    # These previously raised UnboundLocalError and blanked the graph.
    for symbol in ("€", "£", "T$", "PLAY"):
        assert _run(symbol) == "DOLLARS", f"currency {symbol!r} did not select the money query"
