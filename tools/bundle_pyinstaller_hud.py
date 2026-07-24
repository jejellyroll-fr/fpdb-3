#!/usr/bin/env python3
"""Bundle the PyInstaller HUD executable inside the main fpdb distribution."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
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
