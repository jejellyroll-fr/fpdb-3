"""Backend-specific queries used by report filters."""

from __future__ import annotations


def filter_queries(db_server: str) -> dict[str, str]:
    """Return category, position, currency, and limit filter queries."""
    query: dict[str, str] = {}
    # Used in *Filters:
    if db_server == "mysql":
        query["getCategoryBySiteAndPlayer"] = """
        SELECT DISTINCT tt.category
        FROM TourneyTypes tt
        JOIN Tourneys t ON tt.id = t.tourneyTypeId
        JOIN TourneysPlayers tp ON t.id = tp.tourneyId
        JOIN Players p ON tp.playerId = p.id
        WHERE tt.siteId = ? AND p.name = ?
        """

    elif db_server == "postgresql":
        query["getCategoryBySiteAndPlayer"] = """
        SELECT DISTINCT tt.category
        FROM TourneyTypes tt
        JOIN Tourneys t ON tt.id = t.tourneyTypeId
        JOIN TourneysPlayers tp ON t.id = tp.tourneyId
        JOIN Players p ON tp.playerId = p.id
        WHERE tt.siteId = %s AND p.name = %s
        """

    elif db_server == "sqlite":
        query["getCategoryBySiteAndPlayer"] = """
        SELECT DISTINCT tt.category
        FROM TourneyTypes tt
        JOIN Tourneys t ON tt.id = t.tourneyTypeId
        JOIN TourneysPlayers tp ON t.id = tp.tourneyId
        JOIN Players p ON tp.playerId = p.id
        WHERE tt.siteId = ? AND p.name = ?
        """

    if db_server == "mysql":
        query["getCategoryBySiteAndPlayerRing"] = """
        SELECT DISTINCT gt.category
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = ? AND p.name = ? AND gt.type = 'ring'
        """

    elif db_server == "postgresql":
        query["getCategoryBySiteAndPlayerRing"] = """
        SELECT DISTINCT gt.category
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = %s AND p.name = %s AND gt.type = 'ring'
        """

    elif db_server == "sqlite":
        query["getCategoryBySiteAndPlayerRing"] = """
        SELECT DISTINCT gt.category
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = ? AND p.name = ? AND gt.type = 'ring'
        """

    if db_server == "mysql":
        query["getPositionByPlayerAndHandid"] = """
        SELECT DISTINCT hp.position
        FROM HandsPlayers hp
        JOIN Hands h ON hp.handId = h.id
        JOIN Players p ON hp.playerId = p.id
        WHERE p.name = ? AND h.siteHandNo LIKE ?
        """

    elif db_server == "postgresql":
        query["getPositionByPlayerAndHandid"] = """
        SELECT DISTINCT hp.position
        FROM HandsPlayers hp
        JOIN Hands h ON hp.handId = h.id
        JOIN Players p ON hp.playerId = p.id
        WHERE p.name = %s AND CAST(h.siteHandNo AS text) LIKE %s
        """

    elif db_server == "sqlite":
        query["getPositionByPlayerAndHandid"] = """
        SELECT DISTINCT hp.position
        FROM HandsPlayers hp
        JOIN Hands h ON hp.handId = h.id
        JOIN Players p ON hp.playerId = p.id
        WHERE p.name = ? AND h.siteHandNo LIKE ?
        """

    if db_server == "mysql":
        query["getCurrencyBySiteAndPlayer"] = """
        SELECT DISTINCT gt.currency
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = ? AND p.name = ?
        """

    elif db_server == "postgresql":
        query["getCurrencyBySiteAndPlayer"] = """
        SELECT DISTINCT gt.currency
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = %s AND p.name = %s
        """

    elif db_server == "sqlite":
        query["getCurrencyBySiteAndPlayer"] = """
        SELECT DISTINCT gt.currency
        FROM GameTypes gt
        JOIN Hands h ON gt.id = h.gametypeId
        JOIN HandsPlayers hp ON h.id = hp.handId
        JOIN Players p ON hp.playerId = p.id
        WHERE gt.siteId = ? AND p.name = ?
        """

    # query['getLimits'] = already defined further up
    query["getLimits2"] = """SELECT DISTINCT type, limitType, bigBlind
                                  from Gametypes
                                  ORDER by type, limitType DESC, bigBlind DESC"""
    query["getLimits3"] = """select DISTINCT type
                                       , gt.limitType
                                       , case type
                                             when 'ring' then bigBlind
-                                                else buyin
-                                            end as bb_or_buyin
                                  from Gametypes gt
                                  cross join TourneyTypes tt
                                  order by type, gt.limitType DESC, bb_or_buyin DESC"""
    #         query['getCashLimits'] = """select DISTINCT type
    #                                            , limitType
    #                                            , bigBlind as bb_or_buyin
    #                                       from Gametypes gt
    #                                       WHERE type = 'ring'
    #                                       order by type, limitType DESC, bb_or_buyin DESC"""

    query["getCashLimits"] = """select DISTINCT type
                                       , limitType
                                       , bigBlind as bb_or_buyin
                                  from Gametypes gt
                                  WHERE type = 'ring'
                                  order by type, limitType DESC, bb_or_buyin DESC"""

    query["getPositions"] = """select distinct position
                                  from HandsPlayers gt
                                  order by position"""

    return query

