"""The tab-open profiler must report the interval a user actually waits.

Issue #249: ``report()`` was called inline, on the line after the tab was
added, so Qt had not yet delivered a single Paint event. Every production
line read ``not-painted`` and stopped timing at the tab bar. The instrument
built to catch a slow tab could not observe one -- and it still answered,
which is worse than staying silent.

These tests pin the two properties that were violated: a report waits for the
paint, and it is emitted exactly once whether or not the paint arrives.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from fpdb_3_legacy.ui_instrumentation import TabOpenProfiler

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _tab_methods() -> list[ast.FunctionDef]:
    """Every method of ``fpdb`` that opens a tab."""
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    return [node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name.startswith("tab")]


def _calls(method: ast.FunctionDef, attr: str) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
        for node in ast.walk(method)
    )


def test_every_tab_is_instrumented() -> None:
    """Lead 4 of #249: only 3 of ~12 tabs carried a profiler.

    A tab that opens without going through ``open_tab`` produces no timing at
    all, so if the lag were on that tab the log would be silent by
    construction. Opening a tab and measuring it are now the same call.
    """
    unmeasured = [
        method.name
        for method in _tab_methods()
        if _calls(method, "add_and_display_tab") and not _calls(method, "open_tab")
    ]

    assert unmeasured == [], f"ces onglets s'ouvrent sans être mesurés : {unmeasured}"


def test_no_tab_reports_inline() -> None:
    """An inline report() is the #249 defect; open_tab defers to the paint."""
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    offenders = [
        node.name
        for node in fpdb_class.body
        if isinstance(node, ast.FunctionDef) and _calls(node, "report") and node.name != "open_tab"
    ]

    assert offenders == []


class _RecordingLogger(logging.Logger):
    """Captures the formatted [PERF] lines instead of emitting them."""

    def __init__(self) -> None:
        super().__init__("test-tab-open")
        self.lines: list[str] = []

    def warning(self, msg, *args, **kwargs) -> None:  # noqa: A002 - mirrors logging API
        self.lines.append(msg % args if args else msg)


def test_reporting_inline_cannot_see_the_paint(qtbot) -> None:
    """The regression itself, stated as a test.

    This is what every production call site did. It is kept as a test so the
    difference with report_when_painted is visible rather than asserted.
    """
    widget = QWidget()
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()

    # No event-loop turn between show() and report(): exactly the old shape.
    timing = profiler.result()

    assert timing.first_paint_ms is None
    assert "not-painted" in timing.format()


def test_report_when_painted_waits_for_the_first_paint(qtbot) -> None:
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert len(log.lines) == 1
    assert "first_paint=" in log.lines[0]
    assert "not-painted" not in log.lines[0]


def test_a_widget_that_never_paints_still_reports_once(qtbot) -> None:
    """The backstop: a tab that never draws is the symptom, not a reason to go quiet."""
    log = _RecordingLogger()
    widget = QWidget()  # jamais show(), donc jamais peint
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    profiler.report_when_painted(log, timeout_ms=50)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert len(log.lines) == 1
    assert "not-painted" in log.lines[0]


def test_the_report_is_not_emitted_twice(qtbot) -> None:
    """Paint and timeout can both fire; only one line may be written."""
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log, timeout_ms=10)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)
    qtbot.wait(120)  # laisse le backstop expirer après le paint

    assert len(log.lines) == 1


def test_stall_monitor_is_folded_into_the_same_line(qtbot) -> None:
    """Lead 2 of #249: the stall figure was only ever produced inside tests."""
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_ui_stalls(interval_ms=10)
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert "max_stall=" in log.lines[0]


@pytest.mark.parametrize("with_monitor", [False, True])
def test_format_stays_greppable(qtbot, with_monitor: bool) -> None:
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Ring Player Stats")
    if with_monitor:
        profiler.watch_ui_stalls(interval_ms=10)
    with profiler.phase("construct"):
        pass
    profiler.watch_first_paint(widget)
    widget.show()
    qtbot.waitUntil(lambda: profiler.result().first_paint_ms is not None, timeout=5000)

    line = profiler.result().format()

    assert line.startswith("tab='Ring Player Stats'")
    assert "construct=" in line
    assert "total=" in line
    assert ("max_stall=" in line) is with_monitor
