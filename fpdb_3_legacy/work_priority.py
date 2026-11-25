"""Cooperative priority between visible work and long background imports.

Imports can only yield between complete file transactions. Interactive callers
announce themselves here; an importer pauses at its next file boundary, while
still taking one file turn at least every ``BACKGROUND_TURN_SECONDS``. The
bounded turn keeps a stream of searches from starving imports indefinitely.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Iterator

log = logging.getLogger("work_priority")

BACKGROUND_TURN_SECONDS = 0.1
INTERACTIVE_WAIT_SECONDS = 0.25

_condition = threading.Condition()
_interactive_waiters = 0
_interactive_active = 0
_background_paused = False
_background_active = 0


@contextlib.contextmanager
def background_work(name: str) -> Iterator[None]:
    """Mark one indivisible background unit (currently one imported file)."""
    global _background_active
    with _condition:
        _background_active += 1
        _condition.notify_all()
    started = time.monotonic()
    try:
        yield
    finally:
        duration_ms = (time.monotonic() - started) * 1000
        with _condition:
            _background_active -= 1
            _condition.notify_all()
        if duration_ms >= 1000:
            log.warning("[PERF] background-work name=%s duration=%.0fms", name, duration_ms)


@contextlib.contextmanager
def interactive_work(name: str) -> Iterator[None]:
    """Prioritize one user-visible operation at the next import boundary."""
    global _interactive_active, _interactive_waiters
    queued_at = time.monotonic()
    with _condition:
        if not _background_active:
            _interactive_active += 1
            started = time.monotonic()
            queue_wait_ms = 0.0
        else:
            _interactive_waiters += 1
            _condition.notify_all()
            deadline = queued_at + INTERACTIVE_WAIT_SECONDS
            while _background_active and not _background_paused and time.monotonic() < deadline:
                _condition.wait(max(0, deadline - time.monotonic()))
            _interactive_waiters -= 1
            _interactive_active += 1
            started = time.monotonic()
            queue_wait_ms = (started - queued_at) * 1000
    try:
        yield
    finally:
        duration_ms = (time.monotonic() - started) * 1000
        with _condition:
            _interactive_active -= 1
            _condition.notify_all()
        level = logging.WARNING if queue_wait_ms >= 100 or duration_ms >= 1000 else logging.DEBUG
        log.log(
            level,
            "[PERF] interactive-work name=%s queue_wait=%.0fms duration=%.0fms",
            name,
            queue_wait_ms,
            duration_ms,
        )


def background_checkpoint(name: str) -> None:
    """Yield at a safe boundary, then guarantee a bounded background turn."""
    global _background_paused
    started = time.monotonic()
    with _condition:
        if not _interactive_waiters and not _interactive_active:
            return
        _background_paused = True
        _condition.notify_all()
        deadline = started + BACKGROUND_TURN_SECONDS
        while (_interactive_waiters or _interactive_active) and time.monotonic() < deadline:
            _condition.wait(deadline - time.monotonic())
        _background_paused = False
        _condition.notify_all()
    waited_ms = (time.monotonic() - started) * 1000
    log.debug("[PERF] background-checkpoint name=%s yielded=%.0fms", name, waited_ms)


__all__ = [
    "BACKGROUND_TURN_SECONDS",
    "INTERACTIVE_WAIT_SECONDS",
    "background_checkpoint",
    "background_work",
    "interactive_work",
]
