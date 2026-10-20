"""HUD cache rebuild query template.

The rebuild aggregates HandsPlayers into a statistics cache with one
``INSERT ... SELECT``. Its stat column lists are generated from the keys the
import writes, by :mod:`fpdb_3_legacy.cache_rebuild` (#591); this module only
holds the SQL around them.
"""

from __future__ import annotations

# One template for every backend: the backends only differ in how a boolean
# column is summed, which cache_rebuild.rebuild_stat_columns handles.
REBUILD_TEMPLATE = """insert into <insert>
<stat_insert_columns>
            )
            SELECT <select>
<stat_select_columns>
            FROM Hands h
            INNER JOIN HandsPlayers hp ON (h.id = hp.handId<hero_join>)
            INNER JOIN Gametypes g ON (h.gametypeId = g.id)
            <sessions_join_clause>
            <tourney_join_clause>
            <where_clause>
            GROUP BY <group>
"""


def cache_rebuild_queries(db_server: str) -> dict[str, str]:
    """Return the cache rebuild template; its stat columns are filled per table."""
    if db_server not in ("mysql", "postgresql", "sqlite"):
        return {}
    return {"rebuildCache": REBUILD_TEMPLATE}


# Session rebuild (#598): the session tables are emptied, then the import's own
# session grouping is replayed over the stored hands in time order.
SESSION_REBUILD_CLEAR = (
    "DELETE FROM SessionsCache",
    "DELETE FROM TourneysCache",
    "UPDATE Hands SET sessionId = NULL",
    "UPDATE Tourneys SET sessionId = NULL",
    "DELETE FROM Sessions",
)

SESSION_REBUILD_HANDS = """SELECT h.id, h.startTime, h.tourneyId, h.gametypeId, g.type
            FROM Hands h
            INNER JOIN Gametypes g ON (h.gametypeId = g.id)
            ORDER BY h.startTime, h.id"""

SESSION_REBUILD_PLAYERS = """SELECT hp.handId, hp.playerId, hp.sawShowdown, hp.totalProfit<columns>
            FROM HandsPlayers hp
            WHERE hp.handId IN (<hand_ids>)
            ORDER BY hp.handId, hp.seatNo"""

SESSION_REBUILD_HAND_SESSION = "UPDATE Hands SET sessionId = %s WHERE id = %s"

# Weeks and months no session and no period cache points at any more.
SESSION_REBUILD_ORPHAN_PERIODS = (
    """DELETE FROM Weeks WHERE NOT EXISTS (SELECT 1 FROM Sessions s WHERE s.weekId = Weeks.id)
            AND NOT EXISTS (SELECT 1 FROM CardsCache c WHERE c.weekId = Weeks.id)
            AND NOT EXISTS (SELECT 1 FROM PositionsCache p WHERE p.weekId = Weeks.id)""",
    """DELETE FROM Months WHERE NOT EXISTS (SELECT 1 FROM Sessions s WHERE s.monthId = Months.id)
            AND NOT EXISTS (SELECT 1 FROM CardsCache c WHERE c.monthId = Months.id)
            AND NOT EXISTS (SELECT 1 FROM PositionsCache p WHERE p.monthId = Months.id)""",
)
