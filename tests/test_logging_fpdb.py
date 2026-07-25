"""Logging: the rotating file, the registry, and the levels.

When the HUD stopped producing traces, the log file was the first thing that
had to be trusted and could not be. This module covers the parts that decide
whether a message reaches a file at all: the handler that rotates it, the
setup that installs it, and the registry that raises or lowers levels.

Every test that touches global logging state restores it, so the rest of the
suite is unaffected.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

import fpdb_3_legacy.loggingFpdb as logging_fpdb


@pytest.fixture(autouse=True)
def preserve_global_logging():
    """Snapshot and restore the logging state these tests necessarily mutate."""
    root = logging.getLogger()
    saved_handlers, saved_level, saved_disable = root.handlers[:], root.level, logging.root.manager.disable
    saved_levels = {name: lg.level for name, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    yield
    for handler in root.handlers[:]:
        if handler not in saved_handlers:
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    logging.disable(saved_disable)
    for name, level in saved_levels.items():
        existing = logging.root.manager.loggerDict.get(name)
        if isinstance(existing, logging.Logger):
            existing.setLevel(level)


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("asked", "applied"),
    [(logging.DEBUG, logging.DEBUG), (logging.INFO, logging.INFO), (99, logging.WARNING)],
)
def test_a_level_above_the_known_ones_is_capped(asked, applied) -> None:
    # An out-of-range level would otherwise silence a logger completely.
    assert logging_fpdb.cap_logger_level(asked) == applied


# --------------------------------------------------------------------------
# The rotating file handler
# --------------------------------------------------------------------------


def write_lines(handler: Any, count: int, size: int = 40) -> None:
    logger = logging.getLogger("fpdb.test.rotation")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for index in range(count):
        logger.info("%s %d", "x" * size, index)


def test_the_log_rotates_once_it_passes_its_size_limit(tmp_path) -> None:
    target = tmp_path / "fpdb.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), max_bytes=200, backup_count=5)

    write_lines(handler, 20)
    handler.close()

    rotated = [path for path in tmp_path.iterdir() if path.name != "fpdb.log"]
    assert rotated, "nothing rotated despite passing max_bytes"
    assert target.exists()


def test_no_more_backups_are_kept_than_asked_for(tmp_path) -> None:
    # Unbounded rotation fills a player's disk; that is why backup_count exists.
    target = tmp_path / "fpdb.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), max_bytes=200, backup_count=3)

    write_lines(handler, 60)
    handler.close()

    backups = [path for path in tmp_path.iterdir() if path.name != "fpdb.log"]
    assert len(backups) <= 3


def test_a_log_under_its_limit_is_not_rotated(tmp_path) -> None:
    target = tmp_path / "fpdb.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), max_bytes=100_000, backup_count=3)

    write_lines(handler, 5)
    handler.close()

    assert [path.name for path in tmp_path.iterdir()] == ["fpdb.log"]


def test_a_record_is_written_to_the_file(tmp_path) -> None:
    target = tmp_path / "fpdb.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), max_bytes=100_000)

    write_lines(handler, 1)
    handler.close()

    assert "xxxx" in target.read_text(encoding="utf-8", errors="replace")


def test_nothing_is_scheduled_for_deletion_once_the_backups_fit(tmp_path) -> None:
    target = tmp_path / "fpdb.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), max_bytes=200, backup_count=5)

    write_lines(handler, 20)
    surplus = handler.getFilesToDelete()
    handler.close()

    assert surplus == []


# --------------------------------------------------------------------------
# Setting logging up
# --------------------------------------------------------------------------


def test_setting_up_logging_creates_the_log_file(tmp_path) -> None:
    logging_fpdb.setup_logging(log_dir=str(tmp_path))

    assert (tmp_path / "fpdb-log.txt").exists()


def test_a_message_reaches_the_log_file(tmp_path) -> None:
    # The symptom that started this: a silent log file.
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logger = logging_fpdb.get_logger("fpdb.test.file")
    logger.setLevel(logging.INFO)

    logger.info("a message that must be written")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "a message that must be written" in (tmp_path / "fpdb-log.txt").read_text(
        encoding="utf-8", errors="replace"
    )


def test_a_new_logger_inherits_warning_and_drops_its_info(tmp_path) -> None:
    """Why a log can look dead while everything works.

    setup_logging puts the `fpdb` logger at WARNING, so any `fpdb.*` logger
    created afterwards inherits it: its info() goes nowhere until something
    sets a level on it. Worth pinning, because the file is then empty and the
    handler looks broken when it is not.
    """
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logger = logging_fpdb.get_logger("fpdb.test.inherited")

    assert logging.getLogger("fpdb").level == logging.WARNING
    assert logging.getLogger("fpdb.test.inherited").getEffectiveLevel() == logging.WARNING

    logger.info("this one is dropped")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "this one is dropped" not in (tmp_path / "fpdb-log.txt").read_text(encoding="utf-8", errors="replace")


def test_the_logger_returned_is_the_fpdb_wrapper() -> None:
    assert isinstance(logging_fpdb.get_logger("fpdb.test.kind"), logging_fpdb.FpdbLogger)


@pytest.mark.parametrize("method", ["debug", "info", "warning", "error"])
def test_every_level_of_the_wrapper_reaches_the_handler(method, tmp_path) -> None:
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logger = logging_fpdb.get_logger("fpdb.test.levels")
    logger.setLevel(logging.DEBUG)

    getattr(logger, method)(f"message via {method}")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert logger.getEffectiveLevel() <= logging.DEBUG


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------


@pytest.fixture
def registry() -> Any:
    return logging_fpdb.LoggerRegistry()


def test_a_registered_logger_is_listed(registry) -> None:
    registry.register_logger("fpdb.test.one", logging.getLogger("fpdb.test.one"))

    assert "fpdb.test.one" in registry.get_all_loggers()


def test_setting_a_level_reaches_the_underlying_logger(registry) -> None:
    logger = logging.getLogger("fpdb.test.level")
    registry.register_logger("fpdb.test.level", logger)

    assert registry.set_logger_level("fpdb.test.level", logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_disabling_a_logger_puts_it_back_to_inheriting(registry) -> None:
    # "Disabled" here means NOTSET -- the logger inherits again rather than
    # being silenced outright, which is what the registry documents.
    logger = logging.getLogger("fpdb.test.enable")
    registry.register_logger("fpdb.test.enable", logger)
    registry.set_logger_level("fpdb.test.enable", logging.DEBUG)

    assert registry.enable_logger("fpdb.test.enable", enable=False)
    assert logger.level == logging.NOTSET
    assert registry.get_logger_info("fpdb.test.enable").enabled is False


def test_re_enabling_restores_a_usable_level(registry) -> None:
    logger = logging.getLogger("fpdb.test.reenable")
    registry.register_logger("fpdb.test.reenable", logger)
    registry.enable_logger("fpdb.test.reenable", enable=False)

    registry.enable_logger("fpdb.test.reenable", enable=True)

    assert logger.level != logging.NOTSET


def test_an_unknown_logger_has_no_information(registry) -> None:
    assert registry.get_logger_info("fpdb.test.never.registered") is None


def test_loggers_can_be_filtered_by_name(registry) -> None:
    registry.register_logger("fpdb.test.alpha", logging.getLogger("fpdb.test.alpha"))
    registry.register_logger("fpdb.test.beta", logging.getLogger("fpdb.test.beta"))

    assert list(registry.filter_loggers("alpha")) == ["fpdb.test.alpha"]


# --------------------------------------------------------------------------
# Saving and restoring the configuration
# --------------------------------------------------------------------------


def test_a_saved_configuration_can_be_read_back(tmp_path, registry) -> None:
    registry.register_logger("fpdb.test.saved", logging.getLogger("fpdb.test.saved"))
    config = logging_fpdb.LogConfig(config_dir=str(tmp_path))

    assert config.save_config(registry)

    data = config.load_config_data()
    assert "loggers" in data
    assert "fpdb.test.saved" in data["loggers"]


def test_an_exported_configuration_is_readable_json(tmp_path, registry) -> None:
    registry.register_logger("fpdb.test.exported", logging.getLogger("fpdb.test.exported"))
    config = logging_fpdb.LogConfig(config_dir=str(tmp_path))
    target = tmp_path / "export.json"

    assert config.export_config(registry, str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "fpdb.test.exported" in data["loggers"]


def test_an_exported_configuration_can_be_imported_again(tmp_path, registry) -> None:
    logger = logging.getLogger("fpdb.test.roundtrip")
    registry.register_logger("fpdb.test.roundtrip", logger)
    registry.set_logger_level("fpdb.test.roundtrip", logging.DEBUG)
    config = logging_fpdb.LogConfig(config_dir=str(tmp_path))
    target = tmp_path / "export.json"
    config.export_config(registry, str(target))

    other = logging_fpdb.LoggerRegistry()
    other.register_logger("fpdb.test.roundtrip", logger)

    assert config.import_config(other, str(target))


def test_importing_a_file_that_is_not_there_fails_quietly(tmp_path, registry) -> None:
    config = logging_fpdb.LogConfig(config_dir=str(tmp_path))

    assert not config.import_config(registry, str(tmp_path / "absent.json"))


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def record(message: str = "a message", level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord("fpdb.test", level, "module.py", 42, message, None, None)


def test_the_console_format_carries_the_level_and_the_message() -> None:
    formatted = logging_fpdb.FpdbLogFormatter().format(record("something happened"))

    assert "INFO" in formatted
    assert "something happened" in formatted


def test_the_console_format_highlights_a_quoted_value() -> None:
    plain = logging_fpdb.FpdbLogFormatter().format(record("nothing quoted here"))
    quoted = logging_fpdb.FpdbLogFormatter().format(record("value is 'quoted'"))

    assert quoted.count("\x1b[") > plain.count("\x1b[")


def test_the_json_format_names_its_fields() -> None:
    payload = json.loads(logging_fpdb.JsonFormatter().format(record("structured")))

    assert payload["message"] == "structured"
    assert payload["levelname"] == "INFO"
    assert payload["name"] == "fpdb.test"
    assert set(payload) >= {"asctime", "funcName", "module"}
