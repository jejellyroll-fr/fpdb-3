"""Phase 4 - live_min_stack_bb as a real table-scope stat.

Covers the three layers that replaced the old inline-SQL-in-update() hack:
  * Database.get_table_min_stack_bb - the corrected query (placeholder, Hands.id,
    end-of-hand stacks, eliminated/sitout excluded, divided by the big blind);
  * Stats.do_table_stat / live_min_stack_bb - the 6-tuple formatting contract;
  * SimpleStat.update - routing a table-scope (player_id is None) widget to the
    precomputed value on hud.table_stats, with no database access.
"""

from __future__ import annotations

import sqlite3
import types

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import Database, Stats


def _make_db():
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE Gametypes (id INTEGER PRIMARY KEY, smallBlind INT, bigBlind INT);
        CREATE TABLE Hands (id INTEGER PRIMARY KEY, gametypeId INT);
        CREATE TABLE HandsPlayers (id INTEGER PRIMARY KEY, handId INT, playerId INT,
            startCash INT, committed INT, winnings INT, sitout INT);
        INSERT INTO Gametypes VALUES (1, 15, 30);
        INSERT INTO Hands VALUES (100, 1);
        INSERT INTO HandsPlayers VALUES (1,100,10,500,100,0,0);   -- end 400
        INSERT INTO HandsPlayers VALUES (2,100,11,300,300,600,0); -- end 600
        INSERT INTO HandsPlayers VALUES (3,100,12,200,200,0,0);   -- end 0 (eliminated)
        INSERT INTO HandsPlayers VALUES (4,100,13,900,0,0,1);     -- sitout
        """
    )
    db = Database.Database.__new__(Database.Database)
    db.connection = con
    db.sql = types.SimpleNamespace(query={"placeholder": "?"})
    db.get_cursor = lambda: con.cursor()
    return db, con


def test_min_stack_excludes_eliminated_and_sitout():
    db, _ = _make_db()
    val = db.get_table_min_stack_bb(100)
    assert val == pytest.approx(400 / 30)  # min surviving stack / big blind


def test_min_stack_none_when_no_survivors():
    db, con = _make_db()
    con.execute("UPDATE HandsPlayers SET sitout=1")
    assert db.get_table_min_stack_bb(100) is None


def test_min_stack_none_for_unknown_hand():
    db, _ = _make_db()
    assert db.get_table_min_stack_bb(999) is None


def test_do_table_stat_formats_six_tuple():
    n = Stats.do_table_stat({"live_min_stack_bb": 11.06}, "live_min_stack_bb")
    assert len(n) == 6
    assert n[1] == "11.1"
    assert n[5] == "Live Min Stack (BB)"


def test_do_table_stat_missing_or_unknown_is_none():
    assert Stats.do_table_stat({}, "live_min_stack_bb") is None
    assert Stats.do_table_stat({"live_min_stack_bb": 5.0}, "unknown_stat") is None
    assert Stats.do_table_stat({}, "") is None


def test_simplestat_table_scope_reads_hud_table_stats():
    from fpdb_3_legacy import Aux_Hud

    stat = Aux_Hud.SimpleStat.__new__(Aux_Hud.SimpleStat)
    stat.stat = "live_min_stack_bb"
    stat.colors = {}
    stat._bg = ""
    stat.lab = types.SimpleNamespace(stat_dict=None, setText=lambda _t: None)
    stat.hud = types.SimpleNamespace(table_stats={"live_min_stack_bb": 13.33}, hand_instance=None)

    # player_id is None -> table scope, value from hud.table_stats (no DB access)
    stat.update(None, {})
    assert stat.number[1] == "13.3"
    assert stat.number[5] == "Live Min Stack (BB)"


def test_simplestat_table_scope_missing_value_is_falsy():
    from fpdb_3_legacy import Aux_Hud

    stat = Aux_Hud.SimpleStat.__new__(Aux_Hud.SimpleStat)
    stat.stat = "live_min_stack_bb"
    stat.colors = {}
    stat._bg = ""
    stat.lab = types.SimpleNamespace(stat_dict=None, setText=lambda _t: None)
    stat.hud = types.SimpleNamespace(table_stats={}, hand_instance=None)

    stat.update(None, {})
    assert not stat.number  # None -> ClassicStat would early-return, showing placeholder
