"""The guard rails of install_macos.sh, run with stubbed macOS commands.

The full install (Homebrew, pip, the native build) only makes sense on a Mac;
what can be checked anywhere is that the script refuses the situations it is
meant to refuse before it touches anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "install_macos.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="needs a POSIX bash")


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(0o755)


def _run(
    tmp_path: Path,
    *args: str,
    uname: str = "Darwin",
    version: str = "14.5",
    clt: bool = True,
    script: Path = SCRIPT,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "uname", f'[[ "$1" == "-m" ]] && echo arm64 || echo {uname}')
    _stub(bin_dir, "sw_vers", f"echo {version}")
    _stub(
        bin_dir,
        "xcode-select",
        f'[[ "$1" == "-p" ]] && {{ {"echo /Library/Developer/CommandLineTools" if clt else "exit 2"}; }}; exit 0',
    )
    # Only the tools the guard rails use, so no real cmake, brew or pip is ever reached.
    for tool in ("dirname", "sed", "python3"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}
    return subprocess.run(
        [shutil.which("bash") or "bash", str(script), *args], capture_output=True, text=True, env=env, check=False
    )


def test_script_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)


def test_help_lists_the_options(tmp_path: Path) -> None:
    result = _run(tmp_path, "--help")
    assert result.returncode == 0
    for option in ("--dev", "--postgresql", "--mysql", "--no-brew", "--python"):
        assert option in result.stdout


def test_unknown_option_is_rejected(tmp_path: Path) -> None:
    assert _run(tmp_path, "--bogus").returncode == 2


def test_missing_homebrew_is_reported(tmp_path: Path) -> None:
    # Checked before running: the script finds Homebrew at its standard prefixes
    # whatever PATH says, and would then install into the real repository.
    if Path("/opt/homebrew/bin/brew").exists() or Path("/usr/local/bin/brew").exists():
        pytest.skip("Homebrew is installed here")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "Homebrew is not installed" in result.stderr


def test_refuses_to_run_outside_macos(tmp_path: Path) -> None:
    result = _run(tmp_path, uname="Linux")
    assert result.returncode == 1
    assert "for macOS" in result.stderr


def test_refuses_macos_older_than_11(tmp_path: Path) -> None:
    result = _run(tmp_path, version="10.15.7")
    assert result.returncode == 1
    assert "macOS 11" in result.stderr


def test_stops_when_command_line_tools_are_missing(tmp_path: Path) -> None:
    result = _run(tmp_path, clt=False)
    assert result.returncode == 1
    assert "Command Line Tools" in result.stderr


def test_no_brew_without_cmake_stops_before_installing(tmp_path: Path) -> None:
    result = _run(tmp_path, "--no-brew", "--python", sys.executable)
    assert result.returncode == 1
    assert "CMake" in result.stderr
    assert "Creating the virtual environment" not in result.stdout


def _copy_script(tmp_path: Path, pyproject: str | None) -> Path:
    """The script alone in a fake checkout, with the given pyproject.toml."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    script = checkout / SCRIPT.name
    shutil.copy2(SCRIPT, script)
    if pyproject is not None:
        (checkout / "pyproject.toml").write_text(pyproject)
    return script


def test_minimum_python_comes_from_pyproject(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, '[project]\nrequires-python = ">=3.99,<4.0"\n')
    result = _run(tmp_path, "--no-brew", "--python", sys.executable, script=script)
    assert result.returncode == 1
    assert "Python 3.99 or newer is required" in result.stderr


def test_running_interpreter_satisfies_the_real_pyproject(tmp_path: Path) -> None:
    # The interpreter running the suite meets requires-python, so the script must
    # get past the version check and stop at the (absent) CMake instead.
    result = _run(tmp_path, "--no-brew", "--python", sys.executable)
    assert "Using Python" in result.stdout
    assert "or newer is required" not in result.stderr


def test_outside_a_checkout_is_refused(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, None)
    result = _run(tmp_path, script=script)
    assert result.returncode == 1
    assert "requires-python" in result.stderr


def test_launcher_uses_the_console_script() -> None:
    text = SCRIPT.read_text()
    assert "bin/fpdb_3_legacy" in text
    assert "fpdb.command" in (REPO_ROOT / ".gitignore").read_text()
