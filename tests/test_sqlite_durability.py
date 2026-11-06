"""Every SQLite connection fpdb opens survives a power cut (#436).

WAL mode with ``synchronous=OFF`` can leave the file corrupt after an operating
system crash; ``NORMAL`` cannot. The main connection and the worker connections
are opened by two different code paths, so both are checked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from tests.helpers import analytics_golden as golden

# PRAGMA synchronous reports a number: 0 OFF, 1 NORMAL, 2 FULL, 3 EXTRA.
SYNCHRONOUS_NORMAL = 1


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(golden.build_config(tmp_path))
    database.recreate_tables()
    return database


def _assert_crash_safe(cursor) -> None:
    cursor.execute("PRAGMA journal_mode")
    assert str(cursor.fetchone()[0]).lower() == "wal"
    cursor.execute("PRAGMA synchronous")
    assert cursor.fetchone()[0] == SYNCHRONOUS_NORMAL


def test_the_main_connection_is_crash_safe(database: Database) -> None:
    _assert_crash_safe(database.get_cursor())


def test_a_worker_connection_is_crash_safe(database: Database) -> None:
    with database.worker_connection() as connection:
        _assert_crash_safe(connection.cursor())
