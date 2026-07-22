"""Diagnostic-logging guarantees: WARNING+ must always reach the log files.

Covers the three failure modes that left HUD bugs undiagnosable:
- registry levels above WARNING silently suppressed diagnostics,
- a locked log file (two fpdb processes) killed the rotating handler forever,
- module loggers (win_tables, table_window, ...) never reached a file handler.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from fpdb_3_legacy.loggingFpdb import (
    DIAGNOSTIC_LEVEL_CAP,
    LoggerRegistry,
    TimedSizedRotatingFileHandler,
    cap_logger_level,
    get_logger,
)


def _unique_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    return logger


class TestLevelCap:
    def test_levels_above_warning_are_capped(self) -> None:
        assert cap_logger_level(logging.ERROR) == DIAGNOSTIC_LEVEL_CAP
        assert cap_logger_level(logging.CRITICAL) == DIAGNOSTIC_LEVEL_CAP

    def test_verbose_levels_are_untouched(self) -> None:
        assert cap_logger_level(logging.DEBUG) == logging.DEBUG
        assert cap_logger_level(logging.INFO) == logging.INFO
        assert cap_logger_level(logging.WARNING) == logging.WARNING
        assert cap_logger_level(logging.NOTSET) == logging.NOTSET

    def test_register_logger_caps_saved_error_level(self) -> None:
        registry = LoggerRegistry()
        registry._saved_config = {"cap_test_saved": {"level": logging.ERROR, "enabled": True}}
        logger = _unique_logger("cap_test_saved")

        registry.register_logger("cap_test_saved", logger)

        assert logger.level == DIAGNOSTIC_LEVEL_CAP
        assert registry.get_logger_info("cap_test_saved").current_level == DIAGNOSTIC_LEVEL_CAP

    def test_get_logger_never_returns_logger_quieter_than_warning(self) -> None:
        logger = _unique_logger("cap_test_get")
        logger.setLevel(logging.CRITICAL)

        fpdb_logger = get_logger("cap_test_get")

        assert fpdb_logger.getEffectiveLevel() <= DIAGNOSTIC_LEVEL_CAP


class TestModuleWarningsReachRootHandler:
    def test_warning_from_fresh_module_logger_propagates_to_root_file_handler(self, tmp_path: Path) -> None:
        """A logger like "win_tables" must reach a root-attached handler."""
        records: list[logging.LogRecord] = []

        class Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        root = logging.getLogger()
        collector = Collector(level=logging.WARNING)
        old_root_level = root.level
        root.addHandler(collector)
        if root.level > logging.WARNING:
            root.setLevel(logging.WARNING)
        try:
            log = get_logger("cap_test_propagation")
            log.warning("Currently open windows: %s", ["Table A"])
        finally:
            root.removeHandler(collector)
            root.setLevel(old_root_level)

        assert any("Currently open windows" in r.getMessage() for r in records)


class TestRolloverResilience:
    def _handler(self, tmp_path: Path) -> TimedSizedRotatingFileHandler:
        handler = TimedSizedRotatingFileHandler(
            str(tmp_path / "fpdb-log.txt"),
            when="midnight",
            backup_count=3,
            encoding="utf-8",
            max_bytes=0,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def _record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord("rollover_test", logging.WARNING, __file__, 1, msg, None, None)

    def test_locked_file_does_not_kill_logging(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failed rename (file held by the other fpdb process) must not raise,
        must keep writing to the current file, and must reschedule the rollover
        instead of retrying it on every emit."""
        handler = self._handler(tmp_path)
        handler.emit(self._record("before rollover"))

        handler.rolloverAt = 0  # force a time-based rollover on next emit
        monkeypatch.setattr("os.rename", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("locked")))
        monkeypatch.setattr(logging, "raiseExceptions", False)

        handler.emit(self._record("during locked rollover"))
        handler.emit(self._record("after locked rollover"))
        handler.close()

        content = (tmp_path / "fpdb-log.txt").read_text(encoding="utf-8")
        assert "during locked rollover" in content
        assert "after locked rollover" in content
        assert handler.rolloverAt > time.time() - 1  # rescheduled in the future

    def test_successful_rollover_still_rotates(self, tmp_path: Path) -> None:
        handler = self._handler(tmp_path)
        handler.emit(self._record("old line"))

        handler.rolloverAt = 0
        handler.emit(self._record("new line"))
        handler.close()

        rotated = list(tmp_path.glob("fpdb-log.txt-*-part1.txt"))
        assert len(rotated) == 1
        assert "old line" in rotated[0].read_text(encoding="utf-8")
        assert "new line" in (tmp_path / "fpdb-log.txt").read_text(encoding="utf-8")
