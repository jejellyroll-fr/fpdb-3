"""The instruments themselves have to be trustworthy.

A stall monitor that never reports a stall would make the three-tab
regression test pass forever without measuring anything, so what is checked
here is that it sees a block that is really there and stays quiet when there
is none.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    """A blocked event loop must be reported, with roughly the right size."""
    from PySide6.QtCore import QTimer

    monitor = UiStallMonitor()
    monitor.start()
    QTimer.singleShot(100, lambda: time.sleep(0.4))
    qtbot.wait(800)
    monitor.stop()

    assert monitor.max_stall_ms >= 300
    assert monitor.stalls_over(UI_STALL_BUDGET_MS)


def test_stall_monitor_stays_quiet_on_an_idle_loop(qtbot) -> None:
    """An idle loop must not be reported as frozen.

    Without this the three-tab budget could be met by an instrument that
    reports nothing, or missed by one that reports noise.
    """
    monitor = UiStallMonitor()
    monitor.start()
    qtbot.wait(500)
    monitor.stop()

    assert monitor.ticks > 0
    assert not monitor.stalls_over(UI_STALL_BUDGET_MS), f"idle loop reported stalls: {monitor.stalls}"


def test_a_stopped_monitor_keeps_what_it_measured(qtbot) -> None:
    """Stopping ends the measurement; it does not discard it."""
    monitor = UiStallMonitor()
    monitor.start()
    qtbot.wait(200)
    monitor.stop()
    ticks = monitor.ticks
    qtbot.wait(200)

    assert monitor.ticks == ticks
