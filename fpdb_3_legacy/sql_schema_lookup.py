"""Lookup-table DDL for poker actions and ranks."""

from __future__ import annotations


def lookup_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for Actions and Rank."""
    if db_server == "mysql":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        name varchar(32) NOT NULL,\n                        code char(4) NOT NULL)\n                        ENGINE=INNODB",
            "createRankTable": "CREATE TABLE Rank (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        name varchar(8) NOT NULL)\n                        ENGINE=INNODB",
        }
    if db_server == "postgresql":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id SERIAL, PRIMARY KEY (id),\n                        name varchar(32),\n                        code char(4))",
            "createRankTable": "CREATE TABLE Rank (\n                        id SERIAL, PRIMARY KEY (id),\n                        name varchar(8))",
        }
    if db_server == "sqlite":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id INTEGER PRIMARY KEY,\n                        name TEXT NOT NULL,\n                        code TEXT NOT NULL)",
            "createRankTable": "CREATE TABLE Rank (\n                        id INTEGER PRIMARY KEY,\n                        name TEXT NOT NULL)",
        }
    return {}
