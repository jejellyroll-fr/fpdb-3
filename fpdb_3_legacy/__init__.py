# fpdb-3-legacy/__init__.py
from __future__ import annotations

"""
FPDB-3 Legacy Module Package

This package contains the legacy Python implementation of FPDB-3.
It is maintained for parity testing with the new Rust implementation.
"""

import datetime
import importlib
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

__version__ = "3.9.1"


def _is_directory(entry: object, directory: str) -> bool:
    """Whether the `sys.path` entry *entry* names *directory* ("" is the working directory)."""
    if not isinstance(entry, str):
        return False
    try:
        return os.path.normcase(os.path.realpath(entry or os.curdir)) == directory
    except (OSError, ValueError):
        return False


def _import_fpdb_package() -> None:
    """Import the `fpdb` package before any module of this one asks for it.

    The launchers put this directory on `sys.path` -- `python fpdb.pyw` and the
    HUD script by being run from it, `legacy_launcher` and the frozen bootstraps
    explicitly. On Windows ".pyw" is an importable source suffix, so there
    `import fpdb` resolves to the GUI script `fpdb.pyw` instead of the `fpdb`
    package beside this one: the script runs again as a module, and the first
    `from fpdb.compat import ...` ends in a circular ImportError. Importing the
    package once with this directory left out of the search puts the right module
    in `sys.modules` for every later import.
    """
    if "fpdb" in sys.modules:
        return
    here = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(__file__))))
    saved = sys.path[:]
    sys.path[:] = [entry for entry in saved if not _is_directory(entry, here)]
    try:
        importlib.import_module("fpdb")
    except ImportError:
        # Not installed: the modules that need it report it when they import it.
        pass
    finally:
        sys.path[:] = saved


_import_fpdb_package()


def __getattr__(name: str) -> Any:
    if name == "HUD_main":
        if "HUD_main" in sys.modules:
            return sys.modules["HUD_main"]
        if "fpdb_3_legacy.HUD_main" in sys.modules:
            return sys.modules["fpdb_3_legacy.HUD_main"]
        hud_main_path = Path(__file__).parent / "HUD_main.pyw"
        if hud_main_path.exists():
            loader = importlib.machinery.SourceFileLoader("fpdb_3_legacy.HUD_main", str(hud_main_path))
            spec = importlib.util.spec_from_loader("fpdb_3_legacy.HUD_main", loader)
            if spec is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["fpdb_3_legacy.HUD_main"] = mod
                sys.modules["HUD_main"] = mod
                loader.exec_module(mod)
                return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
