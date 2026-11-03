"""The HUD worker must bound its own session on every server backend (#680).

PostgreSQL has statement/lock timeouts on the worker's connection; MySQL used
to have none on that path, so one slow or lock-blocked read on a remote MySQL
server could stall the worker queue indefinitely. SQLite is local and
single-connection, so there is nothing to set.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from fpdb_3_legacy import HUD_main

HudReadWorker = HUD_main.HudReadWorker


def test_postgresql_worker_bounds_statement_lock_and_idle_timeouts() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.PGSQL)
    cursor = database.connection.cursor.return_value

    HudReadWorker._configure_session(database)

    assert cursor.execute.call_args_list == [
        call("SET statement_timeout = 10000"),
        call("SET lock_timeout = 2000"),
        call("SET idle_in_transaction_session_timeout = 30000"),
    ]


def test_mysql_worker_bounds_statement_and_lock_waits() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.MYSQL_INNODB)
    cursor = database.connection.cursor.return_value

    HudReadWorker._configure_session(database)

    # max_execution_time is in milliseconds and is MySQL's statement_timeout;
    # innodb_lock_wait_timeout is in seconds and is its lock_timeout.
    assert cursor.execute.call_args_list == [
        call("SET SESSION max_execution_time = 10000"),
        call("SET SESSION innodb_lock_wait_timeout = 2"),
    ]
    database.connection.commit.assert_called_once()


def test_sqlite_worker_session_is_left_alone() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.SQLITE)

    HudReadWorker._configure_session(database)

    database.connection.cursor.assert_not_called()
