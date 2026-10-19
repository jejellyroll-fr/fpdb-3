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
