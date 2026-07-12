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
from types import ModuleType

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


# Acceptable driver modules per backend. MySQL accepts the pure-Python pymysql
# as a drop-in fallback (via install_as_MySQLdb), so it works without the system
# libraries that mysqlclient needs.
_DRIVER_MODULES: dict[str, tuple[str, ...]] = {
    "sqlite": ("sqlite3",),
    "postgresql": ("psycopg",),
    "mysql": ("MySQLdb", "pymysql"),
}


def driver_available(server: str) -> bool:
    """Return True if a Python driver for ``server`` is importable."""
    modules = _DRIVER_MODULES.get(server)
    if not modules:
        return False
    return any(importlib.util.find_spec(module) is not None for module in modules)


def import_mysqldb() -> ModuleType:
    """Import MySQLdb, falling back to pymysql's MySQLdb-compatible shim."""
    try:
        import MySQLdb  # noqa: PLC0415 - optional driver imported on demand
    except ImportError:
        import pymysql  # noqa: PLC0415 - pure-Python fallback

        pymysql.install_as_MySQLdb()
        import MySQLdb  # noqa: PLC0415
    return MySQLdb


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
    MySQLdb = import_mysqldb()

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


# --- schema inspection -----------------------------------------------------
#
# Used before creating the fpdb schema so we never hand a database to
# ``Database`` when it holds foreign tables. That matters for SQLite: connecting
# with ``Database`` uses create=True, and a missing ``Settings`` table makes it
# drop every table in the file. Inspecting first, read-only, avoids that.

# Possible states returned by inspect_database.
STATE_UNREACHABLE = "unreachable"  # could not connect / driver missing
STATE_EMPTY = "empty"  # reachable, no user tables
STATE_INITIALISED = "initialised"  # already holds the fpdb schema (marker table)
STATE_FOREIGN = "foreign"  # holds tables, but not the fpdb schema

_MARKER_TABLE = "settings"  # fpdb's Settings table, compared case-insensitively


def inspect_database(
    server: str,
    *,
    database: str | None = None,
    host: str | None = None,
    port: str | int | None = None,
    user: str | None = None,
    password: str | None = None,
    sqlite_dir: str | None = None,
) -> tuple[str, str]:
    """Report the state of a target database **without modifying it**.

    Returns ``(state, detail)`` where ``state`` is one of STATE_UNREACHABLE /
    STATE_EMPTY / STATE_INITIALISED / STATE_FOREIGN. ``detail`` carries an error
    message when unreachable.
    """
    if server not in BACKENDS:
        return STATE_UNREACHABLE, f"Unsupported database backend: {server!r}"
    if not driver_available(server):
        return STATE_UNREACHABLE, f"Driver '{BACKENDS[server][1]}' is not installed for {server}."
    try:
        if server == "sqlite":
            tables = _sqlite_tables(database, sqlite_dir)
        elif server == "postgresql":
            tables = _postgresql_tables(database, host, port, user, password)
        else:
            tables = _mysql_tables(database, host, port, user, password)
    except Exception as exc:  # noqa: BLE001 - any driver error means we cannot inspect it
        return STATE_UNREACHABLE, str(exc)

    if not tables:
        return STATE_EMPTY, ""
    if _MARKER_TABLE in {t.lower() for t in tables}:
        return STATE_INITIALISED, ""
    return STATE_FOREIGN, ""


def _sqlite_tables(database: str | None, sqlite_dir: str | None) -> set[str]:
    import sqlite3

    name = database or "fpdb.db3"
    if name == ":memory:":
        return set()  # a fresh in-memory DB is always empty
    path = os.path.join(sqlite_dir, name) if sqlite_dir else name
    if not os.path.exists(path):
        return set()  # no file yet: nothing to inspect, and don't create one
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _postgresql_tables(database, host, port, user, password) -> set[str]:
    import psycopg

    conn = psycopg.connect(
        host=host or None,
        port=_coerce_port(port),
        user=user or None,
        password=password or None,
        dbname=database or None,
        connect_timeout=5,
    )
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _mysql_tables(database, host, port, user, password) -> set[str]:
    MySQLdb = import_mysqldb()

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
    conn = MySQLdb.connect(**kwargs)
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        rows = cursor.fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}
