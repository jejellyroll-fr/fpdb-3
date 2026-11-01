"""A [PERF] line must be a WARNING only when it reports something slow.

Every one of these lines was a WARNING, because the root logger is pinned there
(``loggingFpdb.DIAGNOSTIC_LEVEL_CAP``) and a slow tab has to reach a log that is
not running at DEBUG. True for a slow tab -- and applied to every tab. A user
sent in a log viewer holding eleven WARNING lines, all of them [PERF], the
slowest tab 528 ms and six of them under 60 ms, with the actual problem nowhere
in sight. An instrument that reports "nothing is wrong" at WARNING costs the
reader the warnings that mean something.
"""

from __future__ import annotations

import logging

import pytest

# No sys.path.insert of the repo root: pytest.ini already sets `pythonpath = .`,
# so the inserts the older test modules carry are redundant here.
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ui_instrumentation import (
    SLOW_TAB_OPEN_MS,
    UI_STALL_BUDGET_MS,
    TabOpenProfiler,
    perf_level,
)


def test_a_fast_tab_open_is_not_a_warning() -> None:
    """The lines that flooded the viewer: 5 ms, nothing stalled."""
    assert perf_level(5.0, 0.0) == logging.DEBUG


def test_a_slow_tab_open_is_still_a_warning() -> None:
    """The case the WARNING exists for must survive this change."""
    assert perf_level(SLOW_TAB_OPEN_MS + 1, 0.0) == logging.WARNING


def test_a_frozen_event_loop_is_a_warning_even_when_the_total_is_not() -> None:
    """max_stall is what "frozen" means to a user; a short total does not excuse it."""
    assert perf_level(200.0, UI_STALL_BUDGET_MS + 1) == logging.WARNING


def test_an_unmeasured_stall_does_not_promote_a_fast_open() -> None:
    """max_stall is None when no monitor ran -- absence of a figure is not a stall."""
    assert perf_level(5.0) == logging.DEBUG


@pytest.mark.parametrize(
    ("total_ms", "stall_ms"),
    [(SLOW_TAB_OPEN_MS, 0.0), (0.0, UI_STALL_BUDGET_MS)],
)
def test_the_thresholds_are_inclusive(total_ms: float, stall_ms: float) -> None:
    assert perf_level(total_ms, stall_ms) == logging.WARNING


def _report_record(monkeypatch, total_ms: float) -> logging.LogRecord:
    """Run TabOpenProfiler.report against a captured logger."""
    profiler = TabOpenProfiler("Help")
    records: list[logging.LogRecord] = []

    class Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    log = logging.getLogger("test_perf_log_levels")
    log.handlers = [Recorder()]
    log.setLevel(logging.DEBUG)
    log.propagate = False

    monkeypatch.setattr(
        profiler,
        "result",
        lambda: profiler._timing.__class__(name="Help", total_ms=total_ms),
    )
    profiler.report(log)
    assert len(records) == 1
    return records[0]


def test_report_logs_a_fast_open_at_debug(monkeypatch) -> None:
    record = _report_record(monkeypatch, 5.0)
    assert record.levelno == logging.DEBUG
    assert "[PERF] tab open" in record.getMessage()


def test_report_logs_a_slow_open_at_warning(monkeypatch) -> None:
    record = _report_record(monkeypatch, SLOW_TAB_OPEN_MS + 500)
    assert record.levelno == logging.WARNING
    assert "[PERF] tab open" in record.getMessage()


def _record_via(logger, handler_target, total_ms: float) -> logging.LogRecord:
    """Drive TabOpenProfiler.report through `logger`, return the record it emitted."""
    records: list[logging.LogRecord] = []

    class Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler_target.handlers = [Recorder()]
    handler_target.setLevel(logging.DEBUG)
    handler_target.propagate = False

    profiler = TabOpenProfiler("Help")
    profiler._started -= total_ms / 1000
    profiler.report(logger)

    assert len(records) == 1
    return records[0]


def test_report_works_against_the_logger_the_application_uses() -> None:
    """The production logger is a wrapper, not a logging.Logger.

    get_logger() returns FpdbLogger, which mirrors logging.Logger's per-level
    methods. Reporting at a level chosen at runtime needs the variable-level
    form, and the wrapper had none -- so the first version of this change raised
    AttributeError on every tab open in the real application while every test
    here passed, because they all handed report() a standard logging.Logger.
    Reported by Codex on the pull request.
    """
    logger = get_logger("test_perf_log_levels_wrapper_fast")
    record = _record_via(logger, logger.logger, total_ms=5)

    assert record.levelno == logging.DEBUG
    assert "[PERF] tab open" in record.getMessage()


def test_the_wrapper_reports_a_slow_open_at_warning() -> None:
    logger = get_logger("test_perf_log_levels_wrapper_slow")
    record = _record_via(logger, logger.logger, total_ms=SLOW_TAB_OPEN_MS + 500)

    assert record.levelno == logging.WARNING


def test_the_wrapper_still_credits_the_caller_with_the_line() -> None:
    """_get_stacklevel has to know about log(), or every record points at the wrapper."""
    logger = get_logger("test_perf_log_levels_wrapper_stack")
    record = _record_via(logger, logger.logger, total_ms=5)

    assert record.funcName != "log"
    assert record.filename != "loggingFpdb.py"
