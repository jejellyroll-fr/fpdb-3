"""Final placeholder normalization for the SQL query catalogue."""

from __future__ import annotations

import re


def finalize_query_placeholders(query: dict[str, str], db_server: str) -> dict[str, str]:
    """Install the public placeholder key and normalize SQLite bind markers."""
    if db_server in ("mysql", "postgresql"):
        query["placeholder"] = "%s"
    elif db_server == "sqlite":
        query["placeholder"] = "?"
        for key, statement in list(query.items()):
            query[key] = re.sub("%s", "?", statement)
    return query
