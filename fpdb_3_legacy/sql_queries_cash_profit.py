"""Cash-game profit graph queries."""

from __future__ import annotations


def cash_profit_queries() -> dict[str, str]:
    """Return cash profit curves in native units, big blinds, and dollars."""
    query: dict[str, str] = {}
    query["getRingProfitAllHandsPlayerIdSite"] = """
        SELECT hp.handId, hp.totalProfit, hp.sawShowdown, COALESCE(hp.splashWinnings, 0)
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
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.splashWinnings
        ORDER BY h.startTime, hp.handId"""

    # A hand without an all-in EV (older imports, other trackers) plots its
    # result as its EV, which is what fpdb stores for a hand with no all-in;
    # hands that started in the same second keep their hand-id order (#827).
    # GraphViewer divides every result series by 100 before plotting. Return
    # hundredths of a big blind here; totalProfit, allInEV and bigBlind already
    # use the same currency units, so the BB conversion is amount / bigBlind.
    query["getRingProfitAllHandsPlayerIdSiteInBB"] = """
        SELECT hp.handId,
               ( hp.totalProfit / ( gt.bigBlind + 0.0 ) ) * 100,
               hp.sawShowdown,
               ( COALESCE(hp.allInEV, hp.totalProfit) / ( gt.bigBlind + 0.0 ) ) * 100,
               ( COALESCE(hp.splashWinnings, 0) / ( gt.bigBlind + 0.0 ) ) * 100
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
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV, hp.splashWinnings, gt.bigBlind
        ORDER BY h.startTime, hp.handId"""

    query["getRingProfitAllHandsPlayerIdSiteInDollars"] = """
        SELECT hp.handId, hp.totalProfit, hp.sawShowdown, COALESCE(hp.allInEV, hp.totalProfit),
               COALESCE(hp.splashWinnings, 0)
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
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV, hp.splashWinnings
        ORDER BY h.startTime, hp.handId"""

    # The Results calendar (#827): every cash hand of the hero with what it
    # needs to be filed under its day and summed there. The start time is
    # returned as stored (UTC); period_results moves it to the local day.
    query["periodResultsHands"] = """
        SELECT h.id, h.startTime, hp.totalProfit, COALESCE(hp.allInEV, hp.totalProfit),
               hp.sawShowdown, gt.bigBlind, gt.currency, hp.playerId
        FROM HandsPlayers hp
        INNER JOIN Hands h         ON  (h.id  = hp.handId)
        INNER JOIN Gametypes gt    ON  (gt.id = h.gametypeId)
        WHERE hp.playerId in <player_test>
        AND   h.startTime >= '<startdate_test>'
        AND   h.startTime <= '<enddate_test>'
        AND   gt.type = 'ring'
        AND   hp.tourneysPlayersId IS NULL
        <limit_test>
        <game_test>
        <currency_test>
        <seats_test>
        ORDER BY h.startTime, h.id"""

    return query
