from __future__ import annotations

import inspect
from datetime import datetime

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
