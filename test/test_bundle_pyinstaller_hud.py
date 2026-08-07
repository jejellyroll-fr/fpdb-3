"""Tests for assembling the two PyInstaller applications."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest

from tools.bundle_pyinstaller_hud import _update_mac_info_plist, bundle_pyinstaller_hud


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


def test_info_plist_gains_the_privacy_descriptions(tmp_path: Path) -> None:
    # macOS only remembers a granted permission when the bundle declares why it
    # wants it and keeps a stable identifier, so these four keys are the whole
    # point of the step.
    info_plist = tmp_path / "Info.plist"
    with info_plist.open("wb") as handle:
        plistlib.dump({"CFBundleName": "fpdb", "CFBundleIdentifier": "com.example.fpdb"}, handle)

    assert _update_mac_info_plist(info_plist) is True

    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleIdentifier"] == "org.fpdb.fpdb3"
    assert "AppleScript" in info["NSAppleEventsUsageDescription"]
    assert info["NSScreenCaptureUsageDescription"]
    assert info["NSAccessibilityUsageDescription"]
    # Untouched keys survive the rewrite.
    assert info["CFBundleName"] == "fpdb"


def test_a_missing_or_unreadable_info_plist_is_reported(tmp_path: Path, capsys) -> None:
    assert _update_mac_info_plist(tmp_path / "absent.plist") is False
    assert "No Info.plist" in capsys.readouterr().out

    broken = tmp_path / "Info.plist"
    broken.write_text("not a plist", encoding="utf-8")
    assert _update_mac_info_plist(broken) is False
    assert "Could not update" in capsys.readouterr().out


def test_rejects_incomplete_macos_outputs(tmp_path: Path) -> None:
    (tmp_path / "dist" / "fpdb.app").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Both fpdb.app and HUD_main.app"):
        bundle_pyinstaller_hud(tmp_path / "dist")
