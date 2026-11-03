"""The HudCache flush must cost a handful of statements, not one per entry (#680).

With the database on another machine every statement is a network round trip,
so the old SELECT-then-UPDATE loop cost 2N round trips per flush. These tests
pin the grouped write (one lookup per cache family plus batched UPDATE/INSERT)
and the accumulation semantics it must preserve, including the ring/tour split
where tourneyTypeId is NULL.
"""

from __future__ import annotations

from datetime import datetime

import fpdb_3_legacy.Database as Database
from fpdb_3_legacy import db_profile, latency_profile

CACHE_KEYS = Database.CACHE_KEYS
HUDCACHE_EXTRA_KEYS = Database.HUDCACHE_EXTRA_KEYS

N = CACHE_KEYS.index("n")
VPI = CACHE_KEYS.index("street0VPI")
PROFIT = CACHE_KEYS.index("totalProfit")

RING = {"type": "ring"}
TOUR = {"type": "tour"}


def player_stats(position=0, tourney_type_id=None, **overrides):
    stats = dict.fromkeys(CACHE_KEYS, 0)
    stats.update(dict.fromkeys(HUDCACHE_EXTRA_KEYS, 0))
    stats.update(position=position, tourneyTypeId=tourney_type_id, startCards=0)
    stats.update(overrides)
    return stats


def rows(db, sql, params=()):
    c = db.connection.cursor()
    c.execute(sql, params)
    result = c.fetchall()
    c.close()
    return result


def test_flush_inserts_then_accumulates_into_the_same_row(fresh_db) -> None:
    pids = {"Hero": 11}
    for profit in (250, -100):
        fresh_db.storeHudCache(
            7,
            RING,
            pids,
            datetime(2026, 7, 20, 14, 30),
            {"Hero": player_stats(position=0, street0VPI=1, totalProfit=profit)},
        )
        # The importer flushes and clears the buffer once per file.
        fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
        fresh_db.resetBulkCache()

    (row,) = rows(fresh_db, "SELECT n, street0VPI, totalProfit FROM HudCache WHERE playerId = 11")
    assert row[0] == 2
    assert row[1] == 2
    assert row[2] == 150
    assert rows(fresh_db, "SELECT COUNT(*) FROM HudCache")[0][0] == 1


def test_a_falsy_tourney_type_id_stays_in_the_ring_family(fresh_db) -> None:
    """tourneyTypeId NULL in the table must match a falsy id in the key (None or 0)."""
    pids = {"Hero": 11}
    for tourney_type_id in (None, 0):
        fresh_db.storeHudCache(
            7,
            RING,
            pids,
            datetime(2026, 7, 20, 14, 30),
            {"Hero": player_stats(position=0, tourney_type_id=tourney_type_id)},
        )
        fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
        fresh_db.resetBulkCache()

    hud_rows = rows(fresh_db, "SELECT COUNT(*), SUM(n) FROM HudCache WHERE playerId = 11")
    assert hud_rows[0] == (1, 2)


def test_tourney_entries_flush_into_their_own_rows(fresh_db) -> None:
    fresh_db.storeHudCache(
        7,
        TOUR,
        {"Hero": 11},
        datetime(2026, 7, 20, 14, 30),
        {"Hero": player_stats(position=0, tourney_type_id=3)},
    )
    fresh_db.storeHudCache(7, TOUR, {"Hero": 11}, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
    fresh_db.resetBulkCache()
    fresh_db.storeHudCache(
        7,
        RING,
        {"Hero": 11},
        datetime(2026, 7, 20, 14, 30),
        {"Hero": player_stats(position=0, tourney_type_id=None)},
    )
    fresh_db.storeHudCache(7, RING, {"Hero": 11}, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
    fresh_db.resetBulkCache()

    hud_rows = rows(
        fresh_db, "SELECT tourneyTypeId, n FROM HudCache WHERE playerId = 11 ORDER BY tourneyTypeId IS NULL"
    )
    assert hud_rows == [(3, 1), (None, 1)]


def test_one_flush_costs_a_handful_of_statements_regardless_of_player_count(fresh_db, monkeypatch) -> None:
    monkeypatch.setenv(db_profile.ENV_FLAG, "1")
    profile = db_profile.get_profile()
    profile.reset()
    # Count through a wrapper so the fixture's connection is profiled even
    # though it was opened before the flag was set.
    fresh_db.connection = db_profile.wrap_connection(fresh_db.connection, fresh_db.sql.query)

    pids = {f"P{i}": 100 + i for i in range(9)}
    pdata = {name: player_stats(position=seat % 6, street0VPI=1) for seat, name in enumerate(pids)}
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), pdata)
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)

    hudcache_statements = {
        name: stats.calls for name, stats in profile.by_statement.items() if "hudcache" in name and "create" not in name
    }
    # One grouped lookup plus one batched insert for nine players; the old code
    # issued one SELECT per player here.
    assert hudcache_statements.get("select_hudcache_ring_bulk (assembled)", 0) == 1
    assert hudcache_statements.get("select_hudcache_ring", 0) == 0
    assert hudcache_statements.get("insert_hudcache", 0) == 1
    profile.reset()


def test_flush_reports_cache_counters_to_the_latency_profile(fresh_db, monkeypatch) -> None:
    monkeypatch.setattr(latency_profile, "_ENABLED", True)
    profile = latency_profile.get_profile()
    profile.reset()

    pids = {"Hero": 11, "Villain": 22}
    pdata = {name: player_stats(position=0, street0VPI=1) for name in pids}
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), pdata)
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
    fresh_db.resetBulkCache()
    # Second flush: rows now exist, so the entries are updates.
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 31), pdata)
    fresh_db.storeHudCache(7, RING, pids, datetime(2026, 7, 20, 14, 31), {}, doinsert=True)
    fresh_db.resetBulkCache()

    metrics = profile.snapshot()["metrics"]
    assert metrics["hudcache_lookup"]["counter"] == 4
    assert metrics["hudcache_insert"]["counter"] == 2
    assert metrics["hudcache_update"]["counter"] == 2
    assert metrics["hudcache_write"]["count"] == 2
    profile.reset()


def test_buffered_lines_still_accumulate_before_the_flush() -> None:
    """doinsert=False only buffers; the grouped flush must not change that."""
    db = Database.Database.__new__(Database.Database)
    db.day_start = 0
    db.build_full_hudcache = False
    db.sessionTimeout = 30
    db.import_options = {"hhBulkPath": ""}
    db.ttnew, db.ttold = set(), set()
    db.wmnew, db.wmold = set(), set()
    db.hcbulk = {}

    pids = {"Hero": 11}
    for profit in (250, -100):
        db.storeHudCache(
            7,
            RING,
            pids,
            datetime(2026, 7, 20, 14, 30),
            {"Hero": player_stats(position=0, totalProfit=profit)},
        )
    (line,) = db.hcbulk.values()
    assert line[N] == 2
    assert line[PROFIT] == 150
