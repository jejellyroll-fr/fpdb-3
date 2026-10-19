"""The application package holds application code only (#438).

Everything under ``fpdb_3_legacy/`` is installed by setuptools and bundled by
PyInstaller and PyOxidizer. A test or a one-off script placed there ships to
every user and is never collected by pytest, which only looks in ``tests/`` and
``test/``. Tests belong in ``tests/``; developer scripts belong in ``tools/``.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "fpdb_3_legacy"

DEVELOPMENT_ONLY_PREFIXES = ("test_", "debug_", "fetch_", "migrate_", "validate_")


def test_the_package_ships_no_tests_or_development_scripts() -> None:
    misplaced = sorted(
        path.relative_to(PACKAGE.parent).as_posix()
        for path in PACKAGE.rglob("*.py")
        if path.name.startswith(DEVELOPMENT_ONLY_PREFIXES)
    )

    assert misplaced == [], (
        "Move tests to tests/ and developer scripts to tools/: " + ", ".join(misplaced)
    )
