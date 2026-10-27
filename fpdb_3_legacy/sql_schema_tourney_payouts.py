"""Tournament payout structures (#446): the prize for each finishing place.

A table added after the original schema, created by ``ensure_feature_tables``
on databases that predate it, so no ``DB_VERSION`` bump: it holds the payouts
a summary cannot give -- entered by hand or applied from a preset. Payouts a
summary does give are read from ``TourneysPlayers`` instead of copied here.
Amounts are stored x100, like ``TourneysPlayers.winnings``.
"""

from __future__ import annotations

_DDL = {
    "mysql": """CREATE TABLE TourneyPayouts (
                        id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, PRIMARY KEY (id),
                        tourneyId INT UNSIGNED NOT NULL, FOREIGN KEY (tourneyId) REFERENCES Tourneys(id),
                        place INT NOT NULL,
                        amount BIGINT NOT NULL,
                        source VARCHAR(32) NOT NULL,
                        UNIQUE KEY tourney_payout_place (tourneyId, place))
                        ENGINE=INNODB""",
    "postgresql": """CREATE TABLE TourneyPayouts (
                        id BIGSERIAL, PRIMARY KEY (id),
                        tourneyId INT NOT NULL, FOREIGN KEY (tourneyId) REFERENCES Tourneys(id),
                        place INT NOT NULL,
                        amount BIGINT NOT NULL,
                        source VARCHAR(32) NOT NULL,
                        UNIQUE (tourneyId, place))""",
    "sqlite": """CREATE TABLE TourneyPayouts (
                        id INTEGER PRIMARY KEY,
                        tourneyId INT NOT NULL,
                        place INT NOT NULL,
                        amount INT NOT NULL,
                        source TEXT NOT NULL,
                        FOREIGN KEY (tourneyId) REFERENCES Tourneys(id),
                        UNIQUE (tourneyId, place))""",
}

# %s placeholders; finalize_query_placeholders turns them into ? for SQLite.
_QUERIES = {
    "selectTourneyPayouts": "SELECT place, amount, source FROM TourneyPayouts WHERE tourneyId = %s ORDER BY place",
    "deleteTourneyPayouts": "DELETE FROM TourneyPayouts WHERE tourneyId = %s",
    "insertTourneyPayout": "INSERT INTO TourneyPayouts (tourneyId, place, amount, source) VALUES (%s, %s, %s, %s)",
    "selectTourneyResults": """SELECT tp.rank, tp.winnings FROM TourneysPlayers tp
                        WHERE tp.tourneyId = %s AND tp.rank IS NOT NULL ORDER BY tp.rank""",
    "selectTourneyFacts": """SELECT t.entries, t.prizepool, tt.buyIn, tt.currency, tt.knockout, tt.koBounty,
                        t.siteTourneyNo
                        FROM Tourneys t JOIN TourneyTypes tt ON tt.id = t.tourneyTypeId
                        WHERE t.id = %s""",
    "selectHandTourneyId": "SELECT tourneyId FROM Hands WHERE id = %s",
}


def tourney_payout_queries(db_server: str) -> dict[str, str]:
    """The TourneyPayouts DDL for ``db_server``, and the queries that read and write it."""
    queries = dict(_QUERIES)
    ddl = _DDL.get(db_server)
    if ddl is not None:
        queries["createTourneyPayoutsTable"] = ddl
    return queries
