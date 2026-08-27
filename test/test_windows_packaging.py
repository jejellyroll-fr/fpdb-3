"""What the two Windows packagers must carry, checked as text.

Neither can be exercised from a unit test -- one needs PyInstaller and a
Windows runner, the other needs Rust and a 60-minute build -- but both have
failed silently in ways a single grep would have caught: a PowerShell array
declared without its sigil, a lazily imported module missing from the frozen
bundle, a build target removed from pyoxidizer.bzl.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS1 = (ROOT / "build_fpdb.ps1").read_text(encoding="utf-8")
BZL = (ROOT / "pyoxidizer.bzl").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
PYOX_REQS = (ROOT / "pyoxidizer-requirements.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# build_fpdb.ps1 -- the script a Windows developer actually runs
# ---------------------------------------------------------------------------


def test_the_file_list_is_a_variable_assignment() -> None:
    """``FILES=@(`` is a command name to PowerShell, not an assignment.

    With ErrorActionPreference=Stop that ended the script before it built
    anything; nothing downstream could see $FILES either.
    """
    assert "$FILES = @(" in PS1
    assert not re.search(r"^\s*FILES\s*=", PS1, re.MULTILINE)


def test_no_bare_variable_is_followed_by_a_colon() -> None:
    """``$path:target`` parses as a drive-qualified variable, e.g. $env:PATH.

    One of those anywhere in the file is a parse error for the whole file, so
    the script could not run at all -- on any platform.
    """
    assert not re.search(r"\$[A-Za-z_][A-Za-z0-9_]*:", PS1)


def test_the_com_bindings_of_the_seat_reader_are_packaged() -> None:
    """comtypes is imported inside a try/except, so PyInstaller cannot see it."""
    assert "--hidden-import=comtypes" in PS1
    for command in _windows_pyinstaller_commands():
        assert "--hidden-import comtypes" in command


def test_the_local_build_uses_the_same_hooks_as_ci() -> None:
    assert "--additional-hooks-dir=tools/pyinstaller_hooks" in PS1


def _windows_pyinstaller_commands() -> list[str]:
    """The CI PyInstaller invocations for Windows (they use ';' separators)."""
    commands = [line for line in CI.splitlines() if "PyInstaller --noconfirm" in line and 'gfx;gfx' in line]
    assert commands, "no Windows PyInstaller command found in the workflow"
    return commands


# ---------------------------------------------------------------------------
# pyoxidizer.bzl -- available on Windows again
# ---------------------------------------------------------------------------


def test_the_windows_target_is_buildable() -> None:
    assert "x86_64-pc-windows-msvc" in BZL
    assert "PyOxidizer is deprecated on Windows" not in BZL


def test_the_windows_executable_is_a_gui_binary() -> None:
    """Without this the launcher opens a console window behind the GUI."""
    assert 'exe.windows_subsystem = "windows"' in BZL


def test_the_workflow_builds_the_windows_bundle() -> None:
    assert "fpdb-pyoxidizer-windows-x64" in CI


def test_the_bundled_wheel_libraries_are_collected() -> None:
    """Classification drops "<package>.libs", and numpy cannot start without it."""
    assert "policy.allow_files = True" in BZL
    assert "is_wheel_library_payload" in BZL


def test_the_payload_is_put_back_beside_its_package() -> None:
    """PyOxidizer installs "numpy.libs" as "numpy/libs"; the loaders look beside."""
    assert "tools.relocate_wheel_payloads" in CI


def test_the_bundle_is_verified_to_import_numpy() -> None:
    """A bundle that cannot import numpy cannot open a window; the build must say so."""
    assert "--run-module numpy.__config__" in CI


def test_build_experiment_does_not_refuse_windows() -> None:
    experiment = (ROOT / "build_experiment.sh").read_text(encoding="utf-8")
    assert "PyOxidizer builds on Windows are deprecated" not in experiment


# ---------------------------------------------------------------------------
# The two dependency lists that have to agree
# ---------------------------------------------------------------------------


def test_comtypes_is_declared_for_windows_in_both_dependency_lists() -> None:
    assert "comtypes>=1.4.1; sys_platform == 'win32'" in PYPROJECT
    assert "comtypes>=1.4.1; sys_platform == 'win32'" in PYOX_REQS
