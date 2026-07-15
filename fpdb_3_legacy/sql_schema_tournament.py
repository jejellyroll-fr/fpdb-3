"""Tournament-domain schema queries."""

from __future__ import annotations


def tournament_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for tournament-domain tables."""
    if db_server == "mysql":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        tourneysPlayersId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (tourneysPlayersId) REFERENCES TourneysPlayers(id),\n                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),\n                        buyInPercentage FLOAT UNSIGNED NOT NULL,\n                        payOffPercentage FLOAT UNSIGNED NOT NULL) ENGINE=INNODB",
            "createTourneysTable": """CREATE TABLE Tourneys (
                        id INT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        tourneyTypeId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (tourneyTypeId) REFERENCES TourneyTypes(id),
                        sessionId INT UNSIGNED, FOREIGN KEY (sessionId) REFERENCES Sessions(id),
                        siteTourneyNo BIGINT NOT NULL,
                        entries INT,
                        prizepool BIGINT,
                        startTime DATETIME,
                        endTime DATETIME,
                        tourneyName TEXT,
                        totalRebuyCount INT,
                        totalAddOnCount INT,
                        added BIGINT,
                        addedCurrency VARCHAR(4),
                        comment TEXT,
                        commentTs DATETIME)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id BIGSERIAL, PRIMARY KEY (id),\n                        tourneysPlayersId INT NOT NULL, FOREIGN KEY (tourneysPlayersId) REFERENCES TourneysPlayers(id),\n                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),\n                        buyInPercentage FLOAT NOT NULL,\n                        payOffPercentage FLOAT NOT NULL)",
            "createTourneysTable": """CREATE TABLE Tourneys (
                        id SERIAL, PRIMARY KEY (id),
                        tourneyTypeId INT, FOREIGN KEY (tourneyTypeId) REFERENCES TourneyTypes(id),
                        sessionId INT, FOREIGN KEY (sessionId) REFERENCES Sessions(id),
                        siteTourneyNo BIGINT,
                        entries INT,
                        prizepool BIGINT,
                        startTime timestamp without time zone,
                        endTime timestamp without time zone,
                        tourneyName TEXT,
                        totalRebuyCount INT,
                        totalAddOnCount INT,
                        added BIGINT,
                        addedCurrency VARCHAR(4),
                        comment TEXT,
                        commentTs timestamp without time zone)""",
        }
    if db_server == "sqlite":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id INTEGER PRIMARY KEY,\n                        tourneysPlayersId INT NOT NULL,\n                        playerId INT NOT NULL,\n                        buyInPercentage REAL UNSIGNED NOT NULL,\n                        payOffPercentage REAL UNSIGNED NOT NULL)",
            "createTourneysTable": """CREATE TABLE Tourneys (
                        id INTEGER PRIMARY KEY,
                        tourneyTypeId INT,
                        sessionId INT,
                        siteTourneyNo INT,
                        entries INT,
                        prizepool INT,
                        startTime timestamp,
                        endTime timestamp,
                        tourneyName TEXT,
                        totalRebuyCount INT,
                        totalAddOnCount INT,
                        added INT,
                        addedCurrency VARCHAR(4),
                        comment TEXT,
                        commentTs timestamp)""",
        }
    return {}
