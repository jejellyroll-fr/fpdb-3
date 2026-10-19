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


def _pragma(cursor, name: str):
    cursor.execute("PRAGMA " + name)
    return cursor.fetchone()[0]


def test_the_main_connection_is_crash_safe(database: Database) -> None:
    cursor = database.get_cursor()

    assert str(_pragma(cursor, "journal_mode")).lower() == "wal"
    assert _pragma(cursor, "synchronous") == SYNCHRONOUS_NORMAL


def test_a_worker_connection_is_crash_safe(database: Database) -> None:
    with database.worker_connection() as connection:
        cursor = connection.cursor()

        assert str(_pragma(cursor, "journal_mode")).lower() == "wal"
        assert _pragma(cursor, "synchronous") == SYNCHRONOUS_NORMAL
