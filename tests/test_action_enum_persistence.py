#!/usr/bin/env python3
"""The PT4 action enums must reach HandsPlayers, not just the stats dict.

``DerivedStats.calcActionEnums`` computed twenty ``enum_*`` values that no
schema, insert or key list mentioned, so every one of them was recomputed on
each import and thrown away. These tests cover the three places that have to
agree and the round trip through a real insert.
"""

import re
import sqlite3
from decimal import Decimal

import pytest

import fpdb_3_legacy.Database as Database
import fpdb_3_legacy.SQL as SQL
from fpdb_3_legacy.Database import adapt_decimal, convert_decimal
from fpdb_3_legacy.DerivedStats import ACTION_ENUM_KEYS, DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars


class MockConfig:
    def get_import_parameters(self) -> dict:
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [],
            "handCount": 0,
            "fastFold": False,
            "ringFilter": True,
            "tourneyFilter": True,
        }

    def get_site_id(self, sitename: str) -> int:
        return 32


# The button calls the small blind's flop c-bet and raises the turn barrel:
# Floater's enum_t_float_action is R, which is not the "N" default and so
# proves the value itself survives the round trip.
FLOAT_HAND = """PokerStars Hand #100000000002:  Hold'em No Limit ($0.05/$0.10 USD) - 2024/01/01 12:00:00 ET
Table 'TestFloat' 6-max Seat #3 is the button
Seat 1: PFA ($10 in chips)
Seat 2: BBGuy ($10 in chips)
Seat 3: Floater ($10 in chips)
PFA: posts small blind $0.05
BBGuy: posts big blind $0.10
*** HOLE CARDS ***
Dealt to PFA [As Kd]
Floater: calls $0.10
PFA: raises $0.30 to $0.40
BBGuy: folds
Floater: calls $0.30
*** FLOP *** [9h Kd 2d]
PFA: bets $0.50
Floater: calls $0.50
*** TURN *** [9h Kd 2d] [7c]
PFA: bets $1
Floater: raises $2 to $3
PFA: folds
*** SUMMARY ***
Total pot $3.80 | Rake $0
Board [9h Kd 2d 7c]
Seat 1: PFA folded on the Turn
Seat 3: Floater collected $3.80"""


def _hands_players() -> dict:
    parser = PokerStars(config=MockConfig())

    def mock_read_file() -> bool:
        parser.obs = FLOAT_HAND
        parser.index = 0
        return True

    parser.readFile = mock_read_file
    hand = parser.processHand(parser.allHandsAsList()[0])
    stats = DerivedStats()
    stats.getStats(hand)
    return stats.getHandsPlayers()


def _sqlite_connection() -> sqlite3.Connection:
    """A connection set up the way Database.connect() sets up the SQLite one."""
    sqlite3.register_converter("bool", lambda x: bool(int(x)))
    sqlite3.register_adapter(bool, lambda x: 1 if x else 0)
    sqlite3.register_converter("decimal", convert_decimal)
    sqlite3.register_adapter(Decimal, adapt_decimal)
    conn = sqlite3.connect(":memory:")
    conn.execute(SQL.Sql(db_server="sqlite").query["createHandsPlayersTable"])
    return conn


def _insert_columns() -> list[str]:
    query = SQL.Sql(db_server="sqlite").query["store_hands_players"]
    col_block = re.search(r"\((.*?)\)\s*values", query, re.IGNORECASE | re.DOTALL)
    return [c.strip() for c in col_block.group(1).split(",") if c.strip()]


class TestActionEnumSchemaSync:
    """ACTION_ENUM_KEYS, HANDS_PLAYERS_KEYS and the insert must list the same columns."""

    def test_every_enum_key_is_a_stored_column(self) -> None:
        stored = set(Database.HANDS_PLAYERS_KEYS)
        missing = [key for key in ACTION_ENUM_KEYS if key not in stored]
        assert not missing, f"enum keys absent from HANDS_PLAYERS_KEYS: {missing}"

    def test_no_stored_enum_column_is_unknown_to_derivedstats(self) -> None:
        """A column DerivedStats never fills would KeyError in storeHandsPlayers."""
        stored = [key for key in Database.HANDS_PLAYERS_KEYS if key.startswith("enum_")]
        unknown = [key for key in stored if key not in ACTION_ENUM_KEYS]
        assert not unknown, f"columns no calculator produces: {unknown}"

    def test_insert_lists_the_enum_columns_in_key_order(self) -> None:
        """storeHandsPlayers positions values by HANDS_PLAYERS_KEYS order."""
        columns = [c for c in _insert_columns() if c.startswith("enum_")]
        assert columns == list(ACTION_ENUM_KEYS)

    def test_derivedstats_produces_every_enum_key(self) -> None:
        for player, pdata in _hands_players().items():
            missing = [key for key in ACTION_ENUM_KEYS if key not in pdata]
            assert not missing, f"{player} missing {missing}"


class TestActionEnumRoundTrip:
    """A parsed hand must land its enum values in HandsPlayers."""

    def _stored(self) -> tuple[dict, dict]:
        """Insert a parsed hand through the real storeHandsPlayers, then read back.

        Rows come back as name -> column dict. The select names no columns of
        its own so the query stays a literal: the point is what the insert
        wrote, and sqlite3.Row already labels it.
        """
        pdata = _hands_players()
        conn = _sqlite_connection()

        db = Database.Database.__new__(Database.Database)
        db.backend = Database.Database.SQLITE
        db.connection = conn
        db._in_transaction = 0
        db.sql = SQL.Sql(db_server="sqlite")
        db.hpbulk = []
        pids = {name: i + 1 for i, name in enumerate(pdata)}
        db.storeHandsPlayers(hid=1, pids=pids, pdata=pdata, doinsert=True)

        try:
            conn.row_factory = sqlite3.Row
            rows = {}
            for name, pid in pids.items():
                row = conn.execute(
                    "SELECT * FROM HandsPlayers WHERE playerId = ?",
                    (pid,),
                ).fetchone()
                rows[name] = dict(row) if row is not None else None
        finally:
            conn.close()
            # db has to outlive the reads: Database.__del__ closes the connection.
            del db

        return pdata, rows

    def test_enum_values_survive_the_insert(self) -> None:
        pdata, rows = self._stored()
        assert pdata["Floater"]["enum_t_float_action"] == "R", "fixture no longer exercises a float"
        assert rows["Floater"] is not None, "no HandsPlayers row was written"
        assert rows["Floater"]["enum_t_float_action"] == "R"

    def test_absent_situations_are_stored_as_n(self) -> None:
        """The default must round-trip too, so aggregates can count it."""
        _pdata, rows = self._stored()
        assert rows["BBGuy"]["enum_t_float_action"] == "N"

    def test_every_enum_column_is_written(self) -> None:
        """All twenty columns must carry what DerivedStats computed."""
        pdata, rows = self._stored()
        for name, row in rows.items():
            stored = {key: row[key] for key in ACTION_ENUM_KEYS}
            expected = {key: pdata[name][key] for key in ACTION_ENUM_KEYS}
            assert stored == expected, f"{name} round-tripped wrong"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
