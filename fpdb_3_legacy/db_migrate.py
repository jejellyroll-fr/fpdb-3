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

The engine stays backend-agnostic by routing every per-backend decision
(parameter placeholder, table listing/dropping, foreign-key handling, boolean
coercion, sequence reset) through a :class:`dialects.Dialect`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fpdb_3_legacy import dialects
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db_migrate")

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
    return dialects.dialect_for_backend(db.backend).list_tables(db)


def drop_all_tables(db: Any) -> None:
    """Drop every user table on ``db``, regardless of foreign keys or order.

    Used to rebuild a destination schema from scratch before a migration; this
    deliberately bypasses ``Database.drop_tables`` (whose MySQL path swallows
    errors and can leave tables behind). The per-backend mechanics live in the
    Dialect (FK checks off for MySQL, CASCADE for PostgreSQL, plain for SQLite).
    """
    dialects.dialect_for_backend(db.backend).drop_all_tables(db)


def _suspend_foreign_keys(db: Any) -> Any:
    """Relax foreign-key enforcement for the bulk copy; return a restore token.

    Delegates to the destination Dialect: MySQL/SQLite toggle a session flag,
    PostgreSQL drops and remembers the FK constraints (its global switch needs a
    superuser). Raises on failure so the caller can stop early.
    """
    return dialects.dialect_for_backend(db.backend).suspend_foreign_keys(db)


def _restore_foreign_keys(db: Any, token: Any) -> None:
    """Re-enable foreign-key enforcement (best effort), reversing the suspend."""
    try:
        dialects.dialect_for_backend(db.backend).restore_foreign_keys(db, token)
    except Exception as exc:  # noqa: BLE001 - re-enabling is best-effort cleanup
        log.warning("Could not fully re-enable foreign-key enforcement: %s", exc)


def _reset_sequences(dest: Any, tables: list[str]) -> None:
    """Reset PostgreSQL identity sequences to max(id)+1 after preserving ids."""
    dialects.dialect_for_backend(dest.backend).reset_sequences(dest, tables)


def _boolean_column_indices(dest: Any, table: str, columns: list[str]) -> tuple[int, ...]:
    """Indices of ``columns`` needing int->bool conversion on ``dest`` (PG only)."""
    return dialects.dialect_for_backend(dest.backend).boolean_columns(dest, table, columns)


def _coerce_booleans(row: Any, indices: tuple[int, ...]) -> tuple:
    """Return ``row`` with the given integer columns turned into bool (None kept)."""
    return dialects.Dialect.coerce_row(row, indices)


def _copy_table(source: Any, dest: Any, table: str, dest_table: str | None = None) -> int:
    """Replace the destination table's rows with the source's, preserving ids.

    ``dest_table`` may differ only in physical case: PostgreSQL folds fpdb's
    legacy mixed-case names while Linux MySQL preserves them. Every identifier
    is quoted through its dialect so reserved names such as ``Rank`` remain safe.
    """
    source_dialect = dialects.dialect_for_backend(source.backend)
    dest_dialect = dialects.dialect_for_backend(dest.backend)
    dest_table = dest_table or table

    src_cursor = source.get_cursor()
    src_cursor.execute(f"SELECT * FROM {source_dialect.quote_identifier(table)}")
    columns = [desc[0] for desc in src_cursor.description]

    dest_cursor = dest.get_cursor()
    quoted_dest_table = dest_dialect.quote_identifier(dest_table)
    dest_cursor.execute(f"SELECT * FROM {quoted_dest_table} WHERE 1 = 0")
    destination_columns = {desc[0].lower(): desc[0] for desc in dest_cursor.description}
    mapped_columns = []
    for column in columns:
        mapped = destination_columns.get(column.lower())
        if mapped is None:
            msg = f"Destination column matching {dest_table}.{column} does not exist"
            raise RuntimeError(msg)
        mapped_columns.append(mapped)
    dest_cursor.execute(f"DELETE FROM {quoted_dest_table}")

    # PostgreSQL needs integer 0/1 turned into real booleans for boolean columns.
    bool_indices = dest_dialect.boolean_columns(dest, dest_table, columns)

    placeholder = dest_dialect.placeholder
    column_list = ", ".join(dest_dialect.quote_identifier(column) for column in mapped_columns)
    placeholders = ", ".join([placeholder] * len(columns))
    insert = f"INSERT INTO {quoted_dest_table} ({column_list}) VALUES ({placeholders})"

    copied = 0
    while True:
        rows = src_cursor.fetchmany(_BATCH)
        if not rows:
            break
        if bool_indices:
            rows = [_coerce_booleans(row, bool_indices) for row in rows]
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

    # Relax destination foreign keys so table order doesn't matter. If this fails
    # the transaction is aborted, so we stop early with a clear message rather
    # than cascading table errors.
    try:
        fk_token = _suspend_foreign_keys(dest)
    except Exception as exc:  # noqa: BLE001 - fail fast on an unusable destination
        log.exception("Could not disable destination foreign keys")
        dest.rollback()
        report.error = f"Cannot disable foreign keys on the destination: {exc}"
        return report

    try:
        destination_tables = {table.lower(): table for table in list_data_tables(dest)}
        for index, table in enumerate(tables):
            if progress is not None:
                progress(index, len(tables), table)
            dest_table = destination_tables.get(table.lower())
            if dest_table is None:
                msg = f"Destination table matching {table!r} does not exist"
                raise RuntimeError(msg)
            count = _copy_table(source, dest, table, dest_table)
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
        _restore_foreign_keys(dest, fk_token)
    return report
