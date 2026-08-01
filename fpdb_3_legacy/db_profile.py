"""Count database round trips, and attribute them to what asked for them.

Why round trips rather than query time: with the database on the other side of a
VPN, a statement costs one network latency whatever the server does with it. A
query that runs in 200us locally still costs 40ms from a hotel, so the thing that
decides how the HUD feels is *how many* statements it issues per hand and per
table -- a number no CPU-time benchmark reports.

Off unless ``FPDB_DB_PROFILE=1`` is set in the environment. When on, ``Database``
wraps its driver connection in :class:`CountingConnection`, and callers mark the
work they are doing with :meth:`QueryProfile.scope` so the report can say "12
tables, 41 statements" rather than just "41 statements".

    FPDB_DB_PROFILE=1 fpdb

Statements are named after the entry in the SQL catalogue they came from where
one matches, so a report names ``get_hand_1day_ago`` rather than showing 60
characters of SELECT.
"""

from __future__ import annotations

import functools
import os
import re
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db_profile")

ENV_FLAG = "FPDB_DB_PROFILE"

# How much of an unrecognised statement identifies it in the report.
_LABEL_CHARS = 70

# How much of a statement's opening is taken as identifying, for recognising a
# catalogue query that had columns injected into it before being run.
_PREFIX_CHARS = 60

_WHITESPACE = re.compile(r"\s+")


def is_enabled() -> bool:
    """Report whether round-trip profiling was switched on for this process."""
    return os.getenv(ENV_FLAG, "") == "1"


def _normalise(sql: str) -> str:
    """Collapse a statement to a form that survives formatting differences."""
    return _WHITESPACE.sub(" ", sql).strip().lower()


@dataclass
class StatementStats:
    """What one distinct statement cost over the profiled run."""

    calls: int = 0
    seconds: float = 0.0


@dataclass
class ScopeStats:
    """What one kind of work cost, summed over every time it ran."""

    entries: int = 0
    queries: int = 0
    seconds: float = 0.0

    @property
    def queries_per_entry(self) -> float:
        return self.queries / self.entries if self.entries else 0.0


@dataclass
class QueryProfile:
    """Round-trip counters for one process.

    Scopes nest, and a statement is counted against every scope it runs inside,
    so a hand scope inside a batch scope reports the hand's own statements and
    the batch reports the sum -- which is what makes "per hand" and "per batch"
    separately answerable.
    """

    total: StatementStats = field(default_factory=StatementStats)
    by_statement: dict[str, StatementStats] = field(default_factory=lambda: defaultdict(StatementStats))
    by_scope: dict[str, ScopeStats] = field(default_factory=lambda: defaultdict(ScopeStats))
    _names: dict[str, str] = field(default_factory=dict)
    _prefixes: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _local: threading.local = field(default_factory=threading.local)

    # -- setup ------------------------------------------------------------

    def learn_query_names(self, catalogue: dict[str, Any]) -> None:
        """Teach the profile the SQL catalogue, so reports use its names."""
        collisions = set()
        for name, sql in catalogue.items():
            if not isinstance(sql, str) or not sql.strip():
                continue
            normalised = _normalise(sql)
            self._names.setdefault(normalised, name)
            # Some statements are assembled at run time -- the HUD aggregate has
            # extra columns injected into its SELECT list -- so an exact match
            # would lose the name of the one query it matters most to see. The
            # opening of a statement is enough to recognise it, as long as no
            # two catalogue entries share it.
            prefix = normalised[:_PREFIX_CHARS]
            if prefix in self._prefixes and self._prefixes[prefix] != name:
                collisions.add(prefix)
            else:
                self._prefixes[prefix] = name
        for prefix in collisions:
            self._prefixes.pop(prefix, None)

    def label_for(self, sql: str) -> str:
        """Name a statement: its catalogue name, or a readable prefix."""
        normalised = _normalise(sql)
        known = self._names.get(normalised)
        if known is not None:
            return known
        assembled = self._prefixes.get(normalised[:_PREFIX_CHARS])
        if assembled is not None:
            return assembled + " (assembled)"
        if len(normalised) <= _LABEL_CHARS:
            return normalised
        return normalised[:_LABEL_CHARS] + "..."

    # -- recording --------------------------------------------------------

    @property
    def _stack(self) -> list[str]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def record(self, sql: str, seconds: float) -> None:
        """Count one executed statement against the total and open scopes."""
        label = self.label_for(sql)
        with self._lock:
            self.total.calls += 1
            self.total.seconds += seconds
            statement = self.by_statement[label]
            statement.calls += 1
            statement.seconds += seconds
            # A statement belongs to every scope it ran inside, counted once
            # per distinct scope name so a recursive scope cannot inflate it.
            for name in dict.fromkeys(self._stack):
                self.by_scope[name].queries += 1

    @contextmanager
    def scope(self, name: str):
        """Attribute the statements run inside the block to ``name``."""
        stack = self._stack
        stack.append(name)
        started = time.perf_counter()
        try:
            yield
        finally:
            stack.pop()
            elapsed = time.perf_counter() - started
            with self._lock:
                entry = self.by_scope[name]
                entry.entries += 1
                entry.seconds += elapsed

    def reset(self) -> None:
        """Forget everything recorded so far."""
        with self._lock:
            self.total = StatementStats()
            self.by_statement.clear()
            self.by_scope.clear()

    # -- reporting --------------------------------------------------------

    def report(self, top: int = 15) -> str:
        """Render the counters as a block of text for the log."""
        with self._lock:
            total = StatementStats(self.total.calls, self.total.seconds)
            scopes = sorted(self.by_scope.items(), key=lambda kv: -kv[1].queries)
            statements = sorted(self.by_statement.items(), key=lambda kv: -kv[1].calls)[:top]

        if not total.calls:
            return "Database round trips: none recorded."

        lines = [
            f"Database round trips: {total.calls} statements, {total.seconds * 1000:.0f}ms in the driver.",
        ]
        if scopes:
            lines.append(f"  {'scope':<28}{'runs':>7}{'queries':>9}{'per run':>10}{'wall ms':>10}")
            for name, stats in scopes:
                lines.append(
                    f"  {name:<28}{stats.entries:>7}{stats.queries:>9}"
                    f"{stats.queries_per_entry:>10.1f}{stats.seconds * 1000:>10.0f}",
                )
        lines.append(f"  {'statement':<28}{'calls':>7}{'':>9}{'':>10}{'db ms':>10}")
        for label, stats in statements:
            shown = label if len(label) <= 28 else label[:25] + "..."
            lines.append(f"  {shown:<28}{stats.calls:>7}{'':>9}{'':>10}{stats.seconds * 1000:>10.0f}")
        return "\n".join(lines)

    def log_report(self, header: str = "") -> None:
        """Write the report to the log, if anything was recorded."""
        if not self.total.calls:
            return
        log.info("%s%s%s", header, "\n" if header else "", self.report())


class DeltaReporter:
    """Logs the profile only when statements have been recorded since last time.

    A loop that runs every few seconds would otherwise repeat an unchanged
    report until the log is useless.
    """

    def __init__(self, header: str, profile: QueryProfile | None = None) -> None:
        self.header = header
        self.profile = profile if profile is not None else get_profile()
        self._seen = 0

    def maybe_log(self) -> bool:
        """Log the report if it has moved. Returns whether it did."""
        if not is_enabled():
            return False
        calls = self.profile.total.calls
        if calls == self._seen:
            return False
        self._seen = calls
        self.profile.log_report(self.header)
        return True


# One profile per process; the HUD and the importer are separate processes and
# each answers a different question, so there is nothing to merge.
_PROFILE = QueryProfile()


def get_profile() -> QueryProfile:
    """Return this process's profile."""
    return _PROFILE


@contextmanager
def scope(name: str):
    """Attribute statements to ``name``, cheaply when profiling is off."""
    if not is_enabled():
        yield
        return
    with _PROFILE.scope(name):
        yield


def scoped(name: str):
    """Method decorator form of :func:`scope`.

    Preferred over wrapping a method body in a ``with`` block: it leaves the
    body untouched, so the profiling does not show up as a re-indentation of
    code that has nothing to do with it.
    """

    def decorate(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not is_enabled():
                return func(*args, **kwargs)
            with _PROFILE.scope(name):
                return func(*args, **kwargs)

        return wrapper

    return decorate


class CountingCursor:
    """Delegates to a driver cursor, timing and counting what it executes."""

    __slots__ = ("_cursor", "_profile")

    def __init__(self, cursor: Any, profile: QueryProfile) -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_profile", profile)

    def execute(self, sql, *args, **kwargs):
        started = time.perf_counter()
        try:
            return self._cursor.execute(sql, *args, **kwargs)
        finally:
            # Recorded even when the statement raises: a failed round trip
            # still cost a round trip, and hiding it would flatter the report.
            self._profile.record(str(sql), time.perf_counter() - started)

    def executemany(self, sql, *args, **kwargs):
        started = time.perf_counter()
        try:
            return self._cursor.executemany(sql, *args, **kwargs)
        finally:
            self._profile.record(str(sql), time.perf_counter() - started)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._cursor.__exit__(*exc_info)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._cursor, name, value)


class CountingConnection:
    """Delegates to a driver connection, handing out counting cursors.

    Everything except ``cursor()`` passes straight through, including attribute
    writes -- the dialects toggle ``autocommit`` on the connection, and that has
    to reach the real one.
    """

    __slots__ = ("_connection", "_profile")

    def __init__(self, connection: Any, profile: QueryProfile) -> None:
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_profile", profile)

    def cursor(self, *args, **kwargs):
        return CountingCursor(self._connection.cursor(*args, **kwargs), self._profile)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._connection.__exit__(*exc_info)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._connection, name, value)


def wrap_connection(connection: Any, catalogue: dict[str, Any] | None = None) -> Any:
    """Return ``connection`` counted, or unchanged when profiling is off."""
    if not is_enabled() or connection is None:
        return connection
    if catalogue:
        _PROFILE.learn_query_names(catalogue)
    if isinstance(connection, CountingConnection):
        return connection
    log.info("Database round-trip profiling is on (%s=1)", ENV_FLAG)
    return CountingConnection(connection, _PROFILE)
