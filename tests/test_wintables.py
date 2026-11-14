"""Table-window detection and HUD placement on Windows (WinTables)."""

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


def _make_regular_table() -> WinTables.Table:
    """A table with the fields find_table_parameters touches."""
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
    t._detector = Mock()
    return t


def test_winamax_broadens_search_string() -> None:
    t = _make_regular_table()
    t.search_string = "Winamax Table 3"
    assert t._detection_search_string() == "Winamax"
    t.site = "PokerStars"
    t.search_string = "Test Table"
    assert t._detection_search_string() == "Test Table"


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


def test_get_geometry_uses_cached_geometry_once() -> None:
    # Pinned off win32 on purpose: 3 and 29 are the fallback border and caption
    # this code uses when it cannot ask the window manager. On Windows the real
    # metrics come from GetSystemMetrics, whose values follow the desktop's
    # theme and DPI -- asserting them here would test the machine, not the
    # arithmetic. The win32 branch has its own test, with the metrics mocked.
    t = _make_regular_table()
    t.site = "PokerStars"
    t.number = 42
    t._table_geometry = _GEOM
    with patch("sys.platform", "linux"):
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


def test_find_table_parameters_open_windows_listing_errors() -> None:
    t = _make_regular_table()
    t.site = "PokerStars"
    t._detector.find_tables.side_effect = lambda s: (_ for _ in ()).throw(RuntimeError("boom")) if s == "" else []
    t.find_table_parameters()
    assert t.number is None


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
    assert t.name == "Table 1"
