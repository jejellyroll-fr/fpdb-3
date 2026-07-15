"""Root poker-hand schema queries."""

from __future__ import annotations


def root_hand_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for the root Hands table."""
    if db_server == "mysql":
        ddl = """CREATE TABLE Hands (
                                    id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                                    tableName VARCHAR(50) NOT NULL,
                                    siteHandNo BIGINT NOT NULL,
                                    tourneyId INT UNSIGNED, FOREIGN KEY (tourneyId) REFERENCES Tourneys(id),
                                    gametypeId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (gametypeId) REFERENCES Gametypes(id),
                                    sessionId INT UNSIGNED, FOREIGN KEY (sessionId) REFERENCES Sessions(id),
                                    fileId INT(10) UNSIGNED NOT NULL, FOREIGN KEY (fileId) REFERENCES Files(id),
                                    startTime DATETIME NOT NULL,
                                    importTime DATETIME NOT NULL,
                                    seats TINYINT NOT NULL,
                                    heroSeat TINYINT NOT NULL,
                                    maxPosition TINYINT NOT NULL,
                                    boardcard1 smallint,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                                    boardcard2 smallint,
                                    boardcard3 smallint,
                                    boardcard4 smallint,
                                    boardcard5 smallint,
                                    texture smallint,
                                    runItTwice BOOLEAN,
                                    playersVpi SMALLINT NOT NULL,         /* num of players vpi */
                                    playersAtStreet1 SMALLINT NOT NULL,   /* num of players seeing flop/street4 */
                                    playersAtStreet2 SMALLINT NOT NULL,
                                    playersAtStreet3 SMALLINT NOT NULL,
                                    playersAtStreet4 SMALLINT NOT NULL,
                                    playersAtShowdown SMALLINT NOT NULL,
                                    street0Raises TINYINT NOT NULL, /* num small bets paid to see flop/street4, including blind */
                                    street1Raises TINYINT NOT NULL, /* num small bets paid to see turn/street5 */
                                    street2Raises TINYINT NOT NULL, /* num big bets paid to see river/street6 */
                                    street3Raises TINYINT NOT NULL, /* num big bets paid to see sd/street7 */
                                    street4Raises TINYINT NOT NULL, /* num big bets paid to see showdown */
                                    street0Pot BIGINT,                  /* pot size at pre-flop/street2 */
                                    street1Pot BIGINT,                  /* pot size at flop/street4 */
                                    street2Pot BIGINT,                  /* pot size at turn/street5 */
                                    street3Pot BIGINT,                  /* pot size at river/street6 */
                                    street4Pot BIGINT,                  /* pot size at sd/street7 */
                                    finalPot   BIGINT,                  /* final pot size */
                                    bombPot    BIGINT,                  /* bomb pot amount (0 = no bomb pot) */
                                    comment TEXT,
                                    commentTs DATETIME)
                                ENGINE=INNODB"""
    elif db_server == "postgresql":
        ddl = """CREATE TABLE Hands (
                                    id BIGSERIAL, PRIMARY KEY (id),
                                    tableName VARCHAR(50) NOT NULL,
                                    siteHandNo BIGINT NOT NULL,
                                    tourneyId INT, FOREIGN KEY (tourneyId) REFERENCES Tourneys(id),
                                    gametypeId INT NOT NULL, FOREIGN KEY (gametypeId) REFERENCES Gametypes(id),
                                    sessionId INT, FOREIGN KEY (sessionId) REFERENCES Sessions(id),
                                    fileId BIGINT NOT NULL, FOREIGN KEY (fileId) REFERENCES Files(id),
                                    startTime timestamp without time zone NOT NULL,
                                    importTime timestamp without time zone NOT NULL,
                                    seats SMALLINT NOT NULL,
                                    heroSeat SMALLINT NOT NULL,
                                    maxPosition SMALLINT NOT NULL,
                                    boardcard1 smallint,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                                    boardcard2 smallint,
                                    boardcard3 smallint,
                                    boardcard4 smallint,
                                    boardcard5 smallint,
                                    texture smallint,
                                    runItTwice BOOLEAN,
                                    playersVpi SMALLINT NOT NULL,         /* num of players vpi */
                                    playersAtStreet1 SMALLINT NOT NULL,   /* num of players seeing flop/street4 */
                                    playersAtStreet2 SMALLINT NOT NULL,
                                    playersAtStreet3 SMALLINT NOT NULL,
                                    playersAtStreet4 SMALLINT NOT NULL,
                                    playersAtShowdown SMALLINT NOT NULL,
                                    street0Raises SMALLINT NOT NULL, /* num small bets paid to see flop/street4, including blind */
                                    street1Raises SMALLINT NOT NULL, /* num small bets paid to see turn/street5 */
                                    street2Raises SMALLINT NOT NULL, /* num big bets paid to see river/street6 */
                                    street3Raises SMALLINT NOT NULL, /* num big bets paid to see sd/street7 */
                                    street4Raises SMALLINT NOT NULL, /* num big bets paid to see showdown */
                                    street0Pot BIGINT,                 /* pot size at preflop/street3 */
                                    street1Pot BIGINT,                 /* pot size at flop/street4 */
                                    street2Pot BIGINT,                 /* pot size at turn/street5 */
                                    street3Pot BIGINT,                 /* pot size at river/street6 */
                                    street4Pot BIGINT,                 /* pot size at sd/street7 */
                                    finalPot   BIGINT,                 /* final pot size */
                                    bombPot    BIGINT,                 /* bomb pot amount (0 = no bomb pot) */
                                    comment TEXT,
                                    commentTs timestamp without time zone)"""
    elif db_server == "sqlite":
        ddl = """CREATE TABLE Hands (
                                    id INTEGER PRIMARY KEY,
                                    tableName TEXT(50) NOT NULL,
                                    siteHandNo INT NOT NULL,
                                    tourneyId INT,
                                    gametypeId INT NOT NULL,
                                    sessionId INT,
                                    fileId INT NOT NULL,
                                    startTime timestamp NOT NULL,
                                    importTime timestamp NOT NULL,
                                    seats INT NOT NULL,
                                    heroSeat INT NOT NULL,
                                    maxPosition INT NOT NULL,
                                    boardcard1 INT,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                                    boardcard2 INT,
                                    boardcard3 INT,
                                    boardcard4 INT,
                                    boardcard5 INT,
                                    texture INT,
                                    runItTwice BOOLEAN,
                                    playersVpi INT NOT NULL,         /* num of players vpi */
                                    playersAtStreet1 INT NOT NULL,   /* num of players seeing flop/street4 */
                                    playersAtStreet2 INT NOT NULL,
                                    playersAtStreet3 INT NOT NULL,
                                    playersAtStreet4 INT NOT NULL,
                                    playersAtShowdown INT NOT NULL,
                                    street0Raises INT NOT NULL, /* num small bets paid to see flop/street4, including blind */
                                    street1Raises INT NOT NULL, /* num small bets paid to see turn/street5 */
                                    street2Raises INT NOT NULL, /* num big bets paid to see river/street6 */
                                    street3Raises INT NOT NULL, /* num big bets paid to see sd/street7 */
                                    street4Raises INT NOT NULL, /* num big bets paid to see showdown */
                                    street0Pot INT,                 /* pot size at preflop/street3 */
                                    street1Pot INT,                 /* pot size at flop/street4 */
                                    street2Pot INT,                 /* pot size at turn/street5 */
                                    street3Pot INT,                 /* pot size at river/street6 */
                                    street4Pot INT,                 /* pot size at sd/street7 */
                                    finalPot INT,                   /* final pot size */
                                    bombPot INT,                    /* bomb pot amount (0 = no bomb pot) */
                                    comment TEXT,
                                    commentTs timestamp)"""
    else:
        return {}
    return {"createHandsTable": ddl}

