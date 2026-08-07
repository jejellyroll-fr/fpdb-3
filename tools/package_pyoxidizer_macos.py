#!/usr/bin/env python3
"""Wrap the PyOxidizer macOS output in a signed .app bundle.

Shipped as a loose directory, every one of the ~500 bundled dylibs is a separate
quarantined download, so Gatekeeper prompts for each library in turn and the app
is unusable. Gatekeeper assesses a *bundle* as a unit instead: one approval
covers the libraries inside it.

Only the launcher may live in ``Contents/MacOS`` -- codesign refuses to seal a
bundle whose MacOS directory holds anything else ("bundle format unrecognized,
invalid, or unsuitable") -- so the payload goes to ``Contents/Resources``, which
the interpreter config in pyoxidizer.bzl knows how to find.

This is ad-hoc signing, not notarization: macOS still asks the user once.

Run it from the repository root: ``python -m tools.package_pyoxidizer_macos``.
"""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from tools.adhoc_sign_macos import find_mach_o_files
from tools.adhoc_sign_macos import sign as adhoc_sign

BUNDLE_IDENTIFIER = "org.fpdb.fpdb3"
DEFAULT_VERSION = "0.0.0"


def read_version(pyproject: Path) -> str:
    """Return the project version, or a placeholder when it cannot be read."""
    try:
        with pyproject.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return DEFAULT_VERSION


def write_info_plist(contents: Path, executable: str, version: str, icon: str | None) -> None:
    info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "FPDB 3",
        "CFBundleExecutable": executable,
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "fpdb",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "FPDB requires Automation access to detect poker table window titles via AppleScript.",
        "NSScreenCaptureUsageDescription": "FPDB requires Screen Recording permission to identify poker table window titles for the HUD.",
        "NSAccessibilityUsageDescription": "FPDB requires Accessibility permission to locate and position HUD windows over poker tables.",
    }
    if icon:
        info["CFBundleIconFile"] = icon
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)


def build_app(install_dir: Path, app_path: Path, executable: str, version: str, icon: Path | None) -> Path:
    """Assemble, ad-hoc sign and return the .app bundle."""
    if not (install_dir / executable).is_file():
        msg = f"no {executable} executable in {install_dir}"
        raise FileNotFoundError(msg)

    if app_path.exists():
        shutil.rmtree(app_path)
    contents = app_path / "Contents"
    resources = contents / "Resources"
    shutil.copytree(install_dir, resources, symlinks=True)

    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    shutil.move(str(resources / executable), str(macos / executable))

    icon_name = None
    if icon is not None:
        shutil.copy2(icon, resources / icon.name)
        icon_name = icon.name
    write_info_plist(contents, executable, version, icon_name)

    # Strip quarantine extended attribute if present so Gatekeeper does not block execution
    subprocess.run(  # noqa: S603
        ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(app_path)],  # noqa: S607
        check=False,
    )

    # Sign inside out: nested Mach-O files first, then seal the bundle. The
    # wheels ship linker-signed binaries, which macOS treats as unsigned.
    adhoc_sign(find_mach_o_files(resources))
    subprocess.run(  # noqa: S603
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(app_path)],  # noqa: S607
        check=True,
    )
    return app_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install_dir", type=Path, help="PyOxidizer install directory.")
    parser.add_argument("app_path", type=Path, help="Path of the .app bundle to create.")
    parser.add_argument("--executable", default="fpdb", help="Launcher name inside the install directory.")
    parser.add_argument("--icon", type=Path, default=None, help="Optional .icns file.")
    parser.add_argument("--version", default=None, help="Bundle version (defaults to the pyproject version).")
    args = parser.parse_args(argv)

    if not args.install_dir.is_dir():
        parser.error(f"not a directory: {args.install_dir}")

    version = args.version or read_version(Path(__file__).resolve().parent.parent / "pyproject.toml")
    app = build_app(args.install_dir, args.app_path, args.executable, version, args.icon)
    print(f"built {app} (version {version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
