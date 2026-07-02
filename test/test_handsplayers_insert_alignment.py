#!/usr/bin/env python3
"""Guard: the HandsPlayers INSERT column list, placeholders, and HANDS_PLAYERS_KEYS
must stay aligned. A mismatch silently breaks every hand import, so this is a
cheap canary whenever someone adds a persisted HandsPlayers column.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import SQL
from fpdb_3_legacy.Database import CACHE_KEYS, HANDS_PLAYERS_KEYS, HUDCACHE_EXTRA_KEYS


def _ncols(q, table):
    coltext = q.split("values")[0].split(table + " (")[1]
    return len([c.strip() for c in coltext.split(",") if c.strip() and c.strip() != ")"])


def test_insert_columns_match_keys_plus_two():
    sql = SQL.Sql(db_server="sqlite")
    q = sql.query["store_hands_players"]
    coltext = q.split("values")[0].split("HandsPlayers (")[1]
    ncols = len([c.strip() for c in coltext.split(",") if c.strip() and c.strip() != ")"])
    nplaceholders = q.count(sql.query.get("placeholder", "%s"))
    # +2 for handId and playerId appended in storeHandsPlayers.
    assert ncols == nplaceholders == len(HANDS_PLAYERS_KEYS) + 2


def test_delayed_cbet_columns_persisted_and_insertable():
    sql = SQL.Sql(db_server="sqlite")
    con = sqlite3.connect(":memory:")
    cur = con.cursor()
    cur.execute(sql.query["createHandsPlayersTable"])
    cols = {r[1] for r in cur.execute("PRAGMA table_info(HandsPlayers)")}
    assert "street2DelayedCBChance" in cols
    assert "street2DelayedCBDone" in cols
    # A full-width row inserts without a column/placeholder mismatch.
    row = [1, 1] + [0] * len(HANDS_PLAYERS_KEYS)
    cur.execute(sql.query["store_hands_players"], row)
    assert cur.execute("SELECT COUNT(*) FROM HandsPlayers").fetchone()[0] == 1


def test_keys_have_delayed_cbet():
    assert "street2DelayedCBChance" in HANDS_PLAYERS_KEYS
    assert "street2DelayedCBDone" in HANDS_PLAYERS_KEYS


def test_hudcache_insert_update_aligned():
    # HudCache adds HUDCACHE_EXTRA_KEYS on top of the shared CACHE_KEYS; the
    # other four caches must NOT be affected, so extras live outside CACHE_KEYS.
    sql = SQL.Sql(db_server="sqlite")
    ph = sql.query.get("placeholder", "%s")
    ins = sql.query["insert_hudcache"]
    upd = sql.query["update_hudcache"]
    expected_cols = 6 + len(CACHE_KEYS) + len(HUDCACHE_EXTRA_KEYS)  # 6 key columns
    assert _ncols(ins, "HudCache") == ins.count(ph) == expected_cols
    assert upd.count(ph) == len(CACHE_KEYS) + len(HUDCACHE_EXTRA_KEYS) + 1  # +1 WHERE id


def test_hudcache_extra_not_in_shared_cache_keys():
    # Critical: the extras must stay OUT of CACHE_KEYS or the Cards/Positions/
    # Sessions/Tourneys caches (which build lines from CACHE_KEYS) would break.
    for key in HUDCACHE_EXTRA_KEYS:
        assert key not in CACHE_KEYS


def test_hudcache_create_has_delayed_and_inserts():
    import sqlite3

    sql = SQL.Sql(db_server="sqlite")
    cur = sqlite3.connect(":memory:").cursor()
    cur.execute(sql.query["createHudCacheTable"])
    cols = {r[1] for r in cur.execute("PRAGMA table_info(HudCache)")}
    assert "street2DelayedCBChance" in cols and "street2DelayedCBDone" in cols
    row = [1, 1, 6, "D", 0, "A000000"] + [0] * (len(CACHE_KEYS) + len(HUDCACHE_EXTRA_KEYS))
    cur.execute(sql.query["insert_hudcache"], row)
    assert cur.execute("SELECT COUNT(*) FROM HudCache").fetchone()[0] == 1
