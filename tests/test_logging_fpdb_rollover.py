from __future__ import annotations

import logging

from fpdb_3_legacy.loggingFpdb import TimedSizedRotatingFileHandler, set_default_logging


def test_set_default_logging_accepts_non_stream_handler() -> None:
    root = logging.getLogger()
    handler = logging.NullHandler()
    original_level = root.level
    root.addHandler(handler)
    try:
        set_default_logging()
        assert root.level == logging.ERROR
    finally:
        root.removeHandler(handler)
        root.setLevel(original_level)


def test_size_rollover_opens_delayed_stream(tmp_path) -> None:
    log_path = tmp_path / "fpdb.log"
    handler = TimedSizedRotatingFileHandler(str(log_path), delay=True, max_bytes=1)
    try:
        assert handler.stream is None
        assert handler.shouldRollover(logging.makeLogRecord({})) is False
        assert handler.stream is not None
    finally:
        handler.close()
