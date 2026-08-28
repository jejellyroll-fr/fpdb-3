#!/usr/bin/env python3
"""Regression tests for get_player_id()'s "unknown player" return value.

Every caller tests the result with ``is not None``, so returning False for an
unknown player let the bool through as if it were a player id: the GUI viewers
turned it into ``int(False) == 0``, and the HUD bound it to a ``playerId != %s``
placeholder, which PostgreSQL rejects with "operator does not exist:
integer <> boolean". That surfaced when switching to an iPoker room the hero had
not been imported under yet.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy import Database


def _db_returning(row, rows):
    db = Database.Database.__new__(Database.Database)  # bypass the heavy __init__
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = rows
    db.connection = MagicMock()
    db.connection.cursor.return_value = cursor
    db.sql = MagicMock()
    db.sql.query = {"get_player_id": "SELECT id FROM Players WHERE name = %s AND siteId = %s", "placeholder": "%s"}
    return db


def test_unknown_player_returns_none():
    db = _db_returning(row=None, rows=[])

    result = db.get_player_id(MagicMock(), "Bwin.fr Poker", "hero_never_seen_here")

    assert result is None


def test_unknown_player_is_not_a_bool():
    # `False is not None` is True, so a bool sentinel would defeat every caller's
    # guard and reach the database as a player id.
    db = _db_returning(row=None, rows=[])

    result = db.get_player_id(MagicMock(), "Bwin.fr Poker", "hero_never_seen_here")

    assert not isinstance(result, bool)


def test_known_player_returns_its_id():
    db = _db_returning(row=(4242,), rows=[])

    assert db.get_player_id(MagicMock(), "Bwin.fr Poker", "jejesat76") == 4242


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
