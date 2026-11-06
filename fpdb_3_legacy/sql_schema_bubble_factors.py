"""Each preflop decision's bubble factor in a tournament with a known structure (#446).

A feature table, created by ``ensure_feature_tables`` on databases that predate
it, so no ``DB_VERSION`` bump. It is derived data: a tournament's rows are
replaced whenever its hands, results or payout structure change
(:mod:`fpdb_3_legacy.bubble_factors`). Keyed like ``HandsSituations``, on the
hand and the action number, so the analytics engine joins it the same way.
"""

from __future__ import annotations

_DDL = {
    "mysql": """CREATE TABLE ActionBubbleFactors (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        handId BIGINT UNSIGNED NOT NULL,
                        actionNo SMALLINT NOT NULL,
                        tourneyId INT UNSIGNED NOT NULL,
                        opponent VARCHAR(32) NOT NULL,
                        bubbleFactor INT NOT NULL,
                        UNIQUE KEY action_bubble_factor (handId, actionNo),
                        KEY action_bubble_factor_tourney (tourneyId))
                        ENGINE=INNODB""",
    "postgresql": """CREATE TABLE ActionBubbleFactors (
                        id BIGSERIAL, PRIMARY KEY (id),
                        handId BIGINT NOT NULL,
                        actionNo SMALLINT NOT NULL,
                        tourneyId INT NOT NULL,
                        opponent VARCHAR(32) NOT NULL,
                        bubbleFactor INT NOT NULL,
                        UNIQUE (handId, actionNo))""",
    "sqlite": """CREATE TABLE ActionBubbleFactors (
                        id INTEGER PRIMARY KEY,
                        handId INT NOT NULL,
                        actionNo INT NOT NULL,
                        tourneyId INT NOT NULL,
                        opponent TEXT NOT NULL,
                        bubbleFactor INT NOT NULL,
                        UNIQUE (handId, actionNo))""",
}

# MySQL declares its tourney index in the table; the others add it here, best-effort.
_INDEX = {
    "postgresql": "CREATE INDEX action_bubble_factor_tourney ON ActionBubbleFactors (tourneyId)",
    "sqlite": "CREATE INDEX action_bubble_factor_tourney ON ActionBubbleFactors (tourneyId)",
}

# %s placeholders; finalize_query_placeholders turns them into ? for SQLite.
_QUERIES = {
    "deleteActionBubbleFactors": "DELETE FROM ActionBubbleFactors WHERE tourneyId = %s",
    "insertActionBubbleFactor": """INSERT INTO ActionBubbleFactors (handId, actionNo, tourneyId, opponent, bubbleFactor)
                        VALUES (%s, %s, %s, %s, %s)""",
    "selectTourneyMaxSeats": """SELECT MAX(g.maxSeats) FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId
                        WHERE h.tourneyId = %s""",
    "selectTourneyStartStacks": """SELECT hp.handId, pl.name, hp.startCash FROM HandsPlayers hp
                        JOIN Hands h ON h.id = hp.handId
                        JOIN Players pl ON pl.id = hp.playerId
                        WHERE h.tourneyId = %s""",
    "selectTourneyPreflopDecisions": """SELECT si.handId, si.actionNo, pl.name, si.facingPlayer, si.response
                        FROM HandsSituations si
                        JOIN Hands h ON h.id = si.handId
                        JOIN Players pl ON pl.id = si.playerId
                        WHERE h.tourneyId = %s AND si.streetName = 'preflop'
                        ORDER BY si.handId, si.actionNo""",
    "selectTourneysWithHands": "SELECT DISTINCT tourneyId FROM Hands WHERE tourneyId IS NOT NULL",
}


def bubble_factor_queries(db_server: str) -> dict[str, str]:
    """The ActionBubbleFactors DDL for ``db_server``, and the queries that read and write it."""
    queries = dict(_QUERIES)
    ddl = _DDL.get(db_server)
    if ddl is not None:
        queries["createActionBubbleFactorsTable"] = ddl
    index = _INDEX.get(db_server)
    if index is not None:
        queries["addActionBubbleFactorsTourneyIndex"] = index
    return queries
