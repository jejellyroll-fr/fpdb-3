"""Raw hand and tournament archive table DDL."""

from __future__ import annotations


def _raw_table_ddl(db_server: str, table: str, foreign_column: str, raw_column: str) -> str:
    if db_server == "mysql":
        return f"CREATE TABLE {table} (\n                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        {foreign_column} BIGINT NOT NULL,\n                        {raw_column} TEXT NOT NULL,\n                        complain BOOLEAN NOT NULL DEFAULT FALSE)\n                        ENGINE=INNODB"
    if db_server == "postgresql":
        return f"CREATE TABLE {table} (\n                        id BIGSERIAL, PRIMARY KEY (id),\n                        {foreign_column} BIGINT NOT NULL,\n                        {raw_column} TEXT NOT NULL,\n                        complain BOOLEAN NOT NULL DEFAULT FALSE)"
    if db_server == "sqlite":
        return f"CREATE TABLE {table} (\n                        id INTEGER PRIMARY KEY,\n                        {foreign_column} BIGINT NOT NULL,\n                        {raw_column} TEXT NOT NULL,\n                        complain BOOLEAN NOT NULL DEFAULT FALSE)"
    raise ValueError(f"Unsupported database backend: {db_server}")


def raw_schema_queries(db_server: str) -> dict[str, str]:
    """Return DDL for raw hand-history and tournament-summary archives."""
    if db_server not in {"mysql", "postgresql", "sqlite"}:
        return {}
    return {
        "createRawHands": _raw_table_ddl(db_server, "RawHands", "handId", "rawHand"),
        "createRawTourneys": _raw_table_ddl(db_server, "RawTourneys", "tourneyId", "rawTourney"),
    }
