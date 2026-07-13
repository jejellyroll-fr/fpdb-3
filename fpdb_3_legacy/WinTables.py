"""Windows specific methods for TableWindows Class.
from __future__ import annotations
Now uses the Platform Abstraction Layer (Feature 1.5) for table detection.
"""

import re
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication

from fpdb.infrastructure.platform import get_table_detector
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.TableWindow import Table_Window

# Reuse the QApplication created by the caller (e.g. HUD_main). PySide6 allows
# only one QApplication instance, so creating a new one here at import time
# crashes when one already exists.
app = QApplication.instance() or QApplication(sys.argv)

# logging setup
log = get_logger("win_tables")

# Windows-specific code - only load on Windows platform
if sys.platform == "win32":
    import ctypes

    # Windows API functions needed for HUD positioning
    GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
    IsWindow = ctypes.windll.user32.IsWindow
    MoveWindow = ctypes.windll.user32.MoveWindow

    # Windows API constants
    SM_CXSIZEFRAME = 32
    SM_CYCAPTION = 4

# Global variables for window borders
b_width = 3
tb_height = 29


class Table(Table_Window):
    """Windows-specific table window implementation.

    Now uses the Platform Abstraction Layer (Feature 1.5) for table detection.
    """

    def __init__(self, *args, **kwargs):
        """Initialize table with platform detector."""
        self._detector = get_table_detector()
        self._table_geometry = None
        self.gdkhandle: QWindow | None = None
        super().__init__(*args, **kwargs)

    def _matches_winamax_tournament(self, title: str) -> bool:
        if getattr(self, "type", None) != "tour":
            return True
        tournament = str(getattr(self, "tournament", ""))
        table = str(getattr(self, "table", ""))
        if tournament and tournament not in title:
            return False
        if not table:
            return True
        # Winamax zero-pads the table number in the title (e.g. "(#03)"), so allow
        # optional leading zeros when matching table "3" against "#03".
        return bool(re.search(rf"(?:#|Table\s*)0*{re.escape(table)}\b", title, re.IGNORECASE))

    def find_table_parameters(self) -> None:
        """Find a poker client window with the given table name.

        Now uses the platform abstraction layer for cleaner, testable code.
        """
        log.debug("Starting window detection for search string: %s", self.search_string)

        # Winamax special handling: the exact window-title format of the Winamax
        # client does not always match the precise regex from getTableTitleRe, so
        # we broaden the search to any "Winamax" window and then filter it below
        # with _matches_winamax_tournament. (The previous code did
        # search_string.split(" ")[0], which kept the leading "^" regex anchor and
        # produced "^Winamax" — a pattern no window title ever contains.)
        search_str = self.search_string
        if "Winamax" in search_str:
            search_str = "Winamax"
            log.debug("Winamax detected, adjusted search string to: %s", search_str)

        # Use platform abstraction layer to find tables
        tables = self._detector.find_tables(search_str)
        log.debug("Found %d matching windows", len(tables))

        for table_info in tables:
            try:
                title = table_info.title
                if not title:
                    continue

                # Check bad words
                if self.check_bad_words(title):
                    log.debug("Window rejected due to bad words: %s", title)
                    continue

                if search_str == "Winamax" and not self._matches_winamax_tournament(title):
                    log.debug("Winamax window rejected for current tournament/table: %s", title)
                    continue

                # Found matching table
                self.number = table_info.window_id
                self.title = title
                self._table_geometry = table_info.geometry
                log.debug("Found table - HWND: %s, Title: %s", self.number, self.title)
                break

            except Exception as e:  # intentional broad catch: OS window enumeration boundary, log and keep scanning
                log.exception("Unexpected error processing window: %s", e)

        if self.number is None:
            log.error("Window '%s' not found", self.search_string)

    def get_geometry(self):
        """Get the window geometry using platform abstraction."""
        if self._table_geometry is not None:
            # Single-use cache: consume the geometry captured during detection once,
            # then clear it so every later poll queries the live window. Otherwise
            # get_geometry() would keep returning the stale cached value and never
            # return None, so check_table() could never report "client_destroyed"
            # and the HUD would stay open after the table window is closed (it also
            # would never notice the table being moved or resized).
            table_geom = self._table_geometry
            self._table_geometry = None
            log.debug("Using geometry captured during table detection for window: %s", self.number)
        else:
            # Check if window is still valid
            if not self._detector.is_window_visible(self.number):
                log.error("The window %s is not valid or visible", self.number)
                return None

            # Get geometry using platform abstraction
            table_geom = self._detector.get_window_geometry(self.number)
            if table_geom is None:
                log.error("Failed to retrieve geometry for HWND: %s", self.number)
                return None

        # Get border metrics on Windows
        if sys.platform == "win32":
            self.b_width = GetSystemMetrics(SM_CXSIZEFRAME)
            self.tb_height = GetSystemMetrics(SM_CYCAPTION)
        else:
            self.b_width = 3
            self.tb_height = 29

        # Adjust for window decorations (borders and title bar)
        return {
            "x": int(table_geom.x) + self.b_width,
            "y": int(table_geom.y) + self.tb_height + self.b_width,
            "height": int(table_geom.height) - 2 * self.b_width - self.tb_height,
            "width": int(table_geom.width) - 2 * self.b_width,
        }

    def get_window_title(self):
        """Get window title using platform abstraction."""
        log.debug("Getting title for window: %s", self.number)
        title = self._detector.get_window_title(self.number)
        log.debug("Title: %s", title)
        return title if title is not None else ""

    def move_and_resize_window(self, x, y, width, height) -> None:
        """Move and resize the specified window using platform abstraction."""
        if self.number:
            success = self._detector.resize_window(self.number, x, y, width, height)
            if not success:
                log.warning("Failed to resize window %s", self.number)
        else:
            log.info("No window to move")

    def topify(self, window) -> None:
        """Make the specified Qt window 'always on top' under Windows."""
        if self.gdkhandle is None:
            self.gdkhandle = QWindow.fromWinId(int(self.number))

        qwindow = window.windowHandle()
        qwindow.setTransientParent(self.gdkhandle)
        qwindow.setFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowStaysOnTopHint,
        )

    def check_bad_words(self, title):
        """Check if the title contains any bad words."""
        # Compare in lower case on both sides: the title is lowered, so the bad
        # words must be too, otherwise "Lobby"/"HUD:" would never match and
        # non-table windows (lobby, chat, ...) could be picked as the table.
        bad_words = ["history for table:", "hud:", "chat:", "fpdbhud", "lobby"]
        title_lower = title.lower()
        return any(bad_word in title_lower for bad_word in bad_words)
