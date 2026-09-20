"""Two things the engine got wrong on PostgreSQL and right everywhere else (#349).

Both bugs reached a user's real database while the whole suite stayed green,
because the suite runs on SQLite and each fault is a difference between the two
backends rather than a mistake in the SQL:

* SQLite binds parameters with ``?`` and reads ``%`` as an ordinary operator.
  psycopg binds with ``%s``, so every ``%`` starts a placeholder unless it is
  doubled -- and the Hold'em class dimension is written with the modulo
  operator, which is what the range explorer groups by.
* SQLite hands back a column alias as the SELECT spelled it. PostgreSQL folds
  an unquoted alias to lower case, so ``AS handId`` comes back ``handid``.

So these tests do not use a PostgreSQL server. They compile for it, and they
put the one behaviour that matters -- identifier folding -- in front of the
SQLite fixture, which is a faithful stand-in for the failure and needs no
database to be installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.analytics_profit import compile_profit_query
from fpdb_3_legacy.analytics_query import DIMENSIONS, Query, compile_query, escape_literal_percent
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

PG_PLACEHOLDER = "%s"
SQLITE_PLACEHOLDER = "?"

#: The dimension the range explorer groups by, and the one that carries a
#: modulo operator: ``((card - 1) % 13)``.
CLASS_DIMENSION = "starting_hand_id"


def _bare_percents(sql: str, placeholder: str) -> int:
    """How many ``%`` would psycopg read as the start of a placeholder."""
    return sql.replace("%%", "").replace(placeholder, "").count("%")


# ---------------------------------------------------------------------------
# The modulo operator against a pyformat driver.
# ---------------------------------------------------------------------------


def test_the_range_dimension_leaves_no_bare_percent_for_psycopg() -> None:
    """This is the query that failed: "incomplete placeholder: '%'"."""
    compiled = compile_query(
        Query(metric="raise_frequency", filters={}, group_by=(CLASS_DIMENSION,)),
        PG_PLACEHOLDER,
        "postgresql",
    )

    assert "%%" in compiled.sql, "the modulo operators must be doubled"
    assert _bare_percents(compiled.sql, PG_PLACEHOLDER) == 0
    assert compiled.sql.count(PG_PLACEHOLDER) == len(compiled.params)


def test_the_money_query_of_a_range_is_escaped_too() -> None:
    # build_range() groups the profit report by the same dimension, so fixing
    # only the count query would have moved the error one line down.
    compiled = compile_profit_query(
        Query(metric="total_profit", filters={}, group_by=(CLASS_DIMENSION,)),
        PG_PLACEHOLDER,
        "postgresql",
    )

    assert _bare_percents(compiled.sql, PG_PLACEHOLDER) == 0


@pytest.mark.parametrize("dimension", sorted(DIMENSIONS))
def test_no_dimension_can_reach_psycopg_with_a_bare_percent(dimension: str) -> None:
    # A net rather than a patch: any dimension added later that reaches for an
    # operator psycopg reads as a placeholder fails here rather than in a user's
    # log.
    compiled = compile_query(
        Query(metric="raise_frequency", filters={}, group_by=(dimension,)),
        PG_PLACEHOLDER,
        "postgresql",
    )

    assert _bare_percents(compiled.sql, PG_PLACEHOLDER) == 0


def test_sqlite_keeps_its_percent_operators_as_they_are() -> None:
    """``?`` parameters read ``%`` as arithmetic, so doubling it would break it."""
    compiled = compile_query(
        Query(metric="raise_frequency", filters={}, group_by=(CLASS_DIMENSION,)),
        SQLITE_PLACEHOLDER,
        "sqlite",
    )

    assert "%%" not in compiled.sql
    assert "% 13" in compiled.sql


def test_escaping_protects_the_placeholders_it_finds() -> None:
    assert escape_literal_percent("a % 13 = %s", "%s") == "a %% 13 = %s"
    assert escape_literal_percent("a % 13 = ?", "?") == "a % 13 = ?"


# ---------------------------------------------------------------------------
# Identifier folding.
# ---------------------------------------------------------------------------


class _FoldingCursor:
    """A cursor that lower-cases its column names, as PostgreSQL does."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def description(self) -> Any:
        return [(str(column[0]).lower(), *tuple(column[1:])) for column in self._inner.description]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _FoldingDatabase:
    """The golden SQLite database, answering with PostgreSQL's column names."""

    def __init__(self, inner: Database) -> None:
        self._inner = inner

    def get_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return _FoldingCursor(self._inner.get_cursor(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@pytest.fixture(scope="module")
def golden_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("pg-portability")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)  # its destructor would close the connection
    return db


_MODULE_STATE: list[object] = []


def _fold_query() -> Query:
    return rb.preset_to_query(
        {"metric": "fold_frequency", "filters": {"primary_situation": "facing_cbet"}, "group_by": ["street"]},
    )


def test_the_drill_down_reads_its_columns_whatever_case_they_come_back_in(golden_db: Database) -> None:
    """``KeyError: 'handId'`` was what the user saw on every drill-down."""
    folded = rb.run_drill_down(_FoldingDatabase(golden_db), _fold_query(), group={"street": "flop"})

    assert folded.rows
    for key in ("handId", "startTime", "siteName", "category", "heroName", "heroProfit", "finalPot"):
        assert key in folded.rows[0]


def test_folding_the_column_names_changes_nothing_a_caller_sees(golden_db: Database) -> None:
    # The two backends must answer the same thing, not merely both answer.
    plain = rb.run_drill_down(golden_db, _fold_query(), group={"street": "flop"})
    folded = rb.run_drill_down(_FoldingDatabase(golden_db), _fold_query(), group={"street": "flop"})

    assert [row["handId"] for row in folded.rows] == [row["handId"] for row in plain.rows]
    assert folded.total_matches == plain.total_matches
