from __future__ import annotations

import inspect
from datetime import datetime
from types import SimpleNamespace

import fpdb_3_legacy.Database as Database


def _player_stats(position):
    stats = {key: 0 for key in Database.CACHE_KEYS}
    stats.update({"position": position, "tourneyTypeId": None})
    return stats


def test_fast_store_hudcache_preserves_position_bucket():
    db = Database.Database.__new__(Database.Database)
    db.day_start = 0
    db.build_full_hudcache = False
    db.import_options = {"hhBulkPath": ""}
    db.ttnew = set()
    db.ttold = set()
    db.hcbulk = {}

    db.storeHudCache(
        gid=1,
        gametype={"type": "ring"},
        pids={"Hero": 101},
        starttime=datetime(2024, 1, 1, 12, 0, 0),
        pdata={"Hero": _player_stats(0)},
        doinsert=False,
    )

    key = next(iter(db.hcbulk))
    assert key[3] == "D"
    assert key[5] == "A000000"


def test_fast_rebuild_hudcache_preserves_position_bucket_in_query():
    db = Database.Database.__new__(Database.Database)
    db.build_full_hudcache = False

    query = "<insert> <select> <group> <hc_position> <styleKey> <styleKeyGroup> <sessions_join_clause> <tourney_insert_clause> <tourney_select_clause> <tourney_group_clause> <hero_where> <hero_join>"
    replaced = db.replace_statscache("ring", "HudCache", query)

    assert "when hp.position = '0' then 'D'" in replaced
    assert ",'0' as hc_position" not in replaced
    assert "'A000000' as styleKey" in replaced


def test_get_stats_from_hand_no_longer_exposes_builtin_type_parameter():
    signature = inspect.signature(Database.Database.get_stats_from_hand)
    assert "type" not in signature.parameters
    assert "game_type" in signature.parameters


def test_session_stats_are_not_truncated_after_ten_thousand_rows():
    class Cursor:
        description = [("player_id",), ("vpip",)]

        def __init__(self):
            self.rows = iter([(1, 1)] * 10_001)

        def execute(self, _query, _subs):
            return None

        def fetchone(self):
            return next(self.rows, None)

    cursor = Cursor()
    db = Database.Database.__new__(Database.Database)
    db.sql = SimpleNamespace(query={"get_stats_from_hand_session": "SELECT session stats"})
    db.db_server = "sqlite"
    db.hand_1day_ago = "2026-07-15"
    db.get_cursor = lambda: cursor
    stat_dict = {}

    db.get_stats_from_hand_session(
        hand=123,
        stat_dict=stat_dict,
        hero_id=None,
        stat_range="S",
        seats_min=2,
        seats_max=10,
        h_stat_range="S",
        h_seats_min=2,
        h_seats_max=10,
    )

    assert stat_dict[1]["vpip"] == 10_001


def test_cleanup_connections_ignores_already_closed_cursor(monkeypatch):
    class ClosedCursor:
        def close(self):
            raise RuntimeError("Cannot operate on a closed database")

    class Connection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    warnings = []
    monkeypatch.setattr(Database.log, "warning", lambda message, *args: warnings.append(message % args if args else message))

    db = Database.Database.__new__(Database.Database)
    db.cursor = ClosedCursor()
    db.connection = Connection()
    db._Database__connected = True

    db.cleanup_connections()

    assert warnings == []
    assert db.cursor is None
    assert db.connection is None
    assert db.is_connected() is False


def test_database_cli_exposes_index_rebuild_and_vacuum(monkeypatch, capsys):
    calls = []
    fake_db = SimpleNamespace(
        rebuild_indexes=lambda: calls.append("rebuild"),
        vacuumDB=lambda: calls.append("vacuum"),
    )
    monkeypatch.setattr(Database.Configuration, "set_logfile", lambda _path: None)
    monkeypatch.setattr(Database.Configuration, "Config", lambda: object())
    monkeypatch.setattr(Database.SQL, "Sql", lambda **_kwargs: object())
    monkeypatch.setattr(Database, "Database", lambda _config: fake_db)

    result = Database.main(["--rebuild-indexes", "--vacuum"])

    assert result == 0
    assert calls == ["rebuild", "vacuum"]
    output = capsys.readouterr().out
    assert "Index rebuild complete" in output
    assert "Database vacuum complete" in output


def test_mysql_player_insert_is_an_atomic_upsert():
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, query, params):
            self.calls.append((query, params))

    cursor = Cursor()
    db = Database.Database.__new__(Database.Database)
    db.backend = db.MYSQL_INNODB
    db.sql = SimpleNamespace(query={"placeholder": "%s"})
    db.get_cursor = lambda: cursor
    db.get_last_insert_id = lambda _cursor: 42

    player_id = db.insertPlayer("Hero", 7, True)

    assert player_id == 42
    assert len(cursor.calls) == 1
    query, params = cursor.calls[0]
    assert "ON DUPLICATE KEY UPDATE" in query
    assert "hero=hero OR VALUES(hero)" in query
    assert "id=LAST_INSERT_ID(id)" in query
    assert params == ("Hero", 7, True, "HE")
