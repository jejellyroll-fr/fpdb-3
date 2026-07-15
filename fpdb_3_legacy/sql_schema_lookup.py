"""Lookup-table DDL for poker actions and ranks."""

from __future__ import annotations


def lookup_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for poker lookup tables."""
    if db_server == "mysql":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        name varchar(32) NOT NULL,\n                        code char(4) NOT NULL)\n                        ENGINE=INNODB",
            "createRankTable": "CREATE TABLE Rank (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        name varchar(8) NOT NULL)\n                        ENGINE=INNODB",
            "createStartCardsTable": "CREATE TABLE StartCards (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        category varchar(9) NOT NULL,\n                        name varchar(32) NOT NULL,\n                        rank SMALLINT NOT NULL,\n                        combinations SMALLINT NOT NULL)\n                        ENGINE=INNODB",
            "createSitesTable": "CREATE TABLE Sites (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        name varchar(32) NOT NULL,\n                        code char(2) NOT NULL)\n                        ENGINE=INNODB",
        }
    if db_server == "postgresql":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id SERIAL, PRIMARY KEY (id),\n                        name varchar(32),\n                        code char(4))",
            "createRankTable": "CREATE TABLE Rank (\n                        id SERIAL, PRIMARY KEY (id),\n                        name varchar(8))",
            "createStartCardsTable": "CREATE TABLE StartCards (\n                        id SERIAL, PRIMARY KEY (id),\n                        category varchar(9) NOT NULL,\n                        name varchar(32),\n                        rank SMALLINT NOT NULL,\n                        combinations SMALLINT NOT NULL)",
            "createSitesTable": "CREATE TABLE Sites (\n                        id SERIAL, PRIMARY KEY (id),\n                        name varchar(32),\n                        code char(2))",
        }
    if db_server == "sqlite":
        return {
            "createActionsTable": "CREATE TABLE Actions (\n                        id INTEGER PRIMARY KEY,\n                        name TEXT NOT NULL,\n                        code TEXT NOT NULL)",
            "createRankTable": "CREATE TABLE Rank (\n                        id INTEGER PRIMARY KEY,\n                        name TEXT NOT NULL)",
            "createStartCardsTable": "CREATE TABLE StartCards (\n                        id INTEGER PRIMARY KEY,\n                        category TEXT NOT NULL,\n                        name TEXT NOT NULL,\n                        rank SMALLINT NOT NULL,\n                        combinations SMALLINT NOT NULL)",
            "createSitesTable": "CREATE TABLE Sites (\n                        id INTEGER PRIMARY KEY,\n                        name TEXT NOT NULL,\n                        code TEXT NOT NULL)",
        }
    return {}
