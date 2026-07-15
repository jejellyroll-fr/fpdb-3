"""Poker hand-domain schema queries."""

from __future__ import annotations


def hand_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for hand-domain tables."""
    if db_server == "mysql":
        return {
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
        }
    if db_server == "postgresql":
        return {
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
        }
    if db_server == "sqlite":
        return {
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
        }
    return {}
