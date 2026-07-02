"""Windows table detector implementation

Uses Win32 API (via ctypes) for window detection on Windows systems.
"""

from __future__ import annotations

import logging
import re

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

            self._ctypes = ctypes
            self._wintypes = wintypes

            # Windows API functions
            self._EnumWindows = ctypes.windll.user32.EnumWindows
            self._GetWindowText = ctypes.windll.user32.GetWindowTextW
            self._GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            self._IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            self._GetWindowRect = ctypes.windll.user32.GetWindowRect
            self._SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
            self._MoveWindow = ctypes.windll.user32.MoveWindow

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
            if length > 0 and self._IsWindowVisible(hwnd):
                buff = self._ctypes.create_unicode_buffer(length + 1)
                self._GetWindowText(hwnd, buff, length + 1)
                title = buff.value

                # Check if matches search
                if pattern is None or pattern.search(title):
                    geometry = self.get_window_geometry(hwnd)
                    if geometry:
                        table_info = TableInfo(
                            window_id=hwnd,
                            title=title,
                            geometry=geometry,
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
        """Check if window is visible

        Args:
            window_id: Window handle

        Returns:
            True if window exists and is visible
        """
        try:
            window_id = int(window_id)
            return bool(self._IsWindowVisible(window_id))
        except Exception:
            return False

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
