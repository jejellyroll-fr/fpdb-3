"""Compatibility shim for the iPoker hand history converter.

The implementation lives in ``fpdb_3_legacy.iPoker.base`` so skin-specific
pieces can be split out under the iPoker package without changing legacy
imports such as ``from fpdb_3_legacy.iPokerToFpdb import iPoker``.
"""

from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker

__all__ = ["iPoker"]
