"""A migration must never be able to hang the application that runs it.

``ensure_feature_tables`` runs on every ``Database()`` construction, and the GUI
builds one per heavy tab. Both server backends wait for a table lock forever by
default, so a tab sitting inside an open read transaction on Gametypes was
enough to make the next tab's ``ALTER TABLE`` wait on the GUI thread until the
user killed the process -- the freeze in #249, reproduced as the second tab
opening and never returning.

Two things are pinned here, because either one alone leaves the hang reachable:
the width migration must not issue DDL a database no longer needs, and any DDL
that does go out must be allowed to fail instead of waiting.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpdb_3_legacy import database_schema


class FakeCursor:
    """Records every statement, and answers the one query the code reads back."""

    def __init__(self, owner: FakeDatabase) -> None:
        self.owner = owner

    def execute(self, statement: str, params: tuple[Any, ...] | None = None) -> None:
        self.owner.statements.append(statement)
        if statement in self.owner.failing:
            raise RuntimeError(self.owner.failing[statement])

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.owner.next_row


class FakeDatabase(database_schema.DatabaseSchemaMixin):
    """The mixin's host, reduced to what the migrations actually borrow."""

    MYSQL_INNODB = 2
    PGSQL = 3
    SQLITE = 4

    def __init__(self, backend: int, *, width: int | None = 10) -> None:
        self.backend = backend
        self.statements: list[str] = []
        self.failing: dict[str, str] = {}
        self.next_row: tuple[Any, ...] | None = (width,)
        self.commits = 0
        self.rollbacks = 0

    def get_cursor(self, connect: bool = False) -> FakeCursor:  # noqa: ARG002 - signature borrowed from Database
        return FakeCursor(self)

    def commit(self, force: bool = False) -> None:  # noqa: ARG002 - signature borrowed from Database
        self.commits += 1

    def rollback(self, force: bool = False) -> None:  # noqa: ARG002 - signature borrowed from Database
        self.rollbacks += 1


ALTERS = (
    database_schema.WIDEN_GAMETYPE_CATEGORY_SQL,
    database_schema.WIDEN_GAMETYPE_CATEGORY_MYSQL,
)


@pytest.mark.parametrize("backend", [FakeDatabase.PGSQL, FakeDatabase.MYSQL_INNODB])
def test_a_wide_enough_column_is_left_alone(backend: int) -> None:
    """The check the docstring always promised, which the code never made.

    The old version only asked whether a column named "category" existed, so an
    ALTER TABLE taking ACCESS EXCLUSIVE on Gametypes went out on every single
    connection, forever, to set a width that was already set.
    """
    db = FakeDatabase(backend, width=database_schema.GAMETYPE_CATEGORY_WIDTH)

    db._ensure_gametype_category_width()

    assert not [statement for statement in db.statements if statement in ALTERS]


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        (FakeDatabase.PGSQL, database_schema.WIDEN_GAMETYPE_CATEGORY_SQL),
        (FakeDatabase.MYSQL_INNODB, database_schema.WIDEN_GAMETYPE_CATEGORY_MYSQL),
    ],
)
def test_a_narrow_column_is_still_widened(backend: int, expected: str) -> None:
    db = FakeDatabase(backend, width=database_schema.GAMETYPE_CATEGORY_WIDTH - 1)

    db._ensure_gametype_category_width()

    assert expected in db.statements
    assert db.commits == 1


def test_a_missing_column_is_not_a_migration() -> None:
    db = FakeDatabase(FakeDatabase.PGSQL)
    db.next_row = None

    db._ensure_gametype_category_width()

    assert not [statement for statement in db.statements if statement in ALTERS]


def test_sqlite_is_never_asked_to_widen_anything() -> None:
    """TEXT is unbounded there, and SQLite has no ALTER COLUMN at all."""
    db = FakeDatabase(FakeDatabase.SQLITE, width=1)

    db._ensure_gametype_category_width()

    assert db.statements == []


def test_a_locked_table_is_reported_not_waited_on() -> None:
    db = FakeDatabase(FakeDatabase.PGSQL, width=database_schema.GAMETYPE_CATEGORY_WIDTH - 1)
    db.failing[database_schema.WIDEN_GAMETYPE_CATEGORY_SQL] = "lock timeout"

    db._ensure_gametype_category_width()

    assert db.rollbacks == 1
    assert db.commits == 0


@pytest.mark.parametrize(
    ("backend", "expected_set", "expected_reset"),
    [
        (
            FakeDatabase.PGSQL,
            database_schema.SET_PGSQL_LOCK_TIMEOUT,
            database_schema.RESET_PGSQL_LOCK_TIMEOUT,
        ),
        (
            FakeDatabase.MYSQL_INNODB,
            database_schema.SET_MYSQL_LOCK_TIMEOUT,
            database_schema.RESET_MYSQL_LOCK_TIMEOUT,
        ),
    ],
)
def test_the_migration_block_bounds_its_lock_wait(backend: int, expected_set: str, expected_reset: str) -> None:
    """Set on the way in, restored on the way out, around the whole block."""
    db = FakeDatabase(backend)

    with db.bounded_ddl_lock_wait():
        db.get_cursor().execute("ALTER TABLE Whatever ADD COLUMN x INT")

    assert db.statements[0] == expected_set
    assert db.statements[-1] == expected_reset


def test_the_timeout_is_restored_even_when_a_migration_raises() -> None:
    """Otherwise one failed migration leaves the timeout on the session."""
    db = FakeDatabase(FakeDatabase.PGSQL)

    with pytest.raises(RuntimeError), db.bounded_ddl_lock_wait():
        msg = "migration blew up"
        raise RuntimeError(msg)

    assert db.statements[-1] == database_schema.RESET_PGSQL_LOCK_TIMEOUT


def test_sqlite_gets_no_timeout_statements() -> None:
    """It serialises with its own busy timeout and has neither setting."""
    db = FakeDatabase(FakeDatabase.SQLITE)

    with db.bounded_ddl_lock_wait():
        pass

    assert db.statements == []


def test_ensure_feature_tables_runs_its_migrations_inside_the_block() -> None:
    """The bound has to cover the migrations, not merely exist next to them."""
    db = FakeDatabase(FakeDatabase.PGSQL)
    calls: list[str] = []

    def record() -> None:
        calls.append(db.statements[-1] if db.statements else "")

    db._run_feature_migrations = record  # type: ignore[method-assign]

    db.ensure_feature_tables()

    assert calls == [database_schema.SET_PGSQL_LOCK_TIMEOUT]


def test_a_failed_column_migration_does_not_take_the_connection_down() -> None:
    """It is retried on the next connection, so it must not raise here.

    ``_ensure_table_columns`` re-raised, and ``ensure_feature_tables`` runs from
    ``Database.__init__``: with a bounded lock wait, losing a race for the table
    would otherwise turn a tab that opens slowly into a tab that does not open.
    """
    db = FakeDatabase(FakeDatabase.PGSQL)
    db._get_table_columns = lambda _table: {"id"}  # type: ignore[method-assign]
    statement = "ALTER TABLE HandsPlayers ADD COLUMN enumPreflop CHAR(1) DEFAULT 'N'"
    db.failing[statement] = "lock timeout"

    db._ensure_table_columns("HandsPlayers", {"enumPreflop": "CHAR(1) DEFAULT 'N'"})

    assert statement in db.statements
    assert db.rollbacks == 1
    assert db.commits == 0
