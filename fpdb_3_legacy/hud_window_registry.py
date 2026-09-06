"""One renderer per poker window, decided in one place.

A Fast-Fold table is named after its pool, so several windows write hands
under one name and the HUD's text key is not an identity. The native window id
is. When the resolver produces a different key for a window it has already
built a HUD on -- a retry, an import snapshot arriving after the live log, a
title the client rewrote -- the second key builds a second set of overlays on
top of the first, and the player sees every statistic twice.

This registry is the write-side guard for that: a HUD may only be created
after claiming its window, and a claim says plainly whether the window is
free, already held by this same key (so the create must be refused), or held
by a key that has been superseded (so the old generation must be destroyed
first). Generations exist so an asynchronous read that comes back after its
HUD was torn down can be recognised and dropped instead of painting a window
that no longer belongs to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ClaimOutcome(Enum):
    """What claiming a window means for the caller."""

    #: Nothing held this window. Build the HUD.
    CREATED = "created"
    #: This exact key already holds this window. Refuse the second renderer.
    DUPLICATE = "duplicate"
    #: Another key held this window. Destroy that HUD, then build.
    SUPERSEDED = "superseded"
    #: The window has no usable id, so uniqueness cannot be enforced here.
    UNTRACKED = "untracked"


@dataclass(frozen=True)
class HudRegistration:
    """The HUD currently entitled to render on a native window."""

    window_id: Any
    temp_key: str
    generation: int


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of claiming a window, plus what the caller must do about it."""

    outcome: ClaimOutcome
    registration: HudRegistration | None
    superseded: HudRegistration | None = None

    @property
    def should_create(self) -> bool:
        """Whether the caller may go on to build a HUD."""
        return self.outcome is not ClaimOutcome.DUPLICATE

    @property
    def generation(self) -> int:
        """The generation the caller's HUD belongs to."""
        return 0 if self.registration is None else self.registration.generation


class HudWindowRegistry:
    """Maps ``window_id`` to the single HUD key allowed to render on it."""

    def __init__(self) -> None:
        self._by_window: dict[Any, HudRegistration] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        """The last generation handed out."""
        return self._generation

    def next_generation(self) -> int:
        """Reserve the next generation number."""
        self._generation += 1
        return self._generation

    def lookup(self, window_id: Any) -> HudRegistration | None:
        """Return the registration holding ``window_id``, if any."""
        if window_id is None:
            return None
        return self._by_window.get(window_id)

    def key_for(self, window_id: Any) -> str | None:
        """Return the HUD key holding ``window_id``, if any."""
        registration = self.lookup(window_id)
        return None if registration is None else registration.temp_key

    def registration_for_key(self, temp_key: str) -> HudRegistration | None:
        """Return the registration filed under ``temp_key``, if any."""
        for registration in self._by_window.values():
            if registration.temp_key == temp_key:
                return registration
        return None

    def claim(self, window_id: Any, temp_key: str) -> ClaimResult:
        """Reserve ``window_id`` for ``temp_key``.

        A window with no id cannot be de-duplicated -- an ordinary cash table
        keyed by its own unique title, or a platform whose window ids are not
        readable -- so it is tracked only by generation and left alone.
        """
        if window_id is None:
            return ClaimResult(ClaimOutcome.UNTRACKED, HudRegistration(None, temp_key, self.next_generation()))

        existing = self._by_window.get(window_id)
        if existing is not None and existing.temp_key == temp_key:
            return ClaimResult(ClaimOutcome.DUPLICATE, existing)

        registration = HudRegistration(window_id, temp_key, self.next_generation())
        self._by_window[window_id] = registration
        if existing is None:
            return ClaimResult(ClaimOutcome.CREATED, registration)
        return ClaimResult(ClaimOutcome.SUPERSEDED, registration, superseded=existing)

    def release(self, temp_key: str) -> HudRegistration | None:
        """Forget the window held by ``temp_key`` and return what was released.

        Releasing by key rather than by window id is deliberate: a HUD is torn
        down by key, and the table object it would have read the window id back
        from may already be gone by then.
        """
        for window_id, registration in list(self._by_window.items()):
            if registration.temp_key == temp_key:
                del self._by_window[window_id]
                return registration
        return None

    def release_registration(self, registration: HudRegistration | None) -> bool:
        """Forget exactly ``registration``, if it is still the one on file.

        Undoing one failed claim needs this rather than ``release``: one key can
        hold two windows at once -- a table whose client recreated its window
        keeps the old registration until that HUD is torn down -- and releasing
        by key would then drop whichever was filed first, usually the *live*
        HUD's, leaving the window this attempt just claimed registered and every
        later hand for it refused as a duplicate.
        """
        if registration is None or registration.window_id is None:
            return False
        if self._by_window.get(registration.window_id) is not registration:
            return False
        del self._by_window[registration.window_id]
        return True

    def is_current(self, temp_key: str, generation: int) -> bool:
        """Whether ``generation`` is still the live HUD for ``temp_key``.

        Asynchronous work captures the generation it was started for and
        checks it here before touching any window: a read that comes back
        after its HUD was destroyed and rebuilt must be dropped, not applied
        to the replacement.
        """
        registration = self.registration_for_key(temp_key)
        return registration is not None and registration.generation == generation

    def snapshot(self) -> dict[Any, HudRegistration]:
        """Return the registry contents, for diagnostics and tests."""
        return dict(self._by_window)
