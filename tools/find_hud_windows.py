#!/usr/bin/env python3
"""Name the processes drawing windows over your poker tables (macOS).

Written because a leftover HUD process from an earlier launch drew a second
set of stat blocks over every table, and nothing could find it: ``pkill -f
HUD_main.pyw`` misses a packaged build, whose command line is
``fpdb.app/Contents/MacOS/fpdb --hud``, and a process list of several hundred
entries does not volunteer which one owns the blocks on screen.

The window server knows. Every on-screen window carries the pid and name of
the process that owns it, and that is available without Screen Recording --
only window *contents* need that. So this asks it directly: find the poker
tables, then report every other window sitting on top of one, grouped by the
process responsible.

    python tools/find_hud_windows.py
    python tools/find_hud_windows.py --site PokerStars

Exits 1 when an overlay belongs to a process other than the one you are
running now, so it can be used as a check rather than only read.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

#: Windows at or below this layer are ordinary application windows. The HUD
#: puts its overlays above them, which is what keeps them off the felt.
NORMAL_WINDOW_LAYER = 0

#: An overlay has to cover a good part of a seat to be worth reporting, but a
#: stat block is small next to a table. Anything larger than this fraction of
#: the table is another window, not an overlay on it.
MAX_OVERLAY_AREA_FRACTION = 0.5


@dataclass(frozen=True)
class Window:
    """One on-screen window, as the window server describes it."""

    pid: int
    owner: str
    name: str
    x: float
    y: float
    width: float
    height: float
    layer: int

    @property
    def area(self) -> float:
        return self.width * self.height

    def overlaps(self, other: Window) -> bool:
        """Whether the two rectangles intersect at all."""
        return (
            self.x < other.x + other.width
            and other.x < self.x + self.width
            and self.y < other.y + other.height
            and other.y < self.y + self.height
        )

    def __str__(self) -> str:
        title = f" {self.name!r}" if self.name else ""
        return f"pid {self.pid:>6}  {self.owner}{title}  {int(self.width)}x{int(self.height)} at ({int(self.x)},{int(self.y)})"


def on_screen_windows() -> list[Window]:
    """Every window the server is currently showing.

    Raises:
        RuntimeError: when the Quartz bindings are unavailable, which is any
            platform that is not macOS and any build without pyobjc.
    """
    try:
        import Quartz
    except ImportError as exc:  # pragma: no cover - platform dependent
        msg = "this tool needs macOS and the Quartz bindings (pyobjc)"
        raise RuntimeError(msg) from exc

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windows = []
    for info in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
        bounds = info.get("kCGWindowBounds") or {}
        windows.append(
            Window(
                pid=int(info.get("kCGWindowOwnerPID") or 0),
                owner=str(info.get("kCGWindowOwnerName") or ""),
                name=str(info.get("kCGWindowName") or ""),
                x=float(bounds.get("X", 0)),
                y=float(bounds.get("Y", 0)),
                width=float(bounds.get("Width", 0)),
                height=float(bounds.get("Height", 0)),
                layer=int(info.get("kCGWindowLayer") or 0),
            ),
        )
    return windows


def poker_tables(windows: list[Window], site: str) -> list[Window]:
    """The client's table windows, which the overlays sit on."""
    return [
        window
        for window in windows
        if window.layer <= NORMAL_WINDOW_LAYER
        and site.lower() in f"{window.owner} {window.name}".lower()
        and window.area > 0
    ]


def overlays_on(table: Window, windows: list[Window]) -> list[Window]:
    """Windows sitting on top of one table, small enough to be stat blocks."""
    return [
        window
        for window in windows
        if window is not table
        and window.pid != table.pid
        and window.area > 0
        and window.area < table.area * MAX_OVERLAY_AREA_FRACTION
        and window.overlaps(table)
    ]


def group_by_process(windows: list[Window]) -> dict[tuple[int, str], int]:
    """Count the windows each process owns."""
    counts: dict[tuple[int, str], int] = {}
    for window in windows:
        key = (window.pid, window.owner)
        counts[key] = counts.get(key, 0) + 1
    return counts


def report(site: str, out: Any = sys.stdout) -> int:
    """Print who is drawing over the tables. Returns a process exit status."""
    windows = on_screen_windows()
    tables = poker_tables(windows, site)
    if not tables:
        print(f"No {site} table windows are open, so nothing can be drawn over them.", file=out)
        return 0

    print(f"{len(tables)} {site} table window(s) open:", file=out)
    for table in tables:
        print(f"  {table}", file=out)

    owners: dict[tuple[int, str], int] = {}
    for table in tables:
        for key, count in group_by_process(overlays_on(table, windows)).items():
            owners[key] = owners.get(key, 0) + count

    if not owners:
        print("\nNothing is drawing over them.", file=out)
        return 0

    print("\nProcesses drawing over those tables:", file=out)
    strangers = 0
    for (pid, owner), count in sorted(owners.items(), key=lambda item: -item[1]):
        mine = " (this process)" if pid == os.getpid() else ""
        print(f"  pid {pid:>6}  {owner}  {count} window(s){mine}", file=out)
        if not mine:
            strangers += 1

    if strangers:
        print(
            "\nIf you expected only one HUD, every pid above beyond the first is a leftover.\n"
            "Quit it with:  kill <pid>        (or  kill -9 <pid>  if it will not go)",
            file=out,
        )
    return 1 if strangers else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", default="Winamax", help="text identifying the client's table windows")
    args = parser.parse_args(argv)
    try:
        return report(args.site)
    except RuntimeError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
