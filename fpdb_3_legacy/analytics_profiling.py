"""Query-plan inspection and timing for the analytics engine (#304).

The engine (#297) compiles a query to SQL; this module answers what that SQL
*costs*. It runs the backend's own EXPLAIN, times the statement, counts the
rows that came back, and turns the plan into the handful of findings worth
acting on -- a sequential scan over a big table, a row estimate off by an
order of magnitude, blocks read from disk, or (on SQLite) a filter that fell
back to a table scan instead of an index.

Nothing is written. EXPLAIN ANALYZE executes the statement, so every profile
runs inside a transaction that is rolled back, and analytics statements are
read-only SELECTs by construction.

The plan of a query that scans a million rows is the only honest answer to
"do the analytics indexes (#304) help?", which is why this is the tool the
index catalogue and the cache are justified with (``docs/analytics-performance.md``).
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .analytics_query import Query, compile_query

# Tables where a sequential scan is worth flagging. The small lookup tables
# (Gametypes, Sites, Actions) are supposed to be scanned.
BIG_TABLES: Final = ("handsactions", "handssituations", "handsplayers", "hands", "boardfeatures", "players")

# How far a row estimate may be out before the plan is worth distrusting.
ESTIMATE_TOLERANCE: Final = 10

# The backends the profiler knows how to explain, by Database backend constant.
_BACKEND_NAMES: Final = {2: "mysql", 3: "postgresql", 4: "sqlite"}


@dataclass(frozen=True)
class QueryProfile:
    """One query's SQL, cost and the findings worth acting on."""

    name: str
    metric: str
    backend: str
    sql: str
    params: tuple[Any, ...]
    duration_ms: float
    rows_returned: int
    rows_scanned: int | None
    plan: tuple[str, ...]
    findings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metric": self.metric,
            "backend": self.backend,
            "sql": self.sql,
            "params": list(self.params),
            "duration_ms": round(self.duration_ms, 3),
            "rows_returned": self.rows_returned,
            "rows_scanned": self.rows_scanned,
            "plan": list(self.plan),
            "findings": list(self.findings),
        }


def backend_name(db: Any) -> str:
    """The Database backend constant as the profiler's name."""
    backend = getattr(db, "backend", None)
    return _BACKEND_NAMES[backend] if isinstance(backend, int) and backend in _BACKEND_NAMES else "mysql"


def placeholder(db: Any) -> str:
    """The connection's bind-marker style."""
    try:
        return str(db.sql.query["placeholder"])
    except (AttributeError, KeyError):
        return "%s"


def explain_statement(db: Any, sql: str, params: Sequence[Any] = ()) -> tuple[str, ...]:
    """The backend's plan for one statement, as text lines.

    SQLite answers with ``EXPLAIN QUERY PLAN``; PostgreSQL with
    ``EXPLAIN (ANALYZE, BUFFERS)`` so the plan carries the actual timings and
    buffer counts; MySQL with a plain ``EXPLAIN``.
    """
    backend = backend_name(db)
    cursor = db.get_cursor()
    if backend == "sqlite":
        cursor.execute("EXPLAIN QUERY PLAN " + sql, tuple(params))  # nosec B608  # nosemgrep
        return tuple(" ".join(str(part) for part in row) for row in cursor.fetchall())
    if backend == "postgresql":
        cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, tuple(params))  # nosec B608  # nosemgrep
        return tuple(str(row[0]) for row in cursor.fetchall())
    cursor.execute("EXPLAIN " + sql, tuple(params))  # nosec B608  # nosemgrep
    columns = [description[0] for description in cursor.description or ()]
    return tuple(", ".join(f"{name}={value}" for name, value in zip(columns, row, strict=False)) for row in cursor.fetchall())


def _pg_rows_scanned(plan: Sequence[str]) -> int | None:
    """The largest actual row count in a PostgreSQL plan, as a scan proxy."""
    counts = [int(match) for line in plan for match in re.findall(r"actual time=[\d.]+\.\.[\d.]+ rows=(\d+)", line)]
    return max(counts) if counts else None


def _sqlite_rows_scanned(plan: Sequence[str]) -> int | None:
    """SQLite's plan does not carry row counts; it is honest about that."""
    return None


def analyze_plan(backend: str, plan: Sequence[str]) -> tuple[int | None, list[str]]:
    """The rows scanned (where the backend reports it) and the findings."""
    if backend == "sqlite":
        return _analyze_sqlite(plan)
    return _analyze_postgres(plan)


def _analyze_sqlite(plan: Sequence[str]) -> tuple[int | None, list[str]]:
    """SQLite says which step used an index and which did not; it says no row counts."""
    findings: list[str] = []
    for line in plan:
        lowered = line.lower()
        if "using index" in lowered or "using covering index" in lowered:
            findings.append(f"index used: {line}")
        elif "scan " in lowered and lowered.split("scan ", 1)[1].split()[0] in BIG_TABLES:
            findings.append(f"table scan over {lowered.split('scan ', 1)[1].split()[0]}: {line}")
    return _sqlite_rows_scanned(plan), findings


def _analyze_postgres(plan: Sequence[str]) -> tuple[int | None, list[str]]:
    """PostgreSQL reports actual rows and buffers; flag what usually matters."""
    findings: list[str] = []
    for line in plan:
        lowered = line.lower()
        if "seq scan on" in lowered:
            table = lowered.split("seq scan on", 1)[1].strip().split()[0]
            if table in BIG_TABLES:
                findings.append(f"sequential scan over {table}: {line.strip()}")
        estimate = re.search(r"rows=(\d+).*?rows=(\d+)", line)
        if estimate and "actual" in lowered:
            expected, actual = int(estimate.group(1)), int(estimate.group(2))
            worse = max(max(expected, actual), 1)
            better = max(min(expected, actual), 1)
            if worse / better > ESTIMATE_TOLERANCE:
                findings.append(f"row estimate off by {worse // better}x: {line.strip()}")
        read = re.search(r"Buffers:.*read=(\d+)", line)
        if read and int(read.group(1)) > 0:
            findings.append(f"{read.group(1)} blocks read from disk: {line.strip()}")
    return _pg_rows_scanned(plan), findings


def profile_analytics_query(db: Any, query: Query, name: str = "") -> QueryProfile:
    """Compile, explain, time and count one analytics query.

    The transaction is rolled back before returning: profiling must not leave
    anything behind, and ``EXPLAIN ANALYZE`` does execute the statement.
    """
    backend = backend_name(db)
    compiled = compile_query(query, placeholder(db), backend)
    try:
        plan = explain_statement(db, compiled.sql, compiled.params)
    except Exception:  # noqa: BLE001 - a backend that cannot EXPLAIN is not a failure
        plan = ()
    rows_scanned, findings = analyze_plan(backend, plan)

    cursor = db.get_cursor()
    started = time.perf_counter()
    cursor.execute(compiled.sql, compiled.params)
    rows = cursor.fetchall()
    duration_ms = (time.perf_counter() - started) * 1000.0
    try:
        db.rollback(force=True)
    except Exception:  # noqa: BLE001 - rollback is best-effort bookkeeping
        pass

    return QueryProfile(
        name=name or compiled.metric,
        metric=query.metric,
        backend=backend,
        sql=compiled.sql,
        params=tuple(compiled.params),
        duration_ms=duration_ms,
        rows_returned=len(rows),
        rows_scanned=rows_scanned,
        plan=tuple(plan),
        findings=tuple(findings),
    )


def profile_definitions(db: Any, definitions: Iterable[Any]) -> list[QueryProfile]:
    """Profile every definition's query, for the plan report."""
    from .analytics_definitions import resolve_query  # noqa: PLC0415 - avoid a cycle at import time

    return [profile_analytics_query(db, resolve_query(definition), name=definition.name) for definition in definitions]


def format_profiles(profiles: Sequence[QueryProfile], plans: bool = False) -> str:
    """A readable report: one block per query, findings under it."""
    lines: list[str] = []
    for profile in profiles:
        scanned = "-" if profile.rows_scanned is None else str(profile.rows_scanned)
        lines.append(
            f"--- {profile.name} [{profile.metric}] backend={profile.backend}"
            f" time={profile.duration_ms:.2f}ms rows_returned={profile.rows_returned} rows_scanned={scanned}",
        )
        if plans:
            for line in profile.plan:
                lines.append(f"    {line}")
        for finding in profile.findings:
            lines.append(f"  ! {finding}")
        if not profile.findings:
            lines.append("  nothing to flag")
    return "\n".join(lines)


__all__ = [
    "BIG_TABLES",
    "ESTIMATE_TOLERANCE",
    "QueryProfile",
    "analyze_plan",
    "backend_name",
    "explain_statement",
    "format_profiles",
    "placeholder",
    "profile_analytics_query",
    "profile_definitions",
]
