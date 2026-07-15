"""Calendar and session-period schema queries."""

from __future__ import annotations


def _period_ddl(db_server: str, table: str, start_column: str) -> str:
    if db_server == "mysql":
        return f"""CREATE TABLE {table} (
                        id INT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        {start_column} DATETIME NOT NULL)
                        ENGINE=INNODB
                        """
    if db_server == "postgresql":
        return f"""CREATE TABLE {table} (
                        id SERIAL, PRIMARY KEY (id),
                        {start_column} timestamp without time zone NOT NULL)
                        """
    return f"""CREATE TABLE {table} (
                        id INTEGER PRIMARY KEY,
                        {start_column} timestamp NOT NULL)
                        """


def time_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for calendar periods."""
    if db_server not in {"mysql", "postgresql", "sqlite"}:
        return {}
    return {
        "createWeeksTable": _period_ddl(db_server, "Weeks", "weekStart"),
        "createMonthsTable": _period_ddl(db_server, "Months", "monthStart"),
    }
