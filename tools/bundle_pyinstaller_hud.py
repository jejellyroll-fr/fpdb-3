#!/usr/bin/env python3
"""Bundle the PyInstaller HUD executable inside the main fpdb distribution."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path


def _merge_tree(source: Path, destination: Path) -> None:
    """Copy missing entries from source into destination without replacing fpdb files."""
    destination.mkdir(parents=True, exist_ok=True)
    for source_entry in source.iterdir():
        destination_entry = destination / source_entry.name
        if source_entry.is_symlink():
            if not os.path.lexists(destination_entry):
                destination_entry.symlink_to(os.readlink(source_entry))
        elif source_entry.is_dir():
            _merge_tree(source_entry, destination_entry)
        elif not destination_entry.exists():
            shutil.copy2(source_entry, destination_entry)


def _copy_executable(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"HUD executable not found: {source}")
    shutil.copy2(source, destination)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _update_mac_info_plist(info_plist: Path) -> None:
    if not info_plist.is_file():
        return
    try:
        with info_plist.open("rb") as handle:
            info = plistlib.load(handle)
        info["CFBundleIdentifier"] = "org.fpdb.fpdb3"
        info["NSAppleEventsUsageDescription"] = (
            "FPDB requires Automation access to detect poker table window titles via AppleScript."
        )
        info["NSScreenCaptureUsageDescription"] = (
            "FPDB requires Screen Recording permission to identify poker table window titles for the HUD."
        )
        info["NSAccessibilityUsageDescription"] = (
            "FPDB requires Accessibility permission to locate and position HUD windows over poker tables."
        )
        with info_plist.open("wb") as handle:
            plistlib.dump(info, handle)
    except Exception:
        pass


def bundle_pyinstaller_hud(dist_dir: Path) -> Path:
    """Merge the HUD PyInstaller output into fpdb and return the bundled executable."""
    fpdb_app = dist_dir / "fpdb.app"
    hud_app = dist_dir / "HUD_main.app"

    if fpdb_app.is_dir() or hud_app.is_dir():
        if not fpdb_app.is_dir() or not hud_app.is_dir():
            raise FileNotFoundError("Both fpdb.app and HUD_main.app are required for a macOS bundle")

        fpdb_contents = fpdb_app / "Contents"
        hud_contents = hud_app / "Contents"
        for directory in ("Frameworks", "Resources"):
            source = hud_contents / directory
            if source.is_dir():
                _merge_tree(source, fpdb_contents / directory)

        bundled_executable = fpdb_contents / "MacOS" / "HUD_main"
        _copy_executable(hud_contents / "MacOS" / "HUD_main", bundled_executable)
        shutil.rmtree(hud_app)

        # Update Info.plist privacy usage descriptions & bundle ID
        _update_mac_info_plist(fpdb_contents / "Info.plist")

        # Strip quarantine extended attribute so Gatekeeper does not block execution
        subprocess.run(["/usr/bin/xattr", "-cr", str(fpdb_app)], check=False)

        # Re-sign the merged bundle inside-out
        try:
            from tools.adhoc_sign_macos import adhoc_sign, find_mach_o_files

            adhoc_sign(find_mach_o_files(fpdb_contents / "Resources"))
        except Exception:
            pass

        codesign_bin = shutil.which("codesign") or "/usr/bin/codesign"
        subprocess.run([codesign_bin, "--force", "--deep", "--sign", "-", str(fpdb_app)], check=False)

        return bundled_executable

    fpdb_dir = dist_dir / "fpdb"
    hud_dir = dist_dir / "HUD_main"
    if not fpdb_dir.is_dir() or not hud_dir.is_dir():
        raise FileNotFoundError(f"Expected PyInstaller outputs under {dist_dir}")

    fpdb_internal = fpdb_dir / "_internal"
    hud_internal = hud_dir / "_internal"
    if not hud_internal.is_dir():
        raise FileNotFoundError(f"HUD dependency directory not found: {hud_internal}")
    _merge_tree(hud_internal, fpdb_internal)

    executable_name = "HUD_main.exe" if (hud_dir / "HUD_main.exe").is_file() else "HUD_main"
    bundled_executable = fpdb_dir / executable_name
    _copy_executable(hud_dir / executable_name, bundled_executable)
    shutil.rmtree(hud_dir)
    return bundled_executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", nargs="?", type=Path, default=Path("dist"))
    args = parser.parse_args()

    bundled_executable = bundle_pyinstaller_hud(args.dist_dir.resolve())
    print(f"Bundled HUD executable: {bundled_executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
