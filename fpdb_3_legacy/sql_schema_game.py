"""Poker game-definition schema queries."""

from __future__ import annotations


def game_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for game definitions."""
    if db_server == "mysql":
        return {
            "createGametypesTable": """CREATE TABLE Gametypes (
                        id SMALLINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        siteId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (siteId) REFERENCES Sites(id),
                        currency varchar(4) NOT NULL,
                        type char(4) NOT NULL,
                        base char(4) NOT NULL,
                        category varchar(10) NOT NULL,
                        limitType char(2) NOT NULL,
                        hiLo char(1) NOT NULL,
                        mix varchar(9) NOT NULL,
                        smallBlind bigint,
                        bigBlind bigint,
                        smallBet bigint NOT NULL,
                        bigBet bigint NOT NULL,
                        maxSeats TINYINT NOT NULL,
                        ante INT NOT NULL,
                        buyinType varchar(9) NOT NULL,
                        fast BOOLEAN,
                        newToGame BOOLEAN,
                        homeGame BOOLEAN,
                        split BOOLEAN)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createGametypesTable": """CREATE TABLE Gametypes (
                        id SERIAL NOT NULL, PRIMARY KEY (id),
                        siteId INTEGER NOT NULL, FOREIGN KEY (siteId) REFERENCES Sites(id),
                        currency varchar(4) NOT NULL,
                        type char(4) NOT NULL,
                        base char(4) NOT NULL,
                        category varchar(10) NOT NULL,
                        limitType char(2) NOT NULL,
                        hiLo char(1) NOT NULL,
                        mix varchar(9) NOT NULL,
                        smallBlind bigint,
                        bigBlind bigint,
                        smallBet bigint NOT NULL,
                        bigBet bigint NOT NULL,
                        maxSeats SMALLINT NOT NULL,
                        ante INT NOT NULL,
                        buyinType varchar(9) NOT NULL,
                        fast BOOLEAN,
                        newToGame BOOLEAN,
                        homeGame BOOLEAN,
                        split BOOLEAN)""",
        }
    if db_server == "sqlite":
        return {
            "createGametypesTable": """CREATE TABLE Gametypes (
                        id INTEGER PRIMARY KEY NOT NULL,
                        siteId INTEGER NOT NULL,
                        currency TEXT NOT NULL,
                        type TEXT NOT NULL,
                        base TEXT NOT NULL,
                        category TEXT NOT NULL,
                        limitType TEXT NOT NULL,
                        hiLo TEXT NOT NULL,
                        mix TEXT NOT NULL,
                        smallBlind INTEGER,
                        bigBlind INTEGER,
                        smallBet INTEGER NOT NULL,
                        bigBet INTEGER NOT NULL,
                        maxSeats INT NOT NULL,
                        ante INT NOT NULL,
                        buyinType TEXT NOT NULL,
                        fast INT,
                        newToGame INT,
                        homeGame INT,
                        split INT,
                        FOREIGN KEY(siteId) REFERENCES Sites(id) ON DELETE CASCADE)""",
        }
    return {}
