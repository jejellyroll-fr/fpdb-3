"""OSX specific methods for TableWindows Class."""
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
from typing import Any

from AppKit import NSView, NSWindowAbove, NSWorkspace
from Quartz.CoreGraphics import (
    CGWindowListCopyWindowInfo,
    CGWindowListCreateDescriptionFromArray,
    kCGNullWindowID,
    kCGWindowBounds,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowNumber,
    kCGWindowOwnerName,
)

from loggingFpdb import get_logger

#    FPDB modules
from TableWindow import Table_Window

log = get_logger("osxtables")


class Table(Table_Window):
    """OSX-specific table window implementation."""
    def find_table_parameters(self) -> str | None:
        """Find the poker table window of interest.

        This is called by __init__(). Find the poker table window of interest,
        given the self.search_string. Then populate self.number, self.title,
        self.window, and self.parent (if required).

        Returns:
            The window title if found, None otherwise.
        """
        self.number = None
        curr_pid = NSWorkspace.sharedWorkspace().activeApplication()[
            "NSApplicationProcessIdentifier"
        ]
        options = kCGWindowListOptionOnScreenOnly
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        for window in window_list:
            pid = window["kCGWindowOwnerPID"]
            window_number = window["kCGWindowNumber"]
            owner_name = window["kCGWindowOwnerName"]
            geometry = window["kCGWindowBounds"]
            window_title = window.get("kCGWindowName", self.search_string)
            if curr_pid == pid:
                log.info(
                    "%s - %s (PID: %s, WID: %s): %s",
                    owner_name, window_title, pid, window_number, geometry,
                )

                title = window_title
                if self.check_bad_words(title):
                    continue
                self.number = int(window_number)
                self.title = title
                return self.title
        if self.number is None:
            return None
        return None

    def get_geometry(self) -> dict[str, int] | None:
        """Get the geometry of the table window.

        Returns:
            Dictionary with x, y, width, height coordinates or None if not found.
        """
        win_list_dict = CGWindowListCreateDescriptionFromArray((self.number,))

        for d in win_list_dict:
            if d[kCGWindowNumber] == self.number:
                return {
                    "x": int(d[kCGWindowBounds]["X"]),
                    "y": int(d[kCGWindowBounds]["Y"]),
                    "width": int(d[kCGWindowBounds]["Width"]),
                    "height": int(d[kCGWindowBounds]["Height"]),
                }
        return None

    def get_window_title(self) -> str | None:
        """Get the title of the table window.

        Returns:
            The window title string or None if not found.
        """
        win_list_dict = CGWindowListCreateDescriptionFromArray((self.number,))
        for d in win_list_dict:
            if (
                d[kCGWindowNumber] == self.number
            ):  # and b[kCGWindowNumber] == self.number :
                log.debug("kCGWindowOwnerName: %s", d.get(kCGWindowOwnerName, ""))
                return d[kCGWindowOwnerName]
        return None

    def topify(self, window: Any) -> None:
        """Bring the table window to the front.

        Args:
            window: The Qt widget window to bring to front.
        """
        winid = window.effectiveWinId()
        cvp = ctypes.c_void_p(int(winid))
        view = NSView(c_void_p=cvp)
        if window.isVisible():
            view.window().orderWindow_relativeTo_(NSWindowAbove, self.number)
