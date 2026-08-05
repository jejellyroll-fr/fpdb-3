"""HUD cache maintenance queries."""

from __future__ import annotations


def cache_maintenance_queries() -> dict[str, str]:
    """Return cache clearing and missing-context discovery queries."""
    query: dict[str, str] = {}
    query["clearHudCache"] = """DELETE FROM HudCache"""
    query["clearCardsCache"] = """DELETE FROM CardsCache"""
    query["clearPositionsCache"] = """DELETE FROM PositionsCache"""

    query["clearHudCacheTourneyType"] = """DELETE FROM HudCache WHERE tourneyTypeId = %s"""
    query["clearCardsCacheTourneyType"] = """DELETE FROM CardsCache WHERE tourneyTypeId = %s"""
    query["clearPositionsCacheTourneyType"] = """DELETE FROM PositionsCache WHERE tourneyTypeId = %s"""

    query["fetchNewHudCacheTourneyTypeIds"] = """SELECT TT.id
                                                FROM TourneyTypes TT
                                                LEFT OUTER JOIN HudCache HC ON (TT.id = HC.tourneyTypeId)
                                                WHERE HC.tourneyTypeId is NULL
            """

    query["fetchNewCardsCacheTourneyTypeIds"] = """SELECT TT.id
                                                FROM TourneyTypes TT
                                                LEFT OUTER JOIN CardsCache CC ON (TT.id = CC.tourneyTypeId)
                                                WHERE CC.tourneyTypeId is NULL
            """

    query["fetchNewPositionsCacheTourneyTypeIds"] = """SELECT TT.id
                                                FROM TourneyTypes TT
                                                LEFT OUTER JOIN PositionsCache PC ON (TT.id = PC.tourneyTypeId)
                                                WHERE PC.tourneyTypeId is NULL
            """

    query["clearCardsCacheWeeksMonths"] = """DELETE FROM CardsCache WHERE weekId = %s AND monthId = %s"""
    query["clearPositionsCacheWeeksMonths"] = (
        """DELETE FROM PositionsCache WHERE weekId = %s AND monthId = %s"""
    )

    query["selectSessionWithWeekId"] = """SELECT id FROM Sessions WHERE weekId = %s"""
    query["selectSessionWithMonthId"] = """SELECT id FROM Sessions WHERE monthId = %s"""

    query["deleteWeekId"] = """DELETE FROM Weeks WHERE id = %s"""
    query["deleteMonthId"] = """DELETE FROM Months WHERE id = %s"""

    query["fetchNewCardsCacheWeeksMonths"] = """SELECT SCG.weekId, SCG.monthId
                                        FROM (SELECT DISTINCT weekId, monthId FROM Sessions) SCG
                                        LEFT OUTER JOIN CardsCache CC ON (SCG.weekId = CC.weekId AND SCG.monthId = CC.monthId)
                                        WHERE CC.weekId is NULL OR CC.monthId is NULL
    """

    query["fetchNewPositionsCacheWeeksMonths"] = """SELECT SCG.weekId, SCG.monthId
                                        FROM (SELECT DISTINCT weekId, monthId FROM Sessions) SCG
                                        LEFT OUTER JOIN PositionsCache PC ON (SCG.weekId = PC.weekId AND SCG.monthId = PC.monthId)
                                        WHERE PC.weekId is NULL OR PC.monthId is NULL
    """

    return query

