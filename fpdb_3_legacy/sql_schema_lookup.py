"""Lookup-table DDL for poker actions and ranks."""

from __future__ import annotations


def lookup_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for poker lookup tables."""
    if db_server == "mysql":
        return {
            "createActionsTable": """CREATE TABLE Actions (
                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        name varchar(32) NOT NULL,
                        code char(4) NOT NULL)
                        ENGINE=INNODB""",
            "createRankTable": """CREATE TABLE Rank (
                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        name varchar(8) NOT NULL)
                        ENGINE=INNODB""",
            "createStartCardsTable": """CREATE TABLE StartCards (
                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        category varchar(9) NOT NULL,
                        name varchar(32) NOT NULL,
                        rank SMALLINT NOT NULL,
                        combinations SMALLINT NOT NULL)
                        ENGINE=INNODB""",
            "createSitesTable": """CREATE TABLE Sites (
                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        name varchar(32) NOT NULL,
                        code char(2) NOT NULL)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createActionsTable": """CREATE TABLE Actions (
                        id SERIAL, PRIMARY KEY (id),
                        name varchar(32),
                        code char(4))""",
            "createRankTable": """CREATE TABLE Rank (
                        id SERIAL, PRIMARY KEY (id),
                        name varchar(8))""",
            "createStartCardsTable": """CREATE TABLE StartCards (
                        id SERIAL, PRIMARY KEY (id),
                        category varchar(9) NOT NULL,
                        name varchar(32),
                        rank SMALLINT NOT NULL,
                        combinations SMALLINT NOT NULL)""",
            "createSitesTable": """CREATE TABLE Sites (
                        id SERIAL, PRIMARY KEY (id),
                        name varchar(32),
                        code char(2))""",
        }
    if db_server == "sqlite":
        return {
            "createActionsTable": """CREATE TABLE Actions (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL)""",
            "createRankTable": """CREATE TABLE Rank (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL)""",
            "createStartCardsTable": """CREATE TABLE StartCards (
                        id INTEGER PRIMARY KEY,
                        category TEXT NOT NULL,
                        name TEXT NOT NULL,
                        rank SMALLINT NOT NULL,
                        combinations SMALLINT NOT NULL)""",
            "createSitesTable": """CREATE TABLE Sites (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL)""",
        }
    return {}
