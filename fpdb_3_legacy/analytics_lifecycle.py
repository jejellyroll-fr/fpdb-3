"""Data lifecycle for the analytics-derived tables (issue #305).

The layers built on the parsed hand (#293 events, #294 situations, #295
board features, #296 sizing buckets) all share one lifecycle problem: their
rows are *derived*, so a change of rule can make stored rows lie without
any parser ever being wrong again. This module owns the answer, in three
parts:

**Versions.** Every subsystem that can change semantics declares its
extractor version here, and the one place that knows the rule is the one
that bumps the number. The versions live in ``AnalyticsMeta`` -- an
explicit versioned schema of the analytics tables, separate from
``Settings.version`` (whose number means "recreate and reimport
everything"; a derived-row refresh must not demand that).

**Staleness.** A subsystem whose recorded version differs from the code's
version -- or has no recorded version at all -- is stale: its rows were
written by other rules and the query layers must not present them as
current (``is_stale``, ``stale_subsystems``).

**Rebuild.** ``analytics_rebuild`` re-derives the rows in place, from the
raw hand histories the importer already stored (``RawHands``), with
progress reporting, cancellation and one transaction per hand -- so a
cancelled rebuild leaves the rows it finished current and the rest simply
stale, never a half-written hand.

Downgrades are not supported: a database written by a newer extractor
version keeps its rows but is reported stale-for-reading until the code
catches up, and nothing ever rewinds a recorded version to claim currency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# The subsystems whose stored rows can go stale, with the version of the
# rules that produced them. Bumping a version is a semantic claim: the rows
# already stored were derived by different rules and must be re-derived
# before they can be read as current. #302 hand strength joins the table
# when that classifier lands.
SUBSYSTEMS: Final[tuple[str, ...]] = (
    "action_events",
    "situations",
    "board_features",
    "sizing_buckets",
    "hand_strength",
)

EXTRACTOR_VERSIONS: Final[dict[str, int]] = {
    "action_events": 1,
    "situations": 1,
    "board_features": 1,
    "sizing_buckets": 1,
    "hand_strength": 0,  # not yet implemented (#302); never current until it is
}

# The version of the analytics schema itself (the AnalyticsMeta table and
# anything it governs), separate from the extractors above.
ANALYTICS_SCHEMA_VERSION: Final = 1

# What a missing row means: the subsystem predates the meta table, so its
# rows were written before versioning existed and are stale by definition.
VERSION_UNRECORDED: Final = -1


@dataclass(frozen=True)
class SubsystemStatus:
    """One subsystem's recorded version against the code's version."""

    name: str
    recorded_version: int
    code_version: int

    @property
    def is_stale(self) -> bool:
        """True when the stored rows were derived by other rules.

        Unrecorded and behind are both stale. *Ahead* is stale too, from the
        reading side: rows written by a newer extractor must not be presented
        as current by older code that does not know its rules.
        """
        return self.recorded_version != self.code_version


# Backend identifiers, spelled as the Database class constants so this
# module never has to import Database (which imports this module's users).
_BACKEND_MYSQL, _BACKEND_PGSQL, _BACKEND_SQLITE = 2, 3, 4


def ensure_analytics_meta(db: Any) -> None:
    """Create the AnalyticsMeta table when the database lacks it.

    The table is key/value on purpose: adding a subsystem must never be a
    schema migration. Committed immediately -- it is bookkeeping, not hand
    data, and must survive even when the caller's surrounding transaction is
    rolled back.
    """
    ddl = {
        _BACKEND_MYSQL: "CREATE TABLE IF NOT EXISTS AnalyticsMeta (name VARCHAR(64) PRIMARY KEY, value VARCHAR(255) NOT NULL) ENGINE=INNODB",
        _BACKEND_PGSQL: "CREATE TABLE IF NOT EXISTS AnalyticsMeta (name VARCHAR(64) PRIMARY KEY, value VARCHAR(255) NOT NULL)",
        _BACKEND_SQLITE: "CREATE TABLE IF NOT EXISTS AnalyticsMeta (name TEXT PRIMARY KEY, value TEXT NOT NULL)",
    }
    backend = getattr(db, "backend", None)
    sql = ddl.get(backend) if isinstance(backend, int) else None
    if sql is None:
        raise ValueError(f"Unsupported database backend: {backend!r}")
    c = db.get_cursor()
    c.execute(sql)
    db.commit()


def _read_meta(db: Any) -> dict[str, str]:
    c = db.get_cursor()
    c.execute("SELECT name, value FROM AnalyticsMeta")
    return {str(name): str(value) for name, value in c.fetchall()}


def _write_meta(db: Any, entries: dict[str, str]) -> None:
    c = db.get_cursor()
    backend = getattr(db, "backend", None)
    if backend == _BACKEND_PGSQL:
        statement = (
            "INSERT INTO AnalyticsMeta (name, value) VALUES (%s, %s)"
            " ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value"
        )
    elif backend == _BACKEND_SQLITE:
        statement = (
            "INSERT INTO AnalyticsMeta (name, value) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET value = excluded.value"
        )
    else:
        statement = (
            "INSERT INTO AnalyticsMeta (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)"
        )
    c.executemany(statement, [(name, value) for name, value in entries.items()])
    db.commit()


def _get_version(entry: str | None) -> int:
    try:
        return int(entry) if entry is not None else VERSION_UNRECORDED
    except ValueError:
        return VERSION_UNRECORDED


def subsystem_statuses(db: Any) -> dict[str, SubsystemStatus]:
    """Every subsystem's recorded version against the code's version."""
    meta = _read_meta(db)
    statuses: dict[str, SubsystemStatus] = {}
    for name in SUBSYSTEMS:
        recorded = _get_version(meta.get(f"{name}_version"))
        statuses[name] = SubsystemStatus(
            name=name,
            recorded_version=recorded,
            code_version=EXTRACTOR_VERSIONS[name],
        )
    return statuses


def is_stale(db: Any, subsystem: str) -> bool:
    """True when a subsystem's stored rows must not be read as current."""
    if subsystem not in EXTRACTOR_VERSIONS:
        raise ValueError(f"Unknown analytics subsystem: {subsystem!r}")
    return subsystem_statuses(db)[subsystem].is_stale


def stale_subsystems(db: Any) -> tuple[str, ...]:
    """The subsystems whose stored rows were derived by other rules."""
    return tuple(name for name in SUBSYSTEMS if EXTRACTOR_VERSIONS[name] > 0 and subsystem_statuses(db)[name].is_stale)


def mark_current(db: Any, *subsystems: str) -> None:
    """Record that a subsystem's stored rows match the code's rules.

    Called by the rebuild path after the rows are re-derived, and by the
    importer-side bootstrap on a fresh database where everything the code
    writes is by definition current.
    """
    unknown = [name for name in subsystems if name not in EXTRACTOR_VERSIONS]
    if unknown:
        raise ValueError(f"Unknown analytics subsystem(s): {unknown!r}")
    entries = {f"{name}_version": str(EXTRACTOR_VERSIONS[name]) for name in subsystems}
    _write_meta(db, entries)


def bootstrap_meta(db: Any) -> None:
    """Create the meta table and stamp a fresh database as current.

    For a database just created by ``recreate_tables``: everything in it will
    be written by the running code, so every implemented subsystem is born
    current. An *existing* database keeps its recorded versions and its
    staleness -- only the rebuild moves those.
    """
    ensure_analytics_meta(db)
    meta = _read_meta(db)
    unrecorded = [name for name in SUBSYSTEMS if EXTRACTOR_VERSIONS[name] > 0 and f"{name}_version" not in meta]
    if unrecorded:
        mark_current(db, *unrecorded)


def schema_status(db: Any) -> tuple[bool, int, int]:
    """(current, recorded, code) for the analytics schema itself."""
    meta = _read_meta(db)
    recorded = _get_version(meta.get("analytics_schema_version"))
    return recorded == ANALYTICS_SCHEMA_VERSION, recorded, ANALYTICS_SCHEMA_VERSION


def record_schema_version(db: Any) -> None:
    """Stamp the analytics schema version after creating/migrating its tables."""
    _write_meta(db, {"analytics_schema_version": str(ANALYTICS_SCHEMA_VERSION)})
