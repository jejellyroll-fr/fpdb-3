"""Regression tests for final SQL placeholder normalization."""

from fpdb_3_legacy.sql_query_placeholders import finalize_query_placeholders


def test_finalize_query_placeholders_keeps_percent_markers_for_server_backends() -> None:
    for backend in ("mysql", "postgresql"):
        queries = {"lookup": "SELECT * FROM Players WHERE id=%s"}
        result = finalize_query_placeholders(queries, backend)

        assert result is queries
        assert result == {"lookup": "SELECT * FROM Players WHERE id=%s", "placeholder": "%s"}


def test_finalize_query_placeholders_rewrites_all_sqlite_queries() -> None:
    queries = {
        "lookup": "SELECT * FROM Players WHERE id=%s",
        "update": "UPDATE Players SET comment=%s WHERE id=%s",
    }
    result = finalize_query_placeholders(queries, "sqlite")

    assert result is queries
    assert result == {
        "lookup": "SELECT * FROM Players WHERE id=?",
        "update": "UPDATE Players SET comment=? WHERE id=?",
        "placeholder": "?",
    }


def test_finalize_query_placeholders_leaves_unknown_backend_unchanged() -> None:
    queries = {"lookup": "SELECT * FROM Players WHERE id=%s"}
    assert finalize_query_placeholders(queries, "unknown") == queries
