#!/usr/bin/env python3
"""Regression tests for the psycopg2/psycopg3 isolation-level compat shim.

psycopg3 removed the integer isolation level 0 (autocommit); fpdb still calls
``set_isolation_level(0)`` around DDL. ``Database._pg_set_isolation`` maps the
old integers onto the ``autocommit`` flag so both drivers work.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Database


def _bare_db(connection):
    db = Database.Database.__new__(Database.Database)  # bypass the heavy __init__
    db.connection = connection
    db.backend = 3  # PostgreSQL — the only backend that calls _pg_set_isolation
    return db


def test_level_zero_enables_autocommit_after_committing():
    conn = MagicMock()
    db = _bare_db(conn)
    db._pg_set_isolation(0)
    conn.commit.assert_called_once()  # must not toggle autocommit mid-transaction
    assert conn.autocommit is True


def test_nonzero_level_returns_to_transactional_mode():
    conn = MagicMock()
    db = _bare_db(conn)
    db._pg_set_isolation(1)
    assert conn.autocommit is False


def test_falls_back_to_native_api_without_autocommit():
    class OldPsycopg2Conn:
        def __init__(self):
            self.levels = []

        def set_isolation_level(self, level):
            self.levels.append(level)

    conn = OldPsycopg2Conn()
    db = _bare_db(conn)
    db._pg_set_isolation(0)
    assert conn.levels == [0]  # legacy driver keeps its own semantics


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
