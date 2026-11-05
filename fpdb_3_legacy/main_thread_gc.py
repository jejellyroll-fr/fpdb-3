"""Run Python's cyclic garbage collector on the Qt main thread only (#707).

Python collects on whichever thread crosses the allocation threshold. A Qt
object caught in a reference cycle is then destroyed on that thread, not on the
one it lives in. With the HUD this deadlocked: ``HudReadWorker`` collected a
widget wrapper, ``QObject::~QObject`` held a Qt mutex while its
``disconnectNotify`` override waited for the GIL, and the main thread held the
GIL while waiting for that mutex.

So automatic collection is turned off, and the same generational policy runs
from a timer on the main thread: the collector's thresholds are kept, only the
thread that acts on them changes.
"""

from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer

#: How often the main thread checks whether a collection is due.
CHECK_INTERVAL_MS = 500


def collect_if_due() -> int:
    """Collect the generations the automatic collector would have collected by now.

    Call it on the main thread. Returns the number of unreachable objects found.
    """
    thresholds = gc.get_threshold()
    counts = gc.get_count()
    if counts[0] <= thresholds[0]:
        return 0
    generation = 0
    for older in (1, 2):
        if counts[older] <= thresholds[older]:
            break
        generation = older
    return gc.collect(generation)


class MainThreadGarbageCollector(QObject):
    """Turn automatic collection off and collect from a main-thread timer instead."""

    def __init__(self, parent: QObject | None = None, interval_ms: int = CHECK_INTERVAL_MS) -> None:
        super().__init__(parent)
        self._was_enabled = gc.isenabled()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(collect_if_due)
        gc.disable()
        self._timer.start()

    def stop(self) -> None:
        """Give collection back to Python, as it was before."""
        self._timer.stop()
        if self._was_enabled:
            gc.enable()


def install_main_thread_gc(app: QObject) -> MainThreadGarbageCollector:
    """Collect on the main thread for as long as ``app`` lives. Call it right after creating the application."""
    return MainThreadGarbageCollector(app)
