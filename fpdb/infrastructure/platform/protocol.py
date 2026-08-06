"""Protocol definition for table detection across platforms

Defines the interface that all platform-specific table detectors must implement.
Uses Python's Protocol (PEP 544) for structural subtyping.
"""

from __future__ import annotations

from dataclasses import dataclass
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Fallback StrEnum for Python < 3.11."""

        def __str__(self) -> str:
            return str(self.value)

from typing import Protocol, runtime_checkable


class Platform(StrEnum):
    """Supported operating system platforms"""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TableGeometry:
    """Table window geometry information

    Attributes:
        x: X coordinate (left) of window
        y: Y coordinate (top) of window
        width: Window width in pixels
        height: Window height in pixels
    """

    x: int
    y: int
    width: int
    height: int

    def contains_point(self, px: int, py: int) -> bool:
        """Check if a point is inside this geometry

        Args:
            px: Point X coordinate
            py: Point Y coordinate

        Returns:
            True if point is inside the window bounds
        """
        return self.x <= px <= (self.x + self.width) and self.y <= py <= (self.y + self.height)

    def intersects(self, other: TableGeometry) -> bool:
        """Check if this geometry intersects with another

        Args:
            other: Another TableGeometry to check

        Returns:
            True if the geometries overlap
        """
        return not (
            self.x + self.width <= other.x
            or other.x + other.width <= self.x
            or self.y + self.height <= other.y
            or other.y + other.height <= self.y
        )


@dataclass(frozen=True)
class TableInfo:
    """Information about a detected poker table window

    Attributes:
        window_id: Platform-specific window identifier (HWND, XID, etc.)
        title: Window title/name
        geometry: Window position and size
        process_name: Name of the owning process (e.g., "PokerStars")
        process_id: Platform-specific process identifier
        window_class: Native window class name, when the platform exposes it
            (Win32 GetClassName). Used to disambiguate clients that give every
            window the same title -- e.g. CoinPoker, whose Unity table window
            and Chromium lobby are both titled "CoinPoker". None elsewhere.
    """

    window_id: int | str
    title: str
    geometry: TableGeometry
    process_name: str | None = None
    process_id: int | None = None
    window_class: str | None = None

    def matches_search(self, search_string: str) -> bool:
        """Check if this table matches a search string

        Args:
            search_string: String to search for (case-insensitive)

        Returns:
            True if the title contains the search string
        """
        return search_string.lower() in self.title.lower()


@runtime_checkable
class TableDetector(Protocol):
    """Protocol for platform-specific table window detection

    All platform implementations must implement this interface.

    Example:
        >>> detector = get_table_detector()
        >>> tables = detector.find_tables("PokerStars")
        >>> for table in tables:
        ...     print(f"Found: {table.title} at ({table.geometry.x}, {table.geometry.y})")
    """

    def find_tables(self, search_string: str = "") -> list[TableInfo]:
        """Find all poker table windows matching the search string

        Args:
            search_string: String to search for in window titles (empty = all windows)

        Returns:
            List of TableInfo objects for matching windows
        """
        ...

    def get_window_geometry(self, window_id: int | str) -> TableGeometry | None:
        """Get geometry for a specific window

        Args:
            window_id: Platform-specific window identifier

        Returns:
            TableGeometry if window exists, None otherwise
        """
        ...

    def is_window_visible(self, window_id: int | str) -> bool:
        """Check if a window is currently visible

        Args:
            window_id: Platform-specific window identifier

        Returns:
            True if window exists and is visible
        """
        ...

    def is_window_displayed(self, window_id: int | str) -> bool:
        """Check if a window is actually shown on screen right now

        Stricter than is_window_visible(): a window the compositor hides while
        the platform still reports it as visible must return False here. On
        Windows that is DWM cloaking (a closed CoinPoker Unity host stays
        "visible" but cloaked); platforms with no such concept simply mirror
        is_window_visible().

        Use is_window_visible() for the generic geometry poll -- treating a
        merely cloaked window (e.g. a table on another virtual desktop) as gone
        would kill live HUDs.

        Args:
            window_id: Platform-specific window identifier

        Returns:
            True if the window exists and is really shown on screen
        """
        ...

    def get_window_title(self, window_id: int | str) -> str | None:
        """Get title of a specific window

        Args:
            window_id: Platform-specific window identifier

        Returns:
            Window title if exists, None otherwise
        """
        ...

    def focus_window(self, window_id: int | str) -> bool:
        """Bring window to foreground

        Args:
            window_id: Platform-specific window identifier

        Returns:
            True if successful, False otherwise
        """
        ...

    def resize_window(self, window_id: int | str, x: int, y: int, width: int, height: int) -> bool:
        """Resize and reposition a window

        Args:
            window_id: Platform-specific window identifier
            x: New X coordinate
            y: New Y coordinate
            width: New width
            height: New height

        Returns:
            True if successful, False otherwise
        """
        ...

    @property
    def platform(self) -> Platform:
        """Get the current platform

        Returns:
            Platform enum value
        """
        ...
