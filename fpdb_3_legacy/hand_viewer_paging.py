"""Paging helpers for the Hand Viewer that need no Qt: the hand cache and the ID search.

The Hand Viewer rebuilds every hand it shows from the database, which is the
expensive part on large databases. It keeps the rebuilt hands in a cache so a
page seen before comes back at once, but that cache had no bound: paging
through thousands of hands kept every one of them in memory. ``HandCache``
forgets the hands seen least recently once it holds more than a few pages.

Finding a hand by number used to mean paging until it showed up.
``search_numbers`` turns what the user typed into the numbers stored in the
database, and ``locate_hand`` finds which page of the loaded hands holds it,
without rebuilding any hand.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: The fewest hands the cache keeps, whatever the page size.
MIN_CACHE_SIZE = 300
#: How many pages of hands the cache keeps.
CACHED_PAGES = 3
#: Hands.id and Hands.siteHandNo are BIGINT: a larger number cannot match and
#: would make PostgreSQL reject the query.
_BIGINT_MAX = 2**63 - 1
#: A Winamax hand number as written in the hand history, "#<HID1>-<HID2>-<HID3>".
_WINAMAX_NUMBER = re.compile(r"^(\d+)-(\d+)-(\d+)$")


def cache_limit(page_size: int) -> int:
    """How many rebuilt hands the cache keeps for pages of ``page_size`` hands."""
    return max(MIN_CACHE_SIZE, page_size * CACHED_PAGES)


class HandCache(OrderedDict):
    """Rebuilt hands by hand id, the hand used least recently first.

    It behaves as the plain dict it replaces, plus ``touch`` to mark a hand as
    just used and ``trim`` to forget the hands used least recently.
    """

    def touch(self, hand_id: Any) -> None:
        """Mark ``hand_id`` as the hand used most recently, if it is cached."""
        if hand_id in self:
            self.move_to_end(hand_id)

    def trim(self, limit: int, keep: Iterable[Any] = ()) -> None:
        """Forget the hands used least recently until at most ``limit`` remain.

        The hands in ``keep`` (the page on screen) are never forgotten, even
        when they alone exceed ``limit``.
        """
        kept = set(keep)
        for hand_id in list(self):
            if len(self) <= limit:
                break
            if hand_id not in kept:
                del self[hand_id]


def search_numbers(text: str) -> list[int]:
    """The hand numbers to look up for what the user typed, most likely first.

    It accepts a room hand number as copied from a hand history ("#123",
    GGPoker's "RC123", a Winamax "#1234-56-789") or an fpdb hand id. GGPoker's
    letter prefix is not stored, so only the digits are looked up; a Winamax
    number is stored the way WinamaxToFpdb builds it from its first two parts.
    """
    cleaned = re.sub(r"\s+", "", text or "").lstrip("#")
    numbers: list[int] = []
    winamax = _WINAMAX_NUMBER.match(cleaned)
    if winamax:
        numbers.append(int(f"{int(winamax.group(1)[:14])}{int(winamax.group(2))}"))
    digits = re.sub(r"\D", "", cleaned)
    if digits:
        numbers.append(int(digits))
    unique: list[int] = []
    for number in numbers:
        if 0 < number <= _BIGINT_MAX and number not in unique:
            unique.append(number)
    return unique


def hand_positions(hand_ids: Sequence[Any]) -> dict[Any, int]:
    """Each hand id's position in ``hand_ids``, the first one when it repeats."""
    positions: dict[Any, int] = {}
    for position, hand_id in enumerate(hand_ids):
        positions.setdefault(hand_id, position)
    return positions


def locate_hand(
    matches: Iterable[tuple[Any, Any]],
    numbers: Sequence[int],
    positions: Mapping[Any, int],
    page_size: int,
) -> tuple[Any, int] | None:
    """The loaded hand a search found, and the page it is on.

    ``matches`` are the ``(id, siteHandNo)`` rows of the hands whose room hand
    number or fpdb id is one of ``numbers``; ``positions`` maps each loaded
    hand id to its place in the list. A room hand number wins over an fpdb id,
    since that is what a user copies from a hand history, and the most likely
    number wins over the others. Hands outside the loaded list are ignored.
    """
    rows = [(hand_id, site_number) for hand_id, site_number in matches if hand_id in positions]
    for number in numbers:
        for hand_id, site_number in rows:
            if _as_int(site_number) == number:
                return hand_id, positions[hand_id] // page_size
    for number in numbers:
        for hand_id, _site_number in rows:
            if _as_int(hand_id) == number:
                return hand_id, positions[hand_id] // page_size
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
