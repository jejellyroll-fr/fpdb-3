"""A worker connection belongs to its own database, and only to it (#368)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from tests.helpers import analytics_golden as golden


@pytest.fixture
def two_databases(tmp_path: Path) -> tuple[Database, Database]:
    """Two live databases in one process, the way the test suite holds them."""
    databases = []
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        database = Database(golden.build_config(directory))
        database.recreate_tables()
        databases.append(database)
    return databases[0], databases[1]


def test_each_database_pools_its_own_worker_connections(two_databases) -> None:
    first, second = two_databases

    assert first._worker_conn_pool is not second._worker_conn_pool
    assert type(Database).__dict__.get("_worker_conn_pool") is None


def test_a_borrowed_connection_reads_the_database_it_was_borrowed_from(two_databases) -> None:
    """The failure this guards: a pooled connection to somebody else's data.

    One shared queue across instances meant the second database could hand a
    worker a connection opened against the first, and every query that worker
    ran then answered about the wrong hands -- silently, because the schema is
    identical.
    """
    first, second = two_databases
    first.get_cursor().execute("INSERT INTO Sites (id, name, code) VALUES (901, 'OnlyFirst', 'F1')")
    first.commit()
    second.get_cursor().execute("INSERT INTO Sites (id, name, code) VALUES (902, 'OnlySecond', 'S2')")
    second.commit()

    def names(database: Database) -> set[str]:
        with database.worker_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM Sites WHERE id IN (901, 902)")
            return {row[0] for row in cursor.fetchall()}

    # Borrow from each in turn: the second borrow is the one that used to be
    # served out of the first database's pool.
    assert names(first) == {"OnlyFirst"}
    assert names(second) == {"OnlySecond"}
    assert names(first) == {"OnlyFirst"}


def test_the_concurrency_bound_stays_process_wide(two_databases) -> None:
    """The semaphore is shared on purpose: it limits this process, not one file."""
    first, second = two_databases

    assert first._worker_conn_semaphore is second._worker_conn_semaphore
