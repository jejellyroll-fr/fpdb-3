"""A site whose converter stubs getTableTitleRe must not crash window detection.

Unibet's getTableTitleRe used to be a ``pass`` stub, so Table_Window.search_string
was None and WinTables._detection_search_string died on ``"Winamax" in None``
(TypeError) while creating the HUD for every imported Unibet hand. The search
string is now None-safe, and an empty one matches no window instead of every
window.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

from fpdb_3_legacy import WinTables  # noqa: E402


def _table(search_string) -> WinTables.Table:
    t = object.__new__(WinTables.Table)
    t.site = "Unibet"
    t.name = "99620854"
    t.type = "tour"
    t.number = None
    t.title = ""
    t.gdkhandle = None
    t._resolved_window = None
    t._table_geometry = None
    t._detector = MagicMock()
    t.search_string = search_string
    return t


def test_none_search_string_does_not_crash_and_matches_nothing() -> None:
    t = _table(None)
    assert t._detection_search_string() == ""


def test_empty_search_string_does_not_crash_and_matches_nothing() -> None:
    t = _table("")
    assert t._detection_search_string() == ""


def test_find_table_parameters_with_none_search_string_finds_no_window() -> None:
    t = _table(None)
    t.find_table_parameters()
    assert t.number is None
    # An empty pattern would match every visible window; the detector must not
    # be asked to scan with it.
    t._detector.find_tables.assert_called_once_with("")
