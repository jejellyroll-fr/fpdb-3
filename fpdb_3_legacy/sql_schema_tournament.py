"""Tournament-domain schema queries."""

from __future__ import annotations


def tournament_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for tournament-domain tables."""
    if db_server == "mysql":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),\n                        tourneysPlayersId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (tourneysPlayersId) REFERENCES TourneysPlayers(id),\n                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),\n                        buyInPercentage FLOAT UNSIGNED NOT NULL,\n                        payOffPercentage FLOAT UNSIGNED NOT NULL) ENGINE=INNODB",
        }
    if db_server == "postgresql":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id BIGSERIAL, PRIMARY KEY (id),\n                        tourneysPlayersId INT NOT NULL, FOREIGN KEY (tourneysPlayersId) REFERENCES TourneysPlayers(id),\n                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),\n                        buyInPercentage FLOAT NOT NULL,\n                        payOffPercentage FLOAT NOT NULL)",
        }
    if db_server == "sqlite":
        return {
            "createBackingsTable": "CREATE TABLE Backings (\n                        id INTEGER PRIMARY KEY,\n                        tourneysPlayersId INT NOT NULL,\n                        playerId INT NOT NULL,\n                        buyInPercentage REAL UNSIGNED NOT NULL,\n                        payOffPercentage REAL UNSIGNED NOT NULL)",
        }
    return {}
