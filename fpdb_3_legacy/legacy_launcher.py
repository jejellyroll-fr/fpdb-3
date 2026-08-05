from __future__ import annotations

"""Console entry point for the legacy FPDB launcher."""

import runpy
import sys
from contextlib import contextmanager
from os import chdir
from pathlib import Path


@contextmanager
def pushd(path: Path):
    """Temporarily run the legacy launcher from its own directory."""
    previous = Path.cwd()
    chdir(path)
    try:
        yield
    finally:
        chdir(previous)


def main() -> None:
    """Run the legacy full launcher from an installed console script.

    ``uv run fpdb_3_legacy`` executes this function from the repository root or
    an installed environment. The original legacy launchers expect their working
    directory to be ``fpdb_3_legacy`` because they spawn sibling scripts such as
    ``run_fpdb_api.py`` and ``fpdb.pyw``.
    """
    legacy_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(legacy_dir))
    with pushd(legacy_dir):
        runpy.run_path(str(legacy_dir / "fpdb.pyw"), run_name="__main__")


if __name__ == "__main__":
    main()
