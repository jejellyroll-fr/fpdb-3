"""Focused tests for additive database schema migrations."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database

NARROW = 9  # the width the original schema declared


class RecordingCursor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error


def migration_db(backend: int, cursor: RecordingCursor, width: int | None = NARROW) -> tuple[Database, list[str]]:
    """A Database stubbed down to what the width migration reads.

    ``width`` is what the column currently declares: the migration decides
    from that number alone, which is what keeps it from re-issuing DDL on a
    database that has already been migrated.
    """
    db = Database.__new__(Database)
    db.backend = backend
    db._column_character_length = lambda _table, _column: width
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


def test_gametype_category_already_wide_issues_no_ddl() -> None:
    """The ALTER takes ACCESS EXCLUSIVE on Gametypes, so it must be earned."""
    cursor = RecordingCursor()
    db, events = migration_db(Database.PGSQL, cursor, width=10)

    db._ensure_gametype_category_width()

    assert cursor.statements == []
    assert events == []


def test_gametype_category_lookup_failure_rolls_back() -> None:
    cursor = RecordingCursor()
    db, events = migration_db(Database.PGSQL, cursor)

    def fail_lookup(_table: str, _column: str) -> int:
        raise RuntimeError("missing table")

    db._column_character_length = fail_lookup

    db._ensure_gametype_category_width()

    assert cursor.statements == []
    assert events == ["rollback"]


def test_gametype_category_alter_failure_rolls_back() -> None:
    cursor = RecordingCursor(RuntimeError("table locked"))
    db, events = migration_db(Database.PGSQL, cursor)

    db._ensure_gametype_category_width()

    assert events == ["rollback"]
