"""Portable Win32 title-matching coverage for current poker clients."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

from fpdb.infrastructure.platform.protocol import Platform, TableGeometry
from fpdb.infrastructure.platform.windows import WindowsTableDetector


def _detector(titles: dict[int, str]) -> WindowsTableDetector:
    """Build a detector with the Win32 calls replaced by a tiny fake surface."""
    detector = object.__new__(WindowsTableDetector)
    detector._platform = Platform.WINDOWS
    detector._ctypes = SimpleNamespace(
        WINFUNCTYPE=lambda *_args: lambda callback: callback,
        c_bool=ctypes.c_bool,
        create_unicode_buffer=ctypes.create_unicode_buffer,
        byref=ctypes.byref,
        wintypes=SimpleNamespace(HWND=int, LPARAM=int),
    )
    detector._wintypes = SimpleNamespace(
        HWND=int,
        LPARAM=int,
        DWORD=ctypes.c_ulong,
    )
    detector._GetWindowTextLength = lambda hwnd: len(titles[hwnd])

    def get_window_text(hwnd, buffer, _length):
        buffer.value = titles[hwnd]

    detector._GetWindowText = get_window_text
    detector._window_is_actually_visible = Mock(return_value=True)
    detector._GetWindowThreadProcessId = Mock()
    detector.get_window_geometry = Mock(return_value=TableGeometry(10, 20, 900, 700))

    def enum_windows(callback, lparam):
        for hwnd in titles:
            callback(hwnd, lparam)
        return True

    detector._EnumWindows = enum_windows
    return detector


def test_find_tables_matches_unibet_regex_on_windows_titles() -> None:
    detector = _detector(
        {
            101: "Omaha - PL5 (99465067)",
            102: "SPRINT KO - 10/20 - Tournament 99042656 (99042656)",
            103: "Unibet Poker v3.58.0",
        },
    )

    tables = detector.find_tables(r"\(99042656\)")

    assert [(table.window_id, table.title) for table in tables] == [
        (102, "SPRINT KO - 10/20 - Tournament 99042656 (99042656)"),
    ]
    detector.get_window_geometry.assert_called_once_with(102)


def test_find_tables_keeps_parenthesized_ids_as_regex_not_substrings() -> None:
    detector = _detector(
        {
            101: "SPRINT KO (99042656)",
            102: "SPRINT KO (199042656)",
        },
    )

    tables = detector.find_tables(r"\(99042656\)")

    assert [table.window_id for table in tables] == [101]
