"""Poker hand-domain schema queries."""

from __future__ import annotations


def hand_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for hand-domain tables."""
    if db_server == "mysql":
        return {
            "createHandsActionsTable": """CREATE TABLE HandsActions (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        street SMALLINT NOT NULL,
                        actionNo SMALLINT NOT NULL,
                        streetActionNo SMALLINT NOT NULL,
                        actionId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (actionId) REFERENCES Actions(id),
                        amount BIGINT NOT NULL,
                        raiseTo BIGINT NOT NULL,
                        amountCalled BIGINT NOT NULL,
                        numDiscarded SMALLINT NOT NULL,
                        cardsDiscarded varchar(14),
                        allIn BOOLEAN NOT NULL)
                        ENGINE=INNODB""",
            "createBoardsTable": """CREATE TABLE Boards (
                            id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                            handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                            boardId smallint,
                            boardcard1 smallint,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                            boardcard2 smallint,
                            boardcard3 smallint,
                            boardcard4 smallint,
                            boardcard5 smallint)
                        ENGINE=INNODB""",
            "createHandsCashoutTable": """CREATE TABLE HandsCashout (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        amount NUMERIC,
                        fee NUMERIC)
                        ENGINE=INNODB""",
            "createHandsShowdownTable": """CREATE TABLE HandsShowdown (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        combo VARCHAR(255),
                        cards VARCHAR(64))
                        ENGINE=INNODB""",
            "createHandsStoveTable": """CREATE TABLE HandsStove (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        streetId SMALLINT,
                        boardId SMALLINT,
                        hiLo char(1) NOT NULL,
                        rankId SMALLINT UNSIGNED NOT NULL, FOREIGN KEY (rankId) REFERENCES `Rank`(id),
                        value BIGINT,
                        cards VARCHAR(5),
                        ev NUMERIC)
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createHandsActionsTable": """CREATE TABLE HandsActions (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        street SMALLINT,
                        actionNo SMALLINT,
                        streetActionNo SMALLINT,
                        actionId SMALLINT, FOREIGN KEY (actionId) REFERENCES Actions(id),
                        amount BIGINT,
                        raiseTo BIGINT,
                        amountCalled BIGINT,
                        numDiscarded SMALLINT,
                        cardsDiscarded varchar(14),
                        allIn BOOLEAN)""",
            "createBoardsTable": """CREATE TABLE Boards (
                            id BIGSERIAL, PRIMARY KEY (id),
                            handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                            boardId smallint,
                            boardcard1 smallint,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                            boardcard2 smallint,
                            boardcard3 smallint,
                            boardcard4 smallint,
                            boardcard5 smallint)""",
            "createHandsCashoutTable": """CREATE TABLE HandsCashout (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        amount NUMERIC,
                        fee NUMERIC)""",
            "createHandsShowdownTable": """CREATE TABLE HandsShowdown (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        combo VARCHAR(255),
                        cards VARCHAR(64))""",
            "createHandsStoveTable": """CREATE TABLE HandsStove (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        streetId SMALLINT,
                        boardId SMALLINT,
                        hiLo char(1) NOT NULL,
                        rankId SMALLINT NOT NULL, FOREIGN KEY (rankId) REFERENCES Rank(id),
                        value BIGINT,
                        cards VARCHAR(5),
                        ev NUMERIC)""",
        }
    if db_server == "sqlite":
        return {
            "createHandsActionsTable": """CREATE TABLE HandsActions (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        playerId INT NOT NULL,
                        street SMALLINT,
                        actionNo SMALLINT,
                        streetActionNo SMALLINT,
                        actionId SMALLINT,
                        amount INT,
                        raiseTo INT,
                        amountCalled INT,
                        numDiscarded SMALLINT,
                        cardsDiscarded TEXT,
                        allIn BOOLEAN
                        )""",
            "createBoardsTable": """CREATE TABLE Boards (
                            id INTEGER PRIMARY KEY,
                            handId INT NOT NULL,
                            boardId INT,
                            boardcard1 INT,  /* 0=none, 1-13=2-Ah 14-26=2-Ad 27-39=2-Ac 40-52=2-As */
                            boardcard2 INT,
                            boardcard3 INT,
                            boardcard4 INT,
                            boardcard5 INT)""",
            "createHandsCashoutTable": """CREATE TABLE HandsCashout (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        playerId INT NOT NULL,
                        amount decimal,
                        fee decimal
                        )""",
            "createHandsShowdownTable": """CREATE TABLE HandsShowdown (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        playerId INT NOT NULL,
                        combo TEXT,
                        cards TEXT
                        )""",
            "createHandsStoveTable": """CREATE TABLE HandsStove (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        playerId INT NOT NULL,
                        streetId INT,
                        boardId INT,
                        hiLo TEXT NOT NULL,
                        rankId INT,
                        value INT,
                        cards TEXT,
                        ev decimal
                        )""",
        }
    return {}
