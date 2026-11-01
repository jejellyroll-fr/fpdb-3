"""Regression tests for the extracted metadata SQL catalogue."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_metadata import metadata_queries


def test_metadata_queries_are_installed_unchanged_for_each_backend() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = metadata_queries(backend)
        actual = Sql(db_server=backend).query
        for key, value in expected.items():
            if key == "getTourneyTypes":
                continue  # Replaced later by the detailed tournament-type query.
            if backend == "sqlite":
                value = value.replace("%s", "?")
            assert actual[key] == value


def test_known_late_metadata_override_is_preserved() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        assert Sql(db_server=backend).query["getTourneyTypes"] == "SELECT * FROM TourneyTypes"


def test_metadata_catalogue_has_backend_specific_introspection() -> None:
    assert metadata_queries("mysql")["list_tables"] == "SHOW TABLES"
    assert "information_schema.tables" in metadata_queries("postgresql")["list_tables"]
    assert "sqlite_master" in metadata_queries("sqlite")["list_indexes"]
