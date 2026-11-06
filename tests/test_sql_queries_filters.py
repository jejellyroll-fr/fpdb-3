"""Regression tests for report filter queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_filters import filter_queries


def test_filter_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = filter_queries(backend)
        assert len(expected) == 8
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_filter_queries_keep_room_and_player_constraints() -> None:
    mysql = filter_queries("mysql")
    postgresql = filter_queries("postgresql")
    sqlite = filter_queries("sqlite")

    assert mysql["getCategoryBySiteAndPlayer"].count("?") == 2
    assert postgresql["getCategoryBySiteAndPlayer"].count("%s") == 2
    assert sqlite["getCategoryBySiteAndPlayer"].count("?") == 2
    for queries in (mysql, postgresql, sqlite):
        assert "gt.type = 'ring'" in queries["getCategoryBySiteAndPlayerRing"]
        assert "hp.position" in queries["getPositionByPlayerAndHandid"]
        assert "gt.currency" in queries["getCurrencyBySiteAndPlayer"]
        assert "ORDER by type, limitType" in queries["getLimits2"]
