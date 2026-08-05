"""Regression tests for the destructive rebuild path (Database.drop_tables).

The MySQL path used to strip foreign keys by guessing the ``<table>_ibfk_N``
constraint names out of ``SHOW CREATE TABLE``. Any explicitly named constraint
survived, so the following ``DROP TABLE`` failed with errno 1451 ("Cannot delete
or update a parent row") and recreating the database was impossible.
"""

import sqlite3

import pytest

from fpdb_3_legacy import dialects


class FakeCursor:
    """Records the statements it is given; ``SHOW TABLES`` returns ``tables``."""

    def __init__(self, tables, fail_on=None) -> None:
        self.tables = tables
        self.fail_on = fail_on
        self.statements: list[str] = []
        self._rows: list[tuple] = []

    def execute(self, statement, *args) -> None:
        self.statements.append(statement)
        if self.fail_on and self.fail_on in statement:
            msg = "(1451, 'Cannot delete or update a parent row')"
            raise RuntimeError(msg)
        self._rows = [(name,) for name in self.tables] if statement.startswith("SHOW TABLES") else []

    def fetchall(self):
        return self._rows


class FakeDb:
    def __init__(self, cursor, backend) -> None:
        self.cursor = cursor
        self.backend = backend
        self.commits = 0

    def get_cursor(self):
        return self.cursor

    def commit(self) -> None:
        self.commits += 1


def test_mysql_drop_all_tables_disables_foreign_key_checks() -> None:
    cursor = FakeCursor(["Sites", "Gametypes", "Hands"])
    dialects.MySQLDialect().drop_all_tables(FakeDb(cursor, dialects.MYSQL))

    assert cursor.statements[0] == "SET FOREIGN_KEY_CHECKS = 0"
    assert cursor.statements[-1] == "SET FOREIGN_KEY_CHECKS = 1"
    assert "DROP TABLE IF EXISTS `Hands`" in cursor.statements


def test_mysql_drop_all_tables_quotes_reserved_words() -> None:
    cursor = FakeCursor(["Rank"])
    dialects.MySQLDialect().drop_all_tables(FakeDb(cursor, dialects.MYSQL))

    assert "DROP TABLE IF EXISTS `Rank`" in cursor.statements


def test_mysql_drop_all_tables_restores_checks_on_failure() -> None:
    cursor = FakeCursor(["Hands"], fail_on="DROP TABLE")
    with pytest.raises(RuntimeError):
        dialects.MySQLDialect().drop_all_tables(FakeDb(cursor, dialects.MYSQL))

    assert cursor.statements[-1] == "SET FOREIGN_KEY_CHECKS = 1"


def test_drop_tables_delegates_to_the_dialect() -> None:
    """Database.drop_tables must go through the Dialect, whatever the backend."""
    from fpdb_3_legacy.Database import Database

    cursor = FakeCursor(["Sites", "Hands"])
    db = Database.__new__(Database)
    db.backend = dialects.MYSQL
    db.get_cursor = lambda: cursor
    db.commit = lambda *args, **kwargs: None

    db.drop_tables()

    assert cursor.statements[0] == "SET FOREIGN_KEY_CHECKS = 0"
    assert "DROP TABLE IF EXISTS `Hands`" in cursor.statements


def test_sqlite_drop_all_tables_ignores_internal_tables() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE Sites (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    conn.execute("CREATE TABLE Hands (id INTEGER PRIMARY KEY, siteId INTEGER REFERENCES Sites(id))")
    conn.execute("INSERT INTO Sites DEFAULT VALUES")

    db = FakeDb(conn.cursor(), dialects.SQLITE)
    db.get_cursor = conn.cursor
    db.commit = conn.commit
    dialects.SqliteDialect().drop_all_tables(db)

    remaining = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert [row[0] for row in remaining] == ["sqlite_sequence"]
    conn.close()
