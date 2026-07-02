"""Linux/X11 table detector implementation

Uses xcffib for X11 window detection on Linux systems.
"""

from __future__ import annotations

import logging
import re

from .protocol import Platform, TableGeometry, TableInfo

logger = logging.getLogger(__name__)


class LinuxTableDetector:
    """Linux-specific table detector using X11/xcffib

    This implementation uses the xcffib library to interact with X11
    window system for finding and manipulating poker table windows.

    Note:
        Requires xcffib package to be installed.
        Does not support Wayland (see notes in XTables.py)
    """

    def __init__(self):
        """Initialize Linux table detector"""
        self._platform = Platform.LINUX

        # Lazy-import X11 dependencies to avoid import errors on other platforms
        try:
            import xcffib
            import xcffib.xproto

            self._xconn = xcffib.Connection()
            self._root = self._xconn.get_setup().roots[self._xconn.pref_screen].root

            # Get X11 atoms
            self._nclatom = self._get_atom("_NET_CLIENT_LIST")
            self._winatom = self._get_atom("WINDOW")
            self._wnameatom = self._get_atom("_NET_WM_NAME")
            self._utf8atom = self._get_atom("UTF8_STRING")

            logger.info("Linux X11 table detector initialized")

        except ImportError as e:
            logger.error(f"Failed to import X11 dependencies: {e}")
            raise ImportError("xcffib is required for Linux table detection. Install with: pip install xcffib") from e

    def _get_atom(self, name: str) -> int:
        """Get X11 atom for given name

        Args:
            name: Atom name

        Returns:
            Atom ID
        """
        return self._xconn.core.InternAtom(only_if_exists=False, name_len=len(name), name=name).reply().atom

    @property
    def platform(self) -> Platform:
        """Get the current platform"""
        return self._platform

    def find_tables(self, search_string: str = "") -> list[TableInfo]:
        """Find all windows matching the search string

        Args:
            search_string: String to search for in window titles

        Returns:
            List of TableInfo for matching windows
        """
        tables = []

        try:
            # Get list of all windows
            wins = (
                self._xconn.core.GetProperty(
                    delete=False,
                    window=self._root,
                    property=self._nclatom,
                    type=self._winatom,
                    long_offset=0,
                    long_length=(2**32) - 1,
                )
                .reply()
                .value.to_atoms()
            )

            logger.debug(f"Found {len(wins)} windows to scan")

            # Check each window
            for win in wins:
                try:
                    w_title = (
                        self._xconn.core.GetProperty(
                            delete=False,
                            window=win,
                            property=self._wnameatom,
                            type=self._utf8atom,
                            long_offset=0,
                            long_length=(2**32) - 1,
                        )
                        .reply()
                        .value.to_utf8()
                    )

                    # Check if window matches search string
                    if not search_string or re.search(search_string, w_title, re.IGNORECASE):
                        geometry = self.get_window_geometry(win)
                        if geometry:
                            table_info = TableInfo(
                                window_id=win,
                                title=w_title,
                                geometry=geometry,
                            )
                            tables.append(table_info)
                            logger.debug(f"Found matching table: {w_title}")

                except Exception as e:
                    logger.debug(f"Error getting window info for {win}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error finding tables: {e}", exc_info=True)

        logger.debug(f"Found {len(tables)} matching tables")
        return tables

    def get_window_geometry(self, window_id: int | str) -> TableGeometry | None:
        """Get geometry for a specific window

        Args:
            window_id: X11 window ID (XID)

        Returns:
            TableGeometry if successful, None otherwise
        """
        try:
            window_id = int(window_id)
            geom = self._xconn.core.GetGeometry(drawable=window_id).reply()

            # Translate coordinates to root window to get absolute screen position
            coords = self._xconn.core.TranslateCoordinates(
                src_window=window_id, dst_window=self._root, src_x=0, src_y=0
            ).reply()

            return TableGeometry(x=coords.dst_x, y=coords.dst_y, width=geom.width, height=geom.height)

        except Exception as e:
            logger.debug(f"Error getting geometry for window {window_id}: {e}")
            return None

    def is_window_visible(self, window_id: int | str) -> bool:
        """Check if window is visible

        Args:
            window_id: X11 window ID

        Returns:
            True if window exists and is mapped
        """
        try:
            window_id = int(window_id)
            attrs = self._xconn.core.GetWindowAttributes(window=window_id).reply()
            return attrs.map_state != 0

        except Exception:
            return False

    def get_window_title(self, window_id: int | str) -> str | None:
        """Get window title

        Args:
            window_id: X11 window ID

        Returns:
            Window title or None if not found
        """
        try:
            window_id = int(window_id)
            title = (
                self._xconn.core.GetProperty(
                    delete=False,
                    window=window_id,
                    property=self._wnameatom,
                    type=self._utf8atom,
                    long_offset=0,
                    long_length=(2**32) - 1,
                )
                .reply()
                .value.to_utf8()
            )
            return title

        except Exception as e:
            logger.debug(f"Error getting title for window {window_id}: {e}")
            return None

    def focus_window(self, window_id: int | str) -> bool:
        """Bring window to foreground

        Args:
            window_id: X11 window ID

        Returns:
            True if successful
        """
        try:
            window_id = int(window_id)
            # Raise window to top of stack
            self._xconn.core.ConfigureWindow(window=window_id, value_mask=0x0040, value_list=[0x00000001])
            self._xconn.flush()
            return True

        except Exception as e:
            logger.error(f"Error focusing window {window_id}: {e}")
            return False

    def resize_window(self, window_id: int | str, x: int, y: int, width: int, height: int) -> bool:
        """Resize and reposition window

        Args:
            window_id: X11 window ID
            x: New X coordinate
            y: New Y coordinate
            width: New width
            height: New height

        Returns:
            True if successful
        """
        try:
            window_id = int(window_id)
            # Configure window geometry
            self._xconn.core.ConfigureWindow(
                window=window_id,
                value_mask=0x000F,  # X, Y, Width, Height
                value_list=[x, y, width, height],
            )
            self._xconn.flush()
            return True

        except Exception as e:
            logger.error(f"Error resizing window {window_id}: {e}")
            return False
