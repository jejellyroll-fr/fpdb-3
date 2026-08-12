"""Core hand and player lookup queries."""

from __future__ import annotations


def core_lookup_queries() -> dict[str, str]:
    """Return backend-neutral core lookup queries."""
    query: dict[str, str] = {}
    query["get_last_hand"] = "select max(id) from Hands"

    query["get_last_date"] = "SELECT MAX(startTime) FROM Hands"

    query["get_first_date"] = "SELECT MIN(startTime) FROM Hands"

    query["get_player_id"] = """
            select Players.id AS player_id
            from Players, Sites
            where Players.name = %s
            and Sites.name = %s
            and Players.siteId = Sites.id
        """

    query["get_player_id_by_name"] = "SELECT id FROM Players WHERE name = %s"

    query["get_site_hand_no"] = "SELECT siteHandNo FROM Hands WHERE id = %s"

    query["get_player_names"] = """
            select p.name
            from Players p
            where lower(p.name) like lower(%s)
            and   (p.siteId = %s or %s = -1)
        """

    query["get_gameinfo_from_hid"] = """
            SELECT
                    s.name,
                    g.category,
                    g.base,
                    g.type,
                    g.limitType,
                    g.hilo,
                    round(g.smallBlind / 100.0,2),
                    round(g.bigBlind / 100.0,2),
                    round(g.smallBet / 100.0,2),
                    round(g.bigBet / 100.0,2),
                    g.currency,
                    h.gametypeId,
                    g.split
                FROM
                    Hands as h,
                    Sites as s,
                    Gametypes as g,
                    HandsPlayers as hp,
                    Players as p
                WHERE
                    h.id = %s
                and g.id = h.gametypeId
                and hp.handId = h.id
                and p.id = hp.playerId
                and s.id = p.siteId
                limit 1
        """

    # A Fast-Fold HUD is built from the client log, before any hand of that
    # table has been imported, so it has no hand to take a gametypeId from --
    # and without one the statistics query is skipped and every block shows
    # empty. The pool has been played before, though, so its own last hand
    # answers what game it deals.
    # Keyed on the site's name rather than its id: the id is learned from an
    # imported hand, and this exists precisely for the case where no hand has
    # been imported yet.
    query["get_last_gametype_for_table"] = """
            SELECT h.gametypeId
                FROM Hands h
                JOIN Gametypes g ON g.id = h.gametypeId
                JOIN Sites s ON s.id = g.siteId
                WHERE s.name = %s
                  AND h.tableName = %s
                ORDER BY h.id DESC
                LIMIT 1
        """

    return query
