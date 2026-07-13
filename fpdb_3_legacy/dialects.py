"""Per-backend SQL behaviour, in one place.

fpdb supports SQLite, PostgreSQL and MySQL/MariaDB, which differ in ways that
were previously handled by ``if backend == …`` branches scattered across
``db_migrate``, ``db_backends``, ``Database`` and the 12k-line ``SQL`` module.
Those divergences are the source of the recurring cross-backend bugs (a reserved
``Rank`` table, integer-vs-boolean columns, ``set_isolation_level(0)``,
``session_replication_role`` needing a superuser, …).

A :class:`Dialect` captures one backend's quirks behind a small interface so
callers can stay backend-agnostic and each quirk has a single home. This module
starts with the data-migration surface (identifier quoting, the parameter
placeholder, listing/dropping tables, relaxing foreign keys, boolean coercion,
sequence reset); the schema/DDL surface can adopt it incrementally.
"""

from __future__ import annotations

from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("dialects")

# Backend ids, kept in sync with Database.{MYSQL_INNODB, PGSQL, SQLITE}.
MYSQL = 2
PGSQL = 3
SQLITE = 4

# db_server strings used in HUD_config.xml <database db_server="...">.
_SERVER_TO_BACKEND = {"mysql": MYSQL, "postgresql": PGSQL, "sqlite": SQLITE}


class Dialect:
    """Backend-specific SQL behaviour. Subclasses set ``name``/``backend_id``."""

    name: str = ""
    backend_id: int = 0
    placeholder: str = "%s"  # parameter marker in prepared statements

    # --- identifiers -------------------------------------------------------

    def quote_identifier(self, name: str) -> str:
        """Quote a table/column identifier for this backend (case-preserving)."""
        raise NotImplementedError

    def quote_literal(self, value: str) -> str:
        """Quote a string literal for this backend (ANSI single-quote doubling)."""
        return "'" + value.replace("'", "''") + "'"

    # --- transactions ------------------------------------------------------

    def set_autocommit(self, connection: Any, enabled: bool) -> None:
        """Toggle a driver connection's autocommit, committing any open tx first.

        Replaces the psycopg2 idiom ``set_isolation_level(0/1)``: psycopg3 has no
        level 0 and uses an ``autocommit`` flag instead. Both psycopg2 and
        psycopg3 connections expose ``autocommit``; only a very old psycopg2
        without it falls back to the legacy integer API.
        """
        if hasattr(connection, "autocommit"):
            try:
                connection.commit()  # autocommit cannot be toggled mid-transaction
            except Exception as exc:  # noqa: BLE001 - nothing to commit is fine
                log.debug("set_autocommit: commit before toggle failed: %s", exc)
            connection.autocommit = enabled
        else:  # pragma: no cover - only a very old psycopg2 would lack autocommit
            connection.set_isolation_level(0 if enabled else 1)

    # --- introspection -----------------------------------------------------

    def list_tables(self, db: Any) -> list[str]:
        """Return the names of the user tables in ``db``."""
        raise NotImplementedError

    # --- bulk copy ---------------------------------------------------------

    def boolean_columns(self, db: Any, table: str, columns: list[str]) -> tuple[int, ...]:
        """Indices of ``columns`` needing int->bool conversion (empty by default).

        Only PostgreSQL has a strict boolean type; SQLite/MySQL accept 0/1.
        """
        return ()

    @staticmethod
    def coerce_row(row: Any, bool_indices: tuple[int, ...]) -> tuple:
        """Return ``row`` with the given integer columns turned into bool (None kept)."""
        if not bool_indices:
            return tuple(row)
        values = list(row)
        for i in bool_indices:
            if values[i] is not None:
                values[i] = bool(values[i])
        return tuple(values)

    # --- destructive rebuild ----------------------------------------------

    def drop_all_tables(self, db: Any) -> None:
        """Drop every user table, regardless of foreign keys or order."""
        raise NotImplementedError

    # --- foreign keys (bulk load) -----------------------------------------

    def suspend_foreign_keys(self, db: Any) -> Any:
        """Relax FK enforcement for a bulk copy; return a token for restore."""
        raise NotImplementedError

    def restore_foreign_keys(self, db: Any, token: Any) -> None:
        """Reverse :meth:`suspend_foreign_keys` (best effort)."""
        raise NotImplementedError

    # --- sequences ---------------------------------------------------------

    def reset_sequences(self, db: Any, tables: list[str]) -> None:
        """Reset identity sequences after ids were preserved (no-op by default)."""

    def repair_sequence(self, db: Any, table: str) -> None:
        """Bring one identity sequence in sync with its table (no-op by default)."""
        return


class SqliteDialect(Dialect):
    name = "sqlite"
    backend_id = SQLITE
    placeholder = "?"

    def quote_identifier(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def list_tables(self, db: Any) -> list[str]:
        cursor = db.get_cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        return [row[0] for row in cursor.fetchall()]

    def drop_all_tables(self, db: Any) -> None:
        cursor = db.get_cursor()
        for table in self.list_tables(db):
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        db.commit()

    def suspend_foreign_keys(self, db: Any) -> Any:
        db.get_cursor().execute("PRAGMA foreign_keys = OFF")
        return None

    def restore_foreign_keys(self, db: Any, token: Any) -> None:
        db.get_cursor().execute("PRAGMA foreign_keys = ON")


class MySQLDialect(Dialect):
    name = "mysql"
    backend_id = MYSQL
    placeholder = "%s"

    def quote_identifier(self, name: str) -> str:
        return "`" + name.replace("`", "``") + "`"

    def quote_literal(self, value: str) -> str:
        # MySQL escapes string literals with backslashes by default.
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def list_tables(self, db: Any) -> list[str]:
        cursor = db.get_cursor()
        cursor.execute("SHOW TABLES")
        return [row[0] for row in cursor.fetchall()]

    def drop_all_tables(self, db: Any) -> None:
        cursor = db.get_cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in self.list_tables(db):
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        db.commit()

    def suspend_foreign_keys(self, db: Any) -> Any:
        db.get_cursor().execute("SET FOREIGN_KEY_CHECKS = 0")
        return None

    def restore_foreign_keys(self, db: Any, token: Any) -> None:
        db.get_cursor().execute("SET FOREIGN_KEY_CHECKS = 1")


class PostgresDialect(Dialect):
    name = "postgresql"
    backend_id = PGSQL
    placeholder = "%s"

    def quote_identifier(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def list_tables(self, db: Any) -> list[str]:
        cursor = db.get_cursor()
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return [row[0] for row in cursor.fetchall()]

    def boolean_columns(self, db: Any, table: str, columns: list[str]) -> tuple[int, ...]:
        cursor = db.get_cursor()
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND data_type = 'boolean'",
            (table.lower(),),
        )
        boolean_names = {row[0].lower() for row in cursor.fetchall()}
        return tuple(i for i, name in enumerate(columns) if name.lower() in boolean_names)

    def drop_all_tables(self, db: Any) -> None:
        cursor = db.get_cursor()
        for table in self.list_tables(db):
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        db.commit()

    def suspend_foreign_keys(self, db: Any) -> Any:
        # session_replication_role needs a superuser the fpdb role usually is
        # not, so drop the FK constraints (owner-level) and remember them.
        cursor = db.get_cursor()
        cursor.execute(
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE contype = 'f'",
        )
        constraints = cursor.fetchall()
        for table, name, _definition in constraints:
            cursor.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
        db.commit()
        return constraints

    def restore_foreign_keys(self, db: Any, token: Any) -> None:
        if not token:
            return
        cursor = db.get_cursor()
        for table, name, definition in token:
            cursor.execute(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" {definition}')
        db.commit()

    def reset_sequences(self, db: Any, tables: list[str]) -> None:
        cursor = db.get_cursor()
        for table in tables:
            try:
                cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                row = cursor.fetchone()
                sequence = row[0] if row else None
                if not sequence:
                    continue
                cursor.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)", (sequence,))
            except Exception as exc:  # noqa: BLE001 - a table may have no id sequence
                log.debug("No sequence reset for %s: %s", table, exc)

    def repair_sequence(self, db: Any, table: str) -> None:
        """Repair a stale serial sequence without racing normal table inserts.

        PostgreSQL does not advance a sequence when rows are copied with explicit
        ids.  This commonly happens during a cross-backend migration and leaves
        the next auto-generated id colliding with an existing row.
        """
        cursor = db.get_cursor()
        # fpdb's PostgreSQL DDL uses unquoted identifiers, so PostgreSQL stores
        # legacy mixed-case names such as ``Files`` as lower-case ``files``.
        physical_table = table.lower()
        quoted_table = self.quote_identifier(physical_table)
        cursor.execute(f"LOCK TABLE {quoted_table} IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (physical_table,))
        row = cursor.fetchone()
        sequence = row[0] if row else None
        if sequence:
            cursor.execute(
                f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {quoted_table}), 0) + 1, false)",
                (sequence,),
            )


_DIALECTS: dict[int, Dialect] = {
    SQLITE: SqliteDialect(),
    MYSQL: MySQLDialect(),
    PGSQL: PostgresDialect(),
}


def dialect_for_backend(backend_id: int) -> Dialect:
    """Return the Dialect for a numeric backend id (Database.backend)."""
    try:
        return _DIALECTS[backend_id]
    except KeyError:
        msg = f"No SQL dialect for backend id {backend_id!r}"
        raise ValueError(msg) from None


def dialect_for_server(server: str) -> Dialect:
    """Return the Dialect for a db_server string (e.g. 'postgresql')."""
    try:
        return _DIALECTS[_SERVER_TO_BACKEND[server]]
    except KeyError:
        msg = f"No SQL dialect for server {server!r}"
        raise ValueError(msg) from None
