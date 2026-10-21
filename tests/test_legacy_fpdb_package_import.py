"""`import fpdb` from the legacy package resolves to the package, not to `fpdb.pyw`.

On Windows ".pyw" is an importable source suffix. With `fpdb_3_legacy/` at the
front of `sys.path` -- where `uv run fpdb_3_legacy`, `python fpdb.pyw` and the
HUD script all put it -- `import fpdb` then finds the GUI script before the
package, and the start-up died on `from fpdb.compat import toml_module` in
`phh_import` with a circular ImportError.

These tests emulate Windows by adding ".pyw" to the source suffixes, in process:
nothing here starts an interpreter or the GUI script.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import fpdb_3_legacy

ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = ROOT / "fpdb_3_legacy"
PACKAGE_INIT = ROOT / "fpdb" / "__init__.py"


@pytest.fixture
def windows_suffixes() -> Iterator[None]:
    """Make the path finders treat ".pyw" as source, as they do on Windows."""
    suffixes = importlib.machinery.SOURCE_SUFFIXES
    added = ".pyw" not in suffixes
    if added:
        suffixes.append(".pyw")
    sys.path_importer_cache.clear()
    try:
        yield
    finally:
        if added:
            suffixes.remove(".pyw")
        sys.path_importer_cache.clear()


@pytest.fixture
def fresh_fpdb(monkeypatch: pytest.MonkeyPatch, windows_suffixes: None) -> None:
    """Forget `fpdb` so the next import searches `sys.path`; restored afterwards."""
    for name in [name for name in sys.modules if name == "fpdb" or name.startswith("fpdb.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "path", list(sys.path))


def _same_file(module_file: str | None, expected: Path) -> bool:
    return module_file is not None and Path(module_file).resolve() == expected.resolve()


def test_the_emulation_reproduces_the_windows_shadowing(fresh_fpdb: None) -> None:
    sys.path.insert(0, str(LEGACY_DIR))

    spec = importlib.machinery.PathFinder.find_spec("fpdb", sys.path)

    assert spec is not None
    assert _same_file(spec.origin, LEGACY_DIR / "fpdb.pyw")


def test_the_package_is_imported_with_the_legacy_directory_first(fresh_fpdb: None) -> None:
    sys.path.insert(0, str(LEGACY_DIR))

    fpdb_3_legacy._import_fpdb_package()

    module = sys.modules["fpdb"]
    assert hasattr(module, "__path__")
    assert _same_file(module.__file__, PACKAGE_INIT)


def test_the_working_directory_entry_is_left_out_too(fresh_fpdb: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # `python -c` and the launcher's chdir: "" on sys.path is the legacy directory.
    monkeypatch.chdir(LEGACY_DIR)
    sys.path.insert(0, "")

    fpdb_3_legacy._import_fpdb_package()

    assert _same_file(sys.modules["fpdb"].__file__, PACKAGE_INIT)


def test_fpdb_compat_resolves_after_the_guard(fresh_fpdb: None) -> None:
    sys.path.insert(0, str(LEGACY_DIR))

    fpdb_3_legacy._import_fpdb_package()
    compat = importlib.import_module("fpdb.compat")

    assert _same_file(compat.__file__, ROOT / "fpdb" / "compat.py")
    assert callable(compat.toml_module)


def test_sys_path_is_restored(fresh_fpdb: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(LEGACY_DIR)
    sys.path[:0] = [str(LEGACY_DIR), ""]
    before = list(sys.path)

    fpdb_3_legacy._import_fpdb_package()

    assert sys.path == before


def test_an_already_imported_fpdb_is_kept(fresh_fpdb: None, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setitem(sys.modules, "fpdb", sentinel)

    fpdb_3_legacy._import_fpdb_package()

    assert sys.modules["fpdb"] is sentinel


def test_a_missing_package_is_left_to_its_importers(fresh_fpdb: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # An editable install finds `fpdb` through sys.meta_path whatever sys.path says.
    def missing(name: str) -> None:
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(fpdb_3_legacy.importlib, "import_module", missing)
    before = list(sys.path)

    fpdb_3_legacy._import_fpdb_package()

    assert "fpdb" not in sys.modules
    assert sys.path == before


@pytest.mark.parametrize("entry", [b"bytes-entry", 42, "\0"])
def test_unusual_sys_path_entries_are_kept(entry: object) -> None:
    here = os.path.normcase(os.path.realpath(LEGACY_DIR))

    assert fpdb_3_legacy._is_directory(entry, here) is False
