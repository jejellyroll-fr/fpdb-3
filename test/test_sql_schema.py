#!/usr/bin/env python3
"""Schema-generation regression tests for fpdb_3_legacy/SQL.py."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))

from SQL import Sql


def test_mysql_quotes_rank_table_in_foreign_key():
    """`Rank` collides with MariaDB/MySQL's RANK() window function.

    Without backticks, `REFERENCES Rank(id)` is parsed as a function call and
    fails with error 1064, so the MySQL variant must quote the identifier.
    """
    query = Sql(db_server="mysql").query["createHandsStoveTable"]
    assert "REFERENCES `Rank`(id)" in query
    assert "REFERENCES Rank(id)" not in query


def test_postgresql_leaves_rank_unquoted():
    """PostgreSQL folds unquoted identifiers to lower case; fpdb relies on that,
    so the table reference must stay unquoted (RANK is not function-ambiguous here).
    """
    query = Sql(db_server="postgresql").query["createHandsStoveTable"]
    assert "REFERENCES Rank(id)" in query
    assert "`" not in query


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
