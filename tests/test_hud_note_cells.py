"""The HUD's note cell stays off the database on the Qt thread (#680).

The cell opened a full connection for every seat of every table on every
refresh. On a remote database the Qt thread spent 93 % of a sampled session
waiting on PostgreSQL, which is what made dragging a HUD lag.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import database_migrations
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_migrations import DatabaseMigrationsMixin
from fpdb_3_legacy.hud_read_service import mark_players_with_notes
from tests.helpers import analytics_golden as golden


@pytest.fixture
def db(tmp_path):
    config = golden.build_config(tmp_path)
    params = config.get_db_parameters()
    params.update(
        {"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(tmp_path / "db.sqlite3"), "db-path": ""}
    )
    config.get_db_parameters = lambda: params
    database = Database(config)
    database.recreate_tables()
    yield database
    database.disconnect()


def _player(db: Database, name: str, comment: str | None = None) -> int:
    site = db.connection.execute("SELECT min(id) FROM Sites").fetchone()[0]
    cursor = db.connection.execute(
        "INSERT INTO Players (name, siteId, hero, comment) VALUES (?, ?, 0, ?)", (name, site, comment)
    )
    return cursor.lastrowid


def _auto_note(db: Database, player: int) -> None:
    columns = [row[1] for row in db.connection.execute("PRAGMA table_info(PlayerAutoNotes)") if row[3] and not row[5]]
    values = {column: 0 for column in columns}
    values["playerId"] = player
    names = ", ".join(values)
    marks = ", ".join("?" * len(values))
    db.connection.execute(  # nosemgrep
        "INSERT INTO PlayerAutoNotes (" + names + ") VALUES (" + marks + ")",  # nosec B608  # nosemgrep
        list(values.values()),
    )


def test_players_with_notes_finds_comments_and_generated_notes(db) -> None:
    commented = _player(db, "alice", "fish")
    generated = _player(db, "bob")
    _auto_note(db, generated)
    blank = _player(db, "carol", "")
    silent = _player(db, "dave")

    assert db.players_with_notes([commented, generated, blank, silent]) == {commented, generated}


def test_players_with_notes_with_nobody_runs_no_statement() -> None:
    database = object.__new__(Database)
    database.get_cursor = MagicMock()

    assert database.players_with_notes([]) == set()
    database.get_cursor.assert_not_called()


def test_mark_flags_every_player_with_one_statement() -> None:
    database = MagicMock()
    database.players_with_notes.return_value = {1, 3}
    first, second = {1: {}, 2: {}}, {3: {}}

    mark_players_with_notes(database, first, second)

    assert first == {1: {"has_notes": True}, 2: {"has_notes": False}}
    assert second == {3: {"has_notes": True}}
    assert list(database.players_with_notes.call_args[0][0]) == [1, 2, 3]
    database.players_with_notes.assert_called_once()


def test_a_player_seen_at_two_tables_is_flagged_at_both() -> None:
    database = MagicMock()
    database.players_with_notes.return_value = {1}
    first, second = {1: {}}, {1: {}}

    mark_players_with_notes(database, first, second)

    assert first == {1: {"has_notes": True}}
    assert second == {1: {"has_notes": True}}


class _Connection(DatabaseMigrationsMixin):
    backend = 3
    host = "server"
    port = 5432
    SQLITE = 4

    def __init__(self, database: str = "db") -> None:
        self.database = database
        self.ensure_feature_tables = MagicMock()


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(database_migrations, "_feature_tables_checked", {})
    now = SimpleNamespace(value=1000.0)
    monkeypatch.setattr(database_migrations.time, "monotonic", lambda: now.value)
    return now


@pytest.mark.usefixtures("clock")
def test_a_second_connection_skips_the_migration_pass() -> None:
    first, second = _Connection(), _Connection()

    first.ensure_feature_tables_on_connect()
    second.ensure_feature_tables_on_connect()

    first.ensure_feature_tables.assert_called_once_with()
    second.ensure_feature_tables.assert_not_called()


def test_the_pass_comes_back_so_a_lost_race_gets_another_chance(clock) -> None:
    _Connection().ensure_feature_tables_on_connect()
    clock.value += database_migrations.FEATURE_TABLES_RECHECK_S

    later = _Connection()
    later.ensure_feature_tables_on_connect()

    later.ensure_feature_tables.assert_called_once_with()


@pytest.mark.usefixtures("clock")
def test_another_database_runs_its_own_pass() -> None:
    _Connection("one").ensure_feature_tables_on_connect()

    other = _Connection("two")
    other.ensure_feature_tables_on_connect()

    other.ensure_feature_tables.assert_called_once_with()


@pytest.mark.usefixtures("clock")
def test_dropped_tables_make_the_next_connection_run_the_pass() -> None:
    connection = _Connection()
    connection.ensure_feature_tables_on_connect()

    connection.forget_feature_tables_check()
    after = _Connection()
    after.ensure_feature_tables_on_connect()

    after.ensure_feature_tables.assert_called_once_with()


@pytest.mark.usefixtures("clock")
def test_sqlite_always_runs_the_pass(tmp_path: Path) -> None:
    connection = _Connection(str(tmp_path / "db.sqlite3"))
    connection.backend = connection.SQLITE

    connection.ensure_feature_tables_on_connect()
    connection.ensure_feature_tables_on_connect()

    assert connection.ensure_feature_tables.call_count == 2
