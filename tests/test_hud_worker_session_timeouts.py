"""The HUD worker must bound its own session on every server backend (#680).

PostgreSQL has statement/lock timeouts on the worker's connection; MySQL used
to have none on that path, so one slow or lock-blocked read on a remote MySQL
server could stall the worker queue indefinitely. SQLite is local and
single-connection, so there is nothing to set.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from fpdb_3_legacy import HUD_main  # pylint: disable=no-name-in-module

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
    cursor.fetchone.return_value = ("8.4.3",)  # not MariaDB

    HudReadWorker._configure_session(database)

    # max_execution_time is in milliseconds and is MySQL's statement_timeout;
    # innodb_lock_wait_timeout is in seconds and is its lock_timeout.
    executed = [c.args[0] for c in cursor.execute.call_args_list]
    assert "SELECT VERSION()" in executed  # flavor detection first (#680)
    assert "SET SESSION max_execution_time = 10000" in executed
    assert "SET SESSION innodb_lock_wait_timeout = 2" in executed
    database.connection.commit.assert_called_once()


def test_sqlite_worker_session_is_left_alone() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.SQLITE)

    HudReadWorker._configure_session(database)

    database.connection.cursor.assert_not_called()


def _mysql_db_with_version(version: str):
    database = MagicMock(backend=HUD_main.Database.Database.MYSQL_INNODB)
    cursor = database.connection.cursor.return_value
    cursor.fetchone.return_value = (version,)
    return database, cursor


def test_mariadb_worker_uses_max_statement_time() -> None:
    """MariaDB has no max_execution_time; it uses max_statement_time in seconds (#680)."""
    database, cursor = _mysql_db_with_version("10.11.8-MariaDB")

    HudReadWorker._configure_session(database)

    executed = [c.args[0] for c in cursor.execute.call_args_list]
    assert "SELECT VERSION()" in executed
    assert "SET SESSION max_statement_time = 10" in executed
    assert "SET SESSION innodb_lock_wait_timeout = 2" in executed
    assert not any("max_execution_time" in s for s in executed)


def test_mysql_worker_keeps_max_execution_time() -> None:
    database, cursor = _mysql_db_with_version("8.4.3")

    HudReadWorker._configure_session(database)

    executed = [c.args[0] for c in cursor.execute.call_args_list]
    assert "SET SESSION max_execution_time = 10000" in executed
    assert not any("max_statement_time" in s for s in executed)


def test_mysql_flavor_detection_failure_falls_back_safely() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.MYSQL_INNODB)
    database.connection.cursor.side_effect = RuntimeError("no connection yet")

    from fpdb_3_legacy import hud_workers

    statements = hud_workers._mysql_session_timeouts(database)

    assert statements == (
        "SET SESSION max_execution_time = 10000",
        "SET SESSION innodb_lock_wait_timeout = 2",
    )
