"""CoinPoker table-window detection on Windows.

CoinPoker titles every window (the Unity table and the Chromium lobby) just
"CoinPoker", with no table number, so the title-based match used for other
sites never finds the table. These tests lock in the special case: broaden the
search to the client name and keep only the Unity render window.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Light Qt stubs so WinTables imports without a real display.
sys.modules.setdefault("PySide6", Mock())
sys.modules.setdefault("PySide6.QtCore", Mock())
sys.modules.setdefault("PySide6.QtGui", Mock())
sys.modules.setdefault("PySide6.QtWidgets", Mock())

import fpdb_3_legacy.WinTables as WinTables  # noqa: E402
from fpdb.infrastructure.platform import TableGeometry, TableInfo  # noqa: E402

_GEOM = TableGeometry(x=100, y=100, width=800, height=613)


def _make_table() -> WinTables.Table:
    """A Table with just the attributes find_table_parameters touches."""
    t = object.__new__(WinTables.Table)
    t.site = "CoinPoker"
    t.search_string = "930357"  # the table number, absent from any window title
    t.number = None
    t.title = ""
    t._table_geometry = None
    t._detector = Mock()
    return t


def test_window_reassigned_only_when_argv_shows_a_different_table() -> None:
    # CoinPoker recycles a table's Unity window; the HUD must treat "my window now
    # serves another table id" as closed, but never guess when it can't read the id.
    t = _make_table()
    t.site = "CoinPoker"
    t.search_string = "930357"
    t.number = 111

    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=4672):
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="928730"):
            assert t._coinpoker_window_reassigned() is True  # different table -> reassigned
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="930357"):
            assert t._coinpoker_window_reassigned() is False  # still our table
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value=None):
            assert t._coinpoker_window_reassigned() is False  # can't tell -> keep

    # Fail-safe: no PID, or a non-CoinPoker site, never reports reassigned.
    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=None):
        assert t._coinpoker_window_reassigned() is False
    t.site = "PokerStars"
    assert t._coinpoker_window_reassigned() is False


def test_coinpoker_picks_unity_table_over_lobby() -> None:
    # No argv resolution available -> class heuristic picks the Unity window.
    lobby = TableInfo(window_id=222, title="CoinPoker", geometry=_GEOM, window_class="Chrome_WidgetWin_1")
    table = TableInfo(window_id=111, title="CoinPoker", geometry=_GEOM, window_class="UnityWndClass")
    t = _make_table()
    t._detector.find_tables.return_value = [lobby, table]

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value=None):
        t.find_table_parameters()

    # Search was broadened to the client name; the Unity window was selected.
    t._detector.find_tables.assert_called_once_with("CoinPoker")
    assert t.number == 111


def test_coinpoker_picks_the_right_table_by_argv_among_several() -> None:
    # Two Unity tables open: argv disambiguates by the requested table id.
    other = TableInfo(window_id=111, title="CoinPoker", geometry=_GEOM, process_id=956, window_class="UnityWndClass")
    wanted = TableInfo(window_id=222, title="CoinPoker", geometry=_GEOM, process_id=957, window_class="UnityWndClass")
    lobby = TableInfo(window_id=333, title="CoinPoker", geometry=_GEOM, process_id=17736, window_class="Chrome_WidgetWin_1")
    t = _make_table()
    t.search_string = "930357"  # the table we want
    t._detector.find_tables.return_value = [other, wanted, lobby]

    pid_to_id = {956: "166755", 957: "930357", 17736: None}
    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", side_effect=pid_to_id.get):
        t.find_table_parameters()

    assert t.number == 222  # the window whose process argv carries 930357


def test_multiple_tables_without_argv_are_not_guessed() -> None:
    # argv can't read the table ids and the class only separates tables from the
    # lobby, so with >1 table open the HUD must not attach to a guessed window.
    t1 = TableInfo(window_id=111, title="CoinPoker", geometry=_GEOM, process_id=956, window_class="UnityWndClass")
    t2 = TableInfo(window_id=222, title="CoinPoker", geometry=_GEOM, process_id=957, window_class="UnityWndClass")
    lobby = TableInfo(window_id=333, title="CoinPoker", geometry=_GEOM, process_id=17736, window_class="Chrome_WidgetWin_1")
    t = _make_table()
    t._detector.find_tables.return_value = [t1, t2, lobby]

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value=None):
        t.find_table_parameters()

    assert t.number is None


def test_coinpoker_not_found_when_only_lobby_open() -> None:
    lobby = TableInfo(window_id=222, title="CoinPoker", geometry=_GEOM, window_class="Chrome_WidgetWin_1")
    t = _make_table()
    t._detector.find_tables.return_value = [lobby]
    # The "list open windows" fallback also queries the detector.
    t._detector.find_tables.side_effect = lambda s: [lobby] if s == "CoinPoker" else []

    t.find_table_parameters()

    assert t.number is None


def test_is_coinpoker_table_accepts_when_class_unknown() -> None:
    # Non-Windows detectors report no class; don't hide the HUD in that case.
    no_class = TableInfo(window_id=1, title="CoinPoker", geometry=_GEOM)
    assert WinTables.Table._is_coinpoker_table(None, no_class) is True
    unity = TableInfo(window_id=2, title="CoinPoker", geometry=_GEOM, window_class="UnityWndClass")
    assert WinTables.Table._is_coinpoker_table(None, unity) is True
    lobby = TableInfo(window_id=3, title="CoinPoker", geometry=_GEOM, window_class="Chrome_WidgetWin_1")
    assert WinTables.Table._is_coinpoker_table(None, lobby) is False
