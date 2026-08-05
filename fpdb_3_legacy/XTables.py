"""XWindows specific methods for TableWindows Class."""
from __future__ import annotations

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
# NOTE: This module now uses the modern Platform Abstraction Layer (Feature 1.5)
# for table detection. The legacy X11 code has been replaced with the unified
# TableDetector interface for better maintainability and testing.
#    Standard Library modules
from typing import Any

#    Other Library modules
from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow

from fpdb.infrastructure.platform import get_table_detector
from fpdb_3_legacy import Configuration
from fpdb_3_legacy.loggingFpdb import get_logger

#    FPDB modules
from fpdb_3_legacy.TableWindow import Table_Window

c = Configuration.Config()
log = get_logger("x_tables")


class Table(Table_Window):
    """X11/Linux specific table window implementation.

    Now uses the Platform Abstraction Layer (Feature 1.5) for table detection.
    """

    def __init__(self, *args, **kwargs):
        """Initialize table with platform detector."""
        self._detector = get_table_detector()
        self.gdkhandle: QWindow | None = None
        super().__init__(*args, **kwargs)

    def find_table_parameters(self) -> None:
        """Find table parameters using Platform Abstraction Layer.

        This method now uses the modern TableDetector interface instead of
        direct X11 calls, providing better maintainability and testability.
        """
        log.info("Starting window detection for search string: '%s'", self.search_string)

        # Use the new platform abstraction layer
        tables = self._detector.find_tables(self.search_string)

        log.info("Found %d matching windows", len(tables))

        for table_info in tables:
            log.debug("Window title: %s", table_info.title)

            # Check bad words
            title = table_info.title.replace('"', "")
            if self.check_bad_words(title):
                log.warning("Window rejected due to bad words: '%s'", title)
                continue

            # Found matching table
            self.number = table_info.window_id
            self.title = title

            log.info("TABLE WINDOW DETECTED - ID: %s, Title: '%s'", self.number, self.title)

            # Log initial geometry
            log.info(
                "Initial window geometry - X: %d, Y: %d, Width: %d, Height: %d",
                table_info.geometry.x,
                table_info.geometry.y,
                table_info.geometry.width,
                table_info.geometry.height,
            )
            break

        if self.number is None:
            log.warning("WINDOW DETECTION FAILED: No match found for search string '%s'", self.search_string)
            try:
                all_tables = self._detector.find_tables("")
                titles = [t.title for t in all_tables if t.title]
                log.warning("Currently open windows: %s", titles)
            except Exception as e:
                log.warning("Could not list open windows: %s", e)
        else:
            log.info("WINDOW DETECTION SUCCESS: Table window found and configured")

    def get_geometry(self) -> dict[str, int] | None:
        """Get window geometry coordinates.

        This function serves a double purpose: it fetches the geometry and
        tracks window lifecycle. When it returns None, the table is assumed
        dead and the HUD instance may be killed off.
        """
        log.debug("Getting geometry for window ID: %s", self.number)

        # Check if window is still visible using platform abstraction
        if not self._detector.is_window_visible(self.number):
            log.warning("Window ID %s not visible - table may be closed", self.number)
            return None

        # Get geometry using platform abstraction
        table_geom = self._detector.get_window_geometry(self.number)
        if table_geom is None:
            log.warning("Failed to get geometry for window %s - window may be destroyed", self.number)
            return None

        geometry = {
            "x": table_geom.x,
            "y": table_geom.y,
            "width": table_geom.width,
            "height": table_geom.height,
        }

        log.info(
            "CURRENT GEOMETRY for window %s: X=%d, Y=%d, Width=%d, Height=%d",
            self.number,
            geometry["x"],
            geometry["y"],
            geometry["width"],
            geometry["height"],
        )
        return geometry

    def get_window_title(self) -> str:
        """Get window title string using platform abstraction."""
        title = self._detector.get_window_title(self.number)
        return title if title is not None else ""

    def topify(self, window: Any) -> None:
        """Bring window to front."""
        #    The idea here is to call setTransientParent on the HUD window, with the table window
        #    as the argument. This should keep the HUD window on top of the table window, as if
        #    the hud window was a dialog belonging to the table.

        log.info("Setting up HUD window positioning for table window %s", self.number)

        #    X doesn't like calling the foreign_new function in XTables.
        #    Nope don't know why. Moving it here seems to make X happy.
        if self.gdkhandle is None:
            log.debug("Creating QWindow handle for table window %s", self.number)
            self.gdkhandle = QWindow.fromWinId(int(self.number))
            log.debug("QWindow handle created successfully")

        #   This is the gdkhandle for the HUD window
        qwindow = window.windowHandle()
        log.info("Setting HUD window as transient parent of table window")
        qwindow.setTransientParent(self.gdkhandle)

        # Qt.WindowType.Dialog keeps HUD windows above the table (but not above anything else)
        # Qt.WindowType.CustomizeWindowHint removes the title bar.
        qwindow.setFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.Dialog)
        log.info("HUD window flags set - HUD should now be positioned above table window")

        # Log HUD window position after setup
        hud_geometry = window.geometry()
        log.info(
            "HUD FINAL POSITION: X=%d, Y=%d, Width=%d, Height=%d",
            hud_geometry.x(),
            hud_geometry.y(),
            hud_geometry.width(),
            hud_geometry.height(),
        )
