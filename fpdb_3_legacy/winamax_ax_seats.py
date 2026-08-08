"""Read a Winamax table's seated players straight off the window (macOS).

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

macOS only. Other platforms keep the log-derived ring (see
:mod:`fpdb_3_legacy.winamax_live_log_reader`).
"""

from __future__ import annotations

import logging
import math
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
    """Whether this platform can read seats from the window."""
    if platform.system() != "Darwin":
        return False
    try:
        import ApplicationServices  # noqa: F401
        from AppKit import NSWorkspace  # noqa: F401
    except ImportError:
        return False
    return True


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

    def __init__(self) -> None:
        self._app: Any = None
        self._pid: int | None = None

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
        """
        if not is_supported():
            return None
        try:
            app = self._application()
            if app is None:
                return None
            for window in self._attr(app, "AXWindows") or []:
                title = self._attr(window, "AXTitle") or ""
                m = re.search(r"(\d+)\s*$", title)
                if not m or m.group(1) != str(table_no):
                    continue
                labels: list[AXSeat] = []
                self._collect_text(window, labels)
                # The header is the first text the client draws in the window.
                return AXTableWindow(title=title, description=labels[0].login if labels else "")
        except Exception:
            log.exception("Could not look up the Winamax window for table %s", table_no)
        return None

    def read_window(self, title: str, max_seats: int = 6) -> dict[int, str]:
        """Players at the window with this exact title, keyed by layout slot.

        Slot 0 is the bottom-centre chair, where the client draws the hero, and
        slots count clockwise from there. Empty chairs are simply absent.

        Returns an empty map when the client is not running, the window is not
        found, or accessibility is unavailable -- the caller then keeps whatever
        the log was able to work out.
        """
        if not is_supported():
            return {}
        try:
            app = self._application()
            if app is None:
                return {}
            for window in self._attr(app, "AXWindows") or []:
                if self._attr(window, "AXTitle") != title:
                    continue
                origin, size = self._geometry(window)
                if origin is None or size is None or not size[0] or not size[1]:
                    return {}
                labels: list[AXSeat] = []
                self._collect_text(window, labels)
                players = seats_from_labels(labels)
                if not players:
                    return {}
                centre = (origin[0] + size[0] / 2, origin[1] + size[1] / 2)
                return seat_slots_from_positions(players, centre, max_seats)
        except Exception:
            log.exception("Could not read Winamax seats from window %r", title)
        return {}
