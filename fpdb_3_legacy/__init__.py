# fpdb-3-legacy/__init__.py
from __future__ import annotations

"""
FPDB-3 Legacy Module Package

This package contains the legacy Python implementation of FPDB-3.
It is maintained for parity testing with the new Rust implementation.
"""

import datetime
import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from typing import Any

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

__version__ = "3.8.0"


def __getattr__(name: str) -> Any:
    if name == "HUD_main":
        if "HUD_main" in sys.modules:
            return sys.modules["HUD_main"]
        if "fpdb_3_legacy.HUD_main" in sys.modules:
            return sys.modules["fpdb_3_legacy.HUD_main"]
        hud_main_path = Path(__file__).parent / "HUD_main.pyw"
        if hud_main_path.exists():
            loader = importlib.machinery.SourceFileLoader(
                "fpdb_3_legacy.HUD_main", str(hud_main_path)
            )
            spec = importlib.util.spec_from_loader("fpdb_3_legacy.HUD_main", loader)
            if spec is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["fpdb_3_legacy.HUD_main"] = mod
                sys.modules["HUD_main"] = mod
                loader.exec_module(mod)
                return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
