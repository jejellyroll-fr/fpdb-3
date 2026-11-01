#!/usr/bin/env python3
"""Regression tests for the HudCache schema/keys/SQL sync — GitHub issue #134.

Three drifts broke HudCache population (so the HUD had no aggregated stats):
  1. ``street0OpenLimpChance`` was in ``CACHE_KEYS`` but DerivedStats never
     produced it -> ``storeHudCache`` raised ``KeyError``.
  2. ``insert_hudcache`` named 124 columns but supplied only 121 placeholders.
  3. ``update_hudcache`` was missing 3 trailing SET columns.

The structural tests below catch any future drift between ``CACHE_KEYS``,
``insert_hudcache`` and ``update_hudcache``.
"""

import re
import sqlite3
from contextlib import closing

import pytest

import fpdb_3_legacy.Database as Database
import fpdb_3_legacy.SQL as SQL
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

KEY_COLUMNS = 6  # gametypeId, playerId, seats, position, tourneyTypeId, styleKey


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


# A hand where UTG is the first to act and open-limps (calls an unraised pot).
OPEN_LIMP_HAND = """PokerStars Hand #100000000001:  Hold'em No Limit ($0.05/$0.10 USD) - 2024/01/01 12:00:00 ET
Table 'TestLimp' 6-max Seat #1 is the button
Seat 1: Btn ($10 in chips)
Seat 2: SB ($10 in chips)
Seat 3: BB ($10 in chips)
Seat 4: UTG ($10 in chips)
Seat 5: MP ($10 in chips)
Seat 6: CO ($10 in chips)
SB: posts small blind $0.05
BB: posts big blind $0.10
*** HOLE CARDS ***
Dealt to UTG [As Ks]
UTG: calls $0.10
MP: folds
CO: folds
Btn: folds
SB: folds
BB: checks
*** FLOP *** [2c 7d 9h]
BB: checks
UTG: checks
*** TURN *** [2c 7d 9h] [3s]
BB: checks
UTG: checks
*** RIVER *** [2c 7d 9h 3s] [4c]
BB: checks
UTG: checks
*** SHOW DOWN ***
UTG: shows [As Ks] (high card Ace)
BB: shows [Qh Jh] (high card Queen)
UTG collected $0.20 from pot
*** SUMMARY ***
Total pot $0.20 | Rake $0
Board [2c 7d 9h 3s 4c]
Seat 4: UTG showed [As Ks] and won ($0.20) with high card Ace"""


class TestDerivedStatsOpenLimpChance:
    """DerivedStats must produce street0OpenLimpChance (CACHE_KEYS depends on it)."""

    def _stats(self):
        parser = PokerStars(config=MockConfig())

        def mock_read_file() -> bool:
            parser.obs = OPEN_LIMP_HAND
            parser.index = 0
            return True

        parser.readFile = mock_read_file
        hand = parser.processHand(parser.allHandsAsList()[0])
        stats = DerivedStats()
        stats.getStats(hand)
        return stats.handsplayers

    def test_open_limp_chance_key_present_for_all_players(self) -> None:
        """Every player dict must carry the key (else storeHudCache KeyErrors)."""
        hp = self._stats()
        for player, pdata in hp.items():
            assert "street0OpenLimpChance" in pdata, f"{player} missing street0OpenLimpChance"

    def test_open_limper_has_chance_and_done(self) -> None:
        """UTG open-limps an unraised pot: both chance and done are True."""
        hp = self._stats()
        assert hp["UTG"]["street0OpenLimpChance"] is True
        assert hp["UTG"]["street0OpenLimp"] is True

    def test_player_after_open_limp_has_no_chance(self) -> None:
        """MP acts after the pot was opened by the limp: no open-limp chance."""
        hp = self._stats()
        assert hp["MP"]["street0OpenLimpChance"] is False


class TestHudCacheQuerySync:
    """insert_hudcache / update_hudcache must stay aligned with CACHE_KEYS."""

    def setup_method(self) -> None:
        self.sql = SQL.Sql(db_server="sqlite")
        # HudCache has the shared CACHE_KEYS plus its own HUDCACHE_EXTRA_KEYS
        # (turn delayed-cbet / probe), appended after the CACHE_KEYS values.
        self.n_keys = len(Database.CACHE_KEYS) + len(Database.HUDCACHE_EXTRA_KEYS)

    def test_insert_hudcache_columns_match_values(self) -> None:
        query = self.sql.query["insert_hudcache"]
        col_block = re.search(r"\((.*?)\)\s*values", query, re.IGNORECASE | re.DOTALL)
        n_columns = len([c for c in col_block.group(1).split(",") if c.strip()])
        n_placeholders = query.count("?") + query.count("%s")

        expected = self.n_keys + KEY_COLUMNS
        assert n_columns == expected, f"insert_hudcache has {n_columns} columns, expected {expected}"
        assert n_placeholders == expected, f"insert_hudcache has {n_placeholders} placeholders, expected {expected}"

    def test_update_hudcache_set_count_matches_cache_keys(self) -> None:
        query = self.sql.query["update_hudcache"]
        # Each stat column is updated as "col=col+<placeholder>".
        n_set = query.count("+?") + query.count("+%s")
        assert n_set == self.n_keys, f"update_hudcache updates {n_set} columns, expected {self.n_keys}"

    def test_aggregated_stats_query_is_sqlite_compatible(self) -> None:
        """get_stats_from_hand_aggregated must not use PostgreSQL-only syntax.

        The RFI-by-position columns used `hc.position::text` (a PostgreSQL
        cast), which made the whole HUD stats query fail on SQLite with
        `unrecognized token: ":"`.
        """
        query = self.sql.query["get_stats_from_hand_aggregated"]
        assert "::" not in query, "get_stats_from_hand_aggregated uses a PostgreSQL :: cast"

    def test_aggregated_stats_query_uses_letter_positions(self) -> None:
        """RFI-by-position CASEs must match the D/C/M/E buckets storeHudCache writes."""
        query = self.sql.query["get_stats_from_hand_aggregated"]
        for bucket in ("'D'", "'C'", "'M'", "'E'"):
            assert f"hc.position = {bucket}" in query, f"missing position bucket {bucket}"

    def test_store_hands_players_columns_match_values(self) -> None:
        """store_hands_players columns/placeholders must match HANDS_PLAYERS_KEYS (+ handId, playerId)."""
        query = self.sql.query["store_hands_players"]
        col_block = re.search(r"\((.*?)\)\s*values", query, re.IGNORECASE | re.DOTALL)
        n_columns = len([c for c in col_block.group(1).split(",") if c.strip()])
        n_placeholders = query.count("?") + query.count("%s")

        expected = len(Database.HANDS_PLAYERS_KEYS) + 2  # handId, playerId
        assert n_columns == expected, f"store_hands_players has {n_columns} columns, expected {expected}"
        assert n_placeholders == expected, f"store_hands_players has {n_placeholders} placeholders, expected {expected}"

    def test_store_hands_players_sqlite_insert_executes(self) -> None:
        """The generated SQLite insert must be syntactically valid, not just count-aligned."""
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(self.sql.query["createHandsPlayersTable"])
            values = [0] * (len(Database.HANDS_PLAYERS_KEYS) + 2)

            conn.execute(self.sql.query["store_hands_players"], values)

            assert conn.execute("SELECT COUNT(*) FROM HandsPlayers").fetchone()[0] == 1

    def test_ensure_hudcache_columns_repairs_old_sqlite_schema(self) -> None:
        """Older databases must be upgraded in place when CACHE_KEYS gains columns."""
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(
                """
                CREATE TABLE HudCache (
                    id INTEGER PRIMARY KEY,
                    gametypeId INT,
                    playerId INT,
                    seats INT,
                    position TEXT,
                    tourneyTypeId INT,
                    styleKey TEXT,
                    n INT DEFAULT 0
                )
                """,
            )

            db = Database.Database.__new__(Database.Database)
            db.backend = Database.Database.SQLITE
            db.connection = conn
            db._in_transaction = 0

            db.ensure_hudcache_columns()

            columns = {row[1] for row in conn.execute("PRAGMA table_info(HudCache)")}
            missing = [column for column in Database.CACHE_KEYS if column not in columns]
            assert not missing

    def test_ensure_handsplayers_columns_repairs_old_sqlite_schema(self) -> None:
        """Older databases must gain new HandsPlayers stat columns before inserts run."""
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(
                """
                CREATE TABLE HandsPlayers (
                    id INTEGER PRIMARY KEY,
                    handId INT,
                    playerId INT,
                    startCash INT DEFAULT 0
                )
                """,
            )

            db = Database.Database.__new__(Database.Database)
            db.backend = Database.Database.SQLITE
            db.connection = conn
            db._in_transaction = 0

            db.ensure_handsplayers_columns()

            columns = {row[1] for row in conn.execute("PRAGMA table_info(HandsPlayers)")}
            missing = [column for column in Database.HANDS_PLAYERS_KEYS if column not in columns]
            assert not missing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
