"""Focused tests for additive database schema migrations."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database


class RecordingCursor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error


def migration_db(backend: int, cursor: RecordingCursor) -> tuple[Database, list[str]]:
    db = Database.__new__(Database)
    db.backend = backend
    db._get_table_columns = lambda _table: {"id", "CATEGORY"}
    db.get_cursor = lambda: cursor
    events: list[str] = []
    db.commit = lambda: events.append("commit")
    db.rollback = lambda: events.append("rollback")
    return db, events


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        (Database.MYSQL_INNODB, "ALTER TABLE Gametypes MODIFY category VARCHAR(10) NOT NULL"),
        (Database.PGSQL, "ALTER TABLE Gametypes ALTER COLUMN category TYPE VARCHAR(10)"),
    ],
)
def test_gametype_category_is_widened_for_server_databases(backend: int, expected: str) -> None:
    cursor = RecordingCursor()
    db, events = migration_db(backend, cursor)

    db._ensure_gametype_category_width()

    assert cursor.statements == [expected]
    assert events == ["commit"]


def test_gametype_category_lookup_failure_rolls_back() -> None:
    cursor = RecordingCursor()
    db, events = migration_db(Database.PGSQL, cursor)

    def fail_lookup(_table: str) -> set[str]:
        raise RuntimeError("missing table")

    db._get_table_columns = fail_lookup

    db._ensure_gametype_category_width()

    assert cursor.statements == []
    assert events == ["rollback"]


def test_gametype_category_alter_failure_rolls_back() -> None:
    cursor = RecordingCursor(RuntimeError("table locked"))
    db, events = migration_db(Database.PGSQL, cursor)

    db._ensure_gametype_category_width()

    assert events == ["rollback"]
