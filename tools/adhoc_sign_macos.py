#!/usr/bin/env python3
"""Sign every Mach-O file in a macOS distribution tree.

PySide6 and friends ship *linker-signed* binaries. macOS treats those as
unsigned, so as soon as a download carries ``com.apple.quarantine`` Gatekeeper
refuses to load them ("library load disallowed by system policy") and prompts
about each library in turn. A real ad-hoc signature (``codesign --sign -``)
loads even while quarantined.

Local/PR builds default to ad-hoc signing. Release builds set
``FPDB_MACOS_SIGNING_IDENTITY`` to a Developer ID Application identity and
``FPDB_REQUIRE_STABLE_MACOS_SIGNING=1`` so an unstable build fails closed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Thin (both endiannesses) and universal Mach-O headers.
MACH_O_MAGICS = frozenset(
    {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xca\xfe\xba\xbf",
    },
)

# codesign takes many paths at once; chunk them to keep the argument list sane.
_BATCH = 64

SIGNING_IDENTITY_ENV = "FPDB_MACOS_SIGNING_IDENTITY"
REQUIRE_STABLE_SIGNING_ENV = "FPDB_REQUIRE_STABLE_MACOS_SIGNING"
ADHOC_IDENTITY = "-"


def is_mach_o(path: Path) -> bool:
    """Report whether ``path`` starts with a Mach-O magic number."""
    try:
        with path.open("rb") as handle:
            return handle.read(4) in MACH_O_MAGICS
    except OSError:
        return False


def find_mach_o_files(root: Path) -> list[Path]:
    """Return every Mach-O file under ``root``, symlinks excluded.

    Extensions are no help here: Qt framework binaries have none and are not
    even executable (``QtCore.framework/Versions/A/QtCore``), so the magic
    number is what decides.
    """
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink() and is_mach_o(path))


def resolve_signing_identity(identity: str | None = None) -> str:
    """Resolve the requested identity and enforce the release signing gate."""
    resolved = identity if identity is not None else os.getenv(SIGNING_IDENTITY_ENV, ADHOC_IDENTITY)
    resolved = resolved.strip() or ADHOC_IDENTITY
    if os.getenv(REQUIRE_STABLE_SIGNING_ENV) == "1" and resolved == ADHOC_IDENTITY:
        msg = (
            "stable macOS signing is required, but no Developer ID identity was configured; "
            f"set {SIGNING_IDENTITY_ENV}"
        )
        raise RuntimeError(msg)
    return resolved


def _codesign_command(
    paths: list[Path],
    *,
    identity: str,
    deep: bool = False,
    entitlements: Path | None = None,
) -> list[str]:
    command = ["/usr/bin/codesign", "--force"]
    if deep:
        command.append("--deep")
    if identity != ADHOC_IDENTITY:
        command.extend(("--options", "runtime", "--timestamp"))
        if entitlements is not None:
            command.extend(("--entitlements", str(entitlements)))
    command.extend(("--sign", identity, *(str(path) for path in paths)))
    return command


def _codesign(
    paths: list[Path],
    *,
    identity: str,
    deep: bool = False,
    entitlements: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        _codesign_command(paths, identity=identity, deep=deep, entitlements=entitlements),
        capture_output=True,
        text=True,
        check=False,
    )


def sign(paths: list[Path], *, identity: str | None = None) -> None:
    """Sign the given binaries, replaying a failed batch one file at a time.

    Raises:
        RuntimeError: naming the binaries codesign rejected. It reports only a
            batch exit status, so a failed batch is replayed one file at a time.
    """
    resolved_identity = resolve_signing_identity(identity)
    failures: list[str] = []
    for start in range(0, len(paths), _BATCH):
        batch = paths[start : start + _BATCH]
        if _codesign(batch, identity=resolved_identity).returncode == 0:
            continue
        for path in batch:
            result = _codesign([path], identity=resolved_identity)
            if result.returncode != 0:
                failures.append(f"{path}: {result.stderr.strip()}")
    if failures:
        msg = "codesign failed for:\n" + "\n".join(failures)
        raise RuntimeError(msg)


def sign_bundle(
    bundle: Path,
    *,
    identity: str | None = None,
    entitlements: Path | None = None,
) -> None:
    """Seal an app bundle after its nested Mach-O files have been signed."""
    resolved_identity = resolve_signing_identity(identity)
    if resolved_identity != ADHOC_IDENTITY and entitlements is not None and not entitlements.is_file():
        raise FileNotFoundError(f"macOS entitlements not found: {entitlements}")
    result = _codesign(
        [bundle],
        identity=resolved_identity,
        deep=True,
        entitlements=entitlements,
    )
    if result.returncode != 0:
        raise RuntimeError(f"codesign failed for {bundle}: {result.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory to sign in place.")
    parser.add_argument(
        "--identity",
        default=None,
        help=f"codesign identity (defaults to ${SIGNING_IDENTITY_ENV}, then ad-hoc '-').",
    )
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")

    binaries = find_mach_o_files(args.root)
    if not binaries:
        parser.error(f"no Mach-O files found under {args.root}")

    identity = resolve_signing_identity(args.identity)
    sign(binaries, identity=identity)
    label = "ad-hoc" if identity == ADHOC_IDENTITY else identity
    print(f"signed {len(binaries)} Mach-O files under {args.root} with {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
