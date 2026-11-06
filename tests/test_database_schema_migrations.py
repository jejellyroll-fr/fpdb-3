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


def collation_db(backend: int, cursor: RecordingCursor, collation: str | None) -> tuple[Database, list[str]]:
    """A Database stubbed down to what the collation migration reads and writes.

    *collation* is what the column declares: None for PostgreSQL's database default, and the
    name the server reports otherwise. The migration decides from that alone, which is what
    keeps it from re-issuing DDL on a database that has already been migrated.
    """
    db = Database.__new__(Database)
    db.backend = backend
    db._column_collation = lambda _table, _column: collation
    db.get_cursor = lambda: cursor
    events: list[str] = []
    db.commit = lambda: events.append("commit")
    db.rollback = lambda: events.append("rollback")
    return db, events


@pytest.mark.parametrize(
    ("backend", "collation", "expected"),
    [
        # The server default MySQL compared names with: case- and accent-insensitive.
        (
            Database.MYSQL_INNODB,
            "utf8mb4_0900_ai_ci",
            "ALTER TABLE Players MODIFY name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        ),
        # Byte for byte, but in a character set that cannot store every name: Alice😀 would be
        # refused at insertion, so the column is moved to utf8mb4 as well.
        (
            Database.MYSQL_INNODB,
            "latin1_bin",
            "ALTER TABLE Players MODIFY name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        ),
        (
            Database.MYSQL_INNODB,
            "utf8mb3_bin",
            "ALTER TABLE Players MODIFY name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        ),
        # PostgreSQL's default reports None, and its locale is not known to be byte order.
        (Database.PGSQL, None, 'ALTER TABLE Players ALTER COLUMN name TYPE VARCHAR(32) COLLATE "C"'),
    ],
)
def test_players_name_gets_a_binary_collation(backend: int, collation: str | None, expected: str) -> None:
    cursor = RecordingCursor()
    db, events = collation_db(backend, cursor, collation)

    db._ensure_players_name_collation()

    assert cursor.statements == [expected]
    assert events == ["commit"]


@pytest.mark.parametrize(
    ("backend", "collation"),
    [
        (Database.MYSQL_INNODB, "utf8mb4_bin"),
        (Database.MYSQL_INNODB, "utf8mb4_0900_bin"),
        (Database.PGSQL, "C"),
        (Database.PGSQL, "POSIX"),
        (Database.PGSQL, "ucs_basic"),
    ],
)
def test_a_binary_collation_is_left_alone(backend: int, collation: str) -> None:
    """The ALTER rewrites the table and rebuilds the index, so it must be earned."""
    cursor = RecordingCursor()
    db, events = collation_db(backend, cursor, collation)

    db._ensure_players_name_collation()

    assert cursor.statements == []
    assert events == []


def test_sqlite_needs_no_collation_migration() -> None:
    """SQLite's default is BINARY already, and the DDL says so for a fresh database."""
    cursor = RecordingCursor()
    db, events = collation_db(Database.SQLITE, cursor, "NOCASE")

    db._ensure_players_name_collation()

    assert cursor.statements == []
    assert events == []


def test_a_collation_lookup_failure_rolls_back() -> None:
    cursor = RecordingCursor()
    db, events = collation_db(Database.PGSQL, cursor, None)

    def fail_lookup(_table: str, _column: str) -> str:
        raise RuntimeError("missing table")

    db._column_collation = fail_lookup

    db._ensure_players_name_collation()

    assert cursor.statements == []
    assert events == ["rollback"]


def test_a_collation_alter_failure_rolls_back() -> None:
    cursor = RecordingCursor(RuntimeError("table locked"))
    db, events = collation_db(Database.PGSQL, cursor, None)

    db._ensure_players_name_collation()

    assert events == ["rollback"]


def test_an_alter_that_could_not_run_leaves_the_column_unvouched_for() -> None:
    """The migration is best-effort, so the answer to "is it binary?" is then no.

    ``ensure_feature_tables`` logs a lock timeout and retries on the next connection; a
    caller that stores ``Alice`` and ``alice`` must not read that as success, because the
    unique index would file both seats in one player.
    """
    cursor = RecordingCursor(RuntimeError("table locked"))
    db, _events = collation_db(Database.MYSQL_INNODB, cursor, "utf8mb4_0900_ai_ci")

    db._ensure_players_name_collation()

    # The stub's catalogue still reports the old collation: nothing changed it.
    assert db.players_name_compares_binary() is False


@pytest.mark.parametrize(
    ("backend", "collation", "expected"),
    [
        (Database.MYSQL_INNODB, "utf8mb4_0900_ai_ci", False),
        (Database.MYSQL_INNODB, "utf8mb4_unicode_ci", False),
        (Database.MYSQL_INNODB, "utf8mb4_bin", True),
        (Database.MYSQL_INNODB, "utf8mb4_0900_bin", True),
        # Binary, but not utf8mb4: the column cannot store every name yet.
        (Database.MYSQL_INNODB, "latin1_bin", False),
        (Database.MYSQL_INNODB, "utf8mb3_bin", False),
        # On PostgreSQL a *_bin name proves nothing: only C, POSIX and ucs_basic are byte order.
        (Database.PGSQL, "utf8mb4_bin", False),
        (Database.PGSQL, None, False),
        (Database.PGSQL, "en_US.utf8", False),
        (Database.PGSQL, "C", True),
        (Database.SQLITE, "NOCASE", True),
    ],
)
def test_the_database_says_whether_players_name_compares_binary(
    backend: int, collation: str | None, expected: bool
) -> None:
    """What the importer asks before it accepts two names differing only in case (#417)."""
    cursor = RecordingCursor()
    db, _events = collation_db(backend, cursor, collation)

    assert db.players_name_compares_binary() is expected
    assert cursor.statements == []


def test_a_catalogue_that_cannot_be_read_does_not_vouch_for_the_column() -> None:
    cursor = RecordingCursor()
    db, events = collation_db(Database.PGSQL, cursor, None)

    def fail_lookup(_table: str, _column: str) -> str:
        raise RuntimeError("missing table")

    db._column_collation = fail_lookup

    assert db.players_name_compares_binary() is False
    assert events == ["rollback"]


def test_the_postgres_collation_lookup_is_scoped_to_the_table_it_alters() -> None:
    """Another schema's ``Players`` must not decide whether this one needs the ALTER."""
    from fpdb_3_legacy.database_schema import COLUMN_COLLATION_SQL

    assert "table_schema = (SELECT n.nspname" in COLUMN_COLLATION_SQL
    assert "to_regclass(%s)" in COLUMN_COLLATION_SQL


def test_sqlite_players_name_is_declared_binary_and_keeps_case_apart(tmp_path) -> None:
    """The schema says COLLATE BINARY and ``insertPlayer`` stores both spellings."""
    from tests.helpers import analytics_golden as golden

    db = Database(golden.build_config(tmp_path))
    db.recreate_tables()
    cursor = db.get_cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'Players'")
    assert "COLLATE BINARY" in cursor.fetchone()[0]

    first = db.insertPlayer("Alice", 2, 0)
    second = db.insertPlayer("alice", 2, 0)
    third = db.insertPlayer("Álice", 2, 0)
    assert len({first, second, third}) == 3
    cursor.execute("SELECT name FROM Players WHERE siteId = 2 ORDER BY id")
    assert [row[0] for row in cursor.fetchall()] == ["Alice", "alice", "Álice"]
    db.disconnect()


def test_analytics_indexes_are_installed_by_the_feature_migration(tmp_path) -> None:
    """An existing database gains the analytics indexes (#304) on connect.

    They are created best-effort in ``ensure_feature_tables`` like the other
    additive pieces, so a database that predates them does not need a rebuild.
    """
    from fpdb_3_legacy.sql_indexes import ANALYTICS_INDEX_NAMES
    from tests.helpers import analytics_golden as golden

    db = Database(golden.build_config(tmp_path))
    db.recreate_tables()
    db.ensure_feature_tables()
    if db.backend == Database.PGSQL:
        pytest.skip("the sqlite index probe below needs SQLite")
    cursor = db.get_cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    installed = {row[0] for row in cursor.fetchall()}
    missing = [name for name in ANALYTICS_INDEX_NAMES if name not in installed]
    assert missing == []
    # Re-running the migration is a no-op, not an error.
    db.ensure_feature_tables()
    db.disconnect()
