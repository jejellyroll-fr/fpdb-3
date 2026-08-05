"""Backend-specific metadata and administration SQL queries."""

from __future__ import annotations


def metadata_queries(db_server: str) -> dict[str, str]:
    """Build the common metadata query catalogue for one database backend."""
    queries = {
        "drop_table": "DROP TABLE IF EXISTS ",
        "getSiteId": "SELECT id from Sites where name = %s",
        "getGames": "SELECT DISTINCT category from Gametypes",
        "getCurrencies": "SELECT DISTINCT currency from Gametypes ORDER BY currency",
        "getLimits": "SELECT DISTINCT bigBlind from Gametypes ORDER by bigBlind DESC",
        "getTourneyTypesIds": "SELECT id FROM TourneyTypes",
        "getTourneyTypes": "SELECT DISTINCT tourneyName FROM Tourneys",
        "getTourneyNames": "SELECT tourneyName FROM Tourneys",
    }
    if db_server == "mysql":
        queries.update(
            {
                "list_tables": "SHOW TABLES",
                "list_indexes": "SHOW INDEXES",
                "set tx level": """SET SESSION TRANSACTION
            ISOLATION LEVEL READ COMMITTED""",
            },
        )
    elif db_server == "postgresql":
        queries.update(
            {
                "list_tables": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
                "list_indexes": "SELECT tablename, indexname FROM PG_INDEXES",
                "set tx level": """SET SESSION TRANSACTION
            ISOLATION LEVEL READ COMMITTED""",
            },
        )
    elif db_server == "sqlite":
        queries.update(
            {
                "list_tables": """SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name;""",
                "list_indexes": """SELECT name FROM sqlite_master
                                            WHERE type='index'
                                            ORDER BY name;""",
                "set tx level": " ",
            },
        )
    return queries
