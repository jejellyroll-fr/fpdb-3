"""Latency instrumentation for the live HUD and auto-import path (#680).

Round trips alone do not explain a multi-second freeze: a query that runs in
200us locally can cost one network latency per statement from a LAN database,
and a slow query can cost ten seconds. What the issue asks for is the shape of
the tail, so every metric here is a series of durations (or a counter) reported
as count / mean / p50 / p95 / p99 / max -- averages hide exactly the pauses the
reporter describes.

Off unless ``FPDB_LATENCY_PROFILE=1`` is set in the environment. When on:

* ``FPDB_LATENCY_REPORT=/path/to/report.json`` writes a JSON snapshot on exit
  (registered with ``atexit``) and on demand via :func:`write_report`;
* ``FPDB_LATENCY_LOG_INTERVAL=60`` logs a text report every N seconds when the
  metrics have moved since the last report.

Metric names used across the live path:

* ``hud_queue_wait``      -- time a HUD batch spent in the worker's queue;
* ``hud_batch_total``     -- one full batch read on the worker thread;
* ``hud_batch_resolve_primary`` / ``hud_batch_primary`` / ``hud_batch_secondary``
                          -- the phases of one batch;
* ``hud_query_execute``   -- driver-side execute() only;
* ``hud_query_fetch``     -- fetchall()/fetchone() loop only;
* ``hud_python_aggregate``-- turning fetched rows into stat_dict in Python;
* ``hud_session_rows``    -- counter: rows returned by the session stats path;
* ``hud_analytics_compute`` -- analytics-backed HUD cells;
* ``hud_snapshot_apply``  -- applying a snapshot on the Qt thread;
* ``hudcache_lookup`` / ``hudcache_update`` / ``hudcache_insert`` -- counters of
  the HudCache write path, plus ``hudcache_write`` for its wall time;
* ``db_txn_total`` / ``db_commit`` -- import transaction duration and the commit
  alone.

Recording is a no-op (one cached env lookup) when the profile is off, so the
live path pays nothing in the default configuration.
"""

from __future__ import annotations

import atexit
import json
import os
import random
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("latency_profile")

ENV_FLAG = "FPDB_LATENCY_PROFILE"
REPORT_PATH_ENV = "FPDB_LATENCY_REPORT"
LOG_INTERVAL_ENV = "FPDB_LATENCY_LOG_INTERVAL"

# Above this many samples per metric the series switches to reservoir sampling:
# percentiles stay meaningful without growing memory for the whole session.
MAX_EXACT_SAMPLES = 100_000

_ENABLED: bool | None = None


def is_enabled() -> bool:
    """Report whether latency profiling was switched on for this process."""
    global _ENABLED
    if _ENABLED is None:
        _ENABLED = os.getenv(ENV_FLAG, "") == "1"
    return _ENABLED


def _percentile(sorted_samples: list[float], q: float) -> float:
    """Linear-interpolation percentile of an already sorted sample list."""
    if not sorted_samples:
        return 0.0
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    rank = q * (len(sorted_samples) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_samples) - 1)
    fraction = rank - low
    return sorted_samples[low] * (1 - fraction) + sorted_samples[high] * fraction


class LatencyProfile:
    """Thread-safe duration series and counters for one process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._durations: dict[str, list[float]] = {}
        self._reservoir_seen: dict[str, int] = {}
        self._counts: dict[str, int] = {}

    # -- recording --------------------------------------------------------

    def record(self, name: str, seconds: float) -> None:
        """Add one duration sample to ``name``."""
        with self._lock:
            samples = self._durations.get(name)
            if samples is None:
                self._durations[name] = [seconds]
                self._reservoir_seen[name] = 1
                return
            seen = self._reservoir_seen.get(name, len(samples)) + 1
            self._reservoir_seen[name] = seen
            if len(samples) < MAX_EXACT_SAMPLES:
                samples.append(seconds)
            else:
                # Reservoir sampling: every sample past the cap has the same
                # chance of replacing one already kept, so percentiles remain
                # unbiased for arbitrarily long sessions.
                index = random.randrange(seen)
                if index < MAX_EXACT_SAMPLES:
                    samples[index] = seconds

    def count(self, name: str, amount: int = 1) -> None:
        """Add ``amount`` to the counter ``name`` (rows, cache ops, ...)."""
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + amount

    @contextmanager
    def scope(self, name: str) -> Iterator[None]:
        """Record the wall time of the block under ``name``."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, time.perf_counter() - started)

    def reset(self) -> None:
        """Forget everything recorded so far."""
        with self._lock:
            self._durations.clear()
            self._reservoir_seen.clear()
            self._counts.clear()

    # -- reporting --------------------------------------------------------

    def metric_stats(self, name: str) -> dict[str, Any]:
        """count/counter/mean/p50/p95/p99/max for one metric, durations in seconds."""
        with self._lock:
            samples = sorted(self._durations.get(name, ()))
            counter = self._counts.get(name, 0)
        if not samples:
            return {"count": 0, "counter": counter, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
        return {
            "count": len(samples),
            "counter": counter,
            "mean": sum(samples) / len(samples),
            "p50": _percentile(samples, 0.50),
            "p95": _percentile(samples, 0.95),
            "p99": _percentile(samples, 0.99),
            "max": samples[-1],
        }

    def snapshot(self) -> dict[str, Any]:
        """Every metric as JSON-ready data."""
        with self._lock:
            names = sorted(set(self._durations) | set(self._counts))
        return {
            "recorded_at": time.time(),
            "metrics": {name: self.metric_stats(name) for name in names},
        }

    def report(self, top: int = 30) -> str:
        """Render the metrics as a block of text for the log, worst tail first."""
        metrics = self.snapshot()["metrics"]
        if not metrics:
            return "Latency profile: nothing recorded."
        ranked = sorted(metrics.items(), key=lambda kv: -kv[1]["p99"])
        lines = [
            f"Latency profile ({len(metrics)} metric(s)), durations in ms:",
            f"  {'metric':<28}{'n':>8}{'mean':>9}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}",
        ]
        for name, stats in ranked[:top]:
            lines.append(
                f"  {name:<28}{int(stats['count']) or int(stats['counter']):>8}"
                f"{stats['mean'] * 1000:>9.1f}{stats['p50'] * 1000:>9.1f}"
                f"{stats['p95'] * 1000:>9.1f}{stats['p99'] * 1000:>9.1f}{stats['max'] * 1000:>9.1f}",
            )
        counters = {name: stats for name, stats in metrics.items() if stats["count"] == 0 and stats["counter"]}
        if counters:
            lines.append(
                "  counters: "
                + ", ".join(f"{name}={int(stats['counter'])}" for name, stats in sorted(counters.items()))
            )
        return "\n".join(lines)

    def log_report(self, header: str = "") -> None:
        """Write the report to the log, if anything was recorded."""
        with self._lock:
            empty = not self._durations and not self._counts
        if empty:
            return
        log.info("%s%s%s", header, "\n" if header else "", self.report())

    def write_report(self, path: str | None = None) -> str | None:
        """Write the JSON snapshot to ``path`` (default: the env var's path)."""
        path = path or os.getenv(REPORT_PATH_ENV, "")
        if not path:
            return None
        payload = self.snapshot()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return path


class _IntervalReporter:
    """Logs the latency report every ``FPDB_LATENCY_LOG_INTERVAL`` seconds.

    Only when the metrics moved since the last report, so a quiet HUD does not
    spam the log.
    """

    def __init__(self, profile: LatencyProfile) -> None:
        self.profile = profile
        self._lock = threading.Lock()
        self._last_at = 0.0
        self._last_marker = ""

    def maybe_log(self) -> bool:
        """Log the report if the interval elapsed and the metrics moved."""
        if not is_enabled():
            return False
        try:
            seconds = float(os.getenv(LOG_INTERVAL_ENV, "") or 0.0)
        except ValueError:
            seconds = 0.0
        if seconds <= 0:
            return False
        with self._lock:
            now = time.monotonic()
            if now - self._last_at < seconds:
                return False
            self._last_at = now
            with self.profile._lock:
                marker = repr(
                    (
                        {name: len(samples) for name, samples in self.profile._durations.items()},
                        dict(self.profile._counts),
                    )
                )
            if marker == self._last_marker:
                return False
            self._last_marker = marker
        self.profile.log_report("Periodic latency report:")
        return True


_PROFILE = LatencyProfile()
_REPORTER = _IntervalReporter(_PROFILE)


def get_profile() -> LatencyProfile:
    """Return this process's latency profile."""
    return _PROFILE


def record(name: str, seconds: float) -> None:
    """Record one duration, cheaply when profiling is off."""
    if _ENABLED:
        _PROFILE.record(name, seconds)


def count(name: str, amount: int = 1) -> None:
    """Bump one counter, cheaply when profiling is off."""
    if _ENABLED:
        _PROFILE.count(name, amount)


@contextmanager
def scope(name: str) -> Iterator[None]:
    """Record the wall time of the block, cheaply when profiling is off."""
    if not _ENABLED:
        yield
        return
    with _PROFILE.scope(name):
        yield


def maybe_log() -> bool:
    """Emit the periodic log report when the interval has elapsed."""
    return _REPORTER.maybe_log()


def write_report(path: str | None = None) -> str | None:
    """Write the JSON report now, when profiling is on."""
    if not _ENABLED:
        return None
    return _PROFILE.write_report(path)


def _write_report_at_exit() -> None:
    write_report()


if is_enabled():
    atexit.register(_write_report_at_exit)
