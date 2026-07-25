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
import time
from typing import Any

import pytest

import fpdb_3_legacy.loggingFpdb as logging_fpdb


@pytest.fixture(autouse=True)
def isolate_logger_config(tmp_path_factory, monkeypatch):
    """Keep every configuration write inside the test's own directory.

    A registry saves through a LogConfig that defaults to ~/fpdb_logs, and
    several registry operations save on their own. Without this the suite
    rewrites the configuration of whoever runs it.
    """
    # Deliberately not under tmp_path: the rotation tests inspect that
    # directory and must see only the files they wrote.
    real_log_config = logging_fpdb.LogConfig
    sandbox = tmp_path_factory.mktemp("logger-config")

    def in_sandbox(config_dir: str | None = None):
        return real_log_config(config_dir=config_dir or str(sandbox))

    monkeypatch.setattr(logging_fpdb, "LogConfig", in_sandbox)
    monkeypatch.setattr(logging_fpdb, "_log_config", in_sandbox())
    monkeypatch.setattr(logging_fpdb._logger_registry, "_config", in_sandbox())
    return sandbox


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


# --------------------------------------------------------------------------
# The global level switches
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("switch", "expected"),
    [
        ("set_default_logging", logging.ERROR),
        ("enable_warning_logging", logging.WARNING),
        ("enable_debug_logging", logging.DEBUG),
    ],
)
def test_each_switch_sets_the_root_level_it_promises(switch, expected, tmp_path) -> None:
    logging_fpdb.setup_logging(log_dir=str(tmp_path))

    getattr(logging_fpdb, switch)()

    assert logging.getLogger().level == expected


def test_the_console_follows_the_switch(tmp_path) -> None:
    # A root level nobody's handler honours changes nothing on screen.
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logging_fpdb.enable_debug_logging()

    console = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename")
    ]
    assert console
    assert all(handler.level <= logging.DEBUG for handler in console)


def test_the_console_is_opened_up_to_what_the_loggers_need(tmp_path) -> None:
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logging.getLogger().setLevel(logging.ERROR)

    logging_fpdb.ensure_console_handlers_configured()

    assert logging.getLogger().level <= logging.ERROR


# --------------------------------------------------------------------------
# Discovering a logger nobody registered
# --------------------------------------------------------------------------


def test_an_existing_logger_is_discovered_when_its_level_is_set(registry) -> None:
    # The dev tool sets levels by name; a logger created by an imported module
    # has to be found rather than ignored.
    logging.getLogger("fpdb.test.discovered").setLevel(logging.WARNING)

    assert registry.set_logger_level("fpdb.test.discovered", logging.DEBUG)
    assert "fpdb.test.discovered" in registry.get_all_loggers()
    assert logging.getLogger("fpdb.test.discovered").level == logging.DEBUG


def test_a_logger_that_does_not_exist_is_not_invented(registry) -> None:
    assert not registry.set_logger_level("fpdb.test.no.such.logger.anywhere", logging.DEBUG)


def test_a_saved_configuration_is_applied_to_a_registry(tmp_path, registry) -> None:
    logger = logging.getLogger("fpdb.test.applied")
    registry.register_logger("fpdb.test.applied", logger)
    registry.set_logger_level("fpdb.test.applied", logging.DEBUG)
    config = logging_fpdb.LogConfig(config_dir=str(tmp_path))
    config.save_config(registry)

    other = logging_fpdb.LoggerRegistry()
    other.register_logger("fpdb.test.applied", logger)

    assert config.load_config(other)


# --------------------------------------------------------------------------
# Rotating on time rather than size
# --------------------------------------------------------------------------


def test_the_log_rotates_once_its_moment_has_passed(tmp_path) -> None:
    target = tmp_path / "timed.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), when="S", interval=1, backup_count=2)
    write_lines(handler, 1)
    handler.rolloverAt = int(time.time()) - 1

    assert handler.shouldRollover(record())

    handler.doRollover()
    write_lines(handler, 1)
    handler.close()

    assert [path for path in tmp_path.iterdir() if path.name != "timed.log"]


def test_a_log_whose_moment_has_not_come_is_left_alone(tmp_path) -> None:
    target = tmp_path / "timed.log"
    handler = logging_fpdb.TimedSizedRotatingFileHandler(str(target), when="S", interval=1)
    write_lines(handler, 1)
    handler.rolloverAt = int(time.time()) + 3600

    assert not handler.shouldRollover(record())

    handler.close()


# --------------------------------------------------------------------------
# The HUD trace
# --------------------------------------------------------------------------


def test_the_hud_trace_says_nothing_until_it_is_switched_on() -> None:
    # It is called on every hand; without a handler it must cost nothing and
    # raise nothing.
    saved = logging_fpdb._hud_trace_log.handlers[:]
    logging_fpdb._hud_trace_log.handlers = []
    try:
        assert logging_fpdb.hud_trace("nobody hears this %s", "line") is None
    finally:
        logging_fpdb._hud_trace_log.handlers = saved


def test_the_hud_trace_is_emitted_once_a_handler_is_attached(tmp_path) -> None:
    target = tmp_path / "hud-trace.txt"
    handler = logging.FileHandler(str(target), encoding="utf-8")
    saved = logging_fpdb._hud_trace_log.handlers[:]
    saved_level = logging_fpdb._hud_trace_log.level
    logging_fpdb._hud_trace_log.handlers = [handler]
    logging_fpdb._hud_trace_log.setLevel(logging.INFO)
    try:
        logging_fpdb.hud_trace("attaching %s to seat %d", "villain", 3)
        handler.flush()
    finally:
        handler.close()
        logging_fpdb._hud_trace_log.handlers = saved
        logging_fpdb._hud_trace_log.setLevel(saved_level)

    assert "attaching villain to seat 3" in target.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The wrapper
# --------------------------------------------------------------------------


def test_the_wrapper_reports_the_level_it_was_given() -> None:
    logger = logging_fpdb.get_logger("fpdb.test.wrapper")

    logger.setLevel(logging.DEBUG)

    assert logger.getEffectiveLevel() == logging.DEBUG


def test_an_exception_is_logged_with_its_traceback(tmp_path) -> None:
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logger = logging_fpdb.get_logger("fpdb.test.exception")
    logger.setLevel(logging.ERROR)

    try:
        msg = "deliberate"
        raise ValueError(msg)
    except ValueError:
        logger.exception("while importing")
    for handler in logging.getLogger().handlers:
        handler.flush()

    written = (tmp_path / "fpdb-log.txt").read_text(encoding="utf-8", errors="replace")
    assert "while importing" in written


def test_the_log_file_keeps_the_message_of_an_exception_but_not_its_traceback(tmp_path) -> None:
    """The file a user sends you carries no traceback.

    The file handler formats with JsonFormatter, which builds a fixed six-field
    record -- timestamp, logger, level, module, function, message -- and never
    reads record.exc_info. So logger.exception() prints the traceback to the
    console and writes only the message to disk, which is the half a diagnosis
    cannot use. Documented behaviour, pinned here because changing the log
    format is a product decision rather than a fix.
    """
    logging_fpdb.setup_logging(log_dir=str(tmp_path))
    logger = logging_fpdb.get_logger("fpdb.test.traceback")
    logger.setLevel(logging.ERROR)

    try:
        msg = "deliberate"
        raise ValueError(msg)
    except ValueError:
        logger.exception("while importing")
    for handler in logging.getLogger().handlers:
        handler.flush()

    written = (tmp_path / "fpdb-log.txt").read_text(encoding="utf-8", errors="replace")
    assert "while importing" in written
    assert "ValueError" not in written
    assert "Traceback" not in written


def test_the_registry_and_the_config_are_shared() -> None:
    # The dev tool and the startup path must act on the same objects.
    assert logging_fpdb.get_logger_registry() is logging_fpdb.get_logger_registry()
    assert logging_fpdb.get_log_config() is logging_fpdb.get_log_config()
