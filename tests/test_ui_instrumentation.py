"""The instruments themselves have to be trustworthy.

A stall monitor that never reports a stall would make the three-tab
regression test pass forever without measuring anything, so what is checked
here is that it sees a block that is really there and stays quiet when there
is none.
"""

from __future__ import annotations

import time

import pytest

from fpdb_3_legacy.ui_instrumentation import (
    UI_STALL_BUDGET_MS,
    TabOpenProfiler,
    UiStallMonitor,
)

pytestmark = pytest.mark.qt


def test_profiler_records_each_phase_separately() -> None:
    """Phases are attributed to what actually took the time."""
    profiler = TabOpenProfiler("Session Stats")
    with profiler.phase("import"):
        time.sleep(0.05)
    with profiler.phase("construct"):
        pass

    timing = profiler.result()

    assert timing.phases["import"] >= 40
    assert timing.phases["construct"] < timing.phases["import"]
    assert timing.total_ms >= timing.phases["import"]


def test_profiler_times_a_phase_that_raises() -> None:
    """A tab that fails to open must still say where it got to."""
    profiler = TabOpenProfiler("Graphs")

    with pytest.raises(ValueError, match="boom"), profiler.phase("construct"):
        raise ValueError("boom")

    assert "construct" in profiler.result().phases


def test_profiler_reports_no_paint_when_nothing_was_watched() -> None:
    """A tab added but never painted is not silently reported as instant."""
    assert TabOpenProfiler("Graphs").result().first_paint_ms is None


def test_profiler_records_the_first_paint(qtbot) -> None:
    """First paint is the moment the user actually sees the tab."""
    from PySide6.QtWidgets import QLabel

    widget = QLabel("hello")
    qtbot.addWidget(widget)
    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.waitUntil(lambda: profiler.result().first_paint_ms is not None, timeout=5000)

    assert profiler.result().first_paint_ms is not None


def test_stall_monitor_measures_a_real_block(qtbot) -> None:
    """A blocked event loop must be reported, with roughly the right size.

    A lower bound only. This measures the event loop, so it measures the
    whole machine: load can only make a stall larger, never smaller, so
    asserting "at least 300ms" survives a busy runner. The upper bound is
    what does not -- an earlier version asserted an idle loop stayed under
    100 ms and a runner under coverage reported 557 ms on a loop doing
    nothing at all. That direction is pinned below without a clock.
    """
    from PySide6.QtCore import QTimer

    monitor = UiStallMonitor()
    monitor.start()
    QTimer.singleShot(100, lambda: time.sleep(0.4))
    qtbot.wait(800)
    monitor.stop()

    assert monitor.max_stall_ms >= 300
    assert monitor.stalls_over(UI_STALL_BUDGET_MS)


def test_an_idle_loop_is_not_reported_as_one_long_freeze() -> None:
    """No wall clock: the arithmetic alone, so a busy machine cannot skew it.

    Ticks that arrive when asked contribute nothing, which is what stops the
    three-tab budget being met by an instrument that reports noise.
    """
    monitor = UiStallMonitor()
    monitor._expected = time.perf_counter() + monitor._interval_ms / 1000

    for _ in range(5):
        monitor._expected = time.perf_counter()  # exactly on time
        monitor._on_tick()

    assert monitor.ticks == 5
    assert monitor.stalls_over(UI_STALL_BUDGET_MS) == ()


def test_a_stopped_monitor_keeps_what_it_measured(qtbot) -> None:
    """Stopping ends the measurement; it does not discard it."""
    monitor = UiStallMonitor()
    monitor.start()
    qtbot.wait(200)
    monitor.stop()
    ticks = monitor.ticks
    qtbot.wait(200)

    assert monitor.ticks == ticks
