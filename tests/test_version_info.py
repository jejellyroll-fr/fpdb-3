"""The Version tab must report the running build truthfully, or say it cannot.

Issue #226: fpdb had no place to read its own version, packaging or runtime
environment from, so every bug report started with a round of questions. The
value of the tab is entirely in the accuracy of these facts, and its failure
mode is worse than useless -- a probe that raises takes the whole tab with it,
right when the user is trying to report a problem.

So these tests pin two things: each fact is derived from the right source, and
no missing dependency, absent git or unreachable database can turn into an
exception.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from subprocess import TimeoutExpired

import pytest

from fpdb_3_legacy import version_info


def _git_timeout() -> TimeoutExpired:
    """Build the controlled timeout raised by the subprocess test double."""
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    return TimeoutExpired(cmd="git", timeout=5)


class _Db:
    """Minimal stand-in for Database: only what database_status() reads."""

    def __init__(self, backend="SQLite", connected=True) -> None:
        self._backend = backend
        self._connected = connected

    def get_backend_name(self):
        return self._backend

    def is_connected(self):
        return self._connected


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _make_repo(tmp_path: Path) -> Path:
    """A throwaway checkout with exactly one commit, or skip if git is absent."""
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        _git(repo, "init")
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - CI always has git
        pytest.skip("git is not available")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "file.txt").write_text("content", encoding="utf-8")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_an_unfrozen_process_is_reported_as_running_from_source(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert version_info.detect_packaging() == "Source"


def test_pyinstaller_is_told_apart_by_its_unpacked_bundle_directory(monkeypatch) -> None:
    """Both packagers set sys.frozen; only PyInstaller sets _MEIPASS."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEIxxxx", raising=False)

    assert version_info.detect_packaging() == "PyInstaller"


def test_pyoxidizer_is_told_apart_by_the_marker_it_assigns(monkeypatch) -> None:
    """pyoxidizer.bzl sets sys.frozen = 'pyoxidizer' and never unpacks a bundle."""
    monkeypatch.setattr(sys, "frozen", "pyoxidizer", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert version_info.detect_packaging() == "PyOxidizer"


def test_an_unrecognised_frozen_build_is_not_guessed_at(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.delenv("APPDIR", raising=False)

    assert version_info.detect_packaging() == "Frozen"


def test_a_git_checkout_reports_its_commit_and_branch(tmp_path, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    repo = _make_repo(tmp_path)

    checkout = version_info.git_checkout(repo)

    assert checkout.is_repository
    assert checkout.commit and checkout.commit != version_info.UNKNOWN
    assert checkout.branch not in ("", version_info.UNKNOWN)
    assert not checkout.dirty


def test_an_uncommitted_change_marks_the_working_tree_dirty(tmp_path, monkeypatch) -> None:
    """Untracked files count: "I only edited one file" is the common report."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    repo = _make_repo(tmp_path)
    (repo / "scratch.txt").write_text("uncommitted", encoding="utf-8")

    assert version_info.git_checkout(repo).dirty


def test_a_directory_without_a_repository_is_not_reported_as_one(tmp_path, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert not version_info.git_checkout(tmp_path).is_repository


def test_a_frozen_build_never_shells_out_to_git(monkeypatch) -> None:
    """A packaged build has no repository; spawning git only costs startup time
    and, on Windows, flashes a console window."""
    monkeypatch.setattr(sys, "frozen", "pyoxidizer", raising=False)

    def explode(*args, **kwargs):
        message = "git must not run in a frozen build"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "run", explode)

    assert not version_info.git_checkout().is_repository


def test_a_missing_git_binary_is_reported_rather_than_raised(tmp_path, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)

    assert not version_info.git_checkout(tmp_path).is_repository


def test_a_hanging_git_cannot_freeze_the_gui_thread(tmp_path, monkeypatch) -> None:
    """git on an unreachable network mount blocks; the tab must still open."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    def timeout(*args, **kwargs):
        raise _git_timeout()

    monkeypatch.setattr(subprocess, "run", timeout)

    assert not version_info.git_checkout(tmp_path).is_repository


def test_git_calls_pass_a_timeout_so_they_cannot_block_forever(tmp_path, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    seen: list[object] = []

    def record(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", record)
    version_info.git_checkout(tmp_path)

    assert seen and all(t is not None for t in seen)


def test_the_environment_names_the_interpreter_and_libraries_a_report_needs() -> None:
    environment = version_info.runtime_environment()

    for key in ("Python", "PySide6", "Qt", "SQLite", "NumPy", "OS", "Platform", "Architecture"):
        assert key in environment, f"missing environment key: {key}"
        assert environment[key], f"empty environment value: {key}"


def test_the_python_version_is_the_running_interpreter() -> None:
    expected = ".".join(str(part) for part in sys.version_info[:3])

    assert version_info.runtime_environment()["Python"] == expected


def test_a_missing_optional_dependency_is_displayed_not_raised(monkeypatch) -> None:
    """An optional/platform-specific import must not take the tab down with it."""

    def refuse(name, *args, **kwargs):
        raise ImportError(name)

    monkeypatch.setattr(version_info, "import_module", refuse)

    assert version_info._module_version("numpy") == "not installed"


def test_the_database_row_names_the_backend_and_its_state() -> None:
    status = version_info.database_status(_Db(backend="PostgreSQL", connected=True))

    assert "PostgreSQL" in status
    assert "connected" in status


def test_a_disconnected_database_is_distinguished_from_a_connected_one() -> None:
    assert "disconnected" in version_info.database_status(_Db(connected=False))


def test_no_database_at_all_is_its_own_answer() -> None:
    """The tab can be opened before load_profile ever built a Database."""
    assert version_info.database_status(None) == "not connected"


def test_an_unrecognised_backend_does_not_break_the_report() -> None:
    class Broken:
        def get_backend_name(self):
            message = "invalid backend"
            raise ValueError(message)

        def is_connected(self):
            return True

    status = version_info.database_status(Broken())

    assert version_info.UNKNOWN in status
    assert "connected" in status


def test_the_report_carries_the_version_it_is_given_rather_than_recomputing_it() -> None:
    """fpdb.pyw already resolves the version; recomputing it is how the About
    box and the tab would start disagreeing."""
    report = version_info.collect_report(version="v3.6.4-2-gabc1234")

    assert report.version == "v3.6.4-2-gabc1234"


def test_the_report_falls_back_to_a_placeholder_for_an_unknown_config_path() -> None:
    report = version_info.collect_report(version="3.6.4", config_file=None)

    assert report.config_file == version_info.UNKNOWN


def test_the_report_records_the_configured_file_and_the_live_database() -> None:
    report = version_info.collect_report(version="3.6.4", config_file="/tmp/HUD_config.xml", db=_Db())

    assert report.config_file == "/tmp/HUD_config.xml"
    assert "SQLite" in report.database
    assert report.packaging
    assert report.runtime
