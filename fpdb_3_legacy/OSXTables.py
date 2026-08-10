"""OSX specific methods for TableWindows Class.
from __future__ import annotations
Now uses the Platform Abstraction Layer (Feature 1.5) for table detection.
"""
#    Copyright 2008 - 2011, Ray E. Barker

#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################

from __future__ import annotations

#    Standard Library modules
import ctypes
import time
from typing import Any

from AppKit import NSView, NSWindowAbove

from fpdb.infrastructure.platform import get_table_detector
from fpdb_3_legacy.loggingFpdb import get_logger

#    FPDB modules
from fpdb_3_legacy.TableWindow import Table_Window

log = get_logger("osx_tables")


class Table(Table_Window):
    """OSX-specific table window implementation.

    Now uses the Platform Abstraction Layer (Feature 1.5) for table detection.
    """

    def __init__(self, *args, **kwargs):
        """Initialize table with platform detector."""
        # Fast Fold resolves the indexed Winamax window at hand-start. Reusing
        # that answer avoids a second, potentially different Quartz/System
        # Events scan during HUD construction.
        self._resolved_window = kwargs.pop("resolved_window", None)
        self._detector = get_table_detector()
        super().__init__(*args, **kwargs)

    def find_table_parameters(self) -> str | None:
        """Find the poker table window of interest using platform abstraction.

        This is called by __init__(). Find the poker table window of interest,
        given the self.search_string. Then populate self.number, self.title,
        self.window, and self.parent (if required).

        Returns:
            The window title if found, None otherwise.
        """
        t0 = time.perf_counter()
        self.number = None
        log.debug("DIAGNOSTIC: Starting window detection for search string: '%s'", self.search_string)

        if self._resolved_window is not None:
            try:
                number = int(self._resolved_window.window_id)
                title = str(self._resolved_window.title)
            except (AttributeError, TypeError, ValueError):
                log.warning("Ignoring invalid pre-resolved macOS window: %r", self._resolved_window)
            else:
                if number > 0 and title and not self.check_bad_words(title):
                    self.number = number
                    self.title = title
                    log.debug(
                        "DIAGNOSTIC: Reusing pre-resolved table window ID: %s, title: '%s'",
                        self.number,
                        self.title,
                    )
                    return self.title

        # Use platform abstraction layer to find tables
        tables = self._detector.find_tables(self.search_string)
        log.debug("DIAGNOSTIC: Found %d matching windows in platform detector", len(tables))

        for table_info in tables:
            log.debug(
                "DIAGNOSTIC: Candidate window: '%s' (WID: %s) at (%d, %d) process: %s",
                table_info.title,
                table_info.window_id,
                table_info.geometry.x,
                table_info.geometry.y,
                table_info.process_name,
            )

            title = table_info.title
            if self.check_bad_words(title):
                log.debug("DIAGNOSTIC: Window rejected due to bad words: '%s'", title)
                continue

            # Found matching table
            self.number = int(table_info.window_id)
            self.title = title
            log.info("[PERF-TIMING] OSXTables.find_table_parameters for '%s' matched '%s' in %.3f s", self.search_string, self.title, time.perf_counter() - t0)
            return self.title
        log.info("[PERF-TIMING] OSXTables.find_table_parameters for '%s' completed in %.3f s", self.search_string, time.perf_counter() - t0)
        if self.number is None:
            # At ERROR level: HUD_main reports the same failure as an error, and the
            # osx_tables logger is commonly persisted at ERROR, which would drop the
            # very window list needed to tell a wrong search string from an absent
            # table.
            log.error("Window detection failed: no match found for search string '%s'", self.search_string)
            try:
                all_tables = self._detector.find_tables("")
                titles = [t.title for t in all_tables if t.title]
                log.error("Currently open windows: %s", titles)
            except Exception as e:
                log.error("Could not list open windows: %s", e)
            return None

        return None

    def get_geometry(self) -> dict[str, int] | None:
        """Get the geometry of the table window using platform abstraction.

        Returns:
            Dictionary with x, y, width, height coordinates or None if not found.
        """
        if self.number is None:
            log.warning("Cannot get geometry: window number is None")
            return None

        # Check if window is still visible using platform abstraction
        if not self._detector.is_window_visible(self.number):
            log.debug("The window %s is not valid or visible", self.number)
            return None

        # Use platform abstraction layer
        table_geom = self._detector.get_window_geometry(self.number)
        if table_geom is None:
            log.warning("Failed to get geometry for window %s", self.number)
            return None

        return {
            "x": int(table_geom.x),
            "y": int(table_geom.y),
            "width": int(table_geom.width),
            "height": int(table_geom.height),
        }

    def get_window_title(self) -> str | None:
        """Get the title of the table window using platform abstraction.

        Returns:
            The window title string or None if not found.
        """
        if self.number is None:
            log.warning("Cannot get window title: window number is None")
            return None

        # Use platform abstraction layer
        title = self._detector.get_window_title(self.number)
        log.debug("Window title: %s", title)
        return title

    def topify(self, window: Any) -> None:
        """Bring the table window to the front.

        Args:
            window: The Qt widget window to bring to front.
        """
        if self.number is None:
            log.warning("Cannot topify window: window number is None")
            return

        winid = window.effectiveWinId()
        cvp = ctypes.c_void_p(int(winid))
        view = NSView(c_void_p=cvp)
        if window.isVisible():
            view.window().orderWindow_relativeTo_(NSWindowAbove, self.number)
