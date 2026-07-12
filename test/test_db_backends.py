#!/usr/bin/env python3
"""Tests for the backend-agnostic DB helpers (fpdb_3_legacy/db_backends.py)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import db_backends


def test_backend_id_matches_database_constants():
    assert db_backends.backend_id("mysql") == 2
    assert db_backends.backend_id("postgresql") == 3
    assert db_backends.backend_id("sqlite") == 4


def test_backend_id_rejects_unknown():
    with pytest.raises(ValueError, match="Unsupported"):
        db_backends.backend_id("oracle")


def test_sqlite_driver_always_available():
    backends = db_backends.available_backends()
    assert backends["sqlite"] is True
    assert set(backends) == {"sqlite", "postgresql", "mysql"}


def test_available_backends_reflects_missing_driver():
    with patch.object(db_backends.importlib.util, "find_spec", return_value=None):
        backends = db_backends.available_backends()
    assert backends == {"sqlite": False, "postgresql": False, "mysql": False}


def test_mysql_available_via_pymysql():
    """MySQL must be offered when only the pure-Python pymysql driver is present."""
    with patch.object(
        db_backends.importlib.util,
        "find_spec",
        side_effect=lambda name: object() if name == "pymysql" else None,
    ):
        assert db_backends.driver_available("mysql") is True  # pymysql fallback
        assert db_backends.driver_available("postgresql") is False  # psycopg absent


def test_import_mysqldb_returns_usable_driver():
    """import_mysqldb returns a MySQLdb-compatible module (pymysql shim if needed)."""
    driver = db_backends.import_mysqldb()
    assert hasattr(driver, "connect")
    assert hasattr(driver, "Error")


# --- SQLite (real driver, real filesystem) ---------------------------------


def test_sqlite_connection_ok_in_memory():
    result = db_backends.test_connection("sqlite", database=":memory:")
    assert result.ok is True


def test_sqlite_connection_ok_existing_file(tmp_path):
    result = db_backends.test_connection("sqlite", database="fpdb.db3", sqlite_dir=str(tmp_path))
    assert result.ok is True
    # A brand-new empty test DB must not be left behind.
    assert not (tmp_path / "fpdb.db3").exists()


def test_sqlite_connection_fails_on_missing_directory():
    result = db_backends.test_connection(
        "sqlite", database="fpdb.db3", sqlite_dir="/no/such/directory/here",
    )
    assert result.ok is False
    assert "Directory does not exist" in result.message


def test_sqlite_preserves_existing_file(tmp_path):
    import sqlite3

    db_file = tmp_path / "existing.db3"
    # Create a real (non-empty) SQLite database up front.
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    result = db_backends.test_connection("sqlite", database="existing.db3", sqlite_dir=str(tmp_path))
    assert result.ok is True
    assert db_file.exists()  # pre-existing file untouched


# --- Unsupported / missing driver ------------------------------------------


def test_unsupported_backend():
    result = db_backends.test_connection("oracle")
    assert result.ok is False
    assert "Unsupported" in result.message


def test_missing_driver_reported():
    with patch.object(db_backends, "driver_available", return_value=False):
        result = db_backends.test_connection("postgresql", database="fpdb")
    assert result.ok is False
    assert "not installed" in result.message


# --- PostgreSQL / MySQL (driver mocked) ------------------------------------


def test_postgresql_success_with_mocked_driver():
    fake_psycopg = MagicMock()
    fake_conn = MagicMock()
    fake_psycopg.connect.return_value = fake_conn
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"psycopg": fake_psycopg},
    ):
        result = db_backends.test_connection(
            "postgresql", database="fpdb", host="localhost", port="5432", user="u", password="p",
        )
    assert result.ok is True
    fake_conn.close.assert_called_once()


def test_postgresql_access_denied_is_friendly():
    fake_psycopg = MagicMock()

    class OperationalError(Exception):
        pass

    fake_psycopg.OperationalError = OperationalError
    fake_psycopg.connect.side_effect = OperationalError("password authentication failed for user")
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"psycopg": fake_psycopg},
    ):
        result = db_backends.test_connection("postgresql", database="fpdb", user="u", password="bad")
    assert result.ok is False
    assert "Access denied" in result.message


def test_mysql_success_with_mocked_driver():
    fake_mysqldb = MagicMock()
    fake_conn = MagicMock()
    fake_mysqldb.connect.return_value = fake_conn
    fake_mysqldb.Error = Exception
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"MySQLdb": fake_mysqldb},
    ):
        result = db_backends.test_connection(
            "mysql", database="fpdb", host="localhost", port="3306", user="u", password="p",
        )
    assert result.ok is True
    fake_conn.close.assert_called_once()
    # Port must be coerced to int for the driver.
    assert fake_mysqldb.connect.call_args.kwargs["port"] == 3306


def test_mysql_access_denied_is_friendly():
    fake_mysqldb = MagicMock()

    class MySQLError(Exception):
        pass

    fake_mysqldb.Error = MySQLError
    fake_mysqldb.connect.side_effect = MySQLError(1045, "Access denied for user")
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"MySQLdb": fake_mysqldb},
    ):
        result = db_backends.test_connection("mysql", database="fpdb", user="u", password="bad")
    assert result.ok is False
    assert "Access denied" in result.message


# --- inspect_database (read-only schema state) -----------------------------


def test_inspect_sqlite_missing_file_is_empty(tmp_path):
    state, _ = db_backends.inspect_database("sqlite", database="nope.db3", sqlite_dir=str(tmp_path))
    assert state == db_backends.STATE_EMPTY
    assert not (tmp_path / "nope.db3").exists()  # must not create the file


def test_inspect_sqlite_empty_file(tmp_path):
    import sqlite3

    sqlite3.connect(str(tmp_path / "e.db3")).close()  # empty DB, no tables
    state, _ = db_backends.inspect_database("sqlite", database="e.db3", sqlite_dir=str(tmp_path))
    assert state == db_backends.STATE_EMPTY


def test_inspect_sqlite_detects_fpdb_schema(tmp_path):
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "fpdb.db3"))
    conn.execute("CREATE TABLE Settings (version INTEGER)")
    conn.commit()
    conn.close()
    state, _ = db_backends.inspect_database("sqlite", database="fpdb.db3", sqlite_dir=str(tmp_path))
    assert state == db_backends.STATE_INITIALISED


def test_inspect_sqlite_detects_foreign_tables(tmp_path):
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "user.db3"))
    conn.execute("CREATE TABLE my_notes (id INTEGER, body TEXT)")
    conn.commit()
    conn.close()
    state, _ = db_backends.inspect_database("sqlite", database="user.db3", sqlite_dir=str(tmp_path))
    assert state == db_backends.STATE_FOREIGN


def test_inspect_missing_driver_is_unreachable():
    with patch.object(db_backends, "driver_available", return_value=False):
        state, detail = db_backends.inspect_database("postgresql", database="fpdb")
    assert state == db_backends.STATE_UNREACHABLE
    assert "not installed" in detail


# --- create_database (CREATE DATABASE) -------------------------------------


def test_create_database_sqlite_is_noop():
    result = db_backends.create_database("sqlite", database="fpdb.db3")
    assert result.ok is True
    assert "automatically" in result.message


def test_create_database_requires_a_name():
    with patch.object(db_backends, "driver_available", return_value=True):
        result = db_backends.create_database("postgresql", database="")
    assert result.ok is False
    assert "name is required" in result.message


def test_create_database_reports_missing_driver():
    with patch.object(db_backends, "driver_available", return_value=False):
        result = db_backends.create_database("postgresql", database="fpdb")
    assert result.ok is False
    assert "Driver" in result.message


def test_create_database_postgresql_creates_when_absent():
    fake_psycopg = MagicMock()
    conn = fake_psycopg.connect.return_value
    conn.execute.return_value.fetchone.return_value = None  # database not present
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"psycopg": fake_psycopg},
    ):
        result = db_backends.create_database(
            "postgresql", database="fpdb", host="h", admin_user="admin", admin_password="p",
        )
    assert result.ok is True
    assert "created database 'fpdb'" in result.message
    statements = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
    assert any("CREATE DATABASE" in s for s in statements)
    # Connected to the maintenance database, not the target one.
    assert fake_psycopg.connect.call_args.kwargs["dbname"] == "postgres"


def test_create_database_postgresql_skips_when_present():
    fake_psycopg = MagicMock()
    conn = fake_psycopg.connect.return_value
    conn.execute.return_value.fetchone.return_value = (1,)  # already exists
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"psycopg": fake_psycopg},
    ):
        result = db_backends.create_database("postgresql", database="fpdb", admin_user="a", admin_password="p")
    assert result.ok is True
    assert "already existed" in result.message
    statements = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
    assert not any("CREATE DATABASE" in s for s in statements)


def test_create_database_postgresql_creates_missing_role_and_grants():
    fake_psycopg = MagicMock()
    conn = fake_psycopg.connect.return_value
    # First fetchone() = role lookup (absent), second = database lookup (absent).
    conn.execute.return_value.fetchone.side_effect = [None, None]
    with patch.object(db_backends, "driver_available", return_value=True), patch.dict(
        sys.modules, {"psycopg": fake_psycopg},
    ):
        result = db_backends.create_database(
            "postgresql", database="fpdb", admin_user="postgres", admin_password="p",
            app_user="fpdb", app_password="secret",
        )
    assert result.ok is True
    statements = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
    assert any("CREATE ROLE" in s and '"fpdb"' in s for s in statements)
    assert any("CREATE DATABASE" in s and 'OWNER "fpdb"' in s for s in statements)
    assert any("GRANT ALL PRIVILEGES ON DATABASE" in s for s in statements)


def test_create_database_mysql_issues_create_if_not_exists():
    fake_mysqldb = MagicMock()
    with patch.object(db_backends, "driver_available", return_value=True), patch.object(
        db_backends, "import_mysqldb", return_value=fake_mysqldb,
    ):
        result = db_backends.create_database(
            "mysql", database="fpdb", host="h", admin_user="root", admin_password="p",
        )
    assert result.ok is True
    cursor = fake_mysqldb.connect.return_value.cursor.return_value
    statements = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("CREATE DATABASE IF NOT EXISTS" in s for s in statements)


def test_create_database_mysql_creates_user_and_grants():
    fake_mysqldb = MagicMock()
    with patch.object(db_backends, "driver_available", return_value=True), patch.object(
        db_backends, "import_mysqldb", return_value=fake_mysqldb,
    ):
        result = db_backends.create_database(
            "mysql", database="fpdb", host="h", admin_user="root", admin_password="p",
            app_user="fpdb", app_password="secret",
        )
    assert result.ok is True
    cursor = fake_mysqldb.connect.return_value.cursor.return_value
    statements = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("CREATE USER IF NOT EXISTS 'fpdb'@'%'" in s for s in statements)
    assert any("GRANT ALL PRIVILEGES ON `fpdb`.* TO 'fpdb'@'%'" in s for s in statements)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
