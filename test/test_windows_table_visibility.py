"""Portable contracts for Win32/DWM table visibility."""

from __future__ import annotations

from unittest.mock import Mock

from fpdb.infrastructure.platform.windows import WindowsTableDetector


def _detector(*, win32_visible: bool, cloaked: bool, dwm_result: int = 0) -> WindowsTableDetector:
    detector = object.__new__(WindowsTableDetector)
    detector._IsWindowVisible = Mock(return_value=win32_visible)
    detector._wintypes = Mock()
    cloak_value = Mock(value=int(cloaked))
    detector._wintypes.DWORD.return_value = cloak_value
    detector._ctypes = Mock()
    detector._DwmGetWindowAttribute = Mock(return_value=dwm_result)
    return detector


def test_dwm_cloaked_window_is_not_actually_visible() -> None:
    detector = _detector(win32_visible=True, cloaked=True)
    assert detector._window_is_actually_visible(123) is False


def test_uncloaked_window_remains_visible() -> None:
    detector = _detector(win32_visible=True, cloaked=False)
    assert detector._window_is_actually_visible(123) is True


def test_failed_dwm_query_preserves_win32_visibility() -> None:
    detector = _detector(win32_visible=True, cloaked=True, dwm_result=-1)
    assert detector._window_is_actually_visible(123) is True
