"""The launch banner has to answer the questions a bug report starts from.

Which build ran, as which process, from where, and as part of which launch.
Each of those was missing from the logs of the duplicate-overlay report, and
each absence turned a five-minute answer into a day of inference.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import hud_diagnostics
from fpdb_3_legacy.hud_diagnostics import (
    ROLE_HUD,
    ROLE_MAIN,
    SESSION_ENV_VAR,
    bundle_path,
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
