"""Tournament result and graph queries."""

from __future__ import annotations


def tournament_graph_queries() -> dict[str, str]:
    """Return tournament result, profit graph, and ChipEV queries."""
    query: dict[str, str] = {}
    ####################################
    # Tourney Results query
    ####################################
    query["tourneyResults"] = """
        SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
        FROM TourneysPlayers tp
        INNER JOIN Players pl      ON  (pl.id = tp.playerId)
        INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
        INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
                OR t.startTime is NULL)
        GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                 tp.winnings, tp.koCount,
                 tp.rebuyCount, tp.addOnCount,
                 tt.buyIn, tt.fee, t.siteTourneyNo
        ORDER BY t.startTime"""

    # AND   gt.type = 'ring'
    # <limit_test>
    # <game_test>

    ####################################
    # Tourney Graph query
    # FIXME this is a horrible hack to prevent nonsense data
    #  being graphed - needs proper fix mantis #180 +#182
    ####################################
    query["tourneyGraph"] = """
        SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
        FROM TourneysPlayers tp
        INNER JOIN Players pl      ON  (pl.id = tp.playerId)
        INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
        INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND   (t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
             <currency_test>
        GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                 tp.winnings, tp.koCount,
                 tp.rebuyCount, tp.addOnCount,
                 tt.buyIn, tt.fee, t.siteTourneyNo
        ORDER BY t.startTime"""

    # AND   gt.type = 'ring'
    # <limit_test>
    # <game_test>
    ####################################
    # Tourney Graph query with tourneytypefilter
    # FIXME this is a horrible hack to prevent nonsense data
    #  being graphed - needs proper fix mantis #180 +#182
    ####################################
    query["tourneyGraphType"] = """
        SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
        FROM TourneysPlayers tp
        INNER JOIN Players pl      ON  (pl.id = tp.playerId)
        INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
        INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND tt.category in <tourney_cat>
        AND tt.limitType in <tourney_lim>
        AND tt.buyin in <tourney_buyin>
        AND   (t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
             <currency_test>
        GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                 tp.winnings, tp.koCount,
                 tp.rebuyCount, tp.addOnCount,
                 tt.buyIn, tt.fee, t.siteTourneyNo
        ORDER BY t.startTime"""

    # AND   gt.type = 'ring'
    # <limit_test>
    # <game_test>

    ####################################
    # ChipEV-by-position curves (declarative stats, see stat_registry.py)
    #
    # Per-hand tournament rows ordered by time. <chipev_columns> is filled
    # at runtime by GraphAdapter.select_clause() with one dimension-gated
    # CASE expression per ChipEV-by-position curve, so the cumulative
    # series can be computed in Python. Reuses the same filter placeholders
    # as tourneyGraphType.
    ####################################
    query["tourneyChipEVByPosition"] = """
        SELECT h.startTime AS startTime <chipev_columns>
        FROM HandsPlayers hp
        INNER JOIN Hands h          ON  (h.id = hp.handId)
        INNER JOIN Players pl       ON  (pl.id = hp.playerId)
        INNER JOIN Tourneys t       ON  (t.id = h.tourneyId)
        INNER JOIN TourneyTypes tt  ON  (tt.id = t.tourneyTypeId)
        WHERE pl.id in <player_test>
        AND   pl.siteId in <site_test>
        AND tt.category in <tourney_cat>
        AND tt.limitType in <tourney_lim>
        AND tt.buyin in <tourney_buyin>
        AND   (h.startTime > '<startdate_test>' AND h.startTime < '<enddate_test>')
             <currency_test>
        ORDER BY h.startTime"""

    ####################################
    # ChipEV-by-position aggregated per (tourneyType, player) for the
    # tournament player-stats grid. <chipev_columns> is filled at runtime by
    # GridAdapter.select_clause(). Reuses the refineQuery placeholders
    # (<nametest>, <sitetest>, dates) of tourneyPlayerDetailedStats.
    ####################################
    query["tourneyChipEVByPositionGrid"] = """
        SELECT t.tourneyTypeId AS tourneyTypeId
              ,hp.playerId     AS playerId
              <chipev_columns>
        FROM HandsPlayers hp
        INNER JOIN Hands h          ON  (h.id = hp.handId)
        INNER JOIN Tourneys t       ON  (t.id = h.tourneyId)
        INNER JOIN TourneyTypes tt  ON  (tt.id = t.tourneyTypeId)
        INNER JOIN Players p        ON  (p.id = hp.playerId)
        WHERE hp.playerId in <nametest> <sitetest>
        AND   ((h.startTime > '<startdate_test>' AND h.startTime < '<enddate_test>')
                    OR h.startTime is NULL)
        GROUP BY t.tourneyTypeId, hp.playerId"""

    ####################################
    # Session stats query
    ####################################
    return query

