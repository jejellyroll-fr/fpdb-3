"""Cash-game profit graph queries."""

from __future__ import annotations


def cash_profit_queries() -> dict[str, str]:
    """Return cash profit curves in native units, big blinds, and dollars."""
    query: dict[str, str] = {}
    query["getRingProfitAllHandsPlayerIdSite"] = """
        SELECT hp.handId, hp.totalProfit, hp.sawShowdown
        FROM HandsPlayers hp
        INNER JOIN Players pl      ON  (pl.id = hp.playerId)
        INNER JOIN Hands h         ON  (h.id  = hp.handId)
        INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
        WHERE pl.id in <player_test>
        AND   tt.siteId in <site_test>
        AND   h.startTime > '<startdate_test>'
        AND   h.startTime < '<enddate_test>'
        <limit_test>
        <game_test>
        AND   gt.type = 'ring'
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit
        ORDER BY h.startTime"""

    query["getRingProfitAllHandsPlayerIdSiteInBB"] = """
        SELECT hp.handId, ( hp.totalProfit / ( gt.bigBlind  * 2.0 ) ) * 100 , hp.sawShowdown, ( hp.allInEV / ( gt.bigBlind * 2.0 ) ) * 100
        FROM HandsPlayers hp
        INNER JOIN Players pl      ON  (pl.id = hp.playerId)
        INNER JOIN Hands h         ON  (h.id  = hp.handId)
        INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND   h.startTime > '<startdate_test>'
        AND   h.startTime < '<enddate_test>'
        <limit_test>
        <game_test>
        <currency_test>
        AND   hp.tourneysPlayersId IS NULL
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV, gt.bigBlind
        ORDER BY h.startTime"""

    query["getRingProfitAllHandsPlayerIdSiteInDollars"] = """
        SELECT hp.handId, hp.totalProfit, hp.sawShowdown, hp.allInEV
        FROM HandsPlayers hp
        INNER JOIN Players pl      ON  (pl.id = hp.playerId)
        INNER JOIN Hands h         ON  (h.id  = hp.handId)
        INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND   h.startTime > '<startdate_test>'
        AND   h.startTime < '<enddate_test>'
        <limit_test>
        <game_test>
        <currency_test>
        AND   hp.tourneysPlayersId IS NULL
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV
        ORDER BY h.startTime"""

    return query

