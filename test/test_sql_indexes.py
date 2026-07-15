"""Regression tests for the SQL index catalogue."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_indexes import index_queries


def test_index_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = index_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()
        assert len(expected) == 30


def test_index_queries_keep_backend_specific_syntax() -> None:
    mysql = index_queries("mysql")
    postgresql = index_queries("postgresql")
    sqlite = index_queries("sqlite")

    assert mysql["addTourneyIndex"].startswith("ALTER TABLE")
    assert postgresql["addTourneyIndex"].startswith("CREATE UNIQUE INDEX")
    assert sqlite["addFilesIndex"].endswith("(file)")
    assert mysql["addFilesIndex"].endswith("(file(255))")
    for queries in (mysql, postgresql, sqlite):
        assert "position" in queries["addHudCacheCompundIndex"]
        assert "startCards" in queries["addCardsCacheCompundIndex"]
        assert "bombPot" in queries["addBombPotIndex"]
