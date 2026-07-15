"""Architectural guards for the legacy SQL catalogue facade."""

from __future__ import annotations

from pathlib import Path

SQL_SOURCE = Path(__file__).parents[1] / "fpdb_3_legacy" / "SQL.py"


def test_sql_facade_contains_no_inline_create_table_ddl() -> None:
    source = SQL_SOURCE.read_text(encoding="utf-8")
    assert "CREATE TABLE" not in source


def test_sql_facade_installs_schema_catalogues_before_queries() -> None:
    source = SQL_SOURCE.read_text(encoding="utf-8")
    schema_updates = [
        line for line in source.splitlines() if "self.query.update(" in line
    ]

    assert len(schema_updates) >= 10
    assert "metadata_queries" in schema_updates[0]
    assert all("schema" in line for line in schema_updates[1:])
