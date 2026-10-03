"""Session profit timeline queries."""

from __future__ import annotations


def session_stats_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific session timeline query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["sessionStats"] = """
            SELECT h.id, UNIX_TIMESTAMP(h.startTime) as time, hp.totalProfit,
                   hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
             INNER JOIN Sites s       on  (s.Id = gt.siteId)
             INNER JOIN Players p     on  (p.Id = hp.playerId)
            WHERE hp.playerId in <player_test>
             AND  date_format(h.startTime, '%Y-%m-%d') <datestest>
             AND  gt.type LIKE 'ring'
             <limit_test>
             <game_test>
             <seats_test>
             <currency_test>
            ORDER by time, h.id"""
    elif db_server == "postgresql":
        query["sessionStats"] = """
            SELECT h.id, EXTRACT(epoch from h.startTime) as time, hp.totalProfit,
                   hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
             INNER JOIN Sites s       on  (s.Id = gt.siteId)
             INNER JOIN Players p     on  (p.Id = hp.playerId)
            WHERE hp.playerId in <player_test>
             AND  h.startTime <datestest>
             AND  gt.type LIKE 'ring'
             <limit_test>
             <game_test>
             <seats_test>
             <currency_test>
            ORDER by time, h.id"""
    elif db_server == "sqlite":
        query["sessionStats"] = """
            SELECT h.id, STRFTIME('<ampersand_s>', h.startTime) as time, hp.totalProfit,
                   hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
             INNER JOIN Sites s       on  (s.Id = gt.siteId)
             INNER JOIN Players p     on  (p.Id = hp.playerId)
            WHERE hp.playerId in <player_test>
             AND  h.startTime <datestest>
             AND  gt.type is 'ring'
             <limit_test>
             <game_test>
             <seats_test>
             <currency_test>
            ORDER by time, h.id"""

    # The Session Guard's view of the same rows (#395): one hero id and a start-time
    # cut-off, as parameters, for finding the session being played.
    if db_server == "mysql":
        # Hand times are stored in UTC; UNIX_TIMESTAMP would read them in the connection's
        # time zone, which fpdb does not set, and the guard compares them with the clock.
        query["sessionGuardHands"] = """
            SELECT h.id, TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', h.startTime) as time,
                   hp.totalProfit, hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
            WHERE hp.playerId = %s
             AND  h.startTime >= %s
             AND  gt.type LIKE 'ring'
            ORDER by time, h.id"""
    elif db_server == "postgresql":
        query["sessionGuardHands"] = """
            SELECT h.id, EXTRACT(epoch from h.startTime) as time, hp.totalProfit,
                   hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
            WHERE hp.playerId = %s
             AND  h.startTime >= %s
             AND  gt.type LIKE 'ring'
            ORDER by time, h.id"""
    elif db_server == "sqlite":
        # Epoch seconds through julianday rather than STRFTIME('%s'): the catalogue turns
        # every %s into a bind marker for SQLite, and this text has no template to fill.
        query["sessionGuardHands"] = """
            SELECT h.id, CAST(ROUND((julianday(h.startTime) - 2440587.5) * 86400) AS INTEGER) as time,
                   hp.totalProfit, hp.allInEV, gt.bigBlind, gt.currency
            FROM HandsPlayers hp
             INNER JOIN Hands h       on  (h.id = hp.handId)
             INNER JOIN Gametypes gt  on  (gt.Id = h.gametypeId)
            WHERE hp.playerId = %s
             AND  h.startTime >= %s
             AND  gt.type is 'ring'
            ORDER by time, h.id"""

    return query
