#!/usr/bin/env python3
"""The PT4 action enums, counted into HudCache and rendered as HUD stats.

The chain under test is: DerivedStats writes a response char per situation ->
action_enum_stats counts it -> storeHudCache sums the counters -> the HUD
aggregation selects them -> stats_action_enums renders the F/C/R split.

Every link is a place the three lists can drift apart, so most of what follows
is structural: same columns, same order, in the schema, both writes and both
reads.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from contextlib import closing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fpdb_3_legacy.SQL as SQL
import fpdb_3_legacy.Stats as Stats
from fpdb_3_legacy.action_enum_stats import CACHE_KEYS, SITUATIONS, derive_counters
from fpdb_3_legacy.database_caches import CACHE_KEYS as SHARED_CACHE_KEYS
from fpdb_3_legacy.database_caches import HUDCACHE_EXTRA_KEYS

# The button calls the flop c-bet and raises the turn barrel: one float raise.
FLOAT_HAND = """PokerStars Hand #100000000003:  Hold'em No Limit ($0.05/$0.10 USD) - 2024/01/01 12:00:00 ET
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

KEY_COLUMNS = 6  # gametypeId, playerId, seats, position, tourneyTypeId, styleKey

STAT_NAMES = [f"{action}_{s.stat_base}" for s in SITUATIONS for action in ("call", "raise", "fold")]


def _insert_columns() -> list[str]:
    query = SQL.Sql(db_server="sqlite").query["insert_hudcache"]
    block = re.search(r"\((.*?)\)\s*values", query, re.IGNORECASE | re.DOTALL)
    return [c.strip() for c in block.group(1).split(",") if c.strip()]


class TestCounterDerivation:
    """Each response char becomes exactly one faced/called/raised triple."""

    def test_call_counts_as_faced_and_called(self) -> None:
        row = {"enum_p_3bet_action": "C"}
        derive_counters(row)
        assert (row["cnt_p_face_3bet"], row["cnt_p_call_3bet"], row["cnt_p_raise_3bet"]) == (1, 1, 0)

    def test_raise_counts_as_faced_and_raised(self) -> None:
        row = {"enum_f_cbet_action": "R"}
        derive_counters(row)
        assert (row["cnt_f_face_cbet"], row["cnt_f_call_cbet"], row["cnt_f_raise_cbet"]) == (1, 0, 1)

    def test_fold_counts_as_faced_only(self) -> None:
        """The fold leg is derived, so a fold must show up as faced but neither."""
        row = {"enum_t_donk_action": "F"}
        derive_counters(row)
        assert (row["cnt_t_face_donk"], row["cnt_t_call_donk"], row["cnt_t_raise_donk"]) == (1, 0, 0)

    def test_absent_situation_counts_nothing(self) -> None:
        row = {"enum_r_float_action": "N"}
        derive_counters(row)
        assert (row["cnt_r_face_float"], row["cnt_r_call_float"], row["cnt_r_raise_float"]) == (0, 0, 0)

    def test_missing_enum_is_treated_as_absent(self) -> None:
        """A row from an older calculator must not raise, and must add nothing."""
        row: dict = {}
        derive_counters(row)
        assert not any(row[key] for key in CACHE_KEYS)

    def test_every_situation_is_covered(self) -> None:
        row = {s.enum_key: "R" for s in SITUATIONS}
        derive_counters(row)
        assert all(row[s.raised_key] == 1 for s in SITUATIONS)
        assert len(CACHE_KEYS) == 3 * len(SITUATIONS)


class TestCacheSchemaSync:
    """The counters must exist, in one order, everywhere HudCache is touched."""

    def test_columns_are_registered_as_hudcache_only_keys(self) -> None:
        assert [k for k in HUDCACHE_EXTRA_KEYS if k.startswith("cnt_") and k in CACHE_KEYS] == list(CACHE_KEYS)

    def test_counters_are_not_also_shared_cache_keys(self) -> None:
        """They are HudCache-only: a CACHE_KEYS entry would need a HandsPlayers column."""
        assert not set(CACHE_KEYS) & set(SHARED_CACHE_KEYS)

    def test_insert_column_order_matches_the_key_lists(self) -> None:
        """storeHudCache binds values positionally, so order is correctness.

        The count-only check in test_hudcache_schema_sync would pass with two
        columns transposed, which silently files every raise under calls.
        """
        columns = _insert_columns()[KEY_COLUMNS:]
        assert columns == list(SHARED_CACHE_KEYS) + list(HUDCACHE_EXTRA_KEYS)

    def test_update_sets_every_counter(self) -> None:
        query = SQL.Sql(db_server="sqlite").query["update_hudcache"]
        for key in CACHE_KEYS:
            assert f"{key}={key}+" in query, f"update_hudcache does not accumulate {key}"

    @pytest.mark.parametrize("db_server", ["mysql", "postgresql", "sqlite"])
    def test_every_backend_declares_the_columns(self, db_server: str) -> None:
        ddl = SQL.Sql(db_server=db_server).query["createHudCacheTable"]
        missing = [key for key in CACHE_KEYS if key not in ddl]
        assert not missing, f"{db_server} HudCache DDL missing {missing}"

    def test_sqlite_hudcache_insert_executes(self) -> None:
        """Count-aligned is not enough: the generated insert must actually run."""
        sql = SQL.Sql(db_server="sqlite")
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(sql.query["createHudCacheTable"])
            values = [0] * (len(SHARED_CACHE_KEYS) + len(HUDCACHE_EXTRA_KEYS) + KEY_COLUMNS)
            conn.execute(sql.query["insert_hudcache"].replace("%s", "?"), values)
            assert conn.execute("SELECT COUNT(*) FROM HudCache").fetchone()[0] == 1


class TestHudReadQueries:
    """Both HUD reads must expose the counters under their own names."""

    @pytest.mark.parametrize("query_name", ["get_stats_from_hand_aggregated", "get_stats_from_hand"])
    def test_query_selects_every_counter(self, query_name: str) -> None:
        query = SQL.Sql(db_server="sqlite").query[query_name]
        missing = [key for key in CACHE_KEYS if f"AS {key}" not in query]
        assert not missing, f"{query_name} does not expose {missing}"

    def test_aggregated_query_still_executes(self) -> None:
        """The HUD path: the widened select must remain valid SQL."""
        sql = SQL.Sql(db_server="sqlite")
        with closing(sqlite3.connect(":memory:")) as conn:
            for name in sql.query:
                if name.startswith("create") and name.endswith("Table"):
                    try:
                        conn.execute(sql.query[name])
                    except sqlite3.Error:  # unrelated table, not what this covers
                        pass
            query = sql.query["get_stats_from_hand_aggregated"].replace("<chipev_columns>", "").replace("%s", "?")
            cursor = conn.execute(query, [0] * query.count("?"))
            exposed = {d[0] for d in cursor.description}
        assert set(CACHE_KEYS) <= exposed


class TestStatFunctions:
    """The three legs of one spot share a denominator and add up to 100%."""

    def _row(self, faced: int, called: int, raised: int) -> dict:
        return {1: {"cnt_f_face_cbet": faced, "cnt_f_call_cbet": called, "cnt_f_raise_cbet": raised}}

    def test_legs_sum_to_one(self) -> None:
        stat_dict = self._row(10, 3, 2)
        total = sum(
            Stats.do_stat(stat_dict, 1, name)[0]
            for name in ("call_vs_flop_cbet", "raise_vs_flop_cbet", "fold_vs_flop_cbet")
        )
        assert total == pytest.approx(1.0)

    def test_fold_leg_is_derived_from_the_other_two(self) -> None:
        stat, _pct, _s, _l, detail, _desc = Stats.do_stat(self._row(10, 3, 2), 1, "fold_vs_flop_cbet")
        assert stat == pytest.approx(0.5)
        assert detail == "(5/10)"

    def test_fold_leg_never_renders_negative(self) -> None:
        """A partly rebuilt HudCache can hold more calls than faced spots."""
        stat, _pct, _s, _l, detail, _desc = Stats.do_stat(self._row(2, 3, 1), 1, "fold_vs_flop_cbet")
        assert stat == 0.0
        assert detail == "(0/2)"

    def test_unfaced_spot_reports_no_data(self) -> None:
        for name in ("call_vs_flop_cbet", "raise_vs_flop_cbet", "fold_vs_flop_cbet"):
            assert Stats.do_stat(self._row(0, 0, 0), 1, name)[1] == "-", name

    def test_every_stat_is_dispatchable(self) -> None:
        missing = [name for name in STAT_NAMES if name not in Stats.STATLIST]
        assert not missing, f"not selectable in the HUD: {missing}"

    def test_every_stat_survives_an_empty_stat_dict(self) -> None:
        """The HUD calls each configured stat on players it has no rows for."""
        for name in STAT_NAMES:
            assert Stats.do_stat({1: {}}, 1, name) is not None, name

    def test_abbreviations_are_unique(self) -> None:
        """Two spots sharing a HUD label would be indistinguishable on screen."""
        labels = [Stats.do_stat({1: {}}, 1, name)[2].split("=")[0] for name in STAT_NAMES]
        assert len(set(labels)) == len(labels)


class TestSessionHudQuery:
    """stat_range "S" reads HandsPlayers, not HudCache, and must still see them."""

    @pytest.mark.parametrize("db_server", ["mysql", "postgresql", "sqlite"])
    def test_session_query_derives_every_counter(self, db_server: str) -> None:
        query = SQL.Sql(db_server=db_server).query["get_stats_from_hand_session"]
        missing = [key for key in CACHE_KEYS if f"AS {key}" not in query]
        assert not missing, f"{db_server} session query does not expose {missing}"

    def test_session_aliases_are_lowercase(self) -> None:
        """get_stats_from_hand_session lowercases column names before summing."""
        assert all(key == key.lower() for key in CACHE_KEYS)


def _schema_connection() -> sqlite3.Connection:
    sql = SQL.Sql(db_server="sqlite")
    conn = sqlite3.connect(":memory:")
    for name in sql.query:
        if name.startswith("create") and name.endswith("Table"):
            try:
                conn.execute(sql.query[name])
            except sqlite3.Error:  # unrelated table, not what this covers
                pass
    return conn


class TestCacheRebuild:
    """rebuild_cache clears HudCache, so it has to be able to refill the counters."""

    def _rebuilt_row(self, columns: str) -> tuple:
        import fpdb_3_legacy.Database as Database

        sql = SQL.Sql(db_server="sqlite")
        conn = _schema_connection()
        conn.execute(
            "INSERT INTO Gametypes (id, siteId, currency, type, base, category, limitType,"
            " hiLo, mix, smallBet, bigBet, maxSeats, ante, buyinType)"
            " VALUES (1, 1, 'USD', 'ring', 'hold', 'holdem', 'nl', 'h', 'none', 5, 10, 6, 0, 'regular')",
        )
        conn.execute(
            "INSERT INTO Hands (id, tableName, siteHandNo, gametypeId, fileId, startTime, importTime,"
            " seats, heroSeat, maxPosition, playersVpi, playersAtStreet1, playersAtStreet2,"
            " playersAtStreet3, playersAtStreet4, playersAtShowdown,"
            " street0Raises, street1Raises, street2Raises, street3Raises, street4Raises)"
            " VALUES (1, 'T', '1', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00',"
            " 3, 1, 2, 2, 2, 2, 0, 0, 0, 1, 1, 0, 0, 0)",
        )
        conn.execute("INSERT INTO Players (id, name, siteId) VALUES (7, 'Floater', 1)")
        conn.execute(
            "INSERT INTO HandsPlayers (handId, playerId, startCash, effStack, seatNo, sitout,"
            " card1, card2, common, committed, winnings, rake, rakeDealt, rakeContributed,"
            " rakeWeighted, position, tourneysPlayersId,"
            " enum_t_float_action, enum_f_cbet_action, enum_p_3bet_action)"
            " VALUES (1, 7, 100, 100, 3, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, '0', NULL, 'R', 'C', 'F')",
        )
        conn.commit()

        db = Database.Database.__new__(Database.Database)
        db.backend = Database.Database.SQLITE
        db.build_full_hudcache = True
        db.sql = sql
        db.connection = conn
        db.hero_ids = None
        db._in_transaction = 0
        db._rebuild_ring_cache("HudCache", None, None, None)

        try:
            return conn.execute(f"SELECT {columns} FROM HudCache").fetchone()
        finally:
            conn.close()
            del db

    def test_rebuild_recounts_from_the_stored_enum_chars(self) -> None:
        """Without this the rebuild refills HudCache with zeros and loses them."""
        row = self._rebuilt_row(
            "cnt_t_face_float, cnt_t_call_float, cnt_t_raise_float,"
            " cnt_f_face_cbet, cnt_f_call_cbet, cnt_f_raise_cbet",
        )
        assert row == (1, 0, 1, 1, 1, 0)

    def test_rebuild_counts_a_fold_as_faced_only(self) -> None:
        """The fold leg is derived at render time, so only faced may move."""
        assert self._rebuilt_row("cnt_p_face_3bet, cnt_p_call_3bet, cnt_p_raise_3bet") == (1, 0, 0)

    def test_rebuild_leaves_untouched_situations_at_zero(self) -> None:
        assert self._rebuilt_row("cnt_r_face_donk, cnt_r_face_cbet") == (0, 0)

    @pytest.mark.parametrize("table", ["CardsCache", "PositionsCache", "SessionsCache"])
    def test_other_caches_do_not_inherit_the_columns(self, table: str) -> None:
        """Only HudCache has them; the placeholders must vanish elsewhere."""
        import fpdb_3_legacy.Database as Database

        db = Database.Database.__new__(Database.Database)
        db.backend = Database.Database.SQLITE
        db.build_full_hudcache = True
        query = db.replace_statscache("ring", table, SQL.Sql(db_server="sqlite").query["rebuildCache"])
        assert "<extra_insert_columns>" not in query
        assert "<extra_select_columns>" not in query
        assert not [key for key in CACHE_KEYS if key in query]


class TestParsedHand:
    """A real hand must reach the counters, not just the enum chars."""

    def _hands_players(self) -> dict:
        from fpdb_3_legacy.DerivedStats import DerivedStats
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

    def test_counters_agree_with_the_enums_they_come_from(self) -> None:
        for name, row in self._hands_players().items():
            for situation in SITUATIONS:
                response = row[situation.enum_key]
                assert row[situation.faced_key] == int(response != "N"), (name, situation.enum_key)
                assert row[situation.called_key] == int(response == "C"), (name, situation.enum_key)
                assert row[situation.raised_key] == int(response == "R"), (name, situation.enum_key)

    def test_the_floater_raise_reaches_its_counter(self) -> None:
        """The spot PR #267 restored must now be countable by the HUD."""
        rows = self._hands_players()
        assert rows["Floater"]["enum_t_float_action"] == "R"
        assert rows["Floater"]["cnt_t_raise_float"] == 1
        assert rows["Floater"]["cnt_t_face_float"] == 1
        assert rows["PFA"]["cnt_t_face_float"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
