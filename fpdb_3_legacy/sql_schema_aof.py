"""Structured All-in or Fold decision and analysis schema."""

from __future__ import annotations


def aof_schema_queries(db_server: str) -> dict[str, str]:
    """Return backend-specific DDL for AoF decisions and derived analyses."""
    if db_server == "mysql":
        return {
            "createAofDecisionsTable": """CREATE TABLE AofDecisions (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT UNSIGNED NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        category VARCHAR(24) NOT NULL,
                        decision VARCHAR(8) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        activeOpponents SMALLINT UNSIGNED NOT NULL,
                        potBefore BIGINT NOT NULL,
                        amountToCommit BIGINT NOT NULL,
                        blindCommitted BIGINT NOT NULL,
                        cardsObservable BOOLEAN NOT NULL,
                        holeCards VARCHAR(32),
                        flopCards VARCHAR(16),
                        madeHand VARCHAR(32),
                        flushDraw VARCHAR(32),
                        straightOuts SMALLINT,
                        classifierVersion INT NOT NULL,
                        createdTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updatedTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY aof_decision_version (handId, playerId, classifierVersion))
                        ENGINE=INNODB""",
            "createAofDecisionAnalysesTable": """CREATE TABLE AofDecisionAnalyses (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        decisionId BIGINT UNSIGNED NOT NULL,
                        FOREIGN KEY (decisionId) REFERENCES AofDecisions(id),
                        backend VARCHAR(64) NOT NULL,
                        backendVersion VARCHAR(32) NOT NULL,
                        rangeModel VARCHAR(80) NOT NULL,
                        rangeVersion INT NOT NULL,
                        analysisVersion INT NOT NULL,
                        equityPpm INT,
                        evChips BIGINT,
                        evBbPpm BIGINT,
                        breakEvenPpm INT,
                        samples BIGINT,
                        stderrPpm INT,
                        status VARCHAR(16) NOT NULL,
                        errorText TEXT,
                        createdTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updatedTs DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY aof_analysis_version (
                            decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion))
                        ENGINE=INNODB""",
        }
    if db_server == "postgresql":
        return {
            "createAofDecisionsTable": """CREATE TABLE AofDecisions (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL, FOREIGN KEY (handId) REFERENCES Hands(id),
                        playerId INT NOT NULL, FOREIGN KEY (playerId) REFERENCES Players(id),
                        category VARCHAR(24) NOT NULL,
                        decision VARCHAR(8) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        activeOpponents SMALLINT NOT NULL,
                        potBefore BIGINT NOT NULL,
                        amountToCommit BIGINT NOT NULL,
                        blindCommitted BIGINT NOT NULL,
                        cardsObservable BOOLEAN NOT NULL,
                        holeCards VARCHAR(32),
                        flopCards VARCHAR(16),
                        madeHand VARCHAR(32),
                        flushDraw VARCHAR(32),
                        straightOuts SMALLINT,
                        classifierVersion INT NOT NULL,
                        createdTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (handId, playerId, classifierVersion))""",
            "createAofDecisionAnalysesTable": """CREATE TABLE AofDecisionAnalyses (
                        id BIGSERIAL, PRIMARY KEY (id),
                        decisionId BIGINT NOT NULL,
                        FOREIGN KEY (decisionId) REFERENCES AofDecisions(id),
                        backend VARCHAR(64) NOT NULL,
                        backendVersion VARCHAR(32) NOT NULL,
                        rangeModel VARCHAR(80) NOT NULL,
                        rangeVersion INT NOT NULL,
                        analysisVersion INT NOT NULL,
                        equityPpm INT,
                        evChips BIGINT,
                        evBbPpm BIGINT,
                        breakEvenPpm INT,
                        samples BIGINT,
                        stderrPpm INT,
                        status VARCHAR(16) NOT NULL,
                        errorText TEXT,
                        createdTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (
                            decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion))""",
        }
    if db_server == "sqlite":
        return {
            "createAofDecisionsTable": """CREATE TABLE AofDecisions (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        playerId INT NOT NULL,
                        category TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        role TEXT NOT NULL,
                        activeOpponents INT NOT NULL,
                        potBefore BIGINT NOT NULL,
                        amountToCommit BIGINT NOT NULL,
                        blindCommitted BIGINT NOT NULL,
                        cardsObservable BOOLEAN NOT NULL,
                        holeCards TEXT,
                        flopCards TEXT,
                        madeHand TEXT,
                        flushDraw TEXT,
                        straightOuts INT,
                        classifierVersion INT NOT NULL,
                        createdTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (handId, playerId, classifierVersion),
                        FOREIGN KEY(handId) REFERENCES Hands(id) ON DELETE CASCADE,
                        FOREIGN KEY(playerId) REFERENCES Players(id) ON DELETE CASCADE
                        )""",
            "createAofDecisionAnalysesTable": """CREATE TABLE AofDecisionAnalyses (
                        id INTEGER PRIMARY KEY,
                        decisionId INT NOT NULL,
                        backend TEXT NOT NULL,
                        backendVersion TEXT NOT NULL,
                        rangeModel TEXT NOT NULL,
                        rangeVersion INT NOT NULL,
                        analysisVersion INT NOT NULL,
                        equityPpm INT,
                        evChips BIGINT,
                        evBbPpm BIGINT,
                        breakEvenPpm INT,
                        samples BIGINT,
                        stderrPpm INT,
                        status TEXT NOT NULL,
                        errorText TEXT,
                        createdTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        updatedTs timestamp DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (
                            decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion),
                        FOREIGN KEY(decisionId) REFERENCES AofDecisions(id) ON DELETE CASCADE
                        )""",
        }
    return {}
