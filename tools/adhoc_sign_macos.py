#!/usr/bin/env python3
"""Ad-hoc sign every Mach-O file in a macOS distribution tree.

PySide6 and friends ship *linker-signed* binaries. macOS treats those as
unsigned, so as soon as a download carries ``com.apple.quarantine`` Gatekeeper
refuses to load them ("library load disallowed by system policy") and prompts
about each library in turn. A real ad-hoc signature (``codesign --sign -``)
loads even while quarantined.

This is not a replacement for Developer ID signing and notarization: it makes an
unsigned build usable, it does not make it trusted.
"""

from __future__ import annotations

import argparse
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


def _codesign(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/usr/bin/codesign", "--force", "--sign", "-", *(str(path) for path in paths)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def sign(paths: list[Path]) -> None:
    """Ad-hoc sign the given binaries.

    Raises:
        RuntimeError: naming the binaries codesign rejected. It reports only a
            batch exit status, so a failed batch is replayed one file at a time.
    """
    failures: list[str] = []
    for start in range(0, len(paths), _BATCH):
        batch = paths[start : start + _BATCH]
        if _codesign(batch).returncode == 0:
            continue
        for path in batch:
            result = _codesign([path])
            if result.returncode != 0:
                failures.append(f"{path}: {result.stderr.strip()}")
    if failures:
        msg = "codesign failed for:\n" + "\n".join(failures)
        raise RuntimeError(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory to sign in place.")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")

    binaries = find_mach_o_files(args.root)
    if not binaries:
        parser.error(f"no Mach-O files found under {args.root}")

    sign(binaries)
    print(f"ad-hoc signed {len(binaries)} Mach-O files under {args.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
