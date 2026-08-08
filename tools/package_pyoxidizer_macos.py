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

Local builds are ad-hoc signed. Release CI supplies a Developer ID identity,
then notarizes and staples the completed bundle. CI can defer signing until its
launcher smokes have run, then seal the already assembled app exactly once.

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

from tools.adhoc_sign_macos import find_mach_o_files, resolve_signing_identity, sign, sign_bundle

BUNDLE_IDENTIFIER = "org.fpdb.fpdb3"
DEFAULT_VERSION = "0.0.0"
ENTITLEMENTS = Path(__file__).resolve().with_name("macos-entitlements.plist")


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


def build_app(
    install_dir: Path,
    app_path: Path,
    executable: str,
    version: str,
    icon: Path | None,
    *,
    signing_identity: str | None = None,
    defer_signing: bool = False,
) -> Path:
    """Assemble and return the .app bundle, signing it unless deferred."""
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

    # Clean build inputs can carry quarantine. A browser may attach it again to
    # the download; release notarization, not this build-time xattr, handles that.
    subprocess.run(  # noqa: S603
        ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(app_path)],  # noqa: S607
        check=False,
    )

    if not defer_signing:
        sign_app(app_path, signing_identity=signing_identity)
    return app_path


def sign_app(app_path: Path, *, signing_identity: str | None = None) -> Path:
    """Sign an assembled app after every command that may mutate its resources."""
    resources = app_path / "Contents" / "Resources"
    if not resources.is_dir():
        msg = f"no app resources in {app_path}"
        raise FileNotFoundError(msg)

    # Sign inside out: nested Mach-O files first, then seal the bundle. Wheels
    # ship linker-signed binaries, which macOS treats as unsigned.
    identity = resolve_signing_identity(signing_identity)
    sign(find_mach_o_files(resources), identity=identity)
    sign_bundle(app_path, identity=identity, entitlements=ENTITLEMENTS)
    return app_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install_dir", type=Path, nargs="?", help="PyOxidizer install directory.")
    parser.add_argument("app_path", type=Path, nargs="?", help="Path of the .app bundle to create.")
    parser.add_argument("--executable", default="fpdb", help="Launcher name inside the install directory.")
    parser.add_argument("--icon", type=Path, default=None, help="Optional .icns file.")
    parser.add_argument("--version", default=None, help="Bundle version (defaults to the pyproject version).")
    parser.add_argument(
        "--defer-signing",
        action="store_true",
        help="Assemble without signing so launcher smokes can run before the final seal.",
    )
    parser.add_argument(
        "--sign-existing",
        type=Path,
        metavar="APP",
        help="Sign an already assembled app and exit; accepts no positional paths.",
    )
    parser.add_argument(
        "--signing-identity",
        default=None,
        help="codesign identity (defaults to FPDB_MACOS_SIGNING_IDENTITY, then ad-hoc '-').",
    )
    args = parser.parse_args(argv)

    if args.sign_existing is not None:
        if args.install_dir is not None or args.app_path is not None or args.defer_signing:
            parser.error("--sign-existing accepts no positional paths or --defer-signing")
        app = sign_app(args.sign_existing, signing_identity=args.signing_identity)
        print(f"signed {app}")
        return 0

    if args.install_dir is None or args.app_path is None:
        parser.error("install_dir and app_path are required unless --sign-existing is used")
    if not args.install_dir.is_dir():
        parser.error(f"not a directory: {args.install_dir}")

    version = args.version or read_version(Path(__file__).resolve().parent.parent / "pyproject.toml")
    app = build_app(
        args.install_dir,
        args.app_path,
        args.executable,
        version,
        args.icon,
        signing_identity=args.signing_identity,
        defer_signing=args.defer_signing,
    )
    state = "unsigned" if args.defer_signing else "signed"
    print(f"built {app} (version {version}, {state})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
