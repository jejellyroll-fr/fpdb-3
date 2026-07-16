"""Live schema checks for the PostgreSQL and MySQL catalogues."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

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


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_full_schema_executes_and_enforces_player_site_fk(backend: str) -> None:
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    with _connection(backend) as connection:
        _reset_schema(connection, backend)
        sql = Sql(db_server=backend)
        with connection.cursor() as cursor:
            for key in SCHEMA_KEYS:
                cursor.execute(sql.query[key])
        connection.commit()

        with connection.cursor() as cursor:
            if backend == "postgresql":
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            else:
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
            assert cursor.fetchone()[0] == len(SCHEMA_KEYS)

            with pytest.raises(Exception):
                cursor.execute("INSERT INTO Players(name, siteId) VALUES (%s, %s)", ("orphan", 999999))
        connection.rollback()
