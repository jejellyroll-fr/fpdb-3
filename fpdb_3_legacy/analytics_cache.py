"""Incremental aggregate cache for the analytics engine (#304).

Advanced analytics scans decisions, and a "player x position x situation"
breakdown re-derives the same counters every time it is asked. This module
stores those counters, and -- the part that matters -- keeps them current by
scanning only the hands that arrived since the last refresh.

**What is cached.** Additive metrics: counts (``opportunities``,
``action_count``) and frequencies (a numerator and a denominator), and money
metrics (``total_profit`` and friends sum ``HandsPlayers`` per hand-player and
are additive too). Averages are *not* cached, because an average cannot be
combined from group means: ``average_sizing`` bypasses the cache and runs the
query directly. That is a deliberate hole rather than a silent wrong number.

**How it stays current.** Each cached query records the highest ``Hands.id``
it has seen in ``AnalyticsMeta`` (the lifecycle table from #305). A refresh
re-runs the query with ``hand_id_from = watermark + 1`` and adds the delta to
the stored counters, so importing a thousand hands costs a scan of a thousand
hands, not of the whole database. No full rebuild after an import.

**When it is invalidated.** Deleting or reimporting hands moves or reuses
ids, so the watermark cannot detect it: anything that deletes, reimports or
reassigns hands must call :func:`invalidate_aggregates` first (also exposed by
``tools/analytics_cache.py``), exactly as an alias merge must, since both
change the rows a stored counter was built from. Nothing wires that up
implicitly -- there is no single delete path in the importer to hook -- so it
is a documented obligation of those callers rather than a silent guess. A
change of classification rules needs no such call: #305 tracks it, and if any
derived subsystem is stale, or the cache's own version moved, the cache is
dropped and rebuilt from scratch rather than serving rows the new rules would
reject.

Units and semantics are the engine's: a frequency is in basis points, money is
in cents (``docs/query-engine.md``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .analytics_lifecycle import ensure_analytics_meta
from .analytics_query import METRICS, Query, QueryResult, QueryRow, run_query
from .loggingFpdb import get_logger

log = get_logger("analytics_cache")

# The cache's own version. Bumping it invalidates every database's cache on the
# next read; that is the point, so a semantics change is never served stale.
ANALYTICS_CACHE_VERSION: Final = 1

# Metrics that cannot be combined from group means, and so are never cached.
# They still run -- just not through here.
NON_CACHEABLE_METRICS: Final[frozenset[str]] = frozenset({"average_sizing", "average_facing_sizing", "average_spr", "average_pot"})

# A per-opportunity metric is the paired *total* divided by the decision count.
# The cache must store the raw total and divide on read, so a refresh sums the
# total metric rather than the already-divided number (which would be divided
# again, and would carry the engine's rounding).
TOTAL_METRIC_FOR: Final[dict[str, str]] = {
    "profit_per_opportunity": "total_profit",
    "ev_per_opportunity": "all_in_ev",
}

TABLE_NAME: Final = "AnalyticsAggregates"
_VERSION_KEY: Final = "aggregate_version"
_WATERMARK_PREFIX: Final = "aggregate_watermark:"

_BACKEND_MYSQL, _BACKEND_PGSQL, _BACKEND_SQLITE = 2, 3, 4


@dataclass(frozen=True)
class CacheStats:
    """What the cache currently holds, for a status report."""

    version: int
    rows: int
    queries: int
    watermarks: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {"version": self.version, "rows": self.rows, "queries": self.queries, "watermarks": dict(self.watermarks)}


# ---------------------------------------------------------------------------
# Fingerprints and cacheability.
# ---------------------------------------------------------------------------


def query_fingerprint(query: Query) -> str:
    """A stable key for a query's *meaning*, independent of limits or order.

    Two queries that compute the same counters must share a cache entry, and
    two that do not must never collide -- hence a canonical JSON of the metric,
    the sorted filters, the numerator and the grouping, hashed.
    """
    spec, filters, numerator = query.resolved()
    canonical = json.dumps(
        {
            "metric": spec.name,
            "filters": _canonical(filters),
            "numerator": _canonical(numerator),
            "group_by": list(query.group_by),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical(filters: Mapping[str, Any]) -> dict[str, Any]:
    """Sort a filter dict and make its values JSON-stable."""
    out: dict[str, Any] = {}
    for name in sorted(filters):
        value = filters[name]
        if isinstance(value, (set, frozenset)):
            out[name] = sorted(value, key=str)
        elif isinstance(value, (list, tuple)):
            # Range endpoints are ordered: [None, 100] means a maximum while
            # [100, None] means a minimum.  Only set-style values are
            # order-independent.
            out[name] = list(value)
        else:
            out[name] = value
    return out


def is_cacheable(query: Query) -> bool:
    """Whether this query's metric can be served from stored counters."""
    spec, _filters, _numerator = query.resolved()
    return spec.name not in NON_CACHEABLE_METRICS


# ---------------------------------------------------------------------------
# Table and meta bookkeeping.
# ---------------------------------------------------------------------------


def ensure_aggregates_table(db: Any) -> None:
    """Create the aggregate table (and the meta table it leans on) if missing."""
    ddl = {
        _BACKEND_MYSQL: f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            queryKey CHAR(64) NOT NULL,
                            groupKey VARCHAR(191) NOT NULL,
                            opportunities BIGINT NOT NULL DEFAULT 0,
                            actions BIGINT NOT NULL DEFAULT 0,
                            valueSum NUMERIC NOT NULL DEFAULT 0,
                            PRIMARY KEY (queryKey, groupKey))
                        ENGINE=INNODB""",
        _BACKEND_PGSQL: f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            queryKey CHAR(64) NOT NULL,
                            groupKey VARCHAR(191) NOT NULL,
                            opportunities BIGINT NOT NULL DEFAULT 0,
                            actions BIGINT NOT NULL DEFAULT 0,
                            valueSum NUMERIC NOT NULL DEFAULT 0,
                            PRIMARY KEY (queryKey, groupKey))""",
        _BACKEND_SQLITE: f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            queryKey TEXT NOT NULL,
                            groupKey TEXT NOT NULL,
                            opportunities INTEGER NOT NULL DEFAULT 0,
                            actions INTEGER NOT NULL DEFAULT 0,
                            valueSum REAL NOT NULL DEFAULT 0,
                            PRIMARY KEY (queryKey, groupKey))""",
    }
    backend = getattr(db, "backend", None)
    if backend not in ddl:
        raise ValueError(f"Unsupported database backend: {backend!r}")
    ensure_analytics_meta(db)
    cursor = db.get_cursor()
    cursor.execute(ddl[backend])
    db.commit()


def _read_meta(db: Any) -> dict[str, str]:
    cursor = db.get_cursor()
    cursor.execute("SELECT name, value FROM AnalyticsMeta")
    return {str(name): str(value) for name, value in cursor.fetchall()}


def _write_meta(db: Any, name: str, value: str, commit: bool = True) -> None:
    backend = getattr(db, "backend", None)
    if backend == _BACKEND_PGSQL:
        statement = "INSERT INTO AnalyticsMeta (name, value) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value"
    elif backend == _BACKEND_SQLITE:
        statement = "INSERT INTO AnalyticsMeta (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value"
    else:
        statement = "INSERT INTO AnalyticsMeta (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)"
    cursor = db.get_cursor()
    cursor.execute(statement, (name, value))
    if commit:
        db.commit()


def _max_hand_id(db: Any) -> int:
    cursor = db.get_cursor()
    cursor.execute("SELECT MAX(id) FROM Hands")
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def aggregate_stats(db: Any) -> CacheStats:
    """A status snapshot: version, cached rows and per-query watermarks."""
    ensure_aggregates_table(db)
    meta = _read_meta(db)
    cursor = db.get_cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")  # nosec B608  # nosemgrep
    rows = int(cursor.fetchone()[0] or 0)
    cursor.execute(f"SELECT COUNT(DISTINCT queryKey) FROM {TABLE_NAME}")  # nosec B608  # nosemgrep
    queries = int(cursor.fetchone()[0] or 0)
    watermarks = {name[len(_WATERMARK_PREFIX):]: int(value) for name, value in meta.items() if name.startswith(_WATERMARK_PREFIX)}
    return CacheStats(
        version=int(meta.get(_VERSION_KEY, 0) or 0),
        rows=rows,
        queries=queries,
        watermarks=watermarks,
    )


def invalidate_aggregates(db: Any, reason: str = "") -> int:
    """Drop every cached row and watermark; returns the rows removed.

    Called when hands are deleted or reimported (ids can move), when player
    aliases change (the player dimension changes), and by the version guard.
    ``reason`` is only for the log.
    """
    ensure_aggregates_table(db)
    cursor = db.get_cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")  # nosec B608  # nosemgrep
    removed = int(cursor.fetchone()[0] or 0)
    cursor.execute(f"DELETE FROM {TABLE_NAME}")  # nosec B608  # nosemgrep
    placeholder = _placeholder(db)
    meta_delete_query = (
        "DELETE FROM AnalyticsMeta WHERE name LIKE ?"
        if placeholder == "?"
        else "DELETE FROM AnalyticsMeta WHERE name LIKE %s"
    )
    cursor.execute(meta_delete_query, (_WATERMARK_PREFIX + "%",))
    db.commit()
    del reason
    return removed


# ---------------------------------------------------------------------------
# Reading and refreshing.
# ---------------------------------------------------------------------------


def _stale_reason(db: Any) -> str | None:
    """Why the cache cannot be trusted, or None when it can."""
    meta = _read_meta(db)
    version = int(meta.get(_VERSION_KEY, 0) or 0)
    if version != ANALYTICS_CACHE_VERSION:
        return f"cache version {version} != {ANALYTICS_CACHE_VERSION}"
    from .analytics_lifecycle import stale_subsystems  # noqa: PLC0415 - keeps the import graph flat

    stale = stale_subsystems(db)
    if stale:
        return f"stale derived rows: {', '.join(stale)}"
    return None


def cached_query(db: Any, query: Query, force: bool = False) -> QueryResult:
    """The cached result, refreshed incrementally first when it is behind.

    Non-cacheable metrics fall through to :func:`run_query` unchanged.
    """
    if not is_cacheable(query):
        return run_query(db, query)
    ensure_aggregates_table(db)
    key = query_fingerprint(query)

    reason = _stale_reason(db)
    if reason is not None:
        invalidate_aggregates(db, reason)
        _write_meta(db, _VERSION_KEY, str(ANALYTICS_CACHE_VERSION))

    watermark = _watermark(db, key)
    current = _max_hand_id(db)
    have_rows = _has_rows(db, key)
    full = force or watermark == 0 or not have_rows
    if full or watermark < current:
        _refresh(db, query, key, watermark, current, full)
    return _read(db, query, key)


def cached_query_if_fresh(db: Any, query: Query) -> QueryResult | None:
    """The stored result for a query, when it is already up to date.

    Never refreshes and never writes. That matters for the live HUD (#335),
    which reads inside a transaction its caller rolls back: a refresh triggered
    from there would be undone while the watermark it wrote stayed, leaving the
    cache claiming work that never landed. A miss simply costs a direct query,
    which is the same answer.

    Returns ``None`` for a non-cacheable metric, a cache that is absent, a
    different cache version, stale derived rows, a query this key has never
    been stored for, or a cache that is behind the newest hand.
    """
    if not is_cacheable(query):
        return None
    key = query_fingerprint(query)
    try:
        if _stale_reason(db) is not None:
            return None
        watermark = _watermark(db, key)
        if watermark == 0 or not _has_rows(db, key) or watermark < _max_hand_id(db):
            return None
        return _read(db, query, key)
    except Exception:  # noqa: BLE001 - a cache that cannot be read is a miss, not an error
        log.debug("Analytics aggregate cache unavailable for key %s", key, exc_info=True)
        return None


def _watermark(db: Any, key: str) -> int:
    value = _read_meta(db).get(_WATERMARK_PREFIX + key, "0")
    try:
        return int(value)
    except ValueError:
        return 0


def _has_rows(db: Any, key: str) -> bool:
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    cursor.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE queryKey = {placeholder} LIMIT 1", (key,))  # nosec B608  # nosemgrep
    return cursor.fetchone() is not None


def _placeholder(db: Any) -> str:
    try:
        return str(db.sql.query["placeholder"])
    except (AttributeError, KeyError):
        return "%s"


def _refresh(db: Any, query: Query, key: str, watermark: int, current: int, full: bool) -> None:
    """Bring one query's counters up to ``current``, scanning only the delta."""
    # Store the paired total for a per-opportunity metric, not the ratio.
    storage_query = _storage_query(query)
    try:
        if full:
            result = run_query(db, storage_query)
            _replace_rows(db, key, result.rows, commit=False)
        else:
            delta_filters = dict(storage_query.filters)
            delta_filters["hand_id_from"] = watermark + 1
            delta_query = Query(
                metric=storage_query.metric,
                filters=delta_filters,
                numerator=dict(storage_query.numerator),
                group_by=storage_query.group_by,
            )
            delta = run_query(db, delta_query)
            _merge_rows(db, key, delta.rows, commit=False)
        # The aggregate delta and its watermark are one durable fact.  A
        # failure in either half must leave both at their previous values.
        _write_meta(db, _WATERMARK_PREFIX + key, str(current), commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _storage_query(query: Query) -> Query:
    """The query whose ``value`` column is what the cache stores as valueSum."""
    spec, _filters, _numerator = query.resolved()
    if spec.name in TOTAL_METRIC_FOR:
        return Query(
            metric=TOTAL_METRIC_FOR[spec.name],
            filters=dict(query.filters),
            numerator=dict(query.numerator),
            group_by=query.group_by,
            limit=None,
            offset=0,
        )
    del spec
    return Query(
        metric=query.metric,
        filters=dict(query.filters),
        numerator=dict(query.numerator),
        group_by=query.group_by,
        limit=None,
        offset=0,
    )


def _replace_rows(db: Any, key: str, rows: Sequence[QueryRow], commit: bool = True) -> None:
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE queryKey = {placeholder}", (key,))  # nosec B608  # nosemgrep
    _insert_rows(db, key, rows)
    if commit:
        db.commit()


def _merge_rows(db: Any, key: str, rows: Sequence[QueryRow], commit: bool = True) -> None:
    """Add a delta's counters to the stored ones, rewriting the key's rows."""
    existing = _stored_rows(db, key)
    for row in rows:
        group_key = _group_key(row.group)
        stored = existing.setdefault(group_key, {"group": dict(row.group), "opportunities": 0, "actions": 0, "valueSum": 0.0, "unit": row.unit})
        stored["opportunities"] += row.opportunities
        stored["actions"] += row.actions
        stored["valueSum"] += float(row.value or 0)
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE queryKey = {placeholder}", (key,))  # nosec B608  # nosemgrep
    rows_to_insert = [
        (key, group_key, stored["opportunities"], stored["actions"], stored["valueSum"]) for group_key, stored in existing.items()
    ]
    if rows_to_insert:
        marks = ", ".join(placeholder for _ in range(5))
        cursor.executemany(  # nosec B608  # nosemgrep
            f"INSERT INTO {TABLE_NAME} (queryKey, groupKey, opportunities, actions, valueSum) VALUES ({marks})",  # nosec B608  # nosemgrep
            rows_to_insert,
        )
    if commit:
        db.commit()


def _insert_rows(db: Any, key: str, rows: Sequence[QueryRow]) -> None:
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    marks = ", ".join(placeholder for _ in range(5))
    cursor.executemany(  # nosec B608  # nosemgrep
        f"INSERT INTO {TABLE_NAME} (queryKey, groupKey, opportunities, actions, valueSum) VALUES ({marks})",  # nosec B608  # nosemgrep
        [(key, _group_key(row.group), row.opportunities, row.actions, float(row.value or 0)) for row in rows],
    )


def _group_key(group: Mapping[str, Any]) -> str:
    return json.dumps(dict(group), sort_keys=True, default=str)


def _stored_rows(db: Any, key: str) -> dict[str, dict[str, Any]]:
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    stored_rows_query = (
        "SELECT groupKey, opportunities, actions, valueSum FROM AnalyticsAggregates WHERE queryKey = ?"
        if placeholder == "?"
        else "SELECT groupKey, opportunities, actions, valueSum FROM AnalyticsAggregates WHERE queryKey = %s"
    )
    cursor.execute(stored_rows_query, (key,))
    out: dict[str, dict[str, Any]] = {}
    for group_key, opportunities, actions, value_sum in cursor.fetchall():
        out[str(group_key)] = {
            "group": json.loads(str(group_key)),
            "opportunities": int(opportunities or 0),
            "actions": int(actions or 0),
            "valueSum": float(value_sum or 0),
        }
    return out


def _read(db: Any, query: Query, key: str) -> QueryResult:
    """Rebuild the result from the stored counters, in the engine's shape."""
    spec, _filters, _numerator = query.resolved()
    stored = _stored_rows(db, key)
    rows: list[QueryRow] = []
    for group_key in sorted(stored, key=lambda name: _order_key(stored[name]["group"], query.group_by)):
        entry = stored[group_key]
        opportunities = entry["opportunities"]
        actions = entry["actions"]
        value_sum = entry["valueSum"]
        if spec.frequency:
            value: float | None = float(actions)
        elif spec.per_opportunity:
            # The same rounding the engine applies, so a cached row is
            # byte-for-byte the row a direct query would return.
            value = round(float(value_sum) / opportunities, 4) if opportunities else 0.0
        elif spec.player_expression is not None or spec.value_sql is None:
            value = value_sum
        else:
            value = float(opportunities)
        frequency_bp = actions * 10000 // opportunities if opportunities else 0
        rows.append(
            QueryRow(
                group=entry["group"],
                opportunities=opportunities,
                actions=actions,
                value=value,
                unit=spec.unit,
                frequency_bp=frequency_bp if spec.frequency else None,
            ),
        )
    if query.limit is not None:
        rows = rows[query.offset : query.offset + query.limit]
    from .analytics_query import compile_query  # noqa: PLC0415 - only needed for the description

    compiled = compile_query(query, _placeholder(db), _backend_name(db))
    return QueryResult(rows=rows, compiled=compiled)


def _order_key(group: Mapping[str, Any], dimensions: Sequence[str]) -> tuple[Any, ...]:
    """Sort groups the way the engine does: by the dimensions, in order.

    Numbers sort numerically and text lexicographically, with numbers first,
    so a position grouping reads -2, -1, 0, 1, ... rather than the string
    order a JSON key would give it.
    """
    key: list[Any] = []
    for dimension in dimensions:
        value = group.get(dimension)
        if isinstance(value, bool):
            key.append((1, str(value)))
        elif isinstance(value, (int, float)):
            key.append((0, float(value)))
        else:
            key.append((1, str(value)))
    return tuple(key)


def _backend_name(db: Any) -> str:
    backend = getattr(db, "backend", None)
    names = {2: "mysql", 3: "postgresql", 4: "sqlite"}
    return names[backend] if isinstance(backend, int) and backend in names else "mysql"


def cache_metrics() -> tuple[str, ...]:
    """The metrics the cache can serve, for documentation and the CLI."""
    return tuple(sorted(name for name in METRICS if name not in NON_CACHEABLE_METRICS))


__all__ = [
    "ANALYTICS_CACHE_VERSION",
    "NON_CACHEABLE_METRICS",
    "TABLE_NAME",
    "CacheStats",
    "TOTAL_METRIC_FOR",
    "aggregate_stats",
    "cache_metrics",
    "cached_query",
    "ensure_aggregates_table",
    "invalidate_aggregates",
    "is_cacheable",
    "query_fingerprint",
]
