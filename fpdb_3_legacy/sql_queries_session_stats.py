"""Session profit timeline queries."""

from __future__ import annotations


def session_stats_queries(db_server: str) -> dict[str, str]:
    """Return the backend-specific session timeline query."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["sessionStats"] = """
            SELECT UNIX_TIMESTAMP(h.startTime) as time, hp.totalProfit
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
            ORDER by time"""
    elif db_server == "postgresql":
        query["sessionStats"] = """
            SELECT EXTRACT(epoch from h.startTime) as time, hp.totalProfit
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
            ORDER by time"""
    elif db_server == "sqlite":
        query["sessionStats"] = """
            SELECT STRFTIME('<ampersand_s>', h.startTime) as time, hp.totalProfit
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
            ORDER by time"""

    return query

