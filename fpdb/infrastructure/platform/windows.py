"""Windows table detector implementation

Uses Win32 API (via ctypes) for window detection on Windows systems.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .protocol import Platform, TableGeometry, TableInfo

logger = logging.getLogger(__name__)


class WindowsTableDetector:
    """Windows-specific table detector using Win32 API

    This implementation uses ctypes to call Windows API functions
    for finding and manipulating poker table windows.

    Note:
        Only works on Windows platforms.
        Requires pywin32 or uses ctypes for Win32 API access.
    """

    def __init__(self):
        """Initialize Windows table detector"""
        self._platform = Platform.WINDOWS

        # Lazy-import Windows dependencies
        try:
            import ctypes
            from ctypes import wintypes

            ctypes_api: Any = ctypes
            self._ctypes = ctypes_api
            self._wintypes = wintypes

            # Windows API functions
            self._EnumWindows = ctypes_api.windll.user32.EnumWindows
            self._GetWindowText = ctypes_api.windll.user32.GetWindowTextW
            self._GetWindowTextLength = ctypes_api.windll.user32.GetWindowTextLengthW
            self._GetClassName = ctypes_api.windll.user32.GetClassNameW
            self._GetWindowThreadProcessId = ctypes_api.windll.user32.GetWindowThreadProcessId
            self._IsWindowVisible = ctypes_api.windll.user32.IsWindowVisible
            self._GetWindowRect = ctypes_api.windll.user32.GetWindowRect
            self._SetForegroundWindow = ctypes_api.windll.user32.SetForegroundWindow
            self._MoveWindow = ctypes_api.windll.user32.MoveWindow
            try:
                self._DwmGetWindowAttribute = ctypes_api.windll.dwmapi.DwmGetWindowAttribute
                self._DwmGetWindowAttribute.argtypes = [
                    wintypes.HWND,
                    wintypes.DWORD,
                    ctypes_api.c_void_p,
                    wintypes.DWORD,
                ]
                self._DwmGetWindowAttribute.restype = ctypes_api.c_long
            except (AttributeError, OSError):
                # DWM is unavailable on very old/minimal Windows environments.
                self._DwmGetWindowAttribute = None

            logger.info("Windows table detector initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Windows API: {e}")
            raise ImportError("Failed to access Windows API. Ensure running on Windows.") from e

    @property
    def platform(self) -> Platform:
        """Get the current platform"""
        return self._platform

    def find_tables(self, search_string: str = "") -> list[TableInfo]:
        """Find all windows matching the search string

        The caller passes a regular expression (see getTableTitleRe), so the
        title is matched with re.search — consistent with the Linux and macOS
        detectors. A plain substring match would fail for anchored patterns
        such as ``^Winamax ... /``. If the string is not a valid regex we fall
        back to matching it literally.

        Args:
            search_string: Regex to search for in window titles

        Returns:
            List of TableInfo for matching windows
        """
        tables = []

        if search_string:
            try:
                pattern = re.compile(search_string, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(search_string), re.IGNORECASE)
        else:
            pattern = None

        def enum_callback(hwnd, lParam):
            length = self._GetWindowTextLength(hwnd)
            if length > 0 and self._window_is_actually_visible(hwnd):
                buff = self._ctypes.create_unicode_buffer(length + 1)
                self._GetWindowText(hwnd, buff, length + 1)
                title = buff.value

                # Check if matches search
                if pattern is None or pattern.search(title):
                    geometry = self.get_window_geometry(hwnd)
                    if geometry:
                        cls_buff = self._ctypes.create_unicode_buffer(256)
                        self._GetClassName(hwnd, cls_buff, 256)
                        pid = self._wintypes.DWORD()
                        self._GetWindowThreadProcessId(hwnd, self._ctypes.byref(pid))
                        table_info = TableInfo(
                            window_id=hwnd,
                            title=title,
                            geometry=geometry,
                            process_id=pid.value or None,
                            window_class=cls_buff.value or None,
                        )
                        tables.append(table_info)
            return True

        # Enumerate all windows
        EnumWindowsProc = self._ctypes.WINFUNCTYPE(
            self._ctypes.c_bool,
            self._ctypes.wintypes.HWND,
            self._ctypes.wintypes.LPARAM,
        )
        self._EnumWindows(EnumWindowsProc(enum_callback), 0)

        logger.info(f"Found {len(tables)} matching tables")
        return tables

    def get_window_geometry(self, window_id: int | str) -> TableGeometry | None:
        """Get geometry for a specific window

        Args:
            window_id: Window handle (HWND)

        Returns:
            TableGeometry if successful, None otherwise
        """
        try:
            window_id = int(window_id)
            rect = self._wintypes.RECT()
            if self._GetWindowRect(window_id, self._ctypes.byref(rect)):
                return TableGeometry(
                    x=rect.left,
                    y=rect.top,
                    width=rect.right - rect.left,
                    height=rect.bottom - rect.top,
                )
        except Exception as e:
            logger.debug(f"Error getting geometry for window {window_id}: {e}")

        return None

    def is_window_visible(self, window_id: int | str) -> bool:
        """Check if window is alive and Win32-visible (legacy semantics).

        Deliberately ignores DWM cloaking: a cloaked window (for example a
        table moved to another virtual desktop) is still alive, and the
        generic per-site geometry poll uses this check to decide whether to
        close the HUD — treating "cloaked" as "gone" would kill live HUDs.
        Use is_window_displayed() when cloaking must count as hidden.

        Args:
            window_id: Window handle

        Returns:
            True if window exists and is visible
        """
        try:
            window_id = int(window_id)
            return bool(self._IsWindowVisible(window_id))
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def is_window_displayed(self, window_id: int | str) -> bool:
        """Check if window is actually shown on screen right now.

        Win32-visible AND not DWM-cloaked. CoinPoker keeps its Unity window
        "visible" but cloaked after a table closes, so its close detection
        needs the stricter test.

        Args:
            window_id: Window handle

        Returns:
            True if window is visible and not cloaked
        """
        try:
            window_id = int(window_id)
            return self._window_is_actually_visible(window_id)
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def _window_is_actually_visible(self, window_id: int) -> bool:
        """True only when Win32 and DWM both consider the window visible.

        CoinPoker's Unity host can remain ``IsWindowVisible`` after a table is
        closed while DWM cloaks it. Such a window is not displayed but used to
        keep the HUD alive forever because its PID/argv still carried the table
        id. Treat DWM-cloaked windows as closed. If DWM is unavailable or the
        query fails, preserve the legacy Win32 result.
        """
        if not self._IsWindowVisible(window_id):
            return False
        if self._DwmGetWindowAttribute is None:
            return True
        cloaked = self._wintypes.DWORD()
        # DWMWA_CLOAKED = 14; HRESULT 0 means the value is valid.
        result = self._DwmGetWindowAttribute(
            window_id,
            14,
            self._ctypes.byref(cloaked),
            self._ctypes.sizeof(cloaked),
        )
        return result != 0 or not bool(cloaked.value)

    def get_window_title(self, window_id: int | str) -> str | None:
        """Get window title

        Args:
            window_id: Window handle

        Returns:
            Window title or None if not found
        """
        try:
            window_id = int(window_id)
            length = self._GetWindowTextLength(window_id)
            if length > 0:
                buff = self._ctypes.create_unicode_buffer(length + 1)
                self._GetWindowText(window_id, buff, length + 1)
                return buff.value
        except Exception as e:
            logger.debug(f"Error getting title for window {window_id}: {e}")

        return None

    def focus_window(self, window_id: int | str) -> bool:
        """Bring window to foreground

        Args:
            window_id: Window handle

        Returns:
            True if successful
        """
        try:
            window_id = int(window_id)
            return bool(self._SetForegroundWindow(window_id))
        except Exception as e:
            logger.error(f"Error focusing window {window_id}: {e}")
            return False

    def resize_window(self, window_id: int | str, x: int, y: int, width: int, height: int) -> bool:
        """Resize and reposition window

        Args:
            window_id: Window handle
            x: New X coordinate
            y: New Y coordinate
            width: New width
            height: New height

        Returns:
            True if successful
        """
        try:
            window_id = int(window_id)
            return bool(self._MoveWindow(window_id, x, y, width, height, True))
        except Exception as e:
            logger.error(f"Error resizing window {window_id}: {e}")
            return False
