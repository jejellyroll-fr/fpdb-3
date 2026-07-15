"""Player identity schema queries."""

from __future__ import annotations


def player_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for players."""
    if db_server == "mysql":
        return {
            "createPlayersTable": """CREATE TABLE Players (
                        id INT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        name VARCHAR(32) NOT NULL,
                        siteId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (siteId) REFERENCES Sites(id),
                        hero BOOLEAN,
                        chars char(3),
                        comment text,
                        commentTs DATETIME,
                        profil text,
                        color_code VARCHAR(7) DEFAULT '#FFFFFF',
                        symbol VARCHAR(10) DEFAULT '★'
                        )
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createPlayersTable": """CREATE TABLE Players (
                        id SERIAL, PRIMARY KEY (id),
                        name VARCHAR(32),
                        siteId INTEGER, FOREIGN KEY (siteId) REFERENCES Sites(id),
                        hero BOOLEAN,
                        chars char(3),
                        comment text,
                        commentTs timestamp without time zone,
                        profil text,
                        color_code VARCHAR(7) DEFAULT '#FFFFFF',
                        symbol VARCHAR(10) DEFAULT '★' )""",
        }
    if db_server == "sqlite":
        return {
            "createPlayersTable": """CREATE TABLE Players (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        siteId INTEGER,
                        hero BOOLEAN,
                        chars TEXT,
                        comment TEXT,
                        commentTs timestamp,
                        profil TEXT,
                        color_code TEXT DEFAULT '#FFFFFF',
                        symbol TEXT DEFAULT '★',
                        FOREIGN KEY(siteId) REFERENCES Sites(id) ON DELETE CASCADE)""",
        }
    return {}
