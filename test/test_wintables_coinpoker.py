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
    t.gdkhandle = None
    t._table_geometry = None
    t._coinpoker_argv_confirmed = False
    t._detector = Mock()
    return t


def _windows(*ids_by_pid: tuple[int, str]) -> list[TableInfo]:
    return [
        TableInfo(window_id=100 + pid, title="CoinPoker", geometry=_GEOM, process_id=pid, window_class="UnityWndClass")
        for pid, _tid in ids_by_pid
    ]


def test_live_geometry_reresolves_and_rebinds_hwnd() -> None:
    # Detection is by table id: our id present -> alive, HWND re-bound, the cached
    # parent handle reset, and _coinpoker_argv_confirmed latched by the match.
    t = _make_table()
    t.number = 111
    t.gdkhandle = "STALE"
    t._detector.get_window_geometry.return_value = _GEOM
    t._detector.find_tables.return_value = _windows((956, "166755"), (957, "930357"))
    pid_to_id = {956: "166755", 957: "930357"}

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", side_effect=pid_to_id.get):
        assert t._coinpoker_live_geometry() is _GEOM
    assert t.number == 1057  # re-bound to the window actually serving our id
    assert t.gdkhandle is None  # stale parent handle dropped so topify re-parents
    assert t._coinpoker_argv_confirmed is True  # reading our id latched it


def test_single_table_close_is_detected_even_with_no_other_table() -> None:
    # Ours was the only table and its id was read before (confirmed). No window
    # carries our id now -> closed, even though nothing else is open.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = True  # our id was readable while the table lived
    t._detector.find_tables.return_value = []  # our window vanished; nothing left

    assert t._coinpoker_live_geometry() is None  # closed


def test_unreadable_coinpoker_processes_do_not_kill_a_live_hud() -> None:
    # Codex case: fpdb's own argv is readable but the CoinPoker Unity processes are
    # access-denied (e.g. elevated), so our id was never confirmed. A no-match must
    # NOT be read as closed -- fall back to the tracked window's visibility.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = False  # never managed to read a CoinPoker id
    t._detector.find_tables.return_value = _windows((956, "denied"))
    t._detector.is_window_visible.return_value = True
    t._detector.get_window_geometry.return_value = _GEOM

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value=None):
        assert t._coinpoker_live_geometry() is _GEOM  # stay alive


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
