#!/usr/bin/env python3
"""Report what fpdb's Windows detector sees, and what it throws away (Windows only).

Written because a Winamax cash table that is plainly on screen is never found
on Windows 10, while the same build finds it on Windows 11. The HUD log only
ever says "Window '...' not found", which does not say *where* the window was
lost: it may never have been enumerated, or it may have been dropped by the
title / visibility / DWM-cloak gates, or accepted and then rejected by the
per-site title match.

So this walks the same path as ``WindowsTableDetector.find_tables`` and prints
a verdict for every window at each gate, plus the full window tree of the
poker client -- children included, since an Electron client can draw a table in
a window whose title only its parent carries.

    python tools/diagnose_windows_tables.py
    python tools/diagnose_windows_tables.py --match Winamax
    python tools/diagnose_windows_tables.py --watch 30

``--watch`` polls for the given number of seconds and reports every window that
appears, disappears, or changes title, which is what tells a window created
without a title apart from one that is never created at all.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

#: DwmGetWindowAttribute's "is this window cloaked" question. A cloaked window
#: is composited but not drawn -- another virtual desktop, or a suspended UWP
#: app. fpdb's enumeration drops cloaked windows.
DWMWA_CLOAKED = 14

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000
WS_CAPTION = 0x00C00000
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOREDIRECTIONBITMAP = 0x00200000


@dataclass(frozen=True)
class WindowFacts:
    """Everything the detector's gates look at, for one window."""

    hwnd: int
    pid: int
    title: str
    window_class: str
    text_length: int
    win32_visible: bool
    cloak_hresult: int
    cloak_value: int
    style: int
    exstyle: int
    rect: tuple[int, int, int, int] | None

    @property
    def cloaked(self) -> bool:
        """Cloaked as fpdb reads it: a failed query counts as *not* cloaked."""
        return self.cloak_hresult == 0 and bool(self.cloak_value)

    @property
    def kept_by_find_tables(self) -> bool:
        """Whether find_tables would even consider this window a candidate."""
        return self.text_length > 0 and self.win32_visible and not self.cloaked and self.rect is not None

    def gate_verdict(self) -> str:
        """Which gate this window falls at, in the order find_tables applies them."""
        if self.text_length <= 0:
            return "DROPPED: GetWindowTextLengthW == 0 (no caption text to match)"
        if not self.win32_visible:
            return "DROPPED: IsWindowVisible == False"
        if self.cloaked:
            return f"DROPPED: DWM-cloaked (0x{self.cloak_value:x})"
        if self.rect is None:
            return "DROPPED: GetWindowRect failed (no geometry)"
        return "KEPT"

    def flags(self) -> str:
        names = []
        for bit, name in (
            (WS_VISIBLE, "VISIBLE"),
            (WS_MINIMIZE, "MINIMIZED"),
            (WS_CHILD, "CHILD"),
            (WS_POPUP, "POPUP"),
        ):
            if self.style & bit:
                names.append(name)
        if self.style & WS_CAPTION == WS_CAPTION:
            names.append("CAPTION")
        if self.exstyle & WS_EX_TOOLWINDOW:
            names.append("TOOLWINDOW")
        if self.exstyle & WS_EX_NOREDIRECTIONBITMAP:
            names.append("NOREDIRECTIONBITMAP")
        return "|".join(names) or "-"


class Win32:
    """The handful of Win32 calls this diagnostic needs, with argtypes set.

    argtypes are declared because an HWND is pointer-sized: left to ctypes'
    default marshalling it is passed as a C int, which is the kind of thing
    that behaves differently between machines rather than failing outright.
    """

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.restype = ctypes.c_int
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        # GetWindowLongPtrW exists only in 64-bit user32; the 32-bit build has
        # GetWindowLongW, with identical semantics for the values read here.
        self._get_long = getattr(self.user32, "GetWindowLongPtrW", self.user32.GetWindowLongW)
        self._get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        self._get_long.restype = ctypes.c_ssize_t
        try:
            self.dwm = ctypes.WinDLL("dwmapi")
            self.dwm.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            self.dwm.DwmGetWindowAttribute.restype = ctypes.c_long
        except OSError:
            self.dwm = None

    def title(self, hwnd: int) -> tuple[int, str]:
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return length, ""
        buff = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buff, length + 1)
        return length, buff.value

    def window_class(self, hwnd: int) -> str:
        buff = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buff, 256)
        return buff.value

    def cloak(self, hwnd: int) -> tuple[int, int]:
        if self.dwm is None:
            return (-1, 0)
        value = wintypes.DWORD()
        hresult = self.dwm.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return (hresult, value.value)

    def rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        r = wintypes.RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def pid(self, hwnd: int) -> int:
        value = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(value))
        return value.value

    def facts(self, hwnd: int) -> WindowFacts:
        length, text = self.title(hwnd)
        hresult, cloak_value = self.cloak(hwnd)
        return WindowFacts(
            hwnd=hwnd,
            pid=self.pid(hwnd),
            title=text,
            window_class=self.window_class(hwnd),
            text_length=length,
            win32_visible=bool(self.user32.IsWindowVisible(hwnd)),
            cloak_hresult=hresult,
            cloak_value=cloak_value,
            style=self._get_long(hwnd, GWL_STYLE) & 0xFFFFFFFF,
            exstyle=self._get_long(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF,
            rect=self.rect(hwnd),
        )

    def top_level(self) -> list[int]:
        found: list[int] = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(hwnd, _lparam):  # noqa: ANN001, ANN202 - ctypes callback
            found.append(hwnd)
            return True

        self.user32.EnumWindows(proc(collect), 0)
        return found

    def children(self, hwnd: int) -> list[int]:
        found: list[int] = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(child, _lparam):  # noqa: ANN001, ANN202 - ctypes callback
            found.append(child)
            return True

        self.user32.EnumChildWindows(hwnd, proc(collect), 0)
        return found


def _line(facts: WindowFacts, indent: str = "") -> str:
    rect = "-" if facts.rect is None else "{},{} {}x{}".format(*facts.rect)
    cloak = facts.cloak_value if facts.cloak_hresult == 0 else "n/a"
    return (
        f"{indent}hwnd={facts.hwnd:<9} pid={facts.pid:<6} cls={facts.window_class!r:<34} "
        f"len={facts.text_length:<4} vis={str(facts.win32_visible):<5} cloak={cloak!s:<4} "
        f"[{facts.flags()}] rect={rect:<20} title={facts.title!r}"
    )


def _print_children(win32: Win32, windows: list[WindowFacts]) -> None:
    """The child windows of each given window, which is where a table can hide."""
    print("\n=== children of those windows ===")
    for facts in windows:
        kids = win32.children(facts.hwnd)
        if not kids:
            continue
        print(f"-- {facts.hwnd} {facts.title!r}: {len(kids)} descendant(s)")
        for child in kids[:40]:
            print(_line(win32.facts(child), "   "))


def _print_gates(all_facts: list[WindowFacts]) -> None:
    """What survives the detector's gates, and what the cloak test takes."""
    print("\n=== every window fpdb would keep, all processes ===")
    for facts in all_facts:
        if facts.kept_by_find_tables:
            print(_line(facts))

    print("\n=== titled+visible windows fpdb drops on the DWM cloak test ===")
    dropped = [f for f in all_facts if f.text_length > 0 and f.win32_visible and f.cloaked]
    for facts in dropped:
        print(_line(facts))
    if not dropped:
        print("  (none)")


def _report(win32: Win32, match: str, *, show_children: bool) -> None:
    needle = match.casefold()
    all_facts = [win32.facts(h) for h in win32.top_level()]
    interesting = [f for f in all_facts if needle in f.title.casefold() or needle in f.window_class.casefold()]
    pids = {f.pid for f in interesting}
    # A client draws its tables from the same process as its lobby, so widen
    # the report to every window of those processes -- including the untitled
    # ones, which is exactly where a table window goes missing.
    same_process = [f for f in all_facts if f.pid in pids]

    print(f"Windows enumerated: {len(all_facts)}")
    print(f"Candidates find_tables would keep: {sum(1 for f in all_facts if f.kept_by_find_tables)}")
    print(f"Matching {match!r}: {len(interesting)} window(s) in {len(pids)} process(es)\n")

    print(f"=== every top-level window of the {match!r} process(es) ===")
    for facts in same_process:
        print(_line(facts))
        print(f"    -> {facts.gate_verdict()}")
    if not same_process:
        print(f"  (none -- is the {match} client running?)")

    if show_children:
        _print_children(win32, same_process)
    _print_gates(all_facts)


def _client_pids(win32: Win32, needle: str) -> set[int]:
    """Processes owning at least one window that names the client.

    Tracking by process rather than by title is the whole point: a table window
    can be created untitled, or titled only once it has finished loading, and a
    title-based watch would not see it appear at all.
    """
    pids = set()
    for hwnd in win32.top_level():
        facts = win32.facts(hwnd)
        if needle in facts.title.casefold() or needle in facts.window_class.casefold():
            pids.add(facts.pid)
    return pids


def _watched_state(facts: WindowFacts) -> tuple:
    """The part of a window that a watch reports a change in."""
    return (facts.title, facts.win32_visible, facts.cloaked, facts.rect)


def _print_changes(
    before: dict[int, WindowFacts],
    now: dict[int, WindowFacts],
    *,
    first_pass: bool,
) -> None:
    """Report windows that appeared, changed, or went away between two passes."""
    for hwnd, facts in now.items():
        was = before.get(hwnd)
        if was is None:
            print(f"[+] {'(initial) ' if first_pass else ''}{_line(facts)}")
            print(f"     -> {facts.gate_verdict()}")
        elif _watched_state(was) != _watched_state(facts):
            print(f"[~] {_line(facts)}")
            print(f"     -> {facts.gate_verdict()}")
    for hwnd, facts in before.items():
        if hwnd not in now:
            print(f"[-] gone: hwnd={hwnd} title={facts.title!r} cls={facts.window_class!r}")


def _watch(win32: Win32, match: str, seconds: float) -> None:
    """Poll and report window arrivals, departures and title changes."""
    needle = match.casefold()
    pids = _client_pids(win32, needle)
    if not pids:
        print(f"No window names {match!r} -- start the client first.")
        return
    print(f"Watching every window of pid(s) {sorted(pids)} for {seconds:.0f}s -- open, play and close a table now.\n")
    seen: dict[int, WindowFacts] = {}
    deadline = time.monotonic() + seconds
    first_pass = True
    while time.monotonic() < deadline:
        current: dict[int, WindowFacts] = {}
        for hwnd in win32.top_level():
            facts = win32.facts(hwnd)
            # Match on the process, and re-check the needle too: a table may be
            # drawn by a second process the client spawns after this started.
            if facts.pid in pids or needle in facts.title.casefold() or needle in facts.window_class.casefold():
                pids.add(facts.pid)
                current[hwnd] = facts
                for child in win32.children(hwnd):
                    current[child] = win32.facts(child)
        _print_changes(seen, current, first_pass=first_pass)
        seen = current
        first_pass = False
        time.sleep(0.5)
    print("\nWatch finished.")


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("This diagnostic only runs on Windows.")
        return 1
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--match", default="Winamax", help="client name to look for in titles and window classes")
    parser.add_argument("--watch", type=float, metavar="SECONDS", help="poll for changes instead of a single report")
    parser.add_argument("--no-children", action="store_true", help="skip the child-window tree")
    args = parser.parse_args(argv)

    print(f"Windows version: {sys.getwindowsversion()}")
    print(f"Python: {sys.version}\n")
    win32 = Win32()
    if args.watch:
        _watch(win32, args.match, args.watch)
    else:
        _report(win32, args.match, show_children=not args.no_children)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
