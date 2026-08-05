"""Hand-history import schema queries."""

from __future__ import annotations


def import_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for imported file tracking."""
    if db_server == "mysql":
        return {
            "createFilesTable": """CREATE TABLE Files (
                        id INT(10) UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        file text NOT NULL,
                        site VARCHAR(32),
                        type VARCHAR(7),
                        startTime DATETIME NOT NULL,
                        lastUpdate DATETIME NOT NULL,
                        endTime DATETIME,
                        hands INT,
                        storedHands INT,
                        dups INT,
                        partial INT,
                        skipped INT,
                        errs INT,
                        ttime100 INT,
                        finished BOOLEAN)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createFilesTable": """CREATE TABLE Files (
                        id BIGSERIAL, PRIMARY KEY (id),
                        file TEXT NOT NULL,
                        site VARCHAR(32),
                        type VARCHAR(7),
                        startTime timestamp without time zone NOT NULL,
                        lastUpdate timestamp without time zone NOT NULL,
                        endTime timestamp without time zone,
                        hands INT,
                        storedHands INT,
                        dups INT,
                        partial INT,
                        skipped INT,
                        errs INT,
                        ttime100 INT,
                        finished BOOLEAN)""",
        }
    if db_server == "sqlite":
        return {
            "createFilesTable": """CREATE TABLE Files (
                        id INTEGER PRIMARY KEY,
                        file TEXT NOT NULL,
                        site VARCHAR(32),
                        type VARCHAR(7),
                        startTime timestamp NOT NULL,
                        lastUpdate timestamp NOT NULL,
                        endTime timestamp,
                        hands INT,
                        storedHands INT,
                        dups INT,
                        partial INT,
                        skipped INT,
                        errs INT,
                        ttime100 INT,
                        finished BOOLEAN
                        )""",
        }
    return {}
