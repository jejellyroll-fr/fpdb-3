"""Live-backend check for the grouped HudCache flush (#680).

The bulk lookup uses row constructors -- ``(a, b, ...) IN ((...), ...)`` --
which every supported backend parses, but that is exactly the kind of thing
worth proving against real servers, not just SQLite. Each backend gets a fresh
schema, two flushes of the same cache key, and the assertion that the counters
accumulated into one row (the semantics the per-entry SELECT+UPDATE used to
provide, at a fraction of the round trips).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

import fpdb_3_legacy.Database as Database
from fpdb_3_legacy import dialects
from fpdb_3_legacy.database_caches import DatabaseCachesMixin
from fpdb_3_legacy.SQL import Sql
from tests.test_database_backend_integration import _connection, _create_schema, _enabled_backends

CACHE_KEYS = Database.CACHE_KEYS
HUDCACHE_EXTRA_KEYS = Database.HUDCACHE_EXTRA_KEYS

N = CACHE_KEYS.index("n")
VPI = CACHE_KEYS.index("street0VPI")


def _player_stats(**overrides: Any) -> dict[str, Any]:
    stats: dict[str, Any] = dict.fromkeys(CACHE_KEYS, 0)
    stats.update(dict.fromkeys(HUDCACHE_EXTRA_KEYS, 0))
    stats.update(position=0, tourneyTypeId=None, startCards=0)
    stats.update(overrides)
    return stats


class _CacheHost(DatabaseCachesMixin):
    """Minimal Database-compatible host for the caches mixin, on a live connection."""

    def __init__(self, connection: Any, backend: str) -> None:
        self.connection = connection
        self.backend = dialects.dialect_for_server(backend).backend_id
        self.sql = Sql(db_server=backend)
        self.import_options = {"hhBulkPath": ""}
        self.build_full_hudcache = False
        self.day_start = 0
        self.ttnew, self.ttold = set(), set()
        self.hcbulk: dict[Any, Any] = {}

    def get_cursor(self) -> Any:
        return self.connection.cursor()

    def commit(self, force: bool = False) -> None:
        self.connection.commit()

    def executemany(self, c: Any, q: str, values: Any) -> None:
        c.executemany(q, values)


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_grouped_hudcache_flush_accumulates_into_one_row_on_a_live_backend(backend: str) -> None:
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")

    with _connection(backend) as connection:
        _create_schema(connection, backend)
        host = _CacheHost(connection, backend)
        # HudCache has foreign keys to Gametypes and Players: seed them through
        # the catalogue's own insert so every NOT NULL column is filled.
        placeholder = host.sql.query["placeholder"]
        with connection.cursor() as cursor:
            cursor.execute(  # nosemgrep
                f"INSERT INTO Sites (id,name,code) VALUES ({placeholder},{placeholder},{placeholder})",
                (1, "Room", "RM"),
            )
            # buyinType is a varchar and the last four columns are BOOLEAN on
            # PostgreSQL but tinyint-ish on MySQL, so the values differ per backend.
            flags = (None, None, None, None) if backend == "postgresql" else (0, 0, 0, 0)
            cursor.execute(  # nosemgrep
                host.sql.query["insertGameTypes"].replace("%s", placeholder),
                (1, "USD", "hold", "nl", "holdem", "fl", "h", "none", 5, 10, 10, 20, 6, 0, "none", *flags),
            )
            cursor.execute(  # nosemgrep
                f"INSERT INTO Players (id,name,siteId) VALUES ({placeholder},{placeholder},{placeholder})",
                (11, "Hero", 1),
            )
        connection.commit()
        pids = {"Hero": 11}
        ring = {"type": "ring"}
        for _ in range(2):
            host.storeHudCache(
                1,
                ring,
                pids,
                datetime(2026, 7, 20, 14, 30),
                {"Hero": _player_stats(street0VPI=1)},
            )
            # The importer flushes and clears the buffer once per file.
            host.storeHudCache(1, ring, pids, datetime(2026, 7, 20, 14, 30), {}, doinsert=True)
            host.hcbulk.clear()

        with connection.cursor() as cursor:
            cursor.execute(  # nosemgrep
                f"SELECT COUNT(*), COALESCE(SUM(n), 0), COALESCE(SUM(street0VPI), 0) "
                f"FROM HudCache WHERE playerId = {placeholder}",
                (11,),
            )
            count, total_n, total_vpi = cursor.fetchone()
        assert int(count) == 1
        assert int(total_n) == 2
        assert int(total_vpi) == 2
        connection.commit()
