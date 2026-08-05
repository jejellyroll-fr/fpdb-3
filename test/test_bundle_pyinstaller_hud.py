"""Tests for assembling the two PyInstaller applications."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.bundle_pyinstaller_hud import bundle_pyinstaller_hud


@pytest.mark.parametrize("executable_name", ["HUD_main", "HUD_main.exe"])
def test_bundles_onedir_hud_and_dependencies(tmp_path: Path, executable_name: str) -> None:
    dist = tmp_path / "dist"
    fpdb = dist / "fpdb"
    hud = dist / "HUD_main"
    (fpdb / "_internal").mkdir(parents=True)
    (hud / "_internal" / "hud_only").mkdir(parents=True)
    (fpdb / "_internal" / "shared.bin").write_text("fpdb", encoding="utf-8")
    (hud / "_internal" / "shared.bin").write_text("hud", encoding="utf-8")
    (hud / "_internal" / "hud_only" / "module.so").write_text("dependency", encoding="utf-8")
    (hud / executable_name).write_text("executable", encoding="utf-8")

    bundled = bundle_pyinstaller_hud(dist)

    assert bundled == fpdb / executable_name
    assert bundled.is_file()
    assert os.access(bundled, os.X_OK)
    assert (fpdb / "_internal" / "hud_only" / "module.so").is_file()
    assert (fpdb / "_internal" / "shared.bin").read_text(encoding="utf-8") == "fpdb"
    assert not hud.exists()


def test_bundles_macos_hud_inside_main_app(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    fpdb_contents = dist / "fpdb.app" / "Contents"
    hud_contents = dist / "HUD_main.app" / "Contents"
    (fpdb_contents / "MacOS").mkdir(parents=True)
    (fpdb_contents / "Frameworks").mkdir()
    (fpdb_contents / "Resources").mkdir()
    (hud_contents / "MacOS").mkdir(parents=True)
    (hud_contents / "Frameworks" / "hud_only").mkdir(parents=True)
    (hud_contents / "Resources" / "hud_data").mkdir(parents=True)
    (hud_contents / "MacOS" / "HUD_main").write_text("executable", encoding="utf-8")
    (hud_contents / "Frameworks" / "hud_only" / "module.dylib").write_text("dependency", encoding="utf-8")
    (hud_contents / "Resources" / "hud_data" / "config.xml").write_text("data", encoding="utf-8")

    bundled = bundle_pyinstaller_hud(dist)

    assert bundled == fpdb_contents / "MacOS" / "HUD_main"
    assert bundled.is_file()
    assert os.access(bundled, os.X_OK)
    assert (fpdb_contents / "Frameworks" / "hud_only" / "module.dylib").is_file()
    assert (fpdb_contents / "Resources" / "hud_data" / "config.xml").is_file()
    assert not (dist / "HUD_main.app").exists()


def test_rejects_incomplete_macos_outputs(tmp_path: Path) -> None:
    (tmp_path / "dist" / "fpdb.app").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Both fpdb.app and HUD_main.app"):
        bundle_pyinstaller_hud(tmp_path / "dist")
