#!/usr/bin/env python3
"""Report what a Winamax table window publishes about its seats (Windows).

The Fast-Fold HUD reads a table's chairs from the window itself, because the
client log only names a player once they have acted -- and a HUD built from the
log fills in one block at a time over the first betting round. When the window
read comes back empty, or partial, the HUD silently falls back to that log and
the session looks slow for reasons nothing in the log explains.

This asks the same questions the reader asks, and prints every answer:

    python tools/diagnose_winamax_seats.py
    python tools/diagnose_winamax_seats.py --wait 60

* which windows the table detector can see at all, the lobby included
* whether the UIAutomation client can be built (comtypes, COM, the wrapper)
* the window's own rectangle, and every label under it with its position --
  the two together are what shows a coordinate-space mismatch, which sends
  every player to the wrong chair even when the names are read correctly
* what seats_from_labels and read_window make of those labels

Chromium builds its accessibility tree only when an assistive client asks, so
the request is sent here too, exactly as the HUD sends it. The tree is built
asynchronously: --wait polls until a table publishes something, which is what
you want when the labels only appear while a hand is being dealt.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _tables():
    """Every Winamax window the detector can see, tables first."""
    from fpdb.infrastructure.platform import get_table_detector

    windows = get_table_detector().find_tables("Winamax")
    tables = [w for w in windows if w.title and w.title.strip() != "Winamax"]
    return windows, tables


def _report_table(reader_module, table) -> int:
    """Print everything one table window will say. Returns the label count."""
    hwnd = int(table.window_id)
    reader_module.request_windows_accessibility(hwnd)
    client = reader_module._windows_uia()
    if client is None:
        print("  no UIAutomation client on this machine")
        return 0

    element = client.automation.ElementFromHandle(hwnd)
    if element is None:
        print(f"  hwnd {hwnd} has no UIAutomation element")
        return 0

    rect = element.CurrentBoundingRectangle
    print(f"  window rect ({rect.left},{rect.top})-({rect.right},{rect.bottom})")
    labels = client.collect_labels(element)
    print(f"  labels: {len(labels)}")
    for label in labels:
        print(f"      {label.login!r:24} @ ({label.x},{label.y})")
    if labels:
        # Each label against the window it is supposed to be inside, rather than
        # a min/max over all of them: the window's own title reports itself at
        # the window origin and a stray "Notifications" node reports (0,0), so a
        # range spanning both looked like it covered the window when not one of
        # the client's own labels was inside it.
        outside = [
            label
            for label in labels
            if not (rect.left <= label.x <= rect.right and rect.top <= label.y <= rect.bottom)
        ]
        print(f"  labels outside the window rect: {len(outside)} of {len(labels)}")
        if outside:
            print("      the client is not reporting positions in the window's coordinate space,")
            print("      so the table centre computed from that rect puts every player on the")
            print("      wrong chair -- the hero comes back off the bottom-centre slot.")
            for label in outside[:5]:
                print(f"        {label.login!r} @ ({label.x},{label.y})")
    print(f"  seats_from_labels: {reader_module.seats_from_labels(labels)}")
    print(f"  read_window      : {reader_module.read_window_for(hwnd, table.title)}")
    return len(labels)


def main(argv: list[str] | None = None) -> int:
    """Print the diagnosis; exit 1 when no table published anything."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SECONDS",
        help="keep polling until a table publishes labels (default: report once and stop)",
    )
    args = parser.parse_args(argv)

    from fpdb_3_legacy import winamax_ax_seats

    deadline = time.monotonic() + args.wait
    while True:
        windows, tables = _tables()
        print(f"Winamax windows detected: {len(windows)} ({len(tables)} look like tables)")
        for window in windows:
            kind = "table" if window in tables else "lobby/other"
            print(f"  [{kind}] hwnd={window.window_id} {window.title!r}")

        found = 0
        for table in tables:
            print(f"\n--- {table.title!r}")
            found += _report_table(winamax_ax_seats, table)

        if found or time.monotonic() >= deadline:
            if not tables:
                print("\nNo table window found. Open a Fast-Fold table and run this again,")
                print("or pass --wait 60 and open one while it polls.")
            return 0 if found else 1
        time.sleep(2)
        print()


if __name__ == "__main__":
    sys.exit(main())
