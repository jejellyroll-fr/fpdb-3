"""Read a Winamax table's seated players straight off the window (macOS, Windows).

Why this exists
---------------
The Winamax client log never states a seat: it has no ``seat``, ``button``,
``dealer`` or ``position`` token anywhere, and its ``[core]`` lines carry only
message names, no payloads. The most a log can give is the order players act in,
which is a rotation of the ring whose starting point moves with the button --
and it only names a player once they have acted, so at the start of a hand the
hero's own place in it is unknown.

The client is an Electron app, so its table is a web page. Chromium builds an
accessibility tree on request, and that tree carries every player's name with
its on-screen position. That is the seat, directly: no inference, no waiting for
anyone to act, and separately per window, which is what multi-tabling a pool
needs.

Chromium answers the platform's accessibility API on both macOS (AX, through
``AXManualAccessibility``) and Windows (UIAutomation, through the request
itself), so both read the window. Linux, and any machine whose client will not
answer, keep the log-derived ring (see
:mod:`fpdb_3_legacy.winamax_live_log_reader`) -- which is correct but slow to
fill in: it can only name a player once they have acted, so the stat blocks
appear one at a time over the first betting round instead of all at once.
"""

from __future__ import annotations

import ctypes
import logging
import math
import os
import platform
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# A player's stack, e.g. "552,5 BB" or "7,64 €". The client draws it directly
# under the name, and that pairing is what identifies a seat -- far steadier than
# trying to blacklist every other label on the table (pot, buttons, promos,
# "ABSENT", the player's own hand description...).
_STACK = re.compile(r"^[\d\s., ]+(BB|€|\$)$", re.IGNORECASE)

# How far under a name its stack sits, and how far the two may drift apart
# horizontally. Measured on the client: 17px below, 11px across.
_STACK_DY = (2, 45)
_STACK_DX = 90

# A login carries at least one letter and is not a bare unit or a timer/slider
# readout ("BB", "80%", "23").
_CAN_BE_LOGIN = re.compile(r"^(?![\d\s.,%]+$)(?!(BB|€|\$)$).*[^\W\d_].*$", re.IGNORECASE)

# Labels the client draws in a seat's place, which carry a chip amount underneath
# just as a player does. "SMALL BLIND" was read as a player and took a seat.
_SEAT_LABELS = frozenset(
    {
        "small blind",
        "big blind",
        "ante",
        "dealer",
        "absent",
        "sitting out",
        "sit out",
        "all-in",
        "all in",
        "waiting",
        "empty",
        "3x",
        "x3",
        "x2.25",
        "x2.5",
        "x2",
        "pot",
        "call",
        "fold",
        "raise to",
        "auto-buy",
        "recaver",
        "tu es absent",
        "quitter",
        "revenir",
        "loading hud...",
        "hud - stats",
    }
)


@dataclass(frozen=True)
class AXSeat:
    """One player as the client draws them."""

    login: str
    x: int
    y: int


@dataclass(frozen=True)
class AXTableWindow:
    """A table window, as the client describes itself."""

    title: str
    """OS window title, e.g. ``Winamax Casablanca 6``."""

    description: str
    """The client's own header, e.g. ``ESCAPE - 0,01-0,02 € - Pot Limit Omaha``."""

    window_id: int | None = None
    """CGWindowID (or the detector's synthetic fallback ID), when resolved."""

    @property
    def table_name(self) -> str:
        """The name fpdb keys the table by: the title without the site prefix."""
        return re.sub(r"^Winamax\s+", "", self.title).strip()

    @property
    def poker_game(self) -> str | None:
        """fpdb's category for the game named in the header, if it names one."""
        return poker_game_from_description(self.description)


def poker_game_from_description(description: str) -> str | None:
    """Map a client header to an fpdb game category.

    Mirrors the table WinamaxToFpdb uses for hand histories, so a table created
    from its window and the same table created from an imported hand agree on
    what is being played.
    """
    text = (description or "").lower()
    if "omaha" in text:
        if "hi/lo" in text or "hilo" in text or "8" in text:
            return "5_omahahi" if "5 card" in text else "omahahilo"
        return "5_omahahi" if "5 card" in text else "omahahi"
    if "holdem" in text or "hold'em" in text:
        return "holdem"
    return None


def is_supported() -> bool:
    """Whether this platform can locate the client's table windows at all.

    True on macOS and Windows: ``find_table_window`` resolves table windows
    so a FastFold HUD can be attached on hand-start. Reading seats via accessibility
    still needs the API -- see :func:`is_ax_available`.
    """
    return platform.system() in ("Darwin", "Windows")


def is_ax_available() -> bool:
    """Whether the accessibility API can be called from this process.

    On macOS, checks ApplicationServices / AppKit bindings.
    On Windows, checks comtypes UIAutomationCore binding.
    """
    if platform.system() == "Darwin":
        try:
            import ApplicationServices  # noqa: F401
            from AppKit import NSWorkspace  # noqa: F401
            return True
        except ImportError:
            return False
    elif platform.system() == "Windows":
        try:
            import comtypes.client  # noqa: F401
            return True
        except ImportError:
            return False
    return False


class _WindowsUIAClient:
    """The process-wide UIAutomation client used to read a table's labels.

    Built once, because it used to be built on every read: importing the
    generated UIAutomationCore wrapper and creating the COM object cost ~130ms
    the first time (far more in a frozen build, which has to generate the
    wrapper in memory), and that was paid on the GUI thread while a table was
    being dealt.

    Properties are read live rather than through a cache request. That looks
    like the obvious optimisation and measures the other way round on this
    client: the table is a Chromium window whose subtree runs to thousands of
    nodes, FindAllBuildCache builds a cache for every one of them, and the read
    stops at MAX_ELEMENTS -- three times slower for the same answer.
    """

    # UIAutomationCore.idl: TreeScope_Element | _Children | _Descendants.
    # Taken as a literal because the name comtypes generates for it has moved
    # between versions.
    TREE_SCOPE_SUBTREE = 7

    # The walk returns the whole subtree, which on a Chromium window is far more
    # than a table's own labels. This is what bounds the per-read cost.
    MAX_ELEMENTS = 300

    # Nothing the client labels a chair with is longer than this, and skipping
    # the long ones (chat, promos, rules) keeps seats_from_labels cheap.
    MAX_LABEL_LEN = 40

    def __init__(self, automation: Any, condition: Any) -> None:
        self.automation = automation
        self._condition = condition

    def collect_labels(self, element: Any) -> list[AXSeat]:
        """Every short text label under ``element``, with its screen position.

        Labels belonging to this process are skipped. The HUD's own stat blocks
        are top-level windows made transient children of the table they sit on,
        which puts them inside the subtree searched here -- so a walk of a table
        window came back holding the HUD's own text:

            'HUD - stats'  'MonXt.'  'H 2'  'VP 0.0'  'PR 0.0'  '3B -'  'CB -'

        Those are stat abbreviations, not players, and feeding them to
        seats_from_labels can only produce nonsense or nothing. The HUD reading
        its own output back is a loop worth cutting whatever else the client
        does or does not expose.
        """
        found = element.FindAll(self.TREE_SCOPE_SUBTREE, self._condition)
        if not found or not found.Length:
            return []
        labels: list[AXSeat] = []
        own_pid = os.getpid()
        for index in range(min(found.Length, self.MAX_ELEMENTS)):
            item = found.GetElement(index)
            # Fail open: only an element positively identified as ours is
            # dropped. Losing a real player's label because one attribute read
            # hiccuped would cost the whole seat map, which is the failure this
            # reader exists to avoid.
            try:
                is_ours = item.CurrentProcessId == own_pid
            except Exception:  # noqa: BLE001 - unreadable pid is not proof of anything
                is_ours = False
            if is_ours:
                continue
            name = item.CurrentName
            if not isinstance(name, str) or not name or len(name) > self.MAX_LABEL_LEN:
                continue
            rect = item.CurrentBoundingRectangle
            if not rect:
                continue
            labels.append(AXSeat(name.replace("\xa0", " ").strip(), rect.left, rect.top))
        return labels


_windows_uia_client: _WindowsUIAClient | None = None
_windows_uia_unavailable = False

#: WM_GETOBJECT / OBJID_CLIENT: what an assistive technology sends a window, and
#: what a Chromium client watches for before it builds its accessibility tree.
_WM_GETOBJECT = 0x003D
_OBJID_CLIENT = -4
_SMTO_ABORTIFHUNG = 0x0002
_GETOBJECT_TIMEOUT_MS = 200

#: Windows already asked, so a table is nudged once rather than on every read.
_accessibility_asked: set[int] = set()


def forget_accessibility_requests() -> None:
    """Forget which windows have been asked, so the next read asks again."""
    _accessibility_asked.clear()


def request_windows_accessibility(hwnd: int) -> None:
    """Ask a Chromium client to build its accessibility tree, once per window.

    The macOS reader does this explicitly -- ``AXManualAccessibility`` on the
    application -- and says why: "Chromium only builds its web accessibility
    tree when an assistive client asks for it; without this the windows expose
    nothing but their titles." Windows had no equivalent, and measured exactly
    the symptom that note predicts: six nodes under a whole poker table, the
    window title among them, and not one player. Every hand then fell back to
    the client log, which names a player only once they have acted.

    The Windows way of asking is WM_GETOBJECT with OBJID_CLIENT. It goes to the
    table window and to each of its children, because the content is drawn in a
    child render surface rather than the frame the HUD attached to.

    SendMessageTimeout, never SendMessage: the client is another process, and a
    blocked or busy one must not be able to hang the HUD's GUI thread. The tree
    is built asynchronously, so the read that triggers this one will usually
    still come back empty; the rechecks within the hand are what pick it up.
    """
    if platform.system() != "Windows" or not hwnd or hwnd in _accessibility_asked:
        return
    _accessibility_asked.add(hwnd)
    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        targets = [hwnd]

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _collect(child: int, _param: int) -> bool:
            targets.append(child)
            return True

        user32.EnumChildWindows(wintypes.HWND(hwnd), _collect, 0)
        result = ctypes.c_void_p()
        for target in targets:
            user32.SendMessageTimeoutW(
                wintypes.HWND(target),
                _WM_GETOBJECT,
                0,
                wintypes.LPARAM(_OBJID_CLIENT),
                _SMTO_ABORTIFHUNG,
                _GETOBJECT_TIMEOUT_MS,
                ctypes.byref(result),
            )
        log.info("Asked %d window(s) of %s to publish their accessibility tree", len(targets), hwnd)
    except Exception:
        # Never fatal: without it the reader is exactly as blind as it was.
        log.debug("Could not ask window %s for its accessibility tree", hwnd, exc_info=True)


def reset_windows_uia() -> None:
    """Drop the shared UIAutomation client so the next read rebuilds it."""
    global _windows_uia_client, _windows_uia_unavailable
    _windows_uia_client = None
    _windows_uia_unavailable = False


def _windows_uia() -> _WindowsUIAClient | None:
    """The shared UIAutomation client, or None when this machine has no usable one.

    A failure is remembered so a client that cannot be built (no comtypes, COM
    refusing to start, a frozen build unable to generate the wrapper) is not
    retried on every hand.
    """
    global _windows_uia_client, _windows_uia_unavailable

    if _windows_uia_client is not None or _windows_uia_unavailable:
        return _windows_uia_client
    try:
        import comtypes.client

        module = comtypes.client.GetModule("UIAutomationCore.dll")
        automation = comtypes.client.CreateObject(module.CUIAutomation)
        _windows_uia_client = _WindowsUIAClient(automation, automation.CreateTrueCondition())
        log.info("UIAutomation seat reader ready")
    except Exception:
        _windows_uia_unavailable = True
        # WARNING, not INFO: this is the difference between a Fast-Fold table's
        # blocks appearing together and appearing one at a time over the first
        # betting round, and it was invisible. The root logger is pinned to
        # WARNING (loggingFpdb.DIAGNOSTIC_LEVEL_CAP) and "hud_main" is persisted
        # lower still, so the INFO line this used to be reached no user's log --
        # the HUD lost the window reader and said nothing about it. Once per
        # process: the failure is remembered just above.
        log.warning(
            "No UIAutomation seat reader: Fast-Fold seats will come from the client log, which names a "
            "player only once they have acted, so the stat blocks appear one at a time over the first "
            "betting round.",
            exc_info=True,
        )
    return _windows_uia_client


def read_window_for(hwnd: int, title: str = "", max_seats: int = 6) -> dict[int, str]:
    """One window read by handle, for diagnostics that hold a HWND and no reader."""
    return WinamaxAXSeatReader().read_window(title, max_seats, window_id=hwnd)


def is_stack_label(text: str) -> bool:
    """Whether a text node is a chip count rather than anything else."""
    return bool(_STACK.match(text.strip()))


def is_seat_label(text: str) -> bool:
    """Whether a text node is the client labelling a seat rather than naming a player.

    These sit exactly where a player's name would, with a chip amount beneath
    them, so the name/stack pairing alone cannot tell them apart. Two shapes
    cover what the client draws: known labels, and the hand descriptions it puts
    under the hero ("Full : 2-6", "Hauteur : A").
    """
    text = text.replace("\xa0", " ").strip()
    if text.lower() in _SEAT_LABELS:
        return True
    if " : " in text:
        return True
    # "SMALL BLIND", "ALL IN": shouted labels have spaces, whereas a login in
    # capitals does not.
    return text.isupper() and " " in text


def is_hud_label(text: str) -> bool:
    """Whether a text node comes from an active FPDB HUD overlay window."""
    t = (text or "").replace("\xa0", " ").strip()
    if not t:
        return True

    # Truncated HUD headers, e.g. "jejel.", "almar.", "fishk.", "Lexyn.", "Zibit.", "HERGI.", "Stun_.", "anton."
    if len(t) <= 6 and t.endswith("."):
        return True

    # HUD stat box lines or headers
    if re.search(r"^(H\s*\d+|VP|PR|3B|F3|ST|FS|CB|FC|WW|LP|WS|F|T|R)\b", t, re.IGNORECASE):
        return True

    return False


def seats_from_labels(labels: list[AXSeat]) -> list[AXSeat]:
    """Keep the labels that are player names, by pairing each with its stack.

    A name is a label with a stack drawn just beneath it. Everything else on the
    table -- pot, action buttons, promos, "ABSENT", the hand description -- has
    no stack under it and drops out, without needing to be enumerated.
    """
    stacks = [label for label in labels if is_stack_label(label.login)]
    names = []
    for candidate in labels:
        if (
            is_stack_label(candidate.login)
            or is_seat_label(candidate.login)
            or is_hud_label(candidate.login)
            or not _CAN_BE_LOGIN.match(candidate.login)
        ):
            continue
        for stack in stacks:
            dy = stack.y - candidate.y
            if _STACK_DY[0] <= dy <= _STACK_DY[1] and abs(stack.x - candidate.x) <= _STACK_DX:
                names.append(candidate)
                break
    return names


def seat_slots_from_positions(
    seats: list[AXSeat],
    centre: tuple[float, float],
    max_seats: int,
) -> dict[int, str]:
    """Map players to layout slots, counting clockwise from the bottom-centre.

    Slot 0 is where the client always draws the hero. Slots are derived from
    each player's angle around the table rather than from their order, so an
    empty chair leaves its slot empty instead of pulling everyone after it one
    place round -- which is what puts stat blocks on the wrong players when a
    table is not full.
    """
    if not seats or max_seats <= 0:
        return {}

    cx, cy = centre
    step = 2 * math.pi / max_seats
    slots: dict[int, tuple[float, str]] = {}

    for seat in seats:
        angle = (math.atan2(cx - seat.x, seat.y - cy) + 2 * math.pi) % (2 * math.pi)
        slot = round(angle / step) % max_seats
        # The table is an ellipse, so angles are not evenly spaced; keep the
        # player nearest a slot's centre if two ever round to the same one.
        offset = abs(((angle - slot * step + math.pi) % (2 * math.pi)) - math.pi)
        current = slots.get(slot)
        if current is None or offset < current[0]:
            slots[slot] = (offset, seat.login)

    return {slot: login for slot, (_, login) in slots.items()}


class WinamaxAXSeatReader:
    """Reads seated players from Winamax table windows through macOS accessibility."""

    def __init__(self, table_detector: Any | None = None) -> None:
        self._app: Any = None
        self._pid: int | None = None
        # Reuse the platform singleton also owned by OSXTables. Besides avoiding
        # two independent System Events circuit breakers, this lets the window
        # resolved at hand-start be handed straight to HUD creation.
        self._table_detector: Any | None = table_detector

    def _application(self) -> Any:
        """The AX handle for the running client, with its web tree switched on."""
        from AppKit import NSWorkspace
        from ApplicationServices import AXUIElementCreateApplication, AXUIElementSetAttributeValue

        pid = None
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if (app.localizedName() or "").lower() == "winamax":
                pid = app.processIdentifier()
                break
        if pid is None:
            self._app, self._pid = None, None
            return None

        if self._app is None or self._pid != pid:
            self._app = AXUIElementCreateApplication(pid)
            self._pid = pid
            # Chromium only builds its web accessibility tree when an assistive
            # client asks for it; without this the windows expose nothing but
            # their titles. The call reports an error yet still takes effect.
            AXUIElementSetAttributeValue(self._app, "AXManualAccessibility", True)
        return self._app

    @staticmethod
    def _attr(element: Any, name: str) -> Any:
        from ApplicationServices import AXUIElementCopyAttributeValue

        err, value = AXUIElementCopyAttributeValue(element, name, None)
        return value if err == 0 else None

    @classmethod
    def _geometry(cls, element: Any) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        from ApplicationServices import AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType

        result: list[tuple[int, int] | None] = []
        for name, kind in (("AXPosition", kAXValueCGPointType), ("AXSize", kAXValueCGSizeType)):
            boxed = cls._attr(element, name)
            if boxed is None:
                result.append(None)
                continue
            ok, value = AXValueGetValue(boxed, kind, None)
            if not ok:
                result.append(None)
            elif kind == kAXValueCGPointType:
                result.append((round(value.x), round(value.y)))
            else:
                result.append((round(value.width), round(value.height)))
        return result[0], result[1]

    def _collect_text(self, element: Any, found: list[AXSeat], depth: int = 0) -> None:
        if element is None or depth > 20 or len(found) > 400:
            return
        role = str(self._attr(element, "AXRole"))
        if role == "AXButton":
            # Bet-size and action controls ("POT", "ALL-IN", "x2.25", "F1 FOLD")
            # label themselves with static text and sit above chip amounts, so
            # they would otherwise pair up and read as players.
            return
        if role == "AXStaticText":
            value = self._attr(element, "AXValue")
            if isinstance(value, str):
                # The client separates words with non-breaking spaces ("Pot
                # total\xa0:\xa01,5\xa0BB"), which made a literal " : " test miss
                # and seated the pot as a player. Normalise once, here, so every
                # rule below sees ordinary spaces.
                value = value.replace("\xa0", " ").strip()
            if isinstance(value, str) and value and len(value) <= 40:
                position, _ = self._geometry(element)
                if position is not None:
                    found.append(AXSeat(value, position[0], position[1]))
        for child in self._attr(element, "AXChildren") or []:
            self._collect_text(child, found, depth + 1)

    def find_table_window(self, table_no: str) -> AXTableWindow | None:
        """The window the client calls ``[table] N``, with what it says it is.

        The client numbers its table windows in their titles ("Winamax Casablanca
        6"), which is the same index the log writes, so a pool can be tied to a
        window without waiting for any hand to be imported.

        Quartz is tried first through the shared platform detector, because it
        yields the real CGWindowID without an Apple Event when Screen Recording
        is granted. Accessibility then enriches that answer with the client
        header and seats. Only when Quartz and AX cannot resolve the window does
        the shared detector use its throttled System Events fallback.
        """
        if not is_supported():
            return None

        system = platform.system()
        detected = self._find_table_window_detector(table_no, allow_fallback=False)
        # The detector is the Windows window-resolution contract. The AX tree
        # reader below imports AppKit/ApplicationServices and must never be
        # probed on Windows merely because the shared reader supports both OSes.
        if system == "Windows":
            return detected
        if system != "Darwin":
            return None

        accessible = self._find_table_window_ax(table_no)
        if detected is not None:
            if accessible is not None:
                return AXTableWindow(
                    title=detected.title,
                    description=accessible.description,
                    window_id=detected.window_id,
                )
            return detected

        # AX can name the table without Screen Recording, but it cannot provide
        # the CGWindowID needed to attach an overlay. Give the shared detector a
        # final chance to pair it through System Events and preserve the AX
        # header if it succeeds.
        detected = self._find_table_window_detector(table_no, allow_fallback=True)
        if detected is not None:
            if accessible is not None:
                return AXTableWindow(
                    title=detected.title,
                    description=accessible.description,
                    window_id=detected.window_id,
                )
            return detected
        return accessible

    def _find_table_window_detector(self, table_no: str, *, allow_fallback: bool) -> AXTableWindow | None:
        """Resolve one indexed Winamax window through the platform detector."""
        try:
            if self._table_detector is None:
                from fpdb.infrastructure.platform import get_table_detector

                self._table_detector = get_table_detector()
            search = rf"^Winamax\s+.*\s{re.escape(str(table_no))}\s*$"
            tables = self._table_detector.find_tables(search, allow_fallback=allow_fallback)
        except Exception:
            log.debug("Shared macOS detector could not resolve Winamax table %s", table_no, exc_info=True)
            return None

        for table in tables:
            title = str(getattr(table, "title", "") or "")
            if not self._is_table_no(title, table_no):
                continue
            try:
                window_id = int(table.window_id)
            except (AttributeError, TypeError, ValueError):
                window_id = None
            return AXTableWindow(title=title, description="", window_id=window_id)
        return None

    def _find_table_window_ax(self, table_no: str) -> AXTableWindow | None:
        """The table window and its header, read through the accessibility API."""
        if not is_ax_available():
            return None
        try:
            app = self._application()
            if app is None:
                return None
            for window in self._attr(app, "AXWindows") or []:
                title = self._attr(window, "AXTitle") or ""
                if not self._is_table_no(title, table_no):
                    continue
                labels: list[AXSeat] = []
                self._collect_text(window, labels)
                # The header is the first text the client draws in the window.
                return AXTableWindow(title=title, description=labels[0].login if labels else "")
        except Exception:
            log.exception("Could not look up the Winamax window for table %s", table_no)
        return None

    @staticmethod
    def _is_table_no(title: str, table_no: str) -> bool:
        """Whether a window title carries the client index the log reported."""
        m = re.search(r"(\d+)\s*$", title or "")
        return m is not None and m.group(1) == str(table_no)

    def read_window(  # noqa: C901, PLR0912
        self,
        title: str,
        max_seats: int = 6,
        table_pos: tuple[float, float] | None = None,
        window_id: int | None = None,
    ) -> dict[int, str]:
        """Players at the window with this exact title, keyed by layout slot.

        Slot 0 is the bottom-centre chair, where the client draws the hero, and
        slots count clockwise from there. Empty chairs are simply absent.

        When multiple table windows share the same title (e.g. multi-tabling
        identical stakes), ``table_pos`` selects the window closest to the
        target table's screen coordinates. ``window_id`` settles it outright and
        is preferred where the caller has one: on Windows it also saves
        enumerating every window on the desktop, on every read.
        """
        if not is_ax_available():
            return {}
        if platform.system() == "Windows":
            if window_id:
                return self._read_window_windows(int(window_id), max_seats)
            return self._read_window_windows_by_title(title, max_seats, table_pos=table_pos)
        try:
            app = self._application()
            if app is None:
                return {}
            matching_windows: list[tuple[Any, tuple[float, float], tuple[float, float]]] = []
            clean_title = re.sub(r"\s*#\d+$", "", title)
            for window in self._attr(app, "AXWindows") or []:
                w_title = str(self._attr(window, "AXTitle") or "")
                clean_w_title = re.sub(r"\s*#\d+$", "", w_title)
                if clean_w_title != clean_title:
                    m_req = re.search(r"(\d+)\s*$", clean_title)
                    m_win = re.search(r"(\d+)\s*$", clean_w_title)
                    if m_req and m_win:
                        if m_req.group(1) != m_win.group(1):
                            continue
                    elif clean_w_title not in clean_title and clean_title not in clean_w_title:
                        continue
                origin, size = self._geometry(window)
                if origin is None or size is None or not size[0] or not size[1]:
                    continue
                matching_windows.append((window, origin, size))

            if not matching_windows:
                return {}

            if table_pos is not None and len(matching_windows) > 1:
                tx, ty = table_pos
                best_window, best_origin, best_size = min(
                    matching_windows,
                    key=lambda w: (w[1][0] - tx) ** 2 + (w[1][1] - ty) ** 2,
                )
            else:
                best_window, best_origin, best_size = matching_windows[0]

            labels: list[AXSeat] = []
            self._collect_text(best_window, labels)
            players = seats_from_labels(labels)
            if not players:
                return {}
            centre = (best_origin[0] + best_size[0] / 2, best_origin[1] + best_size[1] / 2)
            return seat_slots_from_positions(players, centre, max_seats)
        except Exception:
            log.exception("Could not read Winamax seats from window %r", title)
        return {}

    def _read_window_windows_by_title(
        self,
        title: str,
        max_seats: int = 6,
        table_pos: tuple[float, float] | None = None,
    ) -> dict[int, str]:
        """Read seated players from Winamax window via Windows UIAutomation."""
        try:
            if self._table_detector is None:
                from fpdb.infrastructure.platform import get_table_detector
                self._table_detector = get_table_detector()
            tables = self._table_detector.find_tables(re.escape(title))
            if not tables:
                return {}
            if table_pos is not None and len(tables) > 1:
                tx, ty = table_pos
                best_table = min(
                    tables,
                    key=lambda t: (
                        (t.geometry.x - tx) ** 2 + (t.geometry.y - ty) ** 2 if t.geometry else 0
                    ),
                )
                hwnd = best_table.window_id
            else:
                hwnd = tables[0].window_id
            if hwnd is None:
                return {}
            return self._read_window_windows(int(hwnd), max_seats)
        except Exception:
            log.debug("Failed to read Windows seats for %r:", title, exc_info=True)
            return {}

    def _read_window_windows(self, hwnd: int, max_seats: int = 6) -> dict[int, str]:
        try:
            client = _windows_uia()
            if client is None:
                return {}

            # Ask before looking: a Chromium client publishes nothing until an
            # assistive client asks, which is what the macOS reader does with
            # AXManualAccessibility.
            request_windows_accessibility(hwnd)
            elem = client.automation.ElementFromHandle(hwnd)
            if elem is None:
                return {}
            labels = client.collect_labels(elem)
            if not labels:
                return {}
            players = seats_from_labels(labels)
            if not players:
                return {}
            win_rect = elem.CurrentBoundingRectangle
            if not win_rect:
                return {}
            centre = (win_rect.left + (win_rect.right - win_rect.left) / 2, win_rect.top + (win_rect.bottom - win_rect.top) / 2)
            return seat_slots_from_positions(players, centre, max_seats)
        except Exception:
            log.debug("Error reading Winamax UIAutomation seats on Windows for HWND %s:", hwnd, exc_info=True)
            return {}

    def prewarm(self) -> None:
        """Build whatever the platform's seat reader needs, before the first hand.

        On Windows that is the UIAutomation client: creating it imports comtypes
        and, in a frozen build with no writable ``comtypes.gen``, generates the
        UIAutomationCore wrapper in memory -- a few hundred milliseconds, once.
        Paid here, at startup, it is not paid on the GUI thread while a table is
        being dealt. Failure is not an error: the log-derived ring still works.
        """
        if platform.system() != "Windows":
            return
        if not is_ax_available():
            # comtypes is not importable. The win32 dependency in pyproject and
            # the PyInstaller hook exist to stop exactly this, so a build that
            # arrives here has lost them somewhere -- and it degraded in
            # silence, because this branch simply returned.
            log.warning(
                "Fast-Fold seats will come from the client log: comtypes is not importable, so this "
                "build cannot read a table's chairs from its window.",
            )
            return
        _windows_uia()
