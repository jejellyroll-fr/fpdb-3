"""CoinPoker table-window detection on Windows.

CoinPoker titles every window (the Unity table and the Chromium lobby) just
"CoinPoker", with no table number, so the title-based match used for other
sites never finds the table. These tests lock in the special case: broaden the
search to the client name and keep only the Unity render window.
"""

import sys
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.qt

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
    t._detector.is_window_displayed.return_value = True
    t._detector.find_tables.return_value = _windows((956, "166755"), (957, "930357"))
    pid_to_id = {956: "166755", 957: "930357"}

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", side_effect=pid_to_id.get):
        assert t._coinpoker_live_geometry() is _GEOM
    assert t.number == 1057  # re-bound to the window actually serving our id
    assert t.gdkhandle is None  # stale parent handle dropped so topify re-parents
    assert t._coinpoker_argv_confirmed is True  # reading our id latched it


def test_matching_argv_does_not_keep_a_hidden_unity_window_alive() -> None:
    # Windows can retain the Unity HWND/process/argv after closing the table but
    # DWM cloaks it. PID matching must not override the detector's live state.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = True
    t._detector.find_tables.return_value = _windows((956, "930357"))
    t._detector.is_window_displayed.return_value = False

    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="930357"):
        assert t._coinpoker_live_geometry() is None


def test_single_table_close_is_detected_even_with_no_other_table() -> None:
    # Ours was the only table and its id was read before (confirmed). No window
    # carries our id now -> closed, even though nothing else is open.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = True  # our id was readable while the table lived
    t._detector.find_tables.return_value = []  # our window vanished; nothing left

    assert t._coinpoker_live_geometry() is None  # closed


def test_fallback_attached_hud_closes_when_tracked_window_is_another_table() -> None:
    # Codex case: attached via the class fallback (never confirmed). A later poll
    # can read argv and the tracked HWND now belongs to a *different* table, so the
    # window we hold is provably not ours -> close, don't cling via is_window_visible.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = False
    t.search_string = "930357"
    # No open window carries our id (another table occupies things).
    t._detector.find_tables.return_value = _windows((956, "928730"))
    t._detector.is_window_displayed.return_value = True  # stale window still "visible"
    t._detector.get_window_geometry.return_value = _GEOM

    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=956):
        # Our tracked HWND's process now serves table 928730, not 930357.
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="928730"):
            assert t._coinpoker_live_geometry() is None  # closed despite visibility


def test_unreadable_coinpoker_processes_do_not_kill_a_live_hud() -> None:
    # Codex case: fpdb's own argv is readable but the CoinPoker Unity processes are
    # access-denied (e.g. elevated), so our id was never confirmed. A no-match must
    # NOT be read as closed -- fall back to the tracked window's visibility.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = False  # never managed to read a CoinPoker id
    t._detector.find_tables.return_value = _windows((956, "denied"))
    t._detector.is_window_displayed.return_value = True
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


def _make_regular_table() -> WinTables.Table:
    """A non-CoinPoker table with the fields find_table_parameters touches."""
    t = object.__new__(WinTables.Table)
    t.site = "Winamax"
    t.search_string = "Test Table"
    t.number = None
    t.title = ""
    t.name = ""
    t.type = "tour"
    t.tournament = "123"
    t.table = "3"
    t.gdkhandle = None
    t._table_geometry = None
    t._coinpoker_argv_confirmed = False
    t._detector = Mock()
    return t


def test_winamax_broadens_search_string() -> None:
    t = _make_regular_table()
    t.search_string = "Winamax Table 3"
    assert t._detection_search_string() == "Winamax"
    t.site = "PokerStars"
    t.search_string = "Test Table"
    assert t._detection_search_string() == "Test Table"


def test_coinpoker_broadens_search_string() -> None:
    t = _make_table()
    t.site = "CoinPoker"
    assert t._detection_search_string() == "CoinPoker"


def test_matches_winamax_tournament_non_tour() -> None:
    t = _make_regular_table()
    t.type = "cash"
    assert t._matches_winamax_tournament("Anything") is True


def test_matches_winamax_tournament_wrong_tournament() -> None:
    t = _make_regular_table()
    t.tournament = "123"
    assert t._matches_winamax_tournament("Winamax (124)") is False


def test_matches_winamax_tournament_no_table_ignores_table() -> None:
    t = _make_regular_table()
    t.table = ""
    assert t._matches_winamax_tournament("Winamax (123)") is True


def test_matches_winamax_tournament_leading_zeros() -> None:
    t = _make_regular_table()
    t.tournament = "123"
    t.table = "3"
    assert t._matches_winamax_tournament("Winamax #03 (123)") is True
    assert t._matches_winamax_tournament("Winamax #3 (123)") is True
    assert t._matches_winamax_tournament("Winamax #04 (123)") is False


def test_select_window_rejects_bad_words_and_empty_titles() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    bad = TableInfo(window_id=1, title="PokerStars Lobby", geometry=_GEOM)
    empty = TableInfo(window_id=2, title="", geometry=_GEOM)
    good = TableInfo(window_id=3, title="PokerStars Table 3", geometry=_GEOM)
    with patch("fpdb_3_legacy.WinTables.Table.check_bad_words", side_effect=lambda title: "lobby" in title.lower()):
        assert t._select_window([bad, empty, good], "Test Table") is good


def test_select_window_none_when_no_qualifying() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    bad = TableInfo(window_id=1, title="PokerStars Lobby", geometry=_GEOM)
    with patch("fpdb_3_legacy.WinTables.Table.check_bad_words", return_value=True):
        assert t._select_window([bad], "Test Table") is None


def test_select_window_winamax_rejects_wrong_tournament() -> None:
    t = _make_regular_table()
    wrong = TableInfo(window_id=1, title="Winamax #04 (124)", geometry=_GEOM)
    good = TableInfo(window_id=2, title="Winamax #03 (123)", geometry=_GEOM)
    assert t._select_window([wrong, good], "Winamax") is good


def test_select_window_logs_and_scans_past_errors() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    failing = TableInfo(window_id=1, title="PokerStars Table 1", geometry=_GEOM)
    good = TableInfo(window_id=2, title="PokerStars Table 2", geometry=_GEOM)
    calls = {"n": 0}

    def explode(title: str) -> bool:
        calls["n"] += 1
        if title == "PokerStars Table 1":
            raise RuntimeError("boom")
        return False

    with patch("fpdb_3_legacy.WinTables.Table.check_bad_words", side_effect=explode):
        assert t._select_window([failing, good], "Test Table") is good
    assert calls["n"] == 2


def test_find_table_parameters_uses_cached_geometry() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t.search_string = "Test Table"
    t._detector.find_tables.return_value = [TableInfo(window_id=42, title="Test Table", geometry=_GEOM)]
    t.find_table_parameters()
    assert t.number == 42
    assert t.title == "Test Table"
    assert t._table_geometry is _GEOM


def test_find_table_parameters_not_found_lists_windows() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t._detector.find_tables.side_effect = lambda s: [] if s == "Test Table" else [TableInfo(window_id=9, title="Other", geometry=_GEOM)]
    t.find_table_parameters()
    assert t.number is None


def test_window_pid_non_windows() -> None:
    assert WinTables._window_pid(None) is None
    assert WinTables._window_pid(0) is None
    with patch("sys.platform", "linux"):
        assert WinTables._window_pid(123) is None


def test_get_geometry_uses_cached_geometry_once() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t.number = 42
    t._table_geometry = _GEOM
    geom = t.get_geometry()
    assert geom is not None
    assert geom["x"] == _GEOM.x + 3
    assert geom["y"] == _GEOM.y + 29 + 3
    assert geom["width"] == _GEOM.width - 2 * 3
    assert geom["height"] == _GEOM.height - 2 * 3 - 29
    # Cache is single-use: next call queries the live window.
    t._detector.is_window_visible.return_value = True
    t._detector.get_window_geometry.return_value = _GEOM
    geom2 = t.get_geometry()
    assert geom2 is not None


def test_get_geometry_visible_false_returns_none() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t.number = 42
    t._detector.is_window_visible.return_value = False
    assert t.get_geometry() is None


def test_get_geometry_no_live_geometry_returns_none() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t.number = 42
    t._detector.is_window_visible.return_value = True
    t._detector.get_window_geometry.return_value = None
    assert t.get_geometry() is None


def test_get_geometry_coinpoker_live() -> None:
    t = _make_table()
    t.number = 111
    t._detector.find_tables.return_value = _windows((957, "930357"))
    t._detector.is_window_displayed.return_value = True
    t._detector.get_window_geometry.return_value = _GEOM
    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="930357"):
        geom = t.get_geometry()
    assert geom is not None
    assert geom["width"] == _GEOM.width - 6


def test_get_window_title() -> None:
    t = _make_regular_table()
    t.number = 42
    t._detector.get_window_title.return_value = "Hello"
    assert t.get_window_title() == "Hello"
    t._detector.get_window_title.return_value = None
    assert t.get_window_title() == ""


def test_move_and_resize_window() -> None:
    t = _make_regular_table()
    t.number = 42
    t._detector.resize_window.return_value = True
    assert t.move_and_resize_window(1, 2, 3, 4) is None
    t._detector.resize_window.assert_called_once_with(42, 1, 2, 3, 4)
    t.number = None
    assert t.move_and_resize_window(1, 2, 3, 4) is None


def test_topify_reparents() -> None:
    """QWindow.fromWinId must be patched, not merely stubbed by import order.

    ``t.number`` is a fabricated table id, and ``fromWinId`` takes it as a
    *native* window handle. The module-level ``sys.modules.setdefault`` stubs
    above only apply when this file imports PySide6 first, which is not the
    case under ``-m qt``: pytest-qt has already imported the real Qt, so the
    real ``fromWinId`` dereferenced 42 as an ``NSView*`` and segfaulted the
    interpreter on macOS, taking the rest of the Qt suite with it (#258).
    """
    t = _make_regular_table()
    t.number = 42
    window = Mock()
    handle = Mock()
    window.windowHandle.return_value = handle

    table_handle = Mock()
    with patch.object(WinTables, "QWindow") as qwindow_cls:
        qwindow_cls.fromWinId.return_value = table_handle

        t.topify(window)

        qwindow_cls.fromWinId.assert_called_once_with(42)
        assert t.gdkhandle is table_handle
        handle.setTransientParent.assert_called_once_with(table_handle)
        handle.setFlags.assert_called_once()

        # Second call reuses the cached handle instead of resolving it again.
        t.topify(window)
        assert handle.setTransientParent.call_count == 2
        qwindow_cls.fromWinId.assert_called_once_with(42)


def test_topify_gives_up_when_the_table_window_is_gone() -> None:
    """A table that closed mid-call must not take the HUD down with it.

    ``fromWinId`` returns None for a window id that no longer exists, and the
    next line called ``setTransientParent`` on it regardless -- and the HUD
    calls topify exactly when tables are appearing and disappearing.
    """
    t = _make_regular_table()
    t.number = 42
    window = Mock()

    with patch.object(WinTables, "QWindow") as qwindow_cls:
        qwindow_cls.fromWinId.return_value = None

        t.topify(window)

        assert t.gdkhandle is None, "un handle non résolu ne doit pas être mis en cache"
        window.windowHandle.assert_not_called()


def test_topify_gives_up_when_the_hud_window_has_no_handle() -> None:
    """windowHandle() is None until the widget is native; skip rather than crash."""
    t = _make_regular_table()
    t.number = 42
    window = Mock()
    window.windowHandle.return_value = None

    with patch.object(WinTables, "QWindow") as qwindow_cls:
        qwindow_cls.fromWinId.return_value = Mock()

        t.topify(window)  # ne doit pas lever


def test_check_bad_words_case_insensitive() -> None:
    t = _make_regular_table()
    assert t.check_bad_words("Table Lobby 1") is True
    assert t.check_bad_words("Table HUD: 1") is True
    assert t.check_bad_words("Normal Table 1") is False


def test_match_coinpoker_by_argv_import_error() -> None:
    t = _make_table()
    with patch.dict(sys.modules, {"fpdb.infrastructure.platform.windows_process": None}):
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", side_effect=ImportError):
            assert t._match_coinpoker_by_argv([]) is None


def test_select_coinpoker_window_warns_when_multiple_unresolved() -> None:
    t = _make_table()
    t1 = TableInfo(window_id=111, title="CoinPoker", geometry=_GEOM, process_id=956, window_class="UnityWndClass")
    t2 = TableInfo(window_id=222, title="CoinPoker", geometry=_GEOM, process_id=957, window_class="UnityWndClass")
    with patch("fpdb_3_legacy.WinTables.Table._match_coinpoker_by_argv", return_value=None):
        assert t._select_coinpoker_window([t1, t2]) is None


def test_tracked_window_belongs_elsewhere_no_target() -> None:
    t = _make_regular_table()
    t.search_string = "NoDigitsHere"
    assert t._tracked_window_belongs_elsewhere() is False


def test_tracked_window_belongs_elsewhere_no_pid() -> None:
    t = _make_regular_table()
    t.search_string = "Table 930357"
    t.number = 42
    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=None):
        assert t._tracked_window_belongs_elsewhere() is False


def test_tracked_window_belongs_elsewhere_different_table() -> None:
    t = _make_regular_table()
    t.search_string = "Table 930357"
    t.number = 42
    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=956):
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="999"):
            assert t._tracked_window_belongs_elsewhere() is True


def test_tracked_window_belongs_elsewhere_same_table() -> None:
    t = _make_regular_table()
    t.search_string = "Table 930357"
    t.number = 42
    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=956):
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="930357"):
            assert t._tracked_window_belongs_elsewhere() is False


def test_match_coinpoker_by_argv_empty_target() -> None:
    t = _make_table()
    t.search_string = "No digits"
    assert t._match_coinpoker_by_argv([]) is None


def test_find_table_parameters_open_windows_listing_errors() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t._detector.find_tables.side_effect = lambda s: (_ for _ in ()).throw(RuntimeError("boom")) if s == "" else []
    t.find_table_parameters()
    assert t.number is None


def test_coinpoker_live_geometry_hidden_fallback() -> None:
    # Not confirmed and the tracked window is hidden: close.
    t = _make_table()
    t.number = 111
    t._coinpoker_argv_confirmed = False
    t._detector.find_tables.return_value = []
    t._detector.is_window_displayed.return_value = False
    assert t._coinpoker_live_geometry() is None


def test_tracked_window_argv_check_error_is_safe() -> None:
    t = _make_regular_table()
    t.search_string = "Table 930357"
    t.number = 42
    with patch("fpdb_3_legacy.WinTables._window_pid", return_value=956):
        with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", side_effect=OSError("denied")):
            assert t._tracked_window_belongs_elsewhere() is False


def test_get_geometry_coinpoker_none_closes() -> None:
    t = _make_table()
    t.number = 111
    t._detector.find_tables.return_value = []
    t._coinpoker_argv_confirmed = True
    assert t.get_geometry() is None


def test_move_and_resize_window_failure_logs() -> None:
    t = _make_regular_table()
    t.number = 42
    t._detector.resize_window.return_value = False
    assert t.move_and_resize_window(1, 2, 3, 4) is None


def test_topify_reuses_existing_handle() -> None:
    # gdkhandle already set: topify must skip creating a new one.
    t = _make_regular_table()
    t.number = 42
    t.gdkhandle = "EXISTING"
    window = Mock()
    handle = Mock()
    window.windowHandle.return_value = handle
    t.topify(window)
    handle.setTransientParent.assert_called_once_with("EXISTING")
    handle.setFlags.assert_called_once()


def test_topify_creates_handle_on_first_call() -> None:
    t = _make_regular_table()
    t.number = 42
    window = Mock()
    handle = Mock()
    window.windowHandle.return_value = handle
    with patch("fpdb_3_legacy.WinTables.QWindow") as qwin:
        qwin.fromWinId.return_value = "QHANDLE"
        t.topify(window)
        qwin.fromWinId.assert_called_once_with(42)
    assert t.gdkhandle == "QHANDLE"


def test_win32_border_metrics_path() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t.number = 42
    t._table_geometry = _GEOM
    WinTables.GetSystemMetrics = Mock(side_effect=[8, 40])
    WinTables.SM_CXSIZEFRAME = 32
    WinTables.SM_CYCAPTION = 4
    with patch("sys.platform", "win32"):
        geom = t.get_geometry()
    assert geom["x"] == _GEOM.x + 8
    assert geom["y"] == _GEOM.y + 40 + 8
    WinTables.GetSystemMetrics.assert_any_call(32)
    WinTables.GetSystemMetrics.assert_any_call(4)


def test_coinpoker_live_geometry_keeps_same_hwnd() -> None:
    # The window still carries our id and its HWND is unchanged: geometry is
    # returned without re-binding or dropping the cached parent handle.
    t = _make_table()
    t.number = 1057
    t.gdkhandle = "HANDLE"
    t._detector.find_tables.return_value = _windows((957, "930357"))
    t._detector.is_window_displayed.return_value = True
    t._detector.get_window_geometry.return_value = _GEOM
    with patch("fpdb.infrastructure.platform.windows_process.table_id_for_pid", return_value="930357"):
        assert t._coinpoker_live_geometry() is _GEOM
    assert t.number == 1057
    assert t.gdkhandle == "HANDLE"


def test_window_pid_win32_path() -> None:
    fake_ulong = Mock()
    fake_ulong.value = 1234
    fake_win = Mock()
    fake_win.GetWindowThreadProcessId = Mock(return_value=1)
    fake_ctypes = Mock()
    fake_ctypes.byref = lambda x: x
    fake_ctypes.c_ulong = Mock(return_value=fake_ulong)
    fake_ctypes.windll = Mock(user32=fake_win)

    with patch("sys.platform", "win32"):
        with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
            with patch("builtins.__import__", lambda name, *a, **k: fake_ctypes if name == "ctypes" else __import__(name, *a, **k)):
                assert WinTables._window_pid(555) == 1234
    fake_win.GetWindowThreadProcessId.assert_called_once_with(555, fake_ulong)


def test_window_pid_win32_zero_is_none() -> None:
    fake_ulong = Mock()
    fake_ulong.value = 0
    fake_win = Mock()
    fake_win.GetWindowThreadProcessId = Mock(return_value=1)
    fake_ctypes = Mock()
    fake_ctypes.byref = lambda x: x
    fake_ctypes.c_ulong = Mock(return_value=fake_ulong)
    fake_ctypes.windll = Mock(user32=fake_win)

    with patch("sys.platform", "win32"):
        with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
            with patch("builtins.__import__", lambda name, *a, **k: fake_ctypes if name == "ctypes" else __import__(name, *a, **k)):
                assert WinTables._window_pid(555) is None


def test_window_pid_win32_error_is_none() -> None:
    with patch("sys.platform", "win32"):
        with patch("builtins.__import__", lambda name, *a, **k: (_ for _ in ()).throw(ImportError("boom")) if name == "ctypes" else __import__(name, *a, **k)):
            assert WinTables._window_pid(555) is None


def test_constructor_initialises_state() -> None:
    detector = Mock()
    detector.find_tables.return_value = []
    detector.is_window_visible.return_value = False
    config = Mock()
    config.hhcs = {"PokerStars": Mock(converter=Mock())}
    with patch("fpdb_3_legacy.WinTables.get_table_detector", return_value=detector):
        with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table 1"):
            with patch("fpdb_3_legacy.TableWindow.sleep"):
                t = WinTables.Table(config, "PokerStars", table_name="Table 1")
    assert t._detector is detector
    assert t._table_geometry is None
    assert t.gdkhandle is None
    assert t._coinpoker_argv_confirmed is False
    assert t.name == "Table 1"
