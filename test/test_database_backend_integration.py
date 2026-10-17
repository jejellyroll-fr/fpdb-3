"""Live schema checks for the PostgreSQL and MySQL catalogues."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from fpdb_3_legacy import db_migrate, dialects
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_schema import DatabaseSchemaMixin
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
            cursor.execute(
                "SELECT collation_name FROM information_schema.columns "
                "WHERE lower(table_name) = 'players' AND lower(column_name) = 'name'"
                + (" AND table_schema = DATABASE()" if backend == "mysql" else "")
            )
            assert cursor.fetchone()[0] == ("C" if backend == "postgresql" else "utf8mb4_bin")
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
        # Twice: the second run reads the collation and issues no DDL.
        DatabaseSchemaMixin._ensure_players_name_collation(live)
        DatabaseSchemaMixin._ensure_players_name_collation(live)

        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("alice", 1))
            cursor.execute("SELECT name FROM Players ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == ["Alice", "alice"]
            cursor.execute(
                "SELECT collation_name FROM information_schema.columns "
                "WHERE lower(table_name) = 'players' AND lower(column_name) = 'name'"
                + (" AND table_schema = DATABASE()" if backend == "mysql" else "")
            )
            assert cursor.fetchone()[0] == ("C" if backend == "postgresql" else "utf8mb4_bin")
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
