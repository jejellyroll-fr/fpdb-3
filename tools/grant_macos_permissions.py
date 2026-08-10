"""Utility to assist with macOS Gatekeeper quarantine removal and privacy permissions setup.

macOS Gatekeeper and TCC (Transparency, Consent, and Control) are separate:
quarantine can translocate or block an unnotarized download, while TCC grants
Screen Recording, Accessibility, and Automation to a code-signing requirement.
A stable bundle ID alone cannot make an ad-hoc signature stable between builds.

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
    except (OSError, subprocess.SubprocessError) as exc:
        # A missing or unrunnable xattr is the only thing that lands here; a
        # non-zero exit is reported through returncode, not raised.
        print(f"Could not run xattr on {app_path}: {exc}", file=sys.stderr)
        return False
    return res.returncode == 0


def re_sign_bundle(app_path: Path) -> bool:
    """Replace the bundle signature with ad-hoc signing (development only).

    This intentionally destroys a Developer ID signature and its stable TCC
    identity. It is never part of the default setup path.
    """
    if not _IS_MACOS or not app_path.exists():
        return False
    codesign_bin = shutil.which("codesign") or "/usr/bin/codesign"
    try:
        res = subprocess.run(
            [codesign_bin, "--force", "--deep", "--sign", "-", str(app_path)],
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not run codesign on {app_path}: {exc}", file=sys.stderr)
        return False
    return res.returncode == 0


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


def setup_app_bundle(
    app_path: Path,
    *,
    clear: bool = True,
    sign: bool = False,
) -> dict[str, bool]:
    """Strip quarantine and, only when explicit, ad-hoc sign the bundle.

    Re-signing is off by default because it invalidates a published Developer
    ID signature and the privacy grants tied to it.
    """
    return {
        "quarantine_cleared": clear_quarantine(app_path) if clear else False,
        "signed": re_sign_bundle(app_path) if sign else False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-path", type=Path, help="Path to fpdb.app bundle.")
    parser.add_argument("--clear-quarantine", action="store_true", help="Remove quarantine extended attribute.")
    parser.add_argument("--re-sign", action="store_true", help="Re-sign app bundle ad-hoc.")
    parser.add_argument(
        "--check-status",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Check current macOS permissions status.",
    )

    args = parser.parse_args(argv)

    if not _IS_MACOS:
        print("macOS permission tools are only applicable on Darwin/macOS systems.")
        return 0

    if args.app_path:
        if not args.app_path.exists():
            # Silently doing nothing here reads as "it worked", and the whole
            # point of the tool is to tell the user where they stand.
            print(f"No bundle at {args.app_path}", file=sys.stderr)
            return 1
        # Neither flag means the safe local workaround: clear quarantine only.
        selected = args.clear_quarantine or args.re_sign
        res = setup_app_bundle(
            args.app_path,
            clear=args.clear_quarantine or not selected,
            sign=args.re_sign,
        )
        print(f"Quarantine cleared: {res['quarantine_cleared']}")
        print(f"Ad-hoc signed:     {res['signed']}")

    if args.check_status:
        check_and_print_permission_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
