"""Core marker and locking table DDL for supported database backends."""

from __future__ import annotations


def core_schema_queries(db_server: str) -> dict[str, str]:
    """Return Settings and optional InsertLock DDL for one backend."""
    if db_server == "mysql":
        return {
            "createSettingsTable": """CREATE TABLE Settings (
                                        version SMALLINT NOT NULL)
                                ENGINE=INNODB""",
            "createLockTable": """CREATE TABLE InsertLock (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        locked BOOLEAN NOT NULL DEFAULT FALSE)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {"createSettingsTable": "CREATE TABLE Settings (version SMALLINT NOT NULL)"}
    if db_server == "sqlite":
        return {
            "createSettingsTable": """CREATE TABLE Settings
            (version INTEGER NOT NULL) """,
        }
    return {}
