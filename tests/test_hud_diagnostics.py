"""The launch banner has to answer the questions a bug report starts from.

Which build ran, as which process, from where, and as part of which launch.
Each of those was missing from the logs of the duplicate-overlay report, and
each absence turned a five-minute answer into a day of inference.
"""

from __future__ import annotations

import faulthandler
import logging
import multiprocessing
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy import hud_diagnostics
from fpdb_3_legacy.hud_diagnostics import (
    HUD_CRASH_LOG_NAME,
    MAIN_CRASH_LOG_NAME,
    ROLE_HUD,
    ROLE_MAIN,
    SESSION_ENV_VAR,
    bundle_path,
    enable_crash_log,
    format_identity,
    is_app_translocated,
    log_process_identity,
    process_identity,
    session_id,
)

TRANSLOCATED = (
    "/private/var/folders/aa/bb/T/AppTranslocation/1A2B3C4D-0000-0000-0000-000000000000/d/fpdb.app"
    "/Contents/MacOS/fpdb"
)


@pytest.fixture(autouse=True)
def _clean_session(monkeypatch):
    """Each test decides its own session, rather than inheriting the runner's."""
    monkeypatch.delenv(SESSION_ENV_VAR, raising=False)


def test_session_id_is_stable_within_a_process() -> None:
    """Every line of one launch must carry the same id."""
    assert session_id() == session_id()


def test_session_id_is_exported_so_children_share_it() -> None:
    """The HUD child belongs to its parent's launch, not to a launch of its own.

    Correlating the GUI and its HUD is the whole point: two processes with
    unrelated ids cannot be told from two separate launches.
    """
    generated = session_id()

    assert os.environ[SESSION_ENV_VAR] == generated


def test_an_inherited_session_is_not_replaced(monkeypatch) -> None:
    """A child must adopt the id it was given."""
    monkeypatch.setenv(SESSION_ENV_VAR, "abc123abc123")

    assert session_id() == "abc123abc123"


def test_identity_reports_every_field_a_report_needs() -> None:
    """The banner is only useful if nothing in it is missing."""
    identity = process_identity(ROLE_HUD)

    assert identity["role"] == ROLE_HUD
    assert identity["pid"] == os.getpid()
    assert identity["ppid"] == os.getppid()
    assert identity["session"]
    assert identity["version"] != "unknown"
    assert identity["executable"]
    assert isinstance(identity["translocated"], bool)
    assert identity["command"]


def test_identity_can_carry_the_command_that_started_the_process() -> None:
    """A frozen HUD's argv is known to its launcher, not to sys.argv."""
    identity = process_identity(ROLE_HUD, command=["/Applications/fpdb.app/Contents/MacOS/fpdb", "--hud"])

    assert identity["command"] == ["/Applications/fpdb.app/Contents/MacOS/fpdb", "--hud"]


def test_formatted_identity_is_one_greppable_line() -> None:
    """One line per launch, so splitting a log by session is a grep."""
    line = format_identity(process_identity(ROLE_MAIN))

    assert "\n" not in line
    assert "role='main'" in line
    assert "pid=" in line


def test_translocation_is_detected_from_the_mount_path() -> None:
    """The random AppTranslocation mount is the only visible sign of it."""
    assert is_app_translocated(TRANSLOCATED)
    assert not is_app_translocated("/Applications/fpdb.app/Contents/MacOS/fpdb")
    assert not is_app_translocated("/Users/someone/src/fpdb-3/.venv/bin/python")


def test_bundle_path_finds_the_enclosing_app() -> None:
    """The warning has to name the bundle the user must move.

    Compared as paths rather than as strings: this runs on Windows too, where
    pathlib renders the same location with backslashes. Asserting the POSIX
    spelling would fail there for no reason -- ``bundle_path`` is called on
    every platform, it simply never finds a ``.app`` outside macOS.
    """
    from pathlib import Path

    translocated = Path(bundle_path(TRANSLOCATED))
    assert translocated.name == "fpdb.app"
    assert translocated.parent.name == "d"
    assert Path(bundle_path("/Applications/fpdb.app/Contents/MacOS/fpdb")) == Path("/Applications/fpdb.app")
    assert bundle_path("/usr/local/bin/fpdb") is None


def test_banner_warns_about_translocation(monkeypatch, caplog) -> None:
    """A translocated launch must say so, and say what to do about it.

    Silence here is what makes the HUD look broken: the permissions are
    granted, the app still cannot read a window, and nothing connects the two.
    """
    monkeypatch.setattr(hud_diagnostics, "executable_path", lambda: TRANSLOCATED)
    log = logging.getLogger("test_hud_diagnostics")

    with caplog.at_level(logging.WARNING, logger=log.name):
        identity = log_process_identity(log, ROLE_MAIN)

    assert identity["translocated"] is True
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "App Translocation" in messages
    assert "/Applications" in messages


def test_banner_is_quiet_when_installed_properly(monkeypatch, caplog) -> None:
    """An ordinary launch gets the banner and no scare."""
    monkeypatch.setattr(hud_diagnostics, "executable_path", lambda: "/Applications/fpdb.app/Contents/MacOS/fpdb")
    log = logging.getLogger("test_hud_diagnostics")

    with caplog.at_level(logging.WARNING, logger=log.name):
        identity = log_process_identity(log, ROLE_HUD)

    assert identity["translocated"] is False
    assert "App Translocation" not in " ".join(record.getMessage() for record in caplog.records)


def test_json_log_records_carry_the_session_and_pid() -> None:
    """One log file holding several launches must be splittable back into them."""
    import json

    from fpdb_3_legacy.loggingFpdb import JsonFormatter

    record = logging.LogRecord("hud_main", logging.WARNING, __file__, 1, "HUD created", None, None)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["session"] == session_id()
    assert payload["pid"] == os.getpid()
    assert payload["message"] == "HUD created"


def _run_spawned(target: object, *args: object) -> int | None:
    """Run ``target`` in a process of its own and return its exit code.

    Its crash or exception is real, and enabling the log here would take this test
    run's own hooks and crash reports away from pytest.
    """
    process = multiprocessing.get_context("spawn").Process(target=target, args=args)
    process.start()
    process.join(120)
    return process.exitcode


def _crash_with_the_log_enabled(log_dir: str, file_name: str = HUD_CRASH_LOG_NAME) -> None:
    enable_crash_log(log_dir, file_name)
    faulthandler._sigsegv()


def _raise_in_a_thread_with_the_log_enabled(log_dir: str, file_name: str) -> None:
    def fail() -> None:
        raise ValueError("no table named bob")

    enable_crash_log(log_dir, file_name)
    # What fpdb and the HUD do on start: the previous hook has to keep writing there.
    sys.stderr = (Path(log_dir) / "errors.txt").open("w", encoding="utf-8")
    thread = threading.Thread(target=fail, name="the-failing-thread")
    thread.start()
    thread.join()
    sys.stderr.flush()


def test_a_native_crash_writes_its_stack_to_the_crash_log(tmp_path: Path) -> None:
    exit_code = _run_spawned(_crash_with_the_log_enabled, str(tmp_path))

    assert exit_code not in (None, 0)
    written = (tmp_path / HUD_CRASH_LOG_NAME).read_text(encoding="utf-8")
    assert "--- started " in written
    assert "Segmentation fault" in written
    assert "_crash_with_the_log_enabled" in written


def test_fpdb_records_a_native_crash_in_a_file_of_its_own(tmp_path: Path) -> None:
    exit_code = _run_spawned(_crash_with_the_log_enabled, str(tmp_path), MAIN_CRASH_LOG_NAME)

    assert exit_code not in (None, 0)
    assert "_crash_with_the_log_enabled" in (tmp_path / MAIN_CRASH_LOG_NAME).read_text(encoding="utf-8")
    assert not (tmp_path / HUD_CRASH_LOG_NAME).exists()


def test_an_uncaught_thread_exception_survives_the_next_start(tmp_path: Path) -> None:
    file_name = MAIN_CRASH_LOG_NAME

    assert _run_spawned(_raise_in_a_thread_with_the_log_enabled, str(tmp_path), file_name) == 0
    # The previous hook still ran: the apps' error file gets the traceback too.
    assert "no table named bob" in (tmp_path / "errors.txt").read_text(encoding="utf-8")

    assert _run_spawned(_raise_in_a_thread_with_the_log_enabled, str(tmp_path), file_name) == 0

    written = (tmp_path / file_name).read_text(encoding="utf-8")
    assert written.count("--- started ") == 2
    assert written.count("--- uncaught exception ") == 2
    assert written.count("ValueError: no table named bob") == 2
    assert "thread=the-failing-thread" in written


@pytest.fixture
def previous_hooks() -> Iterator[tuple[MagicMock, MagicMock]]:
    """Stand-ins for the hooks already installed, so that the real ones stay pytest's."""
    with (
        patch.object(sys, "excepthook", MagicMock()) as previous_hook,
        patch.object(threading, "excepthook", MagicMock()) as previous_thread_hook,
    ):
        yield previous_hook, previous_thread_hook


@pytest.fixture
def enabled_log(tmp_path: Path, previous_hooks: tuple[MagicMock, MagicMock]) -> Iterator[Path]:
    """A crash log enabled in this process, with faulthandler left to pytest."""
    with patch.object(hud_diagnostics.faulthandler, "enable") as enable:
        path = enable_crash_log(tmp_path, HUD_CRASH_LOG_NAME)
    enable.call_args.kwargs["file"].close()
    assert path is not None
    yield path


def _raised(error: BaseException) -> tuple[type[BaseException], BaseException, object]:
    try:
        raise error
    except BaseException as caught:
        return type(caught), caught, caught.__traceback__


def _thread_args(error: BaseException) -> threading.ExceptHookArgs:
    return threading.ExceptHookArgs((*_raised(error), threading.Thread(name="a-worker")))


def test_starting_again_keeps_the_stack_of_the_previous_crash(
    tmp_path: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    (tmp_path / HUD_CRASH_LOG_NAME).write_text("the previous crash\n", encoding="utf-8")

    with patch.object(hud_diagnostics.faulthandler, "enable") as enable:
        assert enable_crash_log(tmp_path, HUD_CRASH_LOG_NAME) == tmp_path / HUD_CRASH_LOG_NAME
    crash_log = enable.call_args.kwargs["file"]
    crash_log.close()

    assert enable.call_args.kwargs["all_threads"] is True
    lines = (tmp_path / HUD_CRASH_LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert lines[0] == "the previous crash"
    assert lines[1].startswith("--- started ")
    assert f"pid={os.getpid()}" in lines[1]


def test_a_log_directory_that_cannot_be_written_does_not_stop_the_app(
    tmp_path: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    not_a_directory = tmp_path / "a_file"
    not_a_directory.write_text("", encoding="utf-8")

    with patch.object(hud_diagnostics.faulthandler, "enable") as enable:
        assert enable_crash_log(not_a_directory / "log", HUD_CRASH_LOG_NAME) is None

    enable.assert_not_called()
    # With nowhere to write, the hooks have nothing to add.
    assert sys.excepthook is previous_hooks[0]
    assert threading.excepthook is previous_hooks[1]


def test_an_uncaught_exception_is_appended_then_passed_on(
    enabled_log: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    raised = _raised(ValueError("no table named bob"))

    sys.excepthook(*raised)

    previous_hooks[0].assert_called_once_with(*raised)
    lines = enabled_log.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("--- started ")
    assert lines[1].startswith("--- uncaught exception ")
    assert f"pid={os.getpid()}" in lines[1]
    assert f"thread={threading.current_thread().name}" in lines[1]
    assert lines[2] == "Traceback (most recent call last):"
    assert lines[-1] == "ValueError: no table named bob"


def test_an_uncaught_thread_exception_is_appended_then_passed_on(
    enabled_log: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    args = _thread_args(ValueError("no table named bob"))

    threading.excepthook(args)

    previous_hooks[1].assert_called_once_with(args)
    written = enabled_log.read_text(encoding="utf-8")
    assert "thread=a-worker" in written
    assert "ValueError: no table named bob" in written


@pytest.mark.parametrize("error", [SystemExit(0), KeyboardInterrupt()])
def test_asking_to_leave_is_not_recorded_but_is_passed_on(
    enabled_log: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
    error: BaseException,
) -> None:
    raised = _raised(error)
    args = _thread_args(error)

    sys.excepthook(*raised)
    threading.excepthook(args)

    previous_hooks[0].assert_called_once_with(*raised)
    previous_hooks[1].assert_called_once_with(args)
    assert "uncaught exception" not in enabled_log.read_text(encoding="utf-8")


def test_a_file_that_has_become_unwritable_loses_the_trace_only(
    enabled_log: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    enabled_log.unlink()
    enabled_log.mkdir()
    raised = _raised(ValueError("no table named bob"))

    sys.excepthook(*raised)
    threading.excepthook(_thread_args(ValueError("no table named bob")))

    previous_hooks[0].assert_called_once_with(*raised)
    previous_hooks[1].assert_called_once()


def test_a_previous_hook_that_fails_does_not_raise_from_the_handler(
    enabled_log: Path,
    previous_hooks: tuple[MagicMock, MagicMock],
) -> None:
    previous_hooks[0].side_effect = RuntimeError("the previous hook failed")
    previous_hooks[1].side_effect = RuntimeError("the previous hook failed")

    sys.excepthook(*_raised(ValueError("first")))
    threading.excepthook(_thread_args(ValueError("second")))

    written = enabled_log.read_text(encoding="utf-8")
    assert "ValueError: first" in written
    assert "ValueError: second" in written


def test_a_message_that_cannot_be_rendered_or_encoded_is_still_recorded(enabled_log: Path) -> None:
    class NoMessage(Exception):
        def __str__(self) -> str:
            raise RuntimeError("no message")

    sys.excepthook(*_raised(NoMessage()))
    sys.excepthook(*_raised(ValueError("table \udce9")))

    written = enabled_log.read_text(encoding="utf-8")
    assert "NoMessage" in written
    assert "table \\udce9" in written
