#!/usr/bin/env python3
"""Tests for the SQL dialect abstraction (fpdb_3_legacy/dialects.py)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import dialects


def _db(backend):
    db = MagicMock()
    db.backend = backend
    return db


# --- factories -------------------------------------------------------------


def test_dialect_for_backend_maps_ids():
    assert dialects.dialect_for_backend(dialects.SQLITE).name == "sqlite"
    assert dialects.dialect_for_backend(dialects.PGSQL).name == "postgresql"
    assert dialects.dialect_for_backend(dialects.MYSQL).name == "mysql"


def test_dialect_for_server_maps_strings():
    assert dialects.dialect_for_server("postgresql").backend_id == dialects.PGSQL
    assert dialects.dialect_for_server("mysql").backend_id == dialects.MYSQL
    assert dialects.dialect_for_server("sqlite").backend_id == dialects.SQLITE


def test_unknown_backend_and_server_raise():
    with pytest.raises(ValueError, match="dialect"):
        dialects.dialect_for_backend(99)
    with pytest.raises(ValueError, match="dialect"):
        dialects.dialect_for_server("oracle")


# --- identifiers & placeholders -------------------------------------------


def test_placeholders_per_backend():
    assert dialects.dialect_for_backend(dialects.SQLITE).placeholder == "?"
    assert dialects.dialect_for_backend(dialects.PGSQL).placeholder == "%s"
    assert dialects.dialect_for_backend(dialects.MYSQL).placeholder == "%s"


def test_quote_identifier_per_backend():
    # Case-preserving so CREATE DATABASE/ROLE use the exact configured name.
    assert dialects.dialect_for_server("mysql").quote_identifier("Rank") == "`Rank`"
    assert dialects.dialect_for_server("sqlite").quote_identifier("Rank") == '"Rank"'
    assert dialects.dialect_for_server("postgresql").quote_identifier("Rank") == '"Rank"'
    assert dialects.dialect_for_server("mysql").quote_identifier("a`b") == "`a``b`"
    assert dialects.dialect_for_server("postgresql").quote_identifier('a"b') == '"a""b"'


def test_quote_literal_per_backend():
    # ANSI single-quote doubling for PostgreSQL/SQLite; backslash escaping for MySQL.
    assert dialects.dialect_for_server("postgresql").quote_literal("O'Brien") == "'O''Brien'"
    assert dialects.dialect_for_server("sqlite").quote_literal("a'b") == "'a''b'"
    assert dialects.dialect_for_server("mysql").quote_literal("O'Brien") == "'O\\'Brien'"
    assert dialects.dialect_for_server("mysql").quote_literal("a\\b") == "'a\\\\b'"


# --- boolean coercion ------------------------------------------------------


def test_coerce_row_converts_only_flagged_columns():
    row = dialects.Dialect.coerce_row((5, 1, 0, "x"), (1, 2))
    assert row == (5, True, False, "x")
    assert dialects.Dialect.coerce_row((5, None, 1), (1,)) == (5, None, 1)  # None preserved


def test_boolean_columns_only_postgresql():
    for server in ("sqlite", "mysql"):
        assert dialects.dialect_for_server(server).boolean_columns(_db(0), "T", ["a", "b"]) == ()

    db = _db(dialects.PGSQL)
    db.get_cursor.return_value.fetchall.return_value = [("fast",), ("ante",)]
    indices = dialects.dialect_for_server("postgresql").boolean_columns(db, "TourneyTypes", ["id", "fast", "ante"])
    assert indices == (1, 2)


# --- destructive rebuild ---------------------------------------------------


def test_drop_all_tables_mysql_brackets_fk_checks():
    db = _db(dialects.MYSQL)
    cursor = db.get_cursor.return_value
    cursor.fetchall.return_value = [("HandsStove",), ("Rank",)]
    dialects.dialect_for_server("mysql").drop_all_tables(db)
    statements = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert statements[0] == "SET FOREIGN_KEY_CHECKS = 0"
    assert "SET FOREIGN_KEY_CHECKS = 1" in statements
    assert any(s.startswith("DROP TABLE IF EXISTS HandsStove") for s in statements)
    assert not any("CASCADE" in s for s in statements)


def test_drop_all_tables_postgresql_uses_cascade():
    db = _db(dialects.PGSQL)
    cursor = db.get_cursor.return_value
    cursor.fetchall.return_value = [("hands",)]
    dialects.dialect_for_server("postgresql").drop_all_tables(db)
    statements = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("DROP TABLE IF EXISTS hands CASCADE" in s for s in statements)


# --- foreign keys ----------------------------------------------------------


def test_suspend_restore_fk_sqlite_toggles_pragma():
    db = _db(dialects.SQLITE)
    d = dialects.dialect_for_server("sqlite")
    assert d.suspend_foreign_keys(db) is None
    d.restore_foreign_keys(db, None)
    statements = [c.args[0] for c in db.get_cursor.return_value.execute.call_args_list if c.args]
    assert "PRAGMA foreign_keys = OFF" in statements
    assert "PRAGMA foreign_keys = ON" in statements


def test_suspend_restore_fk_postgresql_drops_and_readds():
    db = _db(dialects.PGSQL)
    cursor = db.get_cursor.return_value
    cursor.fetchall.return_value = [("handsstove", "hs_rank_fkey", "FOREIGN KEY (rankid) REFERENCES rank(id)")]
    d = dialects.dialect_for_server("postgresql")

    token = d.suspend_foreign_keys(db)
    drop_stmts = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("DROP CONSTRAINT" in s and "hs_rank_fkey" in s for s in drop_stmts)
    assert token

    cursor.reset_mock()
    d.restore_foreign_keys(db, token)
    add_stmts = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("ADD CONSTRAINT" in s and "FOREIGN KEY (rankid) REFERENCES rank(id)" in s for s in add_stmts)


# --- sequences -------------------------------------------------------------


def test_reset_sequences_noop_for_non_postgresql():
    for server in ("sqlite", "mysql"):
        db = _db(0)
        dialects.dialect_for_server(server).reset_sequences(db, ["Hands"])
        db.get_cursor.assert_not_called()


def test_repair_sequence_noop_for_non_postgresql():
    for server in ("sqlite", "mysql"):
        db = _db(0)
        dialects.dialect_for_server(server).repair_sequence(db, "Files")
        db.get_cursor.assert_not_called()


def test_set_autocommit_toggles_flag_after_committing():
    conn = MagicMock()
    dialects.dialect_for_server("postgresql").set_autocommit(conn, True)
    conn.commit.assert_called_once()  # must not toggle mid-transaction
    assert conn.autocommit is True
    dialects.dialect_for_server("postgresql").set_autocommit(conn, False)
    assert conn.autocommit is False


def test_set_autocommit_falls_back_without_autocommit_attribute():
    class OldConn:
        def __init__(self):
            self.levels = []

        def set_isolation_level(self, level):
            self.levels.append(level)

    conn = OldConn()
    dialects.dialect_for_server("postgresql").set_autocommit(conn, True)
    dialects.dialect_for_server("postgresql").set_autocommit(conn, False)
    assert conn.levels == [0, 1]  # legacy psycopg2 integer API


def test_reset_sequences_postgresql_sets_each_sequence():
    db = _db(dialects.PGSQL)
    cursor = db.get_cursor.return_value
    cursor.fetchone.return_value = ("hands_id_seq",)
    dialects.dialect_for_server("postgresql").reset_sequences(db, ["Hands"])
    statements = [c.args[0] for c in cursor.execute.call_args_list if c.args]
    assert any("pg_get_serial_sequence" in s for s in statements)
    assert any("setval" in s for s in statements)


def test_repair_sequence_postgresql_locks_and_sets_next_unused_id():
    db = _db(dialects.PGSQL)
    cursor = db.get_cursor.return_value
    cursor.fetchone.return_value = ("files_id_seq",)

    dialects.dialect_for_server("postgresql").repair_sequence(db, "Files")

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert statements[0] == 'LOCK TABLE "files" IN SHARE ROW EXCLUSIVE MODE'
    assert "pg_get_serial_sequence" in statements[1]
    assert "MAX(id)" in statements[2]
    assert "+ 1, false" in statements[2]
    assert cursor.execute.call_args_list[2].args[1] == ("files_id_seq",)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
