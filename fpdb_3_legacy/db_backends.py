"""Backend-agnostic helpers for the database configuration GUI.

Pure helpers (no Config or Database instance required) to discover which
database drivers are installed and to test a set of connection parameters
before persisting them. This keeps the GUI decoupled from the heavyweight
``Database`` class, which mutates a lot of global/instance state on connect.

The ``db_server`` strings match the ``<database db_server="...">`` values in
HUD_config.xml, and the numeric ids match the backend constants used by
``Database`` (MYSQL_INNODB=2, PGSQL=3, SQLITE=4) via ``Config.get_backend``.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

# db_server -> (human label, driver module name, needs host/port/user/pass fields)
BACKENDS: dict[str, tuple[str, str, bool]] = {
    "sqlite": ("SQLite", "sqlite3", False),
    "postgresql": ("PostgreSQL", "psycopg", True),
    "mysql": ("MySQL / MariaDB", "MySQLdb", True),
}

# db_server -> numeric backend id (kept in sync with Database.{MYSQL_INNODB,PGSQL,SQLITE}).
BACKEND_IDS: dict[str, int] = {"mysql": 2, "postgresql": 3, "sqlite": 4}


def backend_id(server: str) -> int:
    """Return the numeric backend id for a ``db_server`` string."""
    try:
        return BACKEND_IDS[server]
    except KeyError:
        msg = f"Unsupported database backend: {server}"
        raise ValueError(msg) from None


def driver_available(server: str) -> bool:
    """Return True if the Python driver for ``server`` is importable."""
    try:
        module_name = BACKENDS[server][1]
    except KeyError:
        return False
    return importlib.util.find_spec(module_name) is not None


def available_backends() -> dict[str, bool]:
    """Map each supported ``db_server`` to whether its driver is installed."""
    return {server: driver_available(server) for server in BACKENDS}


@dataclass
class ConnectionResult:
    """Outcome of a connection test: success flag plus a human-readable message."""

    ok: bool
    message: str


def test_connection(
    server: str,
    *,
    database: str | None = None,
    host: str | None = None,
    port: str | int | None = None,
    user: str | None = None,
    password: str | None = None,
    sqlite_dir: str | None = None,
) -> ConnectionResult:
    """Attempt a real connection with the given parameters and report the result.

    The connection is opened and immediately closed; nothing is written. For
    SQLite, if the test has to create a brand-new empty database file it is
    removed again so the test stays non-destructive.

    Args:
        server: One of ``sqlite`` / ``postgresql`` / ``mysql``.
        database: Database name (SQLite: file name, or ``:memory:``).
        host, port, user, password: Server connection parameters (PG/MySQL).
        sqlite_dir: Directory that holds the SQLite file (``Config.dir_database``).

    Returns:
        ConnectionResult: ``ok`` and a message suitable for display.
    """
    if server not in BACKENDS:
        return ConnectionResult(ok=False, message=f"Unsupported database backend: {server!r}")
    if not driver_available(server):
        driver = BACKENDS[server][1]
        return ConnectionResult(ok=False, message=f"Driver '{driver}' is not installed for {server}.")

    try:
        if server == "sqlite":
            return _test_sqlite(database, sqlite_dir)
        if server == "postgresql":
            return _test_postgresql(database, host, port, user, password)
        return _test_mysql(database, host, port, user, password)
    except Exception as exc:  # noqa: BLE001 - surface any driver error as a friendly message
        return ConnectionResult(ok=False, message=str(exc))


def _coerce_port(port: str | int | None) -> int | None:
    if port in (None, ""):
        return None
    return int(port)


def _test_sqlite(database: str | None, sqlite_dir: str | None) -> ConnectionResult:
    import sqlite3

    name = database or "fpdb.db3"
    if name == ":memory:":
        path = ":memory:"
        pre_existing = True  # nothing to clean up
    else:
        path = os.path.join(sqlite_dir, name) if sqlite_dir else name
        pre_existing = os.path.exists(path)
        parent = os.path.dirname(path) or "."
        if not pre_existing and not os.path.isdir(parent):
            return ConnectionResult(ok=False, message=f"Directory does not exist: {parent}")

    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()
        # Do not leave an empty file behind if the test created it.
        if path != ":memory:" and not pre_existing and os.path.exists(path) and os.path.getsize(path) == 0:
            try:
                os.remove(path)
            except OSError:
                pass
    return ConnectionResult(ok=True, message=f"SQLite OK — {path}")


def _test_postgresql(database, host, port, user, password) -> ConnectionResult:
    import psycopg

    try:
        conn = psycopg.connect(
            host=host or None,
            port=_coerce_port(port),
            user=user or None,
            password=password or None,
            dbname=database or None,
            connect_timeout=5,
        )
    except psycopg.OperationalError as exc:
        text = str(exc)
        if "password authentication" in text or "role" in text:
            return ConnectionResult(ok=False, message=f"Access denied: {text.strip()}")
        if "does not exist" in text:
            return ConnectionResult(ok=False, message=f"Database not found: {text.strip()}")
        if "Connection refused" in text or "could not connect" in text:
            return ConnectionResult(ok=False, message=f"Server unreachable: {text.strip()}")
        return ConnectionResult(ok=False, message=text.strip())
    conn.close()
    return ConnectionResult(ok=True, message=f"PostgreSQL OK — {database}@{host or 'localhost'}")


def _test_mysql(database, host, port, user, password) -> ConnectionResult:
    import MySQLdb

    kwargs = {
        "host": host or "localhost",
        "user": user or None,
        "passwd": password or "",
        "db": database or None,
        "connect_timeout": 5,
    }
    coerced_port = _coerce_port(port)
    if coerced_port:
        kwargs["port"] = coerced_port
    try:
        conn = MySQLdb.connect(**kwargs)
    except MySQLdb.Error as exc:
        code = exc.args[0] if exc.args else 0
        text = exc.args[1] if len(exc.args) > 1 else str(exc)
        if code == 1045:
            return ConnectionResult(ok=False, message=f"Access denied: {text}")
        if code in (2002, 2003):
            return ConnectionResult(ok=False, message=f"Server unreachable: {text}")
        if code == 1049:
            return ConnectionResult(ok=False, message=f"Database not found: {text}")
        return ConnectionResult(ok=False, message=text)
    conn.close()
    return ConnectionResult(ok=True, message=f"MySQL OK — {database}@{host or 'localhost'}")
