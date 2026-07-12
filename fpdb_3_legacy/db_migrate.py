"""Copy all fpdb data from one database to another, across backends.

Both databases share the fpdb schema, so migration is a straight table-by-table
row copy that **preserves primary keys** (no id remapping, so foreign keys stay
valid). During the copy, foreign-key enforcement is relaxed on the destination
and each destination table is cleared first, so table order does not matter and
the default lookup rows created by a fresh schema (``fillDefaultData``) do not
collide. PostgreSQL sequences are reset afterwards.

The destination must already have the fpdb schema (see GuiDatabase's "Create
tables"). Its existing contents are replaced by the source's — migration is a
destructive operation on the destination, by design.

The engine talks to the two ``Database`` instances through their cursors and
``sql.query['placeholder']``, so it is backend-agnostic; only foreign-key
handling and sequence reset are per-backend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db_migrate")

# Database backend ids (kept in sync with Database.{MYSQL_INNODB,PGSQL,SQLITE}).
_MYSQL = 2
_PGSQL = 3
_SQLITE = 4

_BATCH = 1000

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class MigrationReport:
    """Outcome of a migration: rows copied per table plus any error."""

    tables: dict[str, int] = field(default_factory=dict)
    total_rows: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _quote(backend: int, identifier: str) -> str:
    """Quote a table/column identifier for the given backend."""
    if backend == _MYSQL:
        return f"`{identifier}`"
    return f'"{identifier}"'  # sqlite and postgresql


def list_data_tables(db: Any) -> list[str]:
    """Return the user tables of an fpdb database (excludes internal tables)."""
    cursor = db.get_cursor()
    if db.backend == _SQLITE:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    elif db.backend == _PGSQL:
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    else:  # mysql
        cursor.execute("SHOW TABLES")
    return [row[0] for row in cursor.fetchall()]


def _set_fk_enforcement(db: Any, *, enabled: bool) -> None:
    """Enable/disable foreign-key enforcement on ``db`` (best effort)."""
    cursor = db.get_cursor()
    try:
        if db.backend == _SQLITE:
            cursor.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")
        elif db.backend == _MYSQL:
            cursor.execute(f"SET FOREIGN_KEY_CHECKS = {1 if enabled else 0}")
        elif db.backend == _PGSQL:
            # Requires replication/superuser; ignored if not permitted.
            cursor.execute(f"SET session_replication_role = '{'origin' if enabled else 'replica'}'")
    except Exception as exc:  # noqa: BLE001 - relaxing FKs is best-effort
        log.warning("Could not toggle foreign-key enforcement (%s): %s", "on" if enabled else "off", exc)


def _reset_sequences(dest: Any, tables: list[str]) -> None:
    """Reset PostgreSQL identity sequences to max(id)+1 after preserving ids."""
    if dest.backend != _PGSQL:
        return
    cursor = dest.get_cursor()
    for table in tables:
        try:
            cursor.execute(
                "SELECT pg_get_serial_sequence(%s, 'id')",
                (table,),
            )
            row = cursor.fetchone()
            sequence = row[0] if row else None
            if not sequence:
                continue
            cursor.execute(f'SELECT setval(%s, COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1, false)', (sequence,))
        except Exception as exc:  # noqa: BLE001 - a table may have no id sequence
            log.debug("No sequence reset for %s: %s", table, exc)


def _copy_table(source: Any, dest: Any, table: str) -> int:
    """Replace the destination table's rows with the source's, preserving ids."""
    src_cursor = source.get_cursor()
    src_cursor.execute(f"SELECT * FROM {_quote(source.backend, table)}")
    columns = [desc[0] for desc in src_cursor.description]

    dest_cursor = dest.get_cursor()
    dest_cursor.execute(f"DELETE FROM {_quote(dest.backend, table)}")

    placeholder = dest.sql.query.get("placeholder", "%s")
    column_list = ", ".join(_quote(dest.backend, col) for col in columns)
    placeholders = ", ".join([placeholder] * len(columns))
    insert = f"INSERT INTO {_quote(dest.backend, table)} ({column_list}) VALUES ({placeholders})"

    copied = 0
    while True:
        rows = src_cursor.fetchmany(_BATCH)
        if not rows:
            break
        dest_cursor.executemany(insert, rows)
        copied += len(rows)
    return copied


def migrate(source: Any, dest: Any, *, progress: ProgressCallback | None = None) -> MigrationReport:
    """Copy every fpdb table from ``source`` into ``dest`` (replacing its data).

    Args:
        source: connected Database to read from.
        dest: connected Database (with the fpdb schema) to overwrite.
        progress: optional callback ``(index, total, table_name)`` per table.

    Returns:
        MigrationReport with per-table row counts, or an error message.
    """
    report = MigrationReport()
    tables = list_data_tables(source)

    _set_fk_enforcement(dest, enabled=False)
    try:
        for index, table in enumerate(tables):
            if progress is not None:
                progress(index, len(tables), table)
            count = _copy_table(source, dest, table)
            report.tables[table] = count
            report.total_rows += count
        dest.commit()
        _reset_sequences(dest, tables)
        dest.commit()
    except Exception as exc:  # noqa: BLE001 - report any failure to the caller
        log.exception("Migration failed")
        dest.rollback()
        report.error = str(exc)
    finally:
        _set_fk_enforcement(dest, enabled=True)
    return report
