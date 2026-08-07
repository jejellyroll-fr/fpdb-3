#!/usr/bin/env python3
"""Bundle the PyInstaller HUD executable inside the main fpdb distribution."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import subprocess
import sys
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


def _update_mac_info_plist(info_plist: Path) -> bool:
    """Write the privacy usage descriptions and bundle id into an Info.plist.

    Returns whether the file was rewritten. A failure here is reported rather
    than swallowed: the whole point of this step is that macOS remembers the
    permissions the user grants, and a bundle shipped without the keys asks
    again on every launch -- the exact symptom, arriving silently.
    """
    if not info_plist.is_file():
        print(f"No Info.plist at {info_plist}; privacy descriptions not written")
        return False
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
    except (OSError, plistlib.InvalidFileException) as exc:
        print(f"Could not update {info_plist}: {exc}")
        return False
    return True


def _run_macos_tool(command: list[str]) -> None:
    """Run a macOS-only build tool, reporting rather than raising if it is absent.

    subprocess.run(check=False) only forgives a non-zero exit; a missing binary
    still raises, which is how /usr/bin/xattr took the Linux test run down with
    it once this ran on a bundle built anywhere but macOS.
    """
    try:
        subprocess.run(command, check=False)
    except OSError as exc:
        print(f"Could not run {command[0]}: {exc}")


def _sign_macos_bundle(fpdb_app: Path, resources: Path) -> None:
    """Ad-hoc sign the merged bundle, innermost Mach-O files first.

    Gatekeeper assesses a bundle as a unit, so the nested binaries the merge
    just moved in have to be signed before the bundle itself is sealed.
    """
    from tools.adhoc_sign_macos import find_mach_o_files, sign

    sign(find_mach_o_files(resources))

    codesign_bin = shutil.which("codesign") or "/usr/bin/codesign"
    _run_macos_tool([codesign_bin, "--force", "--deep", "--sign", "-", str(fpdb_app)])


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

        # xattr and codesign only exist on macOS, and signing a bundle assembled
        # anywhere else is meaningless. The tests build an .app tree on whatever
        # host they run on, so this branch is reached off-Darwin too.
        if sys.platform == "darwin":
            # Strip quarantine so Gatekeeper does not block execution
            _run_macos_tool(["/usr/bin/xattr", "-cr", str(fpdb_app)])
            _sign_macos_bundle(fpdb_app, fpdb_contents / "Resources")

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
