"""Measure where opening a tab spends its time, and when the UI is frozen.

The third tab a user opens is reported as slow, and the SQL behind it is not:
the queries measured in isolation come back in tenths of a second. That leaves
the work that a query timer cannot see -- importing the page's module, building
the widget, and the first real paint -- plus the only figure that matches what
"frozen" means to a user, which is how long the Qt event loop went without
running. (This paragraph used to name a Matplotlib font scan. That cost left
with the PyQtGraph migration in #228, and the sentence outliving it is what
sent the #249 analysis after a suspect that no longer existed.)

The import is timed on its own because it is the one phase whose cost depends
on how the application was installed: a PyOxidizer bundle resolves a module
out of its embedded blob on first use, over a randomized read-only mount when
macOS has translocated the .app. ``fpdb.open_tab`` performs it, so a tab that
imports its own page inside ``build`` would hide that figure inside
``construct=``.

Two instruments, both usable in production and in a test:

* :class:`TabOpenProfiler` times the phases of one tab opening, first paint
  included, and reports them as one line.
* :class:`UiStallMonitor` fires every 50 ms and records how late each tick
  was. A tick that should have run at t and ran at t+400ms is 400 ms during
  which nothing could be drawn and no click could be answered.

Both were blind in production until #249. The profiler was reported inline,
before the event loop could deliver a Paint event, so every real log line read
``not-painted`` and stopped timing at the tab bar rather than at the drawn
tab; and the stall monitor was never instantiated outside the test suite. Use
:meth:`TabOpenProfiler.report_when_painted` and
:meth:`TabOpenProfiler.watch_ui_stalls` -- an instrument that cannot observe
the symptom is worse than none, because it answers.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject, QTimer

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable, Iterator

    from PySide6.QtWidgets import QWidget

#: How often the stall monitor asks to be run.
DEFAULT_HEARTBEAT_MS = 50

#: A stall a user would notice. Chosen as the regression threshold because it
#: is roughly the point where a click stops feeling answered immediately.
UI_STALL_BUDGET_MS = 100.0

#: How long :meth:`TabOpenProfiler.report_when_painted` waits for a first paint
#: before logging anyway. A tab that has not drawn within this window is the
#: symptom being investigated, so the line must not be lost to it.
FIRST_PAINT_TIMEOUT_MS = 10_000


@dataclass
class TabTiming:
    """Phase durations of one tab opening, in milliseconds."""

    name: str
    phases: dict[str, float] = field(default_factory=dict)
    first_paint_ms: float | None = None
    total_ms: float = 0.0
    max_stall_ms: float | None = None

    def format(self) -> str:
        """Render the timing as one greppable line."""
        phases = " ".join(f"{phase}={duration:.0f}ms" for phase, duration in self.phases.items())
        paint = "not-painted" if self.first_paint_ms is None else f"first_paint={self.first_paint_ms:.0f}ms"
        stall = "" if self.max_stall_ms is None else f" max_stall={self.max_stall_ms:.0f}ms"
        return f"tab={self.name!r} {phases} {paint} total={self.total_ms:.0f}ms{stall}"


class _FirstPaintWatcher(QObject):
    """Records when a widget is painted for the first time."""

    def __init__(
        self,
        started: float,
        parent: QObject | None = None,
        on_paint: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._started = started
        self._on_paint = on_paint
        self.first_paint_ms: float | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        """Note the first paint, then stop watching."""
        if self.first_paint_ms is None and event.type() == QEvent.Type.Paint:
            self.first_paint_ms = (time.perf_counter() - self._started) * 1000
            watched.removeEventFilter(self)
            if self._on_paint is not None:
                self._on_paint()
        return False


class TabOpenProfiler:
    """Time the phases of opening one tab, first paint included.

    Usage mirrors the shape of the code it measures::

        profiler = TabOpenProfiler("Ring Player Stats")
        profiler.watch_ui_stalls()
        with profiler.phase("import"):
            from fpdb_3_legacy import GuiRingPlayerStats
        with profiler.phase("construct"):
            page = GuiRingPlayerStats.GuiRingPlayerStats(...)
        profiler.watch_first_paint(page)
        with profiler.phase("add_tab"):
            self.add_and_display_tab(page, "Ring Player Stats")
        profiler.report_when_painted(log)

    The last call is :meth:`report_when_painted`, not :meth:`report`. An
    earlier version of this docstring ended in ``profiler.report(log)``, and
    every caller copied it -- which guaranteed that ``first_paint_ms`` was
    still ``None`` when the line was written, because the event loop had not
    run yet. :meth:`report` remains for tests that pump the loop themselves.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._started = time.perf_counter()
        self._timing = TabTiming(name=name)
        self._paint_watcher: _FirstPaintWatcher | None = None
        self._pending_log: logging.Logger | None = None
        self._stall_monitor: UiStallMonitor | None = None
        self._timeout_timer: QTimer | None = None

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
        self._paint_watcher = _FirstPaintWatcher(
            self._started,
            parent=widget,
            on_paint=self._on_first_paint,
        )
        widget.installEventFilter(self._paint_watcher)

    def watch_ui_stalls(self, interval_ms: int = DEFAULT_HEARTBEAT_MS) -> None:
        """Measure how long the event loop is unable to run during this open.

        The lateness of a timer is the only figure that matches what "frozen"
        means to a user, and it needs no cooperation from the code doing the
        freezing. Folded into the same line so one grep answers both questions.
        """
        self._stall_monitor = UiStallMonitor(interval_ms=interval_ms)
        self._stall_monitor.start()

    def _on_first_paint(self) -> None:
        """Emit the deferred report, if one is pending."""
        if self._pending_log is not None:
            self._emit_pending()

    def _emit_pending(self) -> None:
        """Log the deferred line exactly once."""
        log = self._pending_log
        if log is None:
            return
        self._pending_log = None
        self.report(log)

    def report_when_painted(self, log: logging.Logger, timeout_ms: int = FIRST_PAINT_TIMEOUT_MS) -> None:
        """Log the timing once the tab has actually been drawn.

        :meth:`report` called inline cannot see a paint: Qt delivers no Paint
        event until control returns to the event loop, and the caller is still
        on the stack. Every production line therefore read ``not-painted`` and
        stopped timing before the span the user waits through -- the exact
        interval this class exists to measure. Reporting is deferred to the
        paint instead, with ``timeout_ms`` as a backstop so a widget that never
        paints still produces one line (and ``not-painted`` then means it).
        """
        self._pending_log = log
        if self._paint_watcher is not None and self._paint_watcher.first_paint_ms is not None:
            self._emit_pending()
            return

        if self._paint_watcher is None:
            QTimer.singleShot(timeout_ms, self._emit_pending)
            return

        # Parented to the watcher, itself parented to the widget, so the
        # backstop dies with the tab. A free-standing QTimer.singleShot outlives
        # it and fires into a deleted widget when a tab is closed before it has
        # painted -- which crashed the interpreter rather than logging a line.
        self._timeout_timer = QTimer(self._paint_watcher)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._emit_pending)
        self._timeout_timer.start(timeout_ms)

    def result(self) -> TabTiming:
        """Return the timing collected so far."""
        # The watcher is parented to the widget, so a tab closed before it
        # painted leaves a wrapper around a deleted C++ object. Reading through
        # it then raises RuntimeError, and the timing is simply "never painted".
        try:
            self._timing.first_paint_ms = None if self._paint_watcher is None else self._paint_watcher.first_paint_ms
        except RuntimeError:
            self._timing.first_paint_ms = None
        self._timing.total_ms = (time.perf_counter() - self._started) * 1000
        if self._stall_monitor is not None:
            self._stall_monitor.stop()
            self._timing.max_stall_ms = self._stall_monitor.max_stall_ms
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
