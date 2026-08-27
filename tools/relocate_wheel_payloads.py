#!/usr/bin/env python3
"""Give a wheel's bundled shared libraries back the directory name they expect.

delvewheel (Windows) and auditwheel (Linux) install a wheel's shared libraries
*beside* the package, in a directory called ``<package>.libs``. PyOxidizer reads
that dot as a package separator and installs the payload at ``<package>/libs``
instead -- one level inside the package, where neither loader looks for it:

* Windows: the delvewheel shim in ``numpy/__init__.py`` calls
  ``os.add_dll_directory`` on ``<package>.libs`` beside the package.
* Linux: the extension module's RPATH is ``$ORIGIN/../../<package>.libs``.

Either way the first ``import numpy`` dies -- "DLL load failed while importing
_multiarray_umath", or "cannot open shared object file" -- and since pandas
imports numpy, the application never opens a window. That is the whole of the
Windows PyOxidizer bundle's failure to start.

Renaming the directory is all it takes. It is done here rather than in
pyoxidizer.bzl because the Starlark side chooses which resources are collected,
not where the installer writes them.

macOS needs nothing: delocate puts its dylibs *inside* the package, so they are
ordinary package resources and arrive intact.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# The directory names delvewheel and auditwheel/delocate use for a payload.
PAYLOAD_NAMES = ("libs", "dylibs")


def is_shared_library(path: Path) -> bool:
    """Whether a file is a shared library, versioned suffixes included."""
    name = path.name.lower()
    if name.endswith((".dll", ".dylib", ".pyd")):
        return True
    # "libscipy_openblas64_-56d6093b.so", "libfoo.so.1.2" -- both are payload.
    return ".so" in name


def is_payload_directory(path: Path) -> bool:
    """Whether a directory holds a wheel's shared libraries and nothing else.

    A package that genuinely contains a ``libs`` subpackage has Python in it;
    a payload never does. Checking rather than assuming is what keeps this from
    moving a real subpackage out of its package and breaking its imports.
    """
    if not path.is_dir():
        return False
    entries = list(path.iterdir())
    if any(entry.is_dir() or entry.suffix == ".py" for entry in entries):
        return False
    return any(is_shared_library(entry) for entry in entries)


def relocate(lib_dir: Path) -> list[tuple[Path, Path]]:
    """Move every misplaced payload back beside its package.

    Returns the (source, destination) pairs moved, so the caller can report
    them: a build log that says nothing moved and then fails to import numpy is
    a different problem from one that moved the payload and still failed.
    """
    moved: list[tuple[Path, Path]] = []
    if not lib_dir.is_dir():
        return moved

    for package in sorted(lib_dir.iterdir()):
        if not package.is_dir():
            continue
        for payload_name in PAYLOAD_NAMES:
            payload = package / payload_name
            if not is_payload_directory(payload):
                continue
            target = lib_dir / f"{package.name}.{payload_name}"
            if target.exists():
                # Already where it belongs, from a PyOxidizer that got it right
                # or from an earlier run of this script.
                continue
            shutil.move(str(payload), str(target))
            moved.append((payload, target))
    return moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install_dir", type=Path, help="the PyOxidizer install directory")
    args = parser.parse_args(argv)

    lib_dir = args.install_dir / "lib"
    moved = relocate(lib_dir)
    for source, target in moved:
        print(f"moved {source.relative_to(args.install_dir)} -> {target.relative_to(args.install_dir)}")
    if not moved:
        print(f"no misplaced wheel library payload under {lib_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
