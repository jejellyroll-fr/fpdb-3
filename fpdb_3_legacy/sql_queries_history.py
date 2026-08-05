"""Backend-specific hand-history window queries."""

from __future__ import annotations


def history_window_queries(db_server: str) -> dict[str, str]:
    """Return queries for one-day and N-hand history boundaries."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["get_hand_1day_ago"] = """
            select coalesce(max(id),0)
            from Hands
            where startTime < date_sub(utc_timestamp(), interval '1' day)"""
    elif db_server == "postgresql":
        query["get_hand_1day_ago"] = """
            select coalesce(max(id),0)
            from Hands
            where startTime < now() at time zone 'UTC' - interval '1 day'"""
    elif db_server == "sqlite":
        query["get_hand_1day_ago"] = """
            select coalesce(max(id),0)
            from Hands
            where startTime < datetime(strftime('%J', 'now') - 1)"""

    # not used yet ...
    # gets a date, would need to use handsplayers (not hudcache) to get exact hand Id
    if db_server == "mysql":
        query["get_date_nhands_ago"] = """
            select concat( 'd', date_format(max(h.startTime), '%Y%m%d') )
            from (select hp.playerId
                        ,coalesce(greatest(max(hp.handId)-%s,1),1) as maxminusx
                  from HandsPlayers hp
                  where hp.playerId = %s
                  group by hp.playerId) hp2
            inner join HandsPlayers hp3 on (    hp3.handId <= hp2.maxminusx
                                            and hp3.playerId = hp2.playerId)
            inner join Hands h          on (h.id = hp3.handId)
            """
    elif db_server == "postgresql":
        query["get_date_nhands_ago"] = """
            select 'd' || to_char(max(h3.startTime), 'YYMMDD')
            from (select hp.playerId
                        ,coalesce(greatest(max(hp.handId)-%s,1),1) as maxminusx
                  from HandsPlayers hp
                  where hp.playerId = %s
                  group by hp.playerId) hp2
            inner join HandsPlayers hp3 on (    hp3.handId <= hp2.maxminusx
                                            and hp3.playerId = hp2.playerId)
            inner join Hands h          on (h.id = hp3.handId)
            """
    elif db_server == "sqlite":  # untested guess at query:
        query["get_date_nhands_ago"] = """
            select 'd' || strftime(max(h3.startTime), 'YYMMDD')
            from (select hp.playerId
                        ,coalesce(greatest(max(hp.handId)-%s,1),1) as maxminusx
                  from HandsPlayers hp
                  where hp.playerId = %s
                  group by hp.playerId) hp2
            inner join HandsPlayers hp3 on (    hp3.handId <= hp2.maxminusx
                                            and hp3.playerId = hp2.playerId)
            inner join Hands h          on (h.id = hp3.handId)
            """

    return query

