"""Player identity schema queries."""

from __future__ import annotations


def player_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for players and their ratings."""
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
            "createPlayerAutoNotesTable": """CREATE TABLE PlayerAutoNotes (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        ruleId VARCHAR(80) NOT NULL,
                        ruleVersion INT NOT NULL DEFAULT 1,
                        noteText TEXT NOT NULL,
                        evidence TEXT NOT NULL,
                        createdTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updatedTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY player_auto_note_rule_hit (playerId, handId, ruleId, ruleVersion))
                        ENGINE=INNODB""",
            "createAutoratesTable": """CREATE TABLE Autorates (
                            id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                            playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                            gametypeId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (gametypeId) REFERENCES Gametypes(id),
                            description varchar(50) NOT NULL,
                            shortDesc char(8) NOT NULL,
                            ratingTime DATETIME NOT NULL,
                            handCount int NOT NULL)
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
            "createAutoratesTable": """CREATE TABLE Autorates (
                            id BIGSERIAL, PRIMARY KEY (id),
                            playerId INT, FOREIGN KEY (playerId) REFERENCES Players(id),
                            gametypeId INT, FOREIGN KEY (gametypeId) REFERENCES Gametypes(id),
                            description varchar(50),
                            shortDesc char(8),
                            ratingTime timestamp without time zone,
                            handCount int)""",
            "createPlayerAutoNotesTable": """CREATE TABLE PlayerAutoNotes (
                        id BIGSERIAL, PRIMARY KEY (id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        ruleId VARCHAR(80) NOT NULL,
                        ruleVersion INT NOT NULL DEFAULT 1,
                        noteText TEXT NOT NULL,
                        evidence TEXT NOT NULL,
                        createdTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (playerId, handId, ruleId, ruleVersion))""",
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
            "createAutoratesTable": """CREATE TABLE Autorates (
                            id INTEGER PRIMARY KEY,
                            playerId INT,
                            gametypeId INT,
                            description TEXT,
                            shortDesc TEXT,
                            ratingTime timestamp,
                            handCount int)""",
            "createPlayerAutoNotesTable": """CREATE TABLE PlayerAutoNotes (
                        id INTEGER PRIMARY KEY,
                        playerId INT NOT NULL,
                        handId INT NOT NULL,
                        ruleId TEXT NOT NULL,
                        ruleVersion INT NOT NULL DEFAULT 1,
                        noteText TEXT NOT NULL,
                        evidence TEXT NOT NULL,
                        createdTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (playerId, handId, ruleId, ruleVersion)
                        )""",
        }
    return {}
