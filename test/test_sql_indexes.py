"""Regression tests for the SQL index catalogue."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_indexes import index_queries


def test_index_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = index_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()
        assert len(expected) == 52  # 39 core + 13 analytics (#304)


def test_index_queries_keep_backend_specific_syntax() -> None:
    mysql = index_queries("mysql")
    postgresql = index_queries("postgresql")
    sqlite = index_queries("sqlite")

    assert mysql["addTourneyIndex"].startswith("ALTER TABLE")
    assert postgresql["addTourneyIndex"].startswith("CREATE UNIQUE INDEX")
    assert sqlite["addFilesIndex"].endswith("(file)")
    assert mysql["addFilesIndex"].endswith("(file(255))")
    assert "(category, `rank`)" in mysql["addStartCardsIndex"]
    assert mysql["addAofDecisionsPlayerIndex"].startswith("ALTER TABLE")
    assert postgresql["addAofAnalysesDecisionIndex"].startswith("CREATE INDEX")
    assert "(category, role, activeOpponents, handId, cardsObservable)" in mysql["addAofDecisionsRangeIndex"]
    assert "(category, role, activeOpponents, handId, cardsObservable)" in postgresql["addAofDecisionsRangeIndex"]
    for queries in (mysql, postgresql, sqlite):
        assert "boardfeatures_hand_idx" in queries["addBoardFeaturesHandIndex"]
        assert "boardfeatures_texture_idx" in queries["addBoardFeaturesTextureIndex"]
    for queries in (mysql, postgresql, sqlite):
        assert "position" in queries["addHudCacheCompundIndex"]
        assert "startCards" in queries["addCardsCacheCompundIndex"]
        assert "bombPot" in queries["addBombPotIndex"]
        assert "splashPot" in queries["addSplashPotIndex"]


def test_analytics_indexes_cover_the_query_shapes() -> None:
    """Every analytics index is present, backend-appropriate and composite where
    the query shape needs it (#304)."""
    from fpdb_3_legacy.sql_indexes import ANALYTICS_INDEX_NAMES

    assert len(ANALYTICS_INDEX_NAMES) == 13
    mysql = index_queries("mysql")
    postgresql = index_queries("postgresql")
    sqlite = index_queries("sqlite")
    for name in ANALYTICS_INDEX_NAMES:
        assert mysql[name].startswith("ALTER TABLE")
        assert postgresql[name].startswith(f"CREATE INDEX IF NOT EXISTS {name} ON")
        assert sqlite[name].startswith(f"CREATE INDEX IF NOT EXISTS {name} ON")
    # The joins and the watermark scan are the ones that must be composite.
    assert "(handId, actionNo)" in postgresql["handactions_hand_idx"]
    assert "(handId, actionNo)" in postgresql["handssituations_hand_idx"]
    assert "(handId, playerId)" in postgresql["handsplayers_hand_player_idx"]
    assert "(gametypeId, startTime)" in postgresql["hands_gametype_time_idx"]
