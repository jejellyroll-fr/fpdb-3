"""Utility to assist with macOS Gatekeeper quarantine removal and privacy permissions setup.

macOS Gatekeeper and TCC (Transparency, Consent, and Control) security policies enforce:
1. Gatekeeper checks unverified downloads. Stripping 'com.apple.quarantine' and applying
   ad-hoc codesign allows fpdb.app to run without 'Unidentified Developer' blocks.
2. TCC permissions (Screen Recording, Accessibility, AppleScript Automation). Including
   NSAppleEventsUsageDescription, NSScreenCaptureUsageDescription, and NSAccessibilityUsageDescription
   in Info.plist with a stable bundle ID (org.fpdb.fpdb3) ensures macOS retains the user's
   approval permanently across launches.

Run from command line:
    python -m tools.grant_macos_permissions [--app-path PATH] [--clear-quarantine] [--check-status]
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from fpdb.infrastructure.platform import permissions

_IS_MACOS = platform.system() == "Darwin"


def clear_quarantine(app_path: Path) -> bool:
    """Strip com.apple.quarantine extended attribute from the app bundle/path."""
    if not _IS_MACOS or not app_path.exists():
        return False
    try:
        res = subprocess.run(
            ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(app_path)],
            check=False,
            capture_output=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def re_sign_bundle(app_path: Path) -> bool:
    """Apply an ad-hoc code signature to seal the app bundle."""
    if not _IS_MACOS or not app_path.exists():
        return False
    try:
        codesign_bin = shutil.which("codesign") or "/usr/bin/codesign"
        res = subprocess.run(
            [codesign_bin, "--force", "--deep", "--sign", "-", str(app_path)],
            check=False,
            capture_output=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def check_and_print_permission_status() -> permissions.PermissionStatus:
    """Check and display macOS Screen Recording and Accessibility permission status."""
    status = permissions.get_status()
    print("=== macOS Privacy & Security Status ===")
    print(f"Screen Recording Permission: {'Granted' if status.screen_recording else 'Missing'}")
    print(f"Accessibility Permission:    {'Granted' if status.accessibility else 'Missing'}")
    print("=======================================")

    missing = permissions.describe_missing(status)
    if missing:
        print("\nActions required:")
        for msg in missing:
            print(f" - {msg}")
    else:
        print("\nAll required macOS permissions are granted!")
    return status


def setup_app_bundle(app_path: Path) -> dict[str, bool]:
    """Strip quarantine and ad-hoc sign the given .app bundle."""
    results = {
        "quarantine_cleared": clear_quarantine(app_path),
        "signed": re_sign_bundle(app_path),
    }
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-path", type=Path, help="Path to fpdb.app bundle.")
    parser.add_argument("--clear-quarantine", action="store_true", help="Remove quarantine extended attribute.")
    parser.add_argument("--re-sign", action="store_true", help="Re-sign app bundle ad-hoc.")
    parser.add_argument("--check-status", action="store_true", default=True, help="Check current macOS permissions status.")

    args = parser.parse_args(argv)

    if not _IS_MACOS:
        print("macOS permission tools are only applicable on Darwin/macOS systems.")
        return 0

    if args.app_path and args.app_path.exists():
        res = setup_app_bundle(args.app_path)
        print(f"Quarantine cleared: {res['quarantine_cleared']}")
        print(f"Ad-hoc signed:     {res['signed']}")

    check_and_print_permission_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
