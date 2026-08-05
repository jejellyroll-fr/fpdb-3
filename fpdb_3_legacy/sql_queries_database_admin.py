"""Backend-specific database administration queries."""

from __future__ import annotations


def database_admin_queries(db_server: str) -> dict[str, str]:
    """Return analyze, vacuum, and import-lock queries for a backend."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["analyze"] = """
        analyze table Actions, Autorates, Backings, Boards, Files, Gametypes, Hands, HandsActions, HandsPlayers,
                      HandsStove, HudCache, Players, RawHands, RawTourneys, Sessions, Settings, Sites,
                      Tourneys, TourneysPlayers, TourneyTypes
        """
    elif db_server in ("postgresql", "sqlite"):
        query["analyze"] = "analyze"

    if db_server == "mysql":
        query["vacuum"] = """
        optimize table Actions, Autorates, Backings, Boards, Files, Gametypes, Hands, HandsActions, HandsPlayers,
                       HandsStove, HudCache, Players, RawHands, RawTourneys, Sessions, Settings, Sites,
                       Tourneys, TourneysPlayers, TourneyTypes
        """
    elif db_server in ("postgresql", "sqlite"):
        query["vacuum"] = """ vacuum """

    if db_server == "mysql":
        query["switchLockOn"] = """
                    UPDATE InsertLock k1,
                    (SELECT count(locked) as locks FROM InsertLock WHERE locked=True) as k2 SET
                    k1.locked=%s
                    WHERE k1.id=%s
                    AND k2.locks = 0"""

    if db_server == "mysql":
        query["switchLockOff"] = """
                    UPDATE InsertLock SET
                    locked=%s
                    WHERE id=%s"""

    if db_server == "mysql":
        query["lockForInsert"] = """
            lock tables Hands write, HandsPlayers write, HandsActions write, Players write
                      , HudCache write, Gametypes write, Sites write, Tourneys write
                      , TourneysPlayers write, TourneyTypes write, Autorates write
            """
    elif db_server in ("postgresql", "sqlite"):
        query["lockForInsert"] = ""
    return query

