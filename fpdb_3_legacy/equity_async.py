"""Bounded background execution for optional poker-equity analyses."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Fallback StrEnum for Python < 3.11."""

        def __str__(self) -> str:
            return str(self.value)

from queue import Full, Queue
from threading import Lock, Thread
from typing import Any, Generic, TypeVar, cast

from fpdb_3_legacy.equity import EquityEngine, EquityUnavailableError
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("equity")

_STOP = object()
AnalysisResult = TypeVar("AnalysisResult")


@dataclass(frozen=True)
class EquityAnalysisJob(Generic[AnalysisResult]):
    """One calculation and its isolated persistence/notification callbacks.

    ``persist`` runs on the worker thread after the calculation. It must own
    its database connection and transaction; sharing the live import
    connection across threads is deliberately outside this contract.
    """

    key: Hashable
    evaluate: Callable[[EquityEngine], AnalysisResult]
    persist: Callable[[AnalysisResult], None]
    notify: Callable[[AnalysisResult], None] | None = None


class EquitySubmission(StrEnum):
    """Outcome of a non-blocking queue submission."""

    QUEUED = "queued"
    DUPLICATE = "duplicate"
    FULL = "full"
    CLOSED = "closed"


class AsyncEquityService:
    """Run equity jobs away from import, capture and Qt threads."""

    def __init__(
        self,
        engine: EquityEngine | None = None,
        *,
        max_queue: int = 64,
        thread_name: str = "fpdb-equity",
    ) -> None:
        if max_queue <= 0:
            msg = "max_queue must be positive"
            raise ValueError(msg)
        self.engine = engine or EquityEngine()
        self._queue: Queue[EquityAnalysisJob[Any] | object] = Queue(maxsize=max_queue)
        self._pending: set[Hashable] = set()
        self._lock = Lock()
        self._closed = False
        self._thread = Thread(target=self._run, name=thread_name, daemon=True)
        self._thread.start()

    @property
    def pending(self) -> int:
        """Number of queued or currently running distinct jobs."""
        with self._lock:
            return len(self._pending)

    def submit(self, job: EquityAnalysisJob[Any]) -> EquitySubmission:
        """Queue without blocking the caller, deduplicating by stable key."""
        with self._lock:
            if self._closed:
                return EquitySubmission.CLOSED
            if job.key in self._pending:
                return EquitySubmission.DUPLICATE
            self._pending.add(job.key)
        try:
            self._queue.put_nowait(job)
        except Full:
            with self._lock:
                self._pending.discard(job.key)
            return EquitySubmission.FULL
        return EquitySubmission.QUEUED

    def close(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        """Stop accepting jobs and ask the daemon worker to finish its queue."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._queue.put(_STOP, timeout=timeout)
        except Full:
            log.warning("equity worker queue did not accept its stop marker")
            return
        if wait:
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("equity worker did not stop within %.1f seconds", timeout)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                return
            job = cast(EquityAnalysisJob[Any], item)
            try:
                result = job.evaluate(self.engine)
                job.persist(result)
            except EquityUnavailableError:
                # EquityEngine emits the single actionable backend warning.
                pass
            except Exception:
                log.exception("equity analysis %r failed", job.key)
            else:
                self._notify(job, result)
            finally:
                with self._lock:
                    self._pending.discard(job.key)
                self._queue.task_done()

    @staticmethod
    def _notify(job: EquityAnalysisJob[Any], result: Any) -> None:
        if job.notify is None:
            return
        try:
            job.notify(result)
        except Exception:
            # A completed, persisted analysis must not be marked failed merely
            # because a UI wake-up could not be delivered.
            log.exception("equity analysis %r was stored but its notification failed", job.key)

    def __enter__(self) -> AsyncEquityService:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
