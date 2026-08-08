"""The OS backend must be imported through the package, not as a bare module.

On macOS the frozen build runs the HUD inside the *fpdb* executable
(``fpdb --hud``), whose dependency analysis only ever saw ``fpdb_3_legacy.*``
imports. A bare ``import OSXTables`` is therefore absent from that executable's
archive, and the HUD died on startup with::

    ModuleNotFoundError: No module named 'OSXTables'

Nothing in the test suite caught it, because from a source checkout the repo
root is on ``sys.path`` and both spellings resolve.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

HUD_MAIN = Path(__file__).parent.parent / "fpdb_3_legacy" / "HUD_main.pyw"
BACKENDS = ("OSXTables", "XTables", "WinTables")


def _imported_names() -> set[str]:
    """Every module name HUD_main imports, however deep in the file."""
    tree = ast.parse(HUD_MAIN.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_backend_is_imported_as_a_bare_top_level_module() -> None:
    imported = _imported_names()
    bare = sorted(name for name in imported if name in BACKENDS)
    assert bare == [], (
        f"HUD_main imports {bare} as bare top-level modules. The frozen macOS build "
        f"runs the HUD inside the fpdb executable, which has no such modules; import "
        f"them as 'from fpdb_3_legacy import <name> as Tables' instead."
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_every_backend_is_importable_through_the_package(backend: str) -> None:
    """The spelling HUD_main uses has to resolve on this platform's backend.

    Only the current platform's backend can actually be imported -- the others
    need Windows or X11 bindings -- so a missing dependency is not a failure
    here; a missing *module* is.
    """
    try:
        module = importlib.import_module(f"fpdb_3_legacy.{backend}")
    except ImportError as exc:
        if backend in str(exc):
            pytest.fail(f"fpdb_3_legacy.{backend} does not exist: {exc}")
        pytest.skip(f"{backend} needs platform bindings unavailable here: {exc}")
    else:
        assert module.__name__ == f"fpdb_3_legacy.{backend}"
