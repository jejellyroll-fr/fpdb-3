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
    """Return backend-specific DDL for calendar periods and sessions."""
    if db_server not in {"mysql", "postgresql", "sqlite"}:
        return {}
    queries = {
        "createWeeksTable": _period_ddl(db_server, "Weeks", "weekStart"),
        "createMonthsTable": _period_ddl(db_server, "Months", "monthStart"),
    }
    if db_server == "mysql":
        queries["createSessionsTable"] = """CREATE TABLE Sessions (
                        id INT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        weekId INT UNSIGNED, FOREIGN KEY (weekId) REFERENCES Weeks(id),
                        monthId INT UNSIGNED, FOREIGN KEY (monthId) REFERENCES Months(id),
                        sessionStart DATETIME NOT NULL,
                        sessionEnd DATETIME NOT NULL)
                        ENGINE=INNODB
                        """
    elif db_server == "postgresql":
        queries["createSessionsTable"] = """CREATE TABLE Sessions (
                        id SERIAL, PRIMARY KEY (id),
                        weekId INT, FOREIGN KEY (weekId) REFERENCES Weeks(id),
                        monthId INT, FOREIGN KEY (monthId) REFERENCES Months(id),
                        sessionStart timestamp without time zone NOT NULL,
                        sessionEnd timestamp without time zone NOT NULL)
                        """
    else:
        queries["createSessionsTable"] = """CREATE TABLE Sessions (
                        id INTEGER PRIMARY KEY,
                        weekId INT,
                        monthId INT,
                        sessionStart timestamp NOT NULL,
                        sessionEnd timestamp NOT NULL)
                        """
    return queries
