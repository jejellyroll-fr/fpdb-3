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
    GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

    # Windows API constants
    SM_CXSIZEFRAME = 32
    SM_CYCAPTION = 4


def _window_pid(hwnd: int | None) -> int | None:
    """Return the process id owning ``hwnd`` on Windows, or None."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        pid = ctypes.c_ulong()
        GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
        return pid.value or None
    except Exception:  # noqa: BLE001 - defensive: never break the geometry poll
        return None


# Global variables for window borders
b_width = 3
tb_height = 29

# CoinPoker renders each table in a Unity window whose title is just "CoinPoker"
# (no table number), while the lobby is a Chromium window with the *same* title.
# The table is told apart by its native window class, not the title.
COINPOKER_TABLE_CLASS = "UnityWndClass"


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

    def _detection_search_string(self) -> str:
        """Broaden the title search for clients whose title omits the table id.

        Winamax's title does not always match the precise getTableTitleRe regex,
        and CoinPoker titles every window just "CoinPoker"; in both cases we
        search on the client name and filter the matches afterwards.
        """
        search_str = self.search_string
        if "Winamax" in search_str:
            log.debug("Winamax detected, adjusted search string to: Winamax")
            return "Winamax"
        if getattr(self, "site", "") == "CoinPoker":
            log.debug("CoinPoker detected, adjusted search string to: CoinPoker")
            return "CoinPoker"
        return search_str

    def _is_coinpoker_table(self, table_info) -> bool:
        """True for the CoinPoker Unity table window, False for its Chromium lobby.

        Both are titled "CoinPoker"; only the native window class tells them
        apart. If the detector could not report a class (non-Windows, or an
        older detector), accept the window rather than hide the HUD.
        """
        window_class = getattr(table_info, "window_class", None)
        if window_class is None:
            return True
        return window_class == COINPOKER_TABLE_CLASS

    def _match_coinpoker_by_argv(self, tables):
        """Return the CoinPoker window owning the requested table id, or None.

        Each CoinPoker table is a separate Unity process whose command line
        carries the table id (window -> PID -> argv -> id), so this tells several
        open tables apart -- the window-class heuristic alone cannot. Returns
        None when argv is unavailable (psutil missing / access denied), so the
        caller falls back to the class heuristic for the single-table case.
        """
        try:
            from fpdb.infrastructure.platform.windows_process import table_id_for_pid
        except ImportError:
            return None
        target = "".join(ch for ch in str(self.search_string) if ch.isdigit())
        if not target:
            return None
        for table_info in tables:
            pid = getattr(table_info, "process_id", None)
            if not pid:
                continue
            try:
                if table_id_for_pid(pid) == target:
                    return table_info
            except Exception as exc:  # pragma: no cover - psutil/platform dependent
                log.debug("argv lookup failed for pid %s: %s", pid, exc)
        return None

    def _coinpoker_table_candidates(self, tables):
        """The CoinPoker table windows (Unity), excluding the lobby and bad-word windows."""
        return [t for t in tables if t.title and not self.check_bad_words(t.title) and self._is_coinpoker_table(t)]

    def _select_coinpoker_window(self, tables):
        """Pick this CoinPoker table's window, or None if it can't be told apart.

        The process argv carries the exact table id, so it disambiguates several
        open tables. When argv is unavailable (psutil missing / access denied) the
        window class only separates a table from the lobby, not one table from
        another, so fall back to it only when a single table is open -- otherwise
        a HUD could attach to the wrong table.
        """
        argv_match = self._match_coinpoker_by_argv(tables)
        if argv_match is not None:
            return argv_match
        candidates = self._coinpoker_table_candidates(tables)
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            log.warning(
                "%d CoinPoker tables open but the table id could not be read from any process; "
                "not guessing which window to attach to.",
                len(candidates),
            )
        return None

    def _select_window(self, tables, search_str):
        """Pick the table window from candidates, or None if none qualifies."""
        if getattr(self, "site", "") == "CoinPoker":
            return self._select_coinpoker_window(tables)

        for table_info in tables:
            try:
                title = table_info.title
                if not title:
                    continue
                if self.check_bad_words(title):
                    log.debug("Window rejected due to bad words: %s", title)
                    continue
                if search_str == "Winamax" and not self._matches_winamax_tournament(title):
                    log.debug("Winamax window rejected for current tournament/table: %s", title)
                    continue
                return table_info
            except Exception as e:  # intentional broad catch: OS window enumeration boundary, log and keep scanning
                log.exception("Unexpected error processing window: %s", e)
        return None

    def find_table_parameters(self) -> None:
        """Find a poker client window with the given table name.

        Now uses the platform abstraction layer for cleaner, testable code.
        """
        log.debug("Starting window detection for search string: %s", self.search_string)

        search_str = self._detection_search_string()
        tables = self._detector.find_tables(search_str)
        log.debug("Found %d matching windows", len(tables))

        match = self._select_window(tables, search_str)
        if match is not None:
            self.number = match.window_id
            self.title = match.title
            self._table_geometry = match.geometry
            log.debug("Found table - HWND: %s, Title: %s", self.number, self.title)
            return

        log.warning("Window '%s' not found.", self.search_string)
        try:
            all_tables = self._detector.find_tables("")
            titles = [t.title for t in all_tables if t.title]
            log.warning("Currently open windows: %s", titles)
        except Exception as e:
            log.warning("Could not list open windows: %s", e)

    def _coinpoker_window_reassigned(self) -> bool:
        """True only if our CoinPoker window now serves a *different* table id.

        Fail-safe: returns False whenever the site isn't CoinPoker, or the table
        id can't be read (no PID / psutil unavailable / no id in argv), so it can
        only ever add a close signal, never cause a premature kill.
        """
        if getattr(self, "site", "") != "CoinPoker":
            return False
        expected = "".join(ch for ch in str(getattr(self, "search_string", "")) if ch.isdigit())
        if not expected:
            return False
        pid = _window_pid(self.number)
        if not pid:
            return False
        try:
            from fpdb.infrastructure.platform.windows_process import table_id_for_pid

            current = table_id_for_pid(pid)
        except Exception as exc:  # noqa: BLE001 - never break the geometry poll
            log.debug("CoinPoker argv re-check failed for pid %s: %s", pid, exc)
            return False
        return bool(current) and current != expected

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

            # CoinPoker recycles a table's Unity window for the next table, so the
            # HWND can stay "visible" after this table closed while now rendering a
            # different table. Treat that as destroyed (the HUD must move on).
            if self._coinpoker_window_reassigned():
                log.info("CoinPoker window %s now serves a different table; treating as closed", self.number)
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
