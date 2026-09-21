"""A database whose analytics rows were never derived (#351).

The Research Browser reads rows the importer derives while it parses. A
database imported before those layers existed holds its hands and its actions
and none of the derived rows, so every question answers "0 decisions" -- which
a reader takes to mean "you have no such hands". That is what made the browser
look broken and unusable on a real database.

Three things had to be true for that to be fixable at all, and each is pinned
here: the rebuild has to survive PostgreSQL's identifier folding (it did not,
so it rebuilt nothing), it has to be reachable from the application (it was
called by no menu), and an empty answer has to say which of the two things it
means.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import menu_layout
from fpdb_3_legacy.db_rows import Row, row_by_alias, rows_by_alias

ROOT = Path(__file__).parents[1]


class _Cursor:
    """A cursor whose column names are spelled as a given backend spells them."""

    def __init__(self, columns: list[str], rows: list[tuple]) -> None:
        self._columns = columns
        self._rows = list(rows)

    @property
    def description(self) -> Any:
        return [(name,) + (None,) * 6 for name in self._columns]

    def fetchall(self) -> list[tuple]:
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self) -> tuple | None:
        return self._rows.pop(0) if self._rows else None


# --- reading a row whatever the backend calls its columns --------------------


@pytest.mark.parametrize(
    ("columns", "label"),
    [(["actionNo", "streetActionNo"], "sqlite/mysql"), (["actionno", "streetactionno"], "postgresql")],
)
def test_a_row_reads_by_the_selects_own_spelling(columns: list[str], label: str) -> None:
    """``KeyError: 'actionNo'`` is what stopped the rebuild on PostgreSQL."""
    rows = rows_by_alias(_Cursor(columns, [(3, 1)]))

    assert rows[0]["actionNo"] == 3, label
    assert rows[0]["streetActionNo"] == 1, label


def test_a_row_reads_by_a_lower_cased_spelling_too() -> None:
    assert rows_by_alias(_Cursor(["actionNo"], [(3,)]))[0]["actionno"] == 3


def test_a_missing_column_still_raises() -> None:
    # The fold must not turn a genuine mistake into a silent None.
    row = rows_by_alias(_Cursor(["actionNo"], [(3,)]))[0]

    with pytest.raises(KeyError):
        row["streetActionNo"]
    assert row.get("streetActionNo") is None
    assert "streetActionNo" not in row
    assert "actionNo" in row and "ACTIONNO" in row


def test_one_row_at_a_time_reads_the_same_way() -> None:
    cursor = _Cursor(["handId"], [(11,), (12,)])

    assert row_by_alias(cursor)["handId"] == 11
    assert row_by_alias(cursor)["handId"] == 12
    assert row_by_alias(cursor) is None


def test_a_row_is_still_an_ordinary_mapping() -> None:
    row = Row({"handId": 7})

    assert dict(row) == {"handId": 7}
    assert list(row) == ["handId"]


@pytest.mark.parametrize("module", ["analytics_rebuild.py", "research_browser.py"])
def test_the_readers_that_broke_use_the_shared_helper(module: str) -> None:
    # Each had its own hand-rolled zip of description and row, and each was
    # fixed separately; the point of the helper is that there is one.
    source = (ROOT / "fpdb_3_legacy" / module).read_text()

    assert "rows_by_alias" in source, module
    assert not re.search(r"dict\(zip\(\s*names", source), f"{module} still builds rows by hand"


# --- the rebuild is reachable from the application ---------------------------


def test_the_database_menu_offers_the_analytics_rebuild() -> None:
    database_menu = next(menu for menu in menu_layout.menu_layout() if "Database" in menu.title)
    handlers = {item.handler for item in database_menu.items}

    assert "dia_rebuild_analytics" in handlers


def test_the_rebuild_action_is_defined_and_takes_the_global_lock() -> None:
    """It rewrites derived rows, so it belongs behind the same lock as the others."""
    source = (ROOT / "fpdb_3_legacy" / "fpdb.pyw").read_text()
    tree = ast.parse(source)
    action = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "dia_rebuild_analytics"
    )
    calls = [
        node.func.attr
        for node in ast.walk(action)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert "obtain_global_lock" in calls
    assert "release_global_lock" in calls
    assert any("rebuild_subsystems" in ast.dump(node) for node in ast.walk(action))


# --- an empty answer says which kind of empty it is --------------------------


def _browser(stale: tuple[str, ...]):
    """A browser stripped to the two methods the note is built from."""
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    browser = _uninitialised(GuiResearchBrowser)
    browser.db = MagicMock(name="db")
    return browser, stale


def _uninitialised(cls):
    """Allocate a widget without running ``__init__``, which needs a QApplication."""
    return cls.__new__(cls)


@pytest.fixture
def stale_patch(monkeypatch):
    def _set(stale: tuple[str, ...]) -> None:
        import fpdb_3_legacy.analytics_lifecycle as lifecycle

        monkeypatch.setattr(lifecycle, "stale_subsystems", lambda _db: stale)

    return _set


def test_an_empty_answer_names_the_unbuilt_analytics(stale_patch) -> None:
    stale_patch(("situations", "hand_strength"))
    browser, _ = _browser(("situations",))

    note = browser._note_when_empty(0, "Double-click a cell to load the hands behind it.")

    assert "has not been built" in note
    assert "Rebuild Analytics Data" in note


def test_an_answer_with_decisions_keeps_its_own_note(stale_patch) -> None:
    # The warning belongs to a zero, not to every screen of a stale database.
    stale_patch(("situations",))
    browser, _ = _browser(("situations",))

    assert browser._note_when_empty(69, "Double-click a cell.") == "Double-click a cell."


def test_a_built_database_says_nothing_extra(stale_patch) -> None:
    stale_patch(())
    browser, _ = _browser(())

    assert browser._note_when_empty(0, "no hands matched") == "no hands matched"
    assert browser._note_when_empty(0) == ""


def test_a_status_that_cannot_be_read_costs_the_result_nothing(monkeypatch) -> None:
    # The note is a courtesy; a database that refuses the question must not
    # take the answer down with it.
    import fpdb_3_legacy.analytics_lifecycle as lifecycle

    def _explode(_db):
        msg = "no meta table here"
        raise RuntimeError(msg)

    monkeypatch.setattr(lifecycle, "stale_subsystems", _explode)
    browser, _ = _browser(())

    assert browser._note_when_empty(0, "default") == "default"


@pytest.mark.parametrize(
    "renderer", ["_render_range", "_render_composition", "_render_money", "_render_result"]
)
def test_every_view_routes_its_empty_note_through_the_one_helper(renderer: str) -> None:
    """Four views answer zero; fixing three of them is the default mistake."""
    source = (ROOT / "fpdb_3_legacy" / "GuiResearchBrowser.py").read_text()
    tree = ast.parse(source)
    method = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == renderer
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_note_when_empty"
        for node in ast.walk(method)
    ), f"{renderer} sets its note without asking whether the database can answer at all"
