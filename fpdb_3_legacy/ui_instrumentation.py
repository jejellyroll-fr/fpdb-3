"""Measure where opening a tab spends its time, and when the UI is frozen.

The third tab a user opens is reported as slow, and the SQL behind it is not:
the queries measured in isolation come back in tenths of a second. That leaves
the work that a query timer cannot see -- importing Matplotlib and scanning
the system fonts, building the widget, and the first real paint -- plus the
only figure that matches what "frozen" means to a user, which is how long the
Qt event loop went without running.

Two instruments, both usable in production and in a test:

* :class:`TabOpenProfiler` times the phases of one tab opening, first paint
  included, and reports them as one line.
* :class:`UiStallMonitor` fires every 50 ms and records how late each tick
  was. A tick that should have run at t and ran at t+400ms is 400 ms during
  which nothing could be drawn and no click could be answered.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject, QTimer

if TYPE_CHECKING:
    import logging
    from collections.abc import Iterator

    from PySide6.QtWidgets import QWidget

#: How often the stall monitor asks to be run.
DEFAULT_HEARTBEAT_MS = 50

#: A stall a user would notice. Chosen as the regression threshold because it
#: is roughly the point where a click stops feeling answered immediately.
UI_STALL_BUDGET_MS = 100.0


@dataclass
class TabTiming:
    """Phase durations of one tab opening, in milliseconds."""

    name: str
    phases: dict[str, float] = field(default_factory=dict)
    first_paint_ms: float | None = None
    total_ms: float = 0.0

    def format(self) -> str:
        """Render the timing as one greppable line."""
        phases = " ".join(f"{phase}={duration:.0f}ms" for phase, duration in self.phases.items())
        paint = "not-painted" if self.first_paint_ms is None else f"first_paint={self.first_paint_ms:.0f}ms"
        return f"tab={self.name!r} {phases} {paint} total={self.total_ms:.0f}ms"


class _FirstPaintWatcher(QObject):
    """Records when a widget is painted for the first time."""

    def __init__(self, started: float, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._started = started
        self.first_paint_ms: float | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        """Note the first paint, then stop watching."""
        if self.first_paint_ms is None and event.type() == QEvent.Type.Paint:
            self.first_paint_ms = (time.perf_counter() - self._started) * 1000
            watched.removeEventFilter(self)
        return False


class TabOpenProfiler:
    """Time the phases of opening one tab, first paint included.

    Usage mirrors the shape of the code it measures::

        profiler = TabOpenProfiler("Ring Player Stats")
        with profiler.phase("import"):
            from fpdb_3_legacy import GuiRingPlayerStats
        with profiler.phase("construct"):
            page = GuiRingPlayerStats.GuiRingPlayerStats(...)
        profiler.watch_first_paint(page)
        with profiler.phase("add_tab"):
            self.add_and_display_tab(page, "Ring Player Stats")
        profiler.report(log)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._started = time.perf_counter()
        self._timing = TabTiming(name=name)
        self._paint_watcher: _FirstPaintWatcher | None = None

    @contextmanager
    def phase(self, phase: str) -> Iterator[None]:
        """Time one named phase, even if it raises."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self._timing.phases[phase] = (time.perf_counter() - started) * 1000

    def watch_first_paint(self, widget: QWidget) -> None:
        """Start counting until ``widget`` paints for the first time.

        The paint is what the user actually waits for: a widget can be built
        and added to the tab bar and still show nothing for a second while its
        first draw is blocked behind the work that follows.
        """
        self._paint_watcher = _FirstPaintWatcher(self._started, parent=widget)
        widget.installEventFilter(self._paint_watcher)

    def result(self) -> TabTiming:
        """Return the timing collected so far."""
        self._timing.first_paint_ms = None if self._paint_watcher is None else self._paint_watcher.first_paint_ms
        self._timing.total_ms = (time.perf_counter() - self._started) * 1000
        return self._timing

    def report(self, log: logging.Logger) -> TabTiming:
        """Log the timing and return it.

        At WARNING for the same reason the HUD's diagnostics are: a slow tab
        is reported by users whose logs are not running at DEBUG.
        """
        timing = self.result()
        log.warning("[PERF] tab open: %s", timing.format())
        return timing


class UiStallMonitor(QObject):
    """Record how long the Qt event loop was unable to run.

    A timer asking to be run every ``interval_ms`` can only be late if
    something else held the thread. The lateness is therefore a direct
    measurement of a frozen UI, and it needs no cooperation from the code
    doing the freezing -- which is the point, since that code is usually an
    import or a first paint deep inside a library.
    """

    def __init__(self, interval_ms: int = DEFAULT_HEARTBEAT_MS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._timer = QTimer(self)
        self._timer.setTimerType(self._precise_timer_type())
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)
        self._expected: float | None = None
        self._stalls: list[float] = []
        self.ticks = 0

    @staticmethod
    def _precise_timer_type() -> Any:
        """Ask Qt for millisecond accuracy; a coarse timer would invent stalls."""
        from PySide6.QtCore import Qt

        return Qt.TimerType.PreciseTimer

    def start(self) -> None:
        """Begin measuring."""
        self._expected = time.perf_counter() + self._interval_ms / 1000
        self._timer.start()

    def stop(self) -> None:
        """Stop measuring. The recorded stalls are kept."""
        self._timer.stop()

    def _on_tick(self) -> None:
        now = time.perf_counter()
        self.ticks += 1
        if self._expected is not None:
            lateness_ms = (now - self._expected) * 1000
            self._stalls.append(max(0.0, lateness_ms))
        self._expected = now + self._interval_ms / 1000

    @property
    def stalls(self) -> tuple[float, ...]:
        """Every tick's lateness, in milliseconds, in order."""
        return tuple(self._stalls)

    @property
    def max_stall_ms(self) -> float:
        """The longest the event loop went without running."""
        return max(self._stalls, default=0.0)

    def stalls_over(self, threshold_ms: float = UI_STALL_BUDGET_MS) -> tuple[float, ...]:
        """Return the stalls a user would have noticed."""
        return tuple(stall for stall in self._stalls if stall > threshold_ms)

    def report(self, log: logging.Logger, context: str) -> float:
        """Log the worst stall seen and return it."""
        log.warning(
            "[PERF] UI event loop during %s: ticks=%d max_stall=%.0fms over_%.0fms=%d",
            context,
            self.ticks,
            self.max_stall_ms,
            UI_STALL_BUDGET_MS,
            len(self.stalls_over()),
        )
        return self.max_stall_ms
