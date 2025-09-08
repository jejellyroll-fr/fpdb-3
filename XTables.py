"""XWindows specific methods for TableWindows Class."""
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

# TODO(dev): Display management protocols wayland used in some linux distro like ubuntu is not working
# probably need to use lib pyWayland, pywlroots or direct low level binding with ctype of C lib ...to study

#    Standard Library modules
import re
from typing import Any

#    Other Library modules
import xcffib
import xcffib.xproto
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QWindow

import Configuration
from loggingFpdb import get_logger

#    FPDB modules
from TableWindow import Table_Window

xconn = xcffib.Connection()
root = xconn.get_setup().roots[xconn.pref_screen].root


def getAtom(name: str) -> int:
    """Get X11 atom for given name."""
    return xconn.core.InternAtom(only_if_exists=False, name_len=len(name), name=name).reply().atom


nclatom = getAtom("_NET_CLIENT_LIST")
winatom = getAtom("WINDOW")
wnameatom = getAtom("_NET_WM_NAME")
utf8atom = getAtom("UTF8_STRING")

c = Configuration.Config()
log = get_logger("x_tables")


class Table(Table_Window):
    """X11/Linux specific table window implementation."""

    def find_table_parameters(self) -> None:
        """Find table parameters using X11 properties."""
        #    This is called by __init__(). Find the poker table window of interest,
        #    given the self.search_string. Then populate self.number, self.title,
        #    self.window, and self.parent (if required).

        log.info("Starting window detection for search string: '%s'", self.search_string)

        wins = (
            xconn.core.GetProperty(
                delete=False,
                window=root,
                property=nclatom,
                type=winatom,
                long_offset=0,
                long_length=(2**32) - 1,
            )
            .reply()
            .value.to_atoms()
        )

        log.info("Found %d windows to scan", len(wins))
        for win in wins:
            w_title = (
                xconn.core.GetProperty(
                    delete=False,
                    window=win,
                    property=wnameatom,
                    type=utf8atom,
                    long_offset=0,
                    long_length=(2**32) - 1,
                )
                .reply()
                .value.to_utf8()
            )

            log.debug("Window title: %s", w_title)

            if re.search(self.search_string, w_title, re.IGNORECASE):
                log.info("WINDOW MATCH FOUND: '%s' matches search string '%s'", w_title, self.search_string)
                title = w_title.replace('"', "")
                if self.check_bad_words(title):
                    log.warning("Window rejected due to bad words: '%s'", title)
                    continue
                self.number = win
                self.title = title

                log.info("TABLE WINDOW DETECTED - ID: %s, Title: '%s'", self.number, self.title)

                # Get initial geometry for logging
                try:
                    geo = xconn.core.GetGeometry(self.number).reply()
                    absxy = xconn.core.TranslateCoordinates(
                        self.number,
                        root,
                        geo.x,
                        geo.y,
                    ).reply()
                    log.info(
                        "Initial window geometry - X: %d, Y: %d, Width: %d, Height: %d",
                        absxy.dst_x,
                        absxy.dst_y,
                        geo.width,
                        geo.height,
                    )
                except xcffib.xproto.DrawableError:
                    log.exception("Failed to get initial geometry")

                break

        if self.number is None:
            log.error("WINDOW DETECTION FAILED: No match found for search string '%s'", self.search_string)
        else:
            log.info("WINDOW DETECTION SUCCESS: Table window found and configured")

    # This function serves a double purpose. It fetches the X geometry
    # but it also is used to track for window lifecycle. When
    # get_geometry() returns False [None is deal as False], the table is
    # assumed dead and thus the HUD instance may be killed off.
    def get_geometry(self) -> dict[str, int]:
        """Get window geometry coordinates."""
        log.debug("Getting geometry for window ID: %s", self.number)

        wins = (
            xconn.core.GetProperty(
                delete=False,
                window=root,
                property=nclatom,
                type=winatom,
                long_offset=0,
                long_length=(2**32) - 1,
            )
            .reply()
            .value.to_atoms()
        )

        if self.number not in wins:
            log.warning("Window ID %s not found in active windows list - table may be closed", self.number)
            return None

        try:
            geo = xconn.core.GetGeometry(self.number).reply()
            absxy = xconn.core.TranslateCoordinates(
                self.number,
                root,
                geo.x,
                geo.y,
            ).reply()
        except xcffib.xproto.DrawableError:
            log.warning("DrawableError getting geometry for window %s - window may be destroyed", self.number)
            return None
        else:
            geometry = {
                "x": absxy.dst_x,
                "y": absxy.dst_y,
                "width": geo.width,
                "height": geo.height,
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
        """Get window title string."""
        return (
            xconn.core.GetProperty(
                delete=False,
                window=self.number,
                property=wnameatom,
                type=utf8atom,
                long_offset=0,
                long_length=(2**32) - 1,
            )
            .reply()
            .value.to_string()
        )

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

        # Qt.Dialog keeps HUD windows above the table (but not above anything else)
        # Qt.CustomizedWindowHint removes the title bar.
        qwindow.setFlags(Qt.CustomizeWindowHint | Qt.Dialog)
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
