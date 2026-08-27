#!/usr/bin/env python3
"""Put back the shared libraries a wheel bundles, where their loader expects them.

delvewheel (Windows) and auditwheel (Linux) install a wheel's shared libraries
*beside* the package, in a directory called ``<package>.libs``. PyOxidizer does
not keep them there:

* On Linux it collects them but reads the dot as a package separator, so the
  payload lands inside the package as ``<package>/libs``.
* On Windows it does not collect them at all.

Either way the first ``import numpy`` dies -- "DLL load failed while importing
_multiarray_umath", or "cannot open shared object file" -- and since pandas
imports numpy, the application never opens a window. That was the whole of the
Windows PyOxidizer bundle's failure to start, and the Linux bundle had the same
hole with nothing checking for it.

So two repairs, in order:

1. Move a misplaced payload back beside its package.
2. Restore what is missing outright, from the wheel it came from.

Nothing here is guessed. Every wheel installs a ``RECORD`` listing each file it
wrote with its SHA-256, and those RECORDs are in the bundle: they say exactly
which payload files should exist and what their contents must hash to. A file
restored from a re-downloaded wheel is checked against that hash, so a wheel
that does not match the bundle fails the build instead of shipping a library
that does not belong to it.

macOS needs neither repair: delocate keeps its dylibs inside the package, where
they are ordinary package resources and arrive intact.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import re
import shutil
import subprocess  # nosec B404 - fixed argv, no shell; see download_wheel
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

# The directory names delvewheel and auditwheel/delocate give a payload.
PAYLOAD_NAMES = ("libs", "dylibs")

# The interpreter PyOxidizer 0.24 embeds. The payload is not tied to the Python
# ABI, but the wheel it ships in is, and asking for the same one the bundle was
# built from is the only way to be sure the hashes agree.
EMBEDDED_PYTHON_VERSION = "310"

# What may be put on a pip command line. Both values are read out of a directory
# name inside the bundle we just built, so this is a sanity check rather than a
# trust boundary -- but a command line is no place for an unchecked string, and
# a dist-info directory that does not parse should say so rather than become a
# strange pip invocation.
DISTRIBUTION_NAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
DISTRIBUTION_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+-]*$")


@dataclass(frozen=True)
class PayloadFile:
    """One shared library a wheel installed beside its package."""

    path: str
    """Path as the RECORD writes it, e.g. ``numpy.libs/libscipy_openblas64_-abc.dll``."""

    sha256: str
    """The RECORD's own digest: urlsafe base64, unpadded."""


def is_shared_library(path: Path) -> bool:
    """Whether a file is a shared library, versioned suffixes included."""
    name = path.name.lower()
    if name.endswith((".dll", ".dylib", ".pyd")):
        return True
    # "libscipy_openblas64_-56d6093b.so", "libfoo.so.1.2" -- both are payload.
    return ".so" in name


def is_payload_directory(path: Path) -> bool:
    """Whether a directory holds a wheel's shared libraries and nothing else.

    A package that genuinely contains a ``libs`` subpackage has Python in it; a
    payload never does. Checking rather than assuming is what keeps this from
    moving a real subpackage out of its package and breaking every import of it.
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
    a different problem from one that moved a payload and still failed.
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


def payload_files(record: Path) -> list[PayloadFile]:
    """The payload files a wheel's RECORD says it installed."""
    found: list[PayloadFile] = []
    with record.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or not row[0]:
                continue
            path, digest = row[0], row[1]
            head = path.split("/")[0]
            if not any(head.endswith(f".{name}") for name in PAYLOAD_NAMES):
                continue
            if not digest.startswith("sha256="):
                continue
            found.append(PayloadFile(path=path, sha256=digest[len("sha256=") :]))
    return found


def distribution_of(dist_info: Path) -> tuple[str, str]:
    """The (name, version) a ``*.dist-info`` directory belongs to."""
    stem = dist_info.name[: -len(".dist-info")]
    name, _, version = stem.rpartition("-")
    return name, version


def missing_payloads(lib_dir: Path) -> dict[Path, list[PayloadFile]]:
    """Payload files each distribution's RECORD claims and the bundle lacks."""
    missing: dict[Path, list[PayloadFile]] = {}
    if not lib_dir.is_dir():
        return missing
    for dist_info in sorted(lib_dir.glob("*.dist-info")):
        record = dist_info / "RECORD"
        if not record.is_file():
            continue
        absent = [entry for entry in payload_files(record) if not (lib_dir / entry.path).is_file()]
        if absent:
            missing[dist_info] = absent
    return missing


def digest_of(data: bytes) -> str:
    """The digest in the form a RECORD writes it."""
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def target_within(lib_dir: Path, relative_path: str) -> Path:
    """Resolve a RECORD path inside ``lib_dir``, refusing anything that escapes it.

    A RECORD is read out of the bundle and its paths are joined to a directory
    we then write into. "../" in one of them would write outside the bundle, so
    it is checked rather than trusted.
    """
    root = lib_dir.resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        msg = f"{relative_path} would be written outside {lib_dir}"
        raise ValueError(msg)
    return target


def restore_from_wheel(wheel: Path, entries: list[PayloadFile], lib_dir: Path) -> list[Path]:
    """Write ``entries`` from ``wheel`` into ``lib_dir``, refusing a mismatch."""
    restored: list[Path] = []
    with zipfile.ZipFile(wheel) as archive:
        available = set(archive.namelist())
        for entry in entries:
            if entry.path not in available:
                msg = f"{wheel.name} does not contain {entry.path}"
                raise LookupError(msg)
            target = target_within(lib_dir, entry.path)
            data = archive.read(entry.path)
            actual = digest_of(data)
            if actual != entry.sha256:
                msg = (
                    f"{entry.path} in {wheel.name} hashes to {actual}, "
                    f"but the bundle's RECORD says {entry.sha256}"
                )
                raise ValueError(msg)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            restored.append(target)
    return restored


def download_wheel(name: str, version: str, dest: Path, python_version: str = EMBEDDED_PYTHON_VERSION) -> Path:
    """Fetch one wheel of ``name==version`` for the embedded interpreter."""
    if not DISTRIBUTION_NAME.match(name) or not DISTRIBUTION_VERSION.match(version):
        msg = f"refusing to fetch a distribution named {name!r} at version {version!r}"
        raise ValueError(msg)

    dest.mkdir(parents=True, exist_ok=True)
    # Absolute interpreter, fixed argv, no shell, and both interpolated values
    # checked against the patterns above.
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    subprocess.run(  # noqa: S603  # nosec B603
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            f"{name}=={version}",
            "--no-deps",
            "--only-binary=:all:",
            "--python-version",
            python_version,
            "--dest",
            str(dest),
        ],
        check=True,
    )
    wheels = sorted(dest.glob(f"{name.replace('-', '_')}-{version}-*.whl"))
    if not wheels:
        wheels = sorted(dest.glob("*.whl"))
    if not wheels:
        msg = f"pip downloaded no wheel for {name}=={version} into {dest}"
        raise FileNotFoundError(msg)
    return wheels[0]


def repair(
    install_dir: Path,
    wheel_dir: Path,
    *,
    fetch=download_wheel,
    python_version: str = EMBEDDED_PYTHON_VERSION,
) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Relocate what is misplaced, restore what is missing. Reports both."""
    lib_dir = install_dir / "lib"
    moved = relocate(lib_dir)

    restored: list[Path] = []
    for dist_info, entries in missing_payloads(lib_dir).items():
        name, version = distribution_of(dist_info)
        wheel = fetch(name, version, wheel_dir, python_version)
        restored.extend(restore_from_wheel(wheel, entries, lib_dir))
    return moved, restored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install_dir", type=Path, help="the PyOxidizer install directory")
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        default=None,
        help="where to keep downloaded wheels (default: <install_dir>/../wheel-cache)",
    )
    parser.add_argument(
        "--python-version",
        default=EMBEDDED_PYTHON_VERSION,
        help=f"interpreter the bundle embeds, for wheel selection (default: {EMBEDDED_PYTHON_VERSION})",
    )
    args = parser.parse_args(argv)

    wheel_dir = args.wheel_dir or args.install_dir.parent / "wheel-cache"
    moved, restored = repair(args.install_dir, wheel_dir, python_version=args.python_version)

    for source, target in moved:
        print(f"moved {source.relative_to(args.install_dir)} -> {target.relative_to(args.install_dir)}")
    for target in restored:
        print(f"restored {target.relative_to(args.install_dir)} from its wheel")
    if not moved and not restored:
        print(f"every wheel library payload was already in place under {args.install_dir / 'lib'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
