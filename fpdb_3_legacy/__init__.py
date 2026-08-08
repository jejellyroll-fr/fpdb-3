# fpdb-3-legacy/__init__.py
from __future__ import annotations

"""
FPDB-3 Legacy Module Package

This package contains the legacy Python implementation of FPDB-3.
It is maintained for parity testing with the new Rust implementation.
"""

import datetime

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

__version__ = "3.6.0"
