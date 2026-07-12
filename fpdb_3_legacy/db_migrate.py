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


def drop_all_tables(db: Any) -> None:
    """Drop every user table on ``db``, regardless of foreign keys or order.

    Used to rebuild a destination schema from scratch before a migration. This
    deliberately bypasses ``Database.drop_tables`` (whose MySQL path swallows
    errors from its constraint-removal step and can leave tables behind, so a
    following ``create_tables`` fails with "table already exists"). Foreign-key
    constraints are neutralised per backend: FK checks off for MySQL, CASCADE
    for PostgreSQL, and SQLite allows the drops directly.
    """
    cursor = db.get_cursor()
    if db.backend == _MYSQL:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    suffix = " CASCADE" if db.backend == _PGSQL else ""
    for table in list_data_tables(db):
        cursor.execute(f"DROP TABLE IF EXISTS {table}{suffix}")
    if db.backend == _MYSQL:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    db.commit()


def _disable_fk(db: Any) -> None:
    """Disable foreign-key enforcement on ``db``.

    Raises on failure. On PostgreSQL this uses ``session_replication_role``,
    which needs a privileged role; a failure there is fatal (a copy would abort
    the transaction table by table), so we let it propagate and fail early.
    """
    cursor = db.get_cursor()
    if db.backend == _SQLITE:
        cursor.execute("PRAGMA foreign_keys = OFF")
    elif db.backend == _MYSQL:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    elif db.backend == _PGSQL:
        cursor.execute("SET session_replication_role = 'replica'")


def _enable_fk(db: Any) -> None:
    """Re-enable foreign-key enforcement on ``db`` (best effort)."""
    try:
        cursor = db.get_cursor()
        if db.backend == _SQLITE:
            cursor.execute("PRAGMA foreign_keys = ON")
        elif db.backend == _MYSQL:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        elif db.backend == _PGSQL:
            cursor.execute("SET session_replication_role = 'origin'")
    except Exception as exc:  # noqa: BLE001 - re-enabling is best-effort cleanup
        log.warning("Could not re-enable foreign-key enforcement: %s", exc)


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
            cursor.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)", (sequence,))
        except Exception as exc:  # noqa: BLE001 - a table may have no id sequence
            log.debug("No sequence reset for %s: %s", table, exc)


def _copy_table(source: Any, dest: Any, table: str) -> int:
    """Replace the destination table's rows with the source's, preserving ids.

    Identifiers are used unquoted, matching how fpdb creates its schema and runs
    its own queries. That keeps them case-consistent across backends (PostgreSQL
    folds unquoted names to lower case, as it did when the tables were created).
    """
    src_cursor = source.get_cursor()
    src_cursor.execute(f"SELECT * FROM {table}")
    columns = [desc[0] for desc in src_cursor.description]

    dest_cursor = dest.get_cursor()
    dest_cursor.execute(f"DELETE FROM {table}")

    placeholder = dest.sql.query.get("placeholder", "%s")
    column_list = ", ".join(columns)
    placeholders = ", ".join([placeholder] * len(columns))
    insert = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"

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

    # Relax destination foreign keys so table order doesn't matter. On PostgreSQL
    # this needs a privileged role; if it fails the transaction is aborted, so we
    # stop early with a clear message rather than cascading table errors.
    try:
        _disable_fk(dest)
    except Exception as exc:  # noqa: BLE001 - fail fast on an unusable destination
        log.exception("Could not disable destination foreign keys")
        dest.rollback()
        _enable_fk(dest)
        report.error = f"Cannot disable foreign keys on the destination: {exc}"
        return report

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
        _enable_fk(dest)
    return report
