"""Live schema checks for the PostgreSQL and MySQL catalogues."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy import db_migrate, dialects
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_schema import COLUMN_COLLATION_SQL, DatabaseSchemaMixin
from fpdb_3_legacy.phh_import import import_file as import_phh_file
from fpdb_3_legacy.SQL import Sql

SCHEMA_KEYS = (
    "createSettingsTable",
    "createActionsTable",
    "createRankTable",
    "createStartCardsTable",
    "createSitesTable",
    "createGametypesTable",
    "createFilesTable",
    "createPlayersTable",
    "createAutoratesTable",
    "createWeeksTable",
    "createMonthsTable",
    "createSessionsTable",
    "createTourneyTypesTable",
    "createTourneysTable",
    "createTourneysPlayersTable",
    "createSessionsCacheTable",
    "createTourneysCacheTable",
    "createHandsTable",
    "createHandsPlayersTable",
    "createHandsActionsTable",
    "createHandsStoveTable",
    "createHandsShowdownTable",
    "createHandsCashoutTable",
    "createPlayerAutoNotesTable",
    "createAofDecisionsTable",
    "createAofDecisionAnalysesTable",
    "createHandsPotsTable",
    "createHudCacheTable",
    "createCardsCacheTable",
    "createPositionsCacheTable",
    "createBoardsTable",
    "createBackingsTable",
    "createRawHands",
    "createRawTourneys",
)


def _enabled_backends() -> set[str]:
    value = os.environ.get("FPDB_TEST_DATABASES", "")
    return {backend.strip() for backend in value.split(",") if backend.strip()}


@contextmanager
def _connection(backend: str) -> Iterator[Any]:
    if backend == "postgresql":
        import psycopg

        connection = psycopg.connect(
            host=os.environ.get("FPDB_POSTGRES_HOST", "127.0.0.1"),
            port=int(os.environ.get("FPDB_POSTGRES_PORT", "5432")),
            dbname=os.environ.get("FPDB_POSTGRES_DB", "fpdb"),
            user=os.environ.get("FPDB_POSTGRES_USER", "fpdb"),
            password=os.environ.get("FPDB_POSTGRES_PASSWORD", "fpdb"),
        )
    else:
        import pymysql

        connection = pymysql.connect(
            host=os.environ.get("FPDB_MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("FPDB_MYSQL_PORT", "3306")),
            database=os.environ.get("FPDB_MYSQL_DB", "fpdb"),
            user=os.environ.get("FPDB_MYSQL_USER", "fpdb"),
            password=os.environ.get("FPDB_MYSQL_PASSWORD", "fpdb"),
        )
    try:
        yield connection
    finally:
        connection.close()


def _reset_schema(connection: Any, backend: str) -> None:
    with connection.cursor() as cursor:
        if backend == "postgresql":
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
        else:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute("SHOW TABLES")
            for (table,) in cursor.fetchall():
                cursor.execute(f"DROP TABLE `{table}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    connection.commit()


class _LiveDatabase(DatabaseSchemaMixin):
    """Minimal Database-compatible wrapper around a live driver connection."""

    def __init__(self, connection: Any, backend: str) -> None:
        self.connection = connection
        self.backend = dialects.dialect_for_server(backend).backend_id
        # What the schema mixin reads off its host to decide between the backends.
        self.MYSQL_INNODB = Database.MYSQL_INNODB
        self.PGSQL = Database.PGSQL
        self.SQLITE = Database.SQLITE

    def get_cursor(self) -> Any:
        return self.connection.cursor()

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


def _create_schema(connection: Any, backend: str) -> None:
    _reset_schema(connection, backend)
    sql = Sql(db_server=backend)
    with connection.cursor() as cursor:
        for key in SCHEMA_KEYS:
            cursor.execute(sql.query[key])
    connection.commit()


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_full_schema_executes_and_enforces_player_site_fk(backend: str) -> None:
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    with _connection(backend) as connection:
        _create_schema(connection, backend)

        with connection.cursor() as cursor:
            if backend == "postgresql":
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            else:
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
            assert cursor.fetchone()[0] == len(SCHEMA_KEYS)

            with pytest.raises(Exception):
                cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("orphan", 999999))
        connection.rollback()


def _players_name_collation(cursor: Any, backend: str) -> str | None:
    """The collation the live ``Players.name`` declares; MySQL's catalogue needs pinning."""
    # Two whole statements rather than one built from parts: the analyser reads a query
    # assembled by concatenation as an injection site, even when every part is a literal.
    if backend == "mysql":
        cursor.execute(
            "SELECT collation_name FROM information_schema.columns "
            "WHERE lower(table_name) = 'players' AND lower(column_name) = 'name' "
            "AND table_schema = DATABASE()"
        )
    else:
        cursor.execute(
            "SELECT collation_name FROM information_schema.columns "
            "WHERE lower(table_name) = 'players' AND lower(column_name) = 'name'"
        )
    row = cursor.fetchone()
    return None if row is None else row[0]


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_players_names_that_differ_in_case_accent_or_ligature_are_two_rows(backend: str) -> None:
    """The column compares byte for byte, so the unique index keeps the names apart (#417)."""
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    with _connection(backend) as connection:
        _create_schema(connection, backend)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO Sites(id, name, code) VALUES (%s, %s, %s)", (1, "Room", "RM"))
            names = ("Alice", "alice", "Álice", "Ø", "O")
            for name in names:
                cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", (name, 1))
            cursor.execute("SELECT name FROM Players ORDER BY id")
            assert tuple(row[0] for row in cursor.fetchall()) == names
            assert _players_name_collation(cursor, backend) == ("C" if backend == "postgresql" else "utf8mb4_bin")
        connection.commit()


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_an_existing_players_table_gains_the_binary_collation(backend: str) -> None:
    """A database made before the change is migrated on connect, once, and keeps its rows."""
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    with _connection(backend) as connection:
        _reset_schema(connection, backend)
        with connection.cursor() as cursor:
            if backend == "postgresql":
                cursor.execute(
                    "CREATE TABLE Players (id SERIAL PRIMARY KEY, name VARCHAR(32), siteId INT, UNIQUE (name, siteId))"
                )
            else:
                cursor.execute(
                    "CREATE TABLE Players (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(32) NOT NULL, "
                    "siteId INT, UNIQUE KEY name (name, siteId))"
                )
            cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("Alice", 1))
        connection.commit()

        live = _LiveDatabase(connection, backend)
        # What the PHH importer asks before it accepts two names differing only in case.
        assert live.players_name_compares_binary() is False
        # Twice: the second run reads the collation and issues no DDL.
        DatabaseSchemaMixin._ensure_players_name_collation(live)
        DatabaseSchemaMixin._ensure_players_name_collation(live)
        assert live.players_name_compares_binary() is True

        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("alice", 1))
            cursor.execute("SELECT name FROM Players ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == ["Alice", "alice"]
            assert _players_name_collation(cursor, backend) == ("C" if backend == "postgresql" else "utf8mb4_bin")
        connection.commit()


class _MySQLConfig:
    """Enough of a config for ``Database`` to open the test server without a schema check."""

    def __init__(self) -> None:
        self.params = {
            "db-host": os.environ.get("FPDB_MYSQL_HOST", "127.0.0.1"),
            "db-port": int(os.environ.get("FPDB_MYSQL_PORT", "3306")),
            "db-server": "mysql",
            "db-backend": Database.MYSQL_INNODB,
            "db-databaseName": os.environ.get("FPDB_MYSQL_DB", "fpdb"),
        }

    def get_db_parameters(self) -> dict[str, Any]:
        return self.params

    def get_import_parameters(self) -> dict[str, Any]:
        return {"sessionTimeout": 30, "publicDB": False}

    def get_general_params(self) -> dict[str, Any]:
        return {}


@pytest.mark.integration
def test_mysql_connections_carry_utf8mb4_so_a_supplementary_name_is_stored() -> None:
    """A three-byte client character set refused ``Alice😀`` before it reached the column.

    ``Players.name`` is declared ``utf8mb4`` (#417), but the client character set is what the
    server decodes the statement with: both connection paths used to ask for ``utf8``, so a
    supplementary character in a name was an incorrect-string-value error.
    """
    if "mysql" not in _enabled_backends():
        pytest.skip("live mysql service not requested")

    db = Database(_MySQLConfig(), sql=Sql(db_server="mysql"), autoconnect=False)
    try:
        db._connect_mysql(
            os.environ.get("FPDB_MYSQL_HOST", "127.0.0.1"),
            int(os.environ.get("FPDB_MYSQL_PORT", "3306")),
            os.environ.get("FPDB_MYSQL_USER", "fpdb"),
            os.environ.get("FPDB_MYSQL_PASSWORD", "fpdb"),
            os.environ.get("FPDB_MYSQL_DB", "fpdb"),
        )
        _create_schema(db.connection, "mysql")
        cursor = db.get_cursor()
        cursor.execute("SELECT @@character_set_client")
        assert cursor.fetchone()[0] == "utf8mb4"

        cursor.execute("INSERT INTO Sites(id, name, code) VALUES (%s, %s, %s)", (1, "Room", "RM"))
        first = db.insertPlayer("Alice\U0001f600", 1, 0)
        second = db.insertPlayer("Alice\U0001f601", 1, 0)
        assert first != second
    finally:
        db.close_connection()


@pytest.mark.integration
def test_an_import_is_refused_while_mysql_still_folds_names(tmp_path) -> None:
    """The migration is best-effort, so the importer must not accept a merge meanwhile (#417).

    The column is put back to the server's default collation, exactly as a database whose
    ALTER lost the race for the table would be. ``Alice`` and ``alice`` would then be one row
    after ``insertPlayer``'s upsert; the file must be refused whole instead.
    """
    if "mysql" not in _enabled_backends():
        pytest.skip("live mysql service not requested")

    db = Database(_MySQLConfig(), sql=Sql(db_server="mysql"), autoconnect=False)
    try:
        db._connect_mysql(
            os.environ.get("FPDB_MYSQL_HOST", "127.0.0.1"),
            int(os.environ.get("FPDB_MYSQL_PORT", "3306")),
            os.environ.get("FPDB_MYSQL_USER", "fpdb"),
            os.environ.get("FPDB_MYSQL_PASSWORD", "fpdb"),
            os.environ.get("FPDB_MYSQL_DB", "fpdb"),
        )
        _create_schema(db.connection, "mysql")
        cursor = db.get_cursor()
        cursor.execute(
            "ALTER TABLE Players MODIFY name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL"
        )
        db.commit()
        assert db.players_name_compares_binary() is False

        fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phh" / "nl_holdem_heads_up.phh"
        path = tmp_path / "case.phhs"
        path.write_text(
            fixture.read_text(encoding="utf-8").replace('players = ["Alice", "Bob"]', 'players = ["Alice", "alice"]'),
            encoding="utf-8",
        )

        result = import_phh_file(db, None, path)
        assert (result.imported, result.unsupported) == (0, 1)
        assert "does not compare names byte for byte" in result.errors[0]
        cursor.execute("SELECT COUNT(*) FROM Players")
        assert cursor.fetchone()[0] == 0
    finally:
        db.close_connection()


@pytest.mark.integration
def test_the_collation_lookup_reads_the_schema_the_alter_targets() -> None:
    """Another schema's ``Players`` must not answer for the one the migration alters.

    ``information_schema.columns`` spans every schema of the database, while the unqualified
    ``ALTER TABLE Players`` resolves through the search path. Reading another schema's row
    could skip the ALTER on an unmigrated table -- or re-issue it on every connection.
    """
    if "postgresql" not in _enabled_backends():
        pytest.skip("live postgresql service not requested")

    with _connection("postgresql") as connection:
        _reset_schema(connection, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS decoy CASCADE")
            cursor.execute("CREATE SCHEMA decoy")
            # The decoy holds the collation the migration is looking for, so a lookup that
            # read it would believe the target has already been migrated.
            cursor.execute(
                'CREATE TABLE decoy.Players (id SERIAL PRIMARY KEY, name VARCHAR(32) COLLATE "C", '
                "siteId INT, UNIQUE (name, siteId))"
            )
            cursor.execute(
                "CREATE TABLE Players (id SERIAL PRIMARY KEY, name VARCHAR(32), siteId INT, UNIQUE (name, siteId))"
            )
            cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("Alice", 1))
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(COLUMN_COLLATION_SQL, ("players", "name", "Players"))
            rows = cursor.fetchall()
        assert len(rows) == 1, "the lookup read a Players table outside the search path"
        assert rows[0][0] != "C"

        live = _LiveDatabase(connection, "postgresql")
        assert live.players_name_compares_binary() is False
        DatabaseSchemaMixin._ensure_players_name_collation(live)
        assert live.players_name_compares_binary() is True

        with connection.cursor() as cursor:
            # Allowed only because the target gained "C": under the locale, "alice" folded.
            cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("alice", 1))
            cursor.execute("SELECT name FROM Players ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == ["Alice", "alice"]
            cursor.execute(
                "SELECT c.collname FROM pg_attribute a JOIN pg_collation c ON c.oid = a.attcollation "
                "WHERE a.attrelid = to_regclass('Players') AND a.attname = 'name'"
            )
            assert cursor.fetchone()[0] == "C"
        connection.commit()


@pytest.mark.integration
def test_data_round_trip_between_mysql_and_postgresql_repairs_sequences() -> None:
    if not {"postgresql", "mysql"}.issubset(_enabled_backends()):
        pytest.skip("live PostgreSQL and MySQL services not requested")

    with _connection("mysql") as mysql_connection, _connection("postgresql") as postgres_connection:
        _create_schema(mysql_connection, "mysql")
        _create_schema(postgres_connection, "postgresql")

        with mysql_connection.cursor() as cursor:
            cursor.execute("INSERT INTO Sites(id, name, code) VALUES (%s, %s, %s)", (7, "Migration Room", "MR"))
            cursor.execute(
                "INSERT INTO Players(id, name, siteId, hero) VALUES (%s, %s, %s, %s)",
                (12, "roundtrip", 7, 1),
            )
            cursor.execute("INSERT INTO `Rank`(id, name) VALUES (%s, %s)", (3, "queen"))
        mysql_connection.commit()

        mysql_db = _LiveDatabase(mysql_connection, "mysql")
        postgres_db = _LiveDatabase(postgres_connection, "postgresql")
        to_postgres = db_migrate.migrate(mysql_db, postgres_db)

        assert to_postgres.ok, to_postgres.error
        assert to_postgres.tables["Sites"] == 1
        with postgres_connection.cursor() as cursor:
            cursor.execute("SELECT name, siteId, hero FROM Players WHERE id = %s", (12,))
            assert cursor.fetchone() == ("roundtrip", 7, True)
            cursor.execute("SELECT name FROM Rank WHERE id = %s", (3,))
            assert cursor.fetchone() == ("queen",)
            cursor.execute("INSERT INTO Sites(name, code) VALUES (%s, %s) RETURNING id", ("Sequence Room", "SR"))
            assert cursor.fetchone()[0] == 8
        postgres_connection.commit()

        to_mysql = db_migrate.migrate(postgres_db, mysql_db)

        assert to_mysql.ok, to_mysql.error
        assert to_mysql.tables["sites"] == 2
        with mysql_connection.cursor() as cursor:
            cursor.execute("SELECT name, siteId, hero FROM Players WHERE id = %s", (12,))
            assert cursor.fetchone() == ("roundtrip", 7, 1)
            cursor.execute("SELECT name FROM `Rank` WHERE id = %s", (3,))
            assert cursor.fetchone() == ("queen",)
            cursor.execute("INSERT INTO Sites(name, code) VALUES (%s, %s)", ("MySQL Sequence", "MS"))
            assert cursor.lastrowid == 9
        mysql_connection.rollback()


# What _rebuild_ring_cache / _rebuild_tourney_cache pass without hero filtering.
REBUILD_WHERE = {
    "ring": "WHERE g.type = 'ring'<hero_where>",
    "tour": "WHERE g.type = 'tour'<hero_where>",
}


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
@pytest.mark.parametrize("table", ["HudCache", "CardsCache", "PositionsCache"])
@pytest.mark.parametrize("game_type", ["ring", "tour"])
def test_the_generated_cache_rebuild_runs_on_the_live_schema(backend: str, table: str, game_type: str) -> None:
    """PostgreSQL type-checks the statement before reading a row: summing a BOOLEAN fails here (#591)."""
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    host = Database.__new__(Database)
    host.backend = dialects.dialect_for_server(backend).backend_id
    host.sql = Sql(db_server=backend)
    host.build_full_hudcache = True
    host.day_start = 0.0
    query = host.rebuild_sql(game_type, table, REBUILD_WHERE[game_type])

    with _connection(backend) as connection:
        _create_schema(connection, backend)
        with connection.cursor() as cursor:
            cursor.execute(query)
        connection.rollback()
