"""The HUD shows Total Profit in the game type's currency (#797).

``totalprofit`` read ``currency`` from the stat dict with a USD default, and no
HUD query selected it, so a euro game showed dollars and a tournament showed its
chips as dollars. The three HUD query families now select it.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.database_hud_stats import DatabaseHudStatsMixin
from fpdb_3_legacy.localized_formats import set_format_locale
from fpdb_3_legacy.sql_queries_hud_aggregated_stats import hud_aggregated_stats_queries
from fpdb_3_legacy.sql_queries_hud_current_stats import hud_current_stats_queries
from fpdb_3_legacy.sql_queries_hud_session_stats import hud_session_stats_queries
from fpdb_3_legacy.stats_financial import totalprofit


@pytest.fixture(autouse=True)
def _english_formats() -> None:
    set_format_locale("en_US")


def _select_list(query: str) -> str:
    return query.split("FROM", 1)[0]


@pytest.mark.parametrize(
    "query",
    [
        *hud_current_stats_queries().values(),
        *hud_aggregated_stats_queries().values(),
        *(q for server in ("mysql", "postgresql", "sqlite") for q in hud_session_stats_queries(server).values()),
    ],
)
def test_every_hud_query_selects_the_currency(query: str) -> None:
    assert re.search(r"\bAS currency\b", _select_list(query))


#: The pooling expression of the current and aggregated queries, written out so
#: the test runs a fixed statement (no SQL is assembled at run time).
POOLED_CURRENCY = "CASE WHEN MIN(gt.currency) = MAX(gt.currency) THEN MAX(gt.currency) ELSE '' END"
POOLED_CURRENCY_QUERY = "SELECT CASE WHEN MIN(gt.currency) = MAX(gt.currency) THEN MAX(gt.currency) ELSE '' END FROM gt"


@pytest.mark.parametrize(
    "query",
    [*hud_current_stats_queries().values(), *hud_aggregated_stats_queries().values()],
)
def test_the_pooled_queries_use_the_tested_expression(query: str) -> None:
    assert f"{POOLED_CURRENCY} AS currency" in " ".join(_select_list(query).split())


def test_pooled_game_types_keep_one_currency_or_none() -> None:
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE gt (currency TEXT)")
        db.executemany("INSERT INTO gt VALUES (?)", [("EUR",), ("EUR",)])
        assert db.execute(POOLED_CURRENCY_QUERY).fetchone()[0] == "EUR"
        db.execute("INSERT INTO gt VALUES ('USD')")
        assert db.execute(POOLED_CURRENCY_QUERY).fetchone()[0] == ""


def test_total_profit_uses_the_selected_currency() -> None:
    assert totalprofit({1: {"net": 123450, "currency": "EUR"}}, 1)[1] == "€1,234.50"
    assert totalprofit({1: {"net": 123450, "currency": "T$"}}, 1)[1].startswith("T$")


def test_total_profit_without_one_currency_shows_no_symbol() -> None:
    assert totalprofit({1: {"net": 123450, "currency": ""}}, 1)[1] == "1,234.50"
    assert totalprofit({1: {"net": 123450}}, 1)[1] == "1,234.50"


class _Cursor:
    description = [("player_id",), ("seats",), ("hand_id",), ("net",), ("currency",)]

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = list(rows)

    def execute(self, *_args: object) -> None:
        return None

    def fetchone(self) -> tuple | None:
        return self._rows.pop(0) if self._rows else None


def _session_stats(rows: list[tuple]) -> dict:
    """Run the session merge of DatabaseHudStatsMixin on the given rows, for player 7."""
    db = SimpleNamespace(
        sql=SimpleNamespace(query={"get_stats_from_hand_session": "SELECT"}),
        db_server="sqlite",
        hand_1day_ago=0,
        get_cursor=lambda: _Cursor(rows),
    )
    stat_dict: dict = {}
    DatabaseHudStatsMixin.get_stats_from_hand_session(db, 1, stat_dict, None, "S", 2, 10, "S", 2, 10)  # type: ignore[arg-type]
    return stat_dict[7]


def test_the_session_merge_does_not_add_up_the_currency() -> None:
    same = _session_stats([(7, 6, 1, 100, "EUR"), (7, 6, 2, 50, "EUR")])
    assert same["net"] == 150
    assert same["currency"] == "EUR"
    mixed = _session_stats([(7, 6, 1, 100, "EUR"), (7, 6, 2, 50, "USD")])
    assert mixed["net"] == 150
    assert mixed["currency"] == ""
