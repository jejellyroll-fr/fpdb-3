"""Helper-process command building for source and frozen installs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from fpdb_3_legacy.subprocess_launch import (
    HUD_FLAG,
    RUN_MODULE_FLAG,
    dispatch_hud_main,
    dispatch_run_module,
    hud_main_command,
    python_module_command,
)


def test_source_install_runs_module_with_dash_m(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert python_module_command("pkg.mod", "--live") == [sys.executable, "-u", "-m", "pkg.mod", "--live"]


@pytest.mark.parametrize("frozen", ["pyoxidizer", True])
def test_frozen_install_never_passes_dash_m(monkeypatch, frozen) -> None:
    """A frozen sys.executable parses fpdb's own options: -m dies with 'no such option'."""
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)

    command = python_module_command("pkg.mod", "--live")

    assert command == [sys.executable, RUN_MODULE_FLAG, "pkg.mod", "--live"]
    assert "-m" not in command


def test_hud_command_uses_pyoxidizer_subcommand(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", "pyoxidizer", raising=False)

    assert hud_main_command("-x") == [sys.executable, "--hud", "-x"]


def test_hud_command_reuses_the_main_executable_on_pyinstaller_macos(monkeypatch, tmp_path) -> None:
    """One executable gives both processes the same macOS TCC identity."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "fpdb"))

    command = hud_main_command("-x")

    assert command == [str(tmp_path / "fpdb"), HUD_FLAG, "-x"]


def test_hud_command_uses_sibling_executable_when_frozen(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32" if os.name == "nt" else "linux")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "fpdb"))
    hud = tmp_path / ("HUD_main.exe" if os.name == "nt" else "HUD_main")
    hud.write_text("")

    command = hud_main_command("-x")

    assert Path(command[0]) == hud.resolve()
    assert command[1:] == ["-x"]


def test_hud_command_reports_missing_packaged_executable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32" if os.name == "nt" else "linux")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "fpdb"))

    with pytest.raises(FileNotFoundError):
        hud_main_command()


def test_hud_command_runs_script_from_source(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = hud_main_command("-x")

    assert command[0] == sys.executable
    assert Path(command[1]).name == "HUD_main.pyw"
    assert command[2] == "-x"


def test_dispatch_ignores_a_normal_launch(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["fpdb", "-c", "HUD_config.xml"])

    assert dispatch_run_module() is False
    assert sys.argv == ["fpdb", "-c", "HUD_config.xml"]


def test_dispatch_makes_output_line_buffered(monkeypatch, tmp_path) -> None:
    """Without this a helper's log stays empty until its buffer fills."""
    module_dir = tmp_path / "buffered"
    module_dir.mkdir()
    (module_dir / "__init__.py").write_text("")
    (module_dir / "mod.py").write_text(
        "import sys, pathlib\npathlib.Path(sys.argv[1]).write_text(str(sys.stdout.line_buffering))\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    marker = tmp_path / "buffering.txt"
    monkeypatch.setattr(sys, "argv", ["fpdb", RUN_MODULE_FLAG, "buffered.mod", str(marker)])

    dispatch_run_module()

    assert marker.read_text() == "True"


def test_dispatch_runs_the_requested_module(monkeypatch, tmp_path) -> None:
    module_dir = tmp_path / "pkg"
    module_dir.mkdir()
    (module_dir / "__init__.py").write_text("")
    (module_dir / "mod.py").write_text(
        "import sys, pathlib\npathlib.Path(sys.argv[1]).write_text(f'{__name__}|{sys.argv[2]}')\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    marker = tmp_path / "ran.txt"
    monkeypatch.setattr(sys, "argv", ["fpdb", RUN_MODULE_FLAG, "pkg.mod", str(marker), "--live"])

    assert dispatch_run_module() is True
    assert marker.read_text() == "__main__|--live"


def test_dispatch_hud_main_runs_packaged_script_with_forwarded_args(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["fpdb", HUD_FLAG, "--config", "bundled.xml"])

    monkeypatch.setattr("fpdb_3_legacy.subprocess_launch.runpy.run_path", lambda *args, **kwargs: None)

    assert dispatch_hud_main() is True

    assert Path(sys.argv[0]).name == "HUD_main.pyw"
    assert sys.argv[1:] == ["--config", "bundled.xml"]
