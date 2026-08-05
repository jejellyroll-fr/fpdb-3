"""Per-thread context used by statistics that inspect the current hand."""

from __future__ import annotations

import threading
from typing import Any

_thread_local = threading.local()


def get_hand_instance() -> Any | None:
    """Return the hand associated with the current thread, if any."""
    return getattr(_thread_local, "hand", None)


def set_hand_instance(hand: Any | None) -> None:
    """Associate a hand with the current thread."""
    _thread_local.hand = hand
