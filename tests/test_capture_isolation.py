"""fpdb's core imports without the captures that reach into a client (#451).

The SwC tap, its injector and the CoinPoker packet capture live in
``fpdb_3_legacy.capture``. The core decodes what they wrote and reaches into
that package only from the action that starts a capture, so an install that
leaves it out still starts, imports files and runs the HUD.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "fpdb_3_legacy"
CAPTURE = LEGACY / "capture"

#: What a source install runs: the main window, the HUD, Auto Import and the
#: decoders a capture's archive goes through.
CORE_ENTRY_POINTS = (
    "fpdb_3_legacy.GuiAutoImport",
    "fpdb_3_legacy.Importer",
    "fpdb_3_legacy.swc_native_capture",
    "fpdb_3_legacy.http_capture_db_import",
    "fpdb_3_legacy.live_capture_consent",
    "fpdb_3_legacy.dynamic_panels_consent",
)


def _core_sources() -> list[Path]:
    return [path for pattern in ("*.py", "*.pyw") for path in LEGACY.glob(pattern)]


def _module_level_imports(tree: ast.Module) -> list[ast.stmt]:
    """Imports that run when the module is imported: top level, or under a top-level if/try."""
    found: list[ast.stmt] = []
    pending: list[ast.stmt] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
        elif isinstance(node, (ast.If, ast.Try)):
            pending.extend(node.body)
            pending.extend(node.orelse)
            pending.extend(getattr(node, "finalbody", []))
            for handler in getattr(node, "handlers", []):
                pending.extend(handler.body)
    return found


def _names_capture(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.startswith("fpdb_3_legacy.capture") for alias in node.names)
    assert isinstance(node, ast.ImportFrom)
    module = node.module or ""
    if module.startswith("fpdb_3_legacy.capture"):
        return True
    return module == "fpdb_3_legacy" and any(alias.name == "capture" for alias in node.names)


def test_no_core_module_imports_the_capture_package_when_it_loads() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in _core_sources()
        for node in _module_level_imports(ast.parse(path.read_text(encoding="utf-8")))
        if _names_capture(node)
    ]

    assert offenders == []


def test_the_capture_modules_left_the_core() -> None:
    moved = {
        "swc_tap_build.py",
        "swc_windows_inject.py",
        "swc_inject.c",
        "swc_native_tap.c",
        "swc_http_capture.py",
        "swc_poker_console.py",
        "coinpoker_pcap.py",
        "coinpoker_live_capture.py",
        "GuiCoinPokerCapture.py",
    }

    assert moved <= {path.name for path in CAPTURE.iterdir()}
    assert not moved & {path.name for path in LEGACY.iterdir()}


def test_the_core_imports_with_the_capture_package_absent() -> None:
    import fpdb_3_legacy

    # Imported afresh, as a build without the package would. Everything is put
    # back exactly afterwards -- the modules, and the package attributes they
    # set -- so the rest of the run never meets a second copy of a module.
    saved_modules = dict(sys.modules)
    saved_attributes = dict(vars(fpdb_3_legacy))
    try:
        for name in [name for name in sys.modules if name.startswith("fpdb_3_legacy.")]:
            del sys.modules[name]
        # A None entry is how Python spells "this module cannot be imported".
        sys.modules["fpdb_3_legacy.capture"] = None  # type: ignore[assignment]

        for module in CORE_ENTRY_POINTS:
            importlib.import_module(module)

        assert not importlib.import_module("fpdb_3_legacy.live_capture_consent").capture_installed()
    finally:
        sys.modules.clear()
        sys.modules.update(saved_modules)
        for attribute in set(vars(fpdb_3_legacy)) - set(saved_attributes):
            delattr(fpdb_3_legacy, attribute)
        vars(fpdb_3_legacy).update(saved_attributes)


@pytest.mark.parametrize("installed", [True, False])
def test_capture_installed_answers_what_the_import_system_finds(monkeypatch, installed) -> None:
    from fpdb_3_legacy import live_capture_consent

    found = object() if installed else None
    monkeypatch.setattr("importlib.util.find_spec", lambda name: found if name == "fpdb_3_legacy.capture" else None)

    assert live_capture_consent.capture_installed() is installed
