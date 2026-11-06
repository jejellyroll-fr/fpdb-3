"""Compute a bulk import's exact all-in equities ahead of it, in worker processes (#443).

Most of a bulk import's time goes to one thing: the exact equity of each all-in
(an exhaustive poker_eval enumeration, up to half a second for a preflop Omaha
all-in). Parsing is a tenth of it. The import itself stays sequential, with a
single writer, exactly as before; worker processes parse the files ahead of it
and derive their hands, which computes those equities, and hand the results
back. When the import reaches a hand, its equity is already known.

Exhaustive enumeration is deterministic, so the database is the same whether a
result came from a worker or not. A result the workers did not get to is
computed by the import as before: the workers can only save time.

Workers load a copy of the configuration written to a private temporary
directory, never the user's file: building a configuration may migrate and
save it.
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import os
import tempfile
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fpdb_3_legacy import equity
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("import_prefetch")

AUTO = -1
# Beyond four, start-up and memory (each worker loads the parsers and the
# configuration) cost more than they save on the benchmark corpus.
MAX_AUTO_WORKERS = 4


@dataclass(frozen=True)
class PrefetchJob:
    """What a worker needs to parse one file the way the importer does."""

    path: str
    filter_name: str
    sitename: str
    archive: bool
    # Its place in the import, set on submission.
    order: int = 0


def worker_count(threads: int | None) -> int:
    """Workers for the ``threads`` import setting: 1 is none, AUTO every core but one, up to four."""
    if threads is None:
        return 0
    if threads in (AUTO, 0):
        return min(MAX_AUTO_WORKERS, max(0, (os.cpu_count() or 1) - 1))
    return threads if threads > 1 else 0


_worker_config: Any = None
# The place of the file the import has reached; a worker skips any file up to it.
_worker_reached: Any = None


class _PlaceholderIds:
    """Stands in for the database in Hand.prepInsert, which the derivation needs run first.

    The derived rows are keyed by database ids; the ids handed out here are
    placeholders, which do not change any equity and are never written.
    """

    def getSqlPlayerIDs(self, names: list[str], _site_id: int, _hero: str) -> dict[str, int]:  # noqa: N802 - Database's name
        return {name: number for number, name in enumerate(names, 1)}

    def getSqlGameTypeId(self, *_args: Any, **_kwargs: Any) -> int:  # noqa: N802 - Database's name
        return 1

    def getSqlTourneyTypeIDs(self, _hand: Any) -> int:  # noqa: N802 - Database's name
        return 1

    def getSqlTourneyIDs(self, _hand: Any) -> int:  # noqa: N802 - Database's name
        return 1

    def getSqlTourneysPlayersIDs(self, _hand: Any) -> dict[Any, int]:  # noqa: N802 - Database's name
        return {}


def _start_worker(config_file: str, reached: Any = None) -> None:
    global _worker_config, _worker_reached
    _worker_reached = reached
    logging.disable(logging.CRITICAL)
    from fpdb_3_legacy.Configuration import Config

    _worker_config = Config(file=config_file)


def exact_equities(job: PrefetchJob) -> dict[equity.ExactKey, equity.EquityResult]:
    """Parse and derive one file; return the exact equities that computed. Never raises.

    A file the import has already reached is skipped: the import computes it
    itself, and the worker moves on to the files ahead of it.
    """
    if _worker_reached is not None and job.order <= _worker_reached.value:
        return {}
    try:
        from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path
        from fpdb_3_legacy.parser_registry import get_parser_class

        parser = (
            get_parser_class_for_path(job.path) if job.filter_name == "iPoker" else get_parser_class(job.filter_name)
        )
        converter = parser(
            _worker_config,
            in_path=job.path,
            index=0,
            autostart=False,
            starsArchive=job.archive,
            ftpArchive=job.archive,
            sitename=job.sitename,
        )
        converter.setAutoPop(False)
        with equity.recording_exact() as recorded:
            converter.start()
            ids = _PlaceholderIds()
            for hand in converter.getProcessedHands():
                # A hand that fails here fails in the import too, which reports it.
                with contextlib.suppress(Exception):
                    hand.prepInsert(ids)
                    hand.assembleHand()
        return dict(recorded)
    except Exception:  # noqa: BLE001 - a worker that fails only means the import computes the equities itself
        return {}


class EquityPrefetch:
    """Worker processes running ahead of a sequential bulk import."""

    def __init__(self, config: Any, workers: int) -> None:
        self._directory = tempfile.TemporaryDirectory(prefix="fpdb-import-")
        config_file = Path(self._directory.name) / "HUD_config.xml"
        config_file.write_text(config.doc.toxml(), encoding="utf-8")
        context = multiprocessing.get_context("spawn")
        self._reached = context.Value("i", -1)
        self._order: dict[str, int] = {}
        self._pool = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_start_worker,
            initargs=(str(config_file), self._reached),
        )
        self._futures: dict[str, Future[dict[equity.ExactKey, equity.EquityResult]]] = {}

    def submit(self, jobs: list[PrefetchJob]) -> None:
        for job in jobs:
            order = len(self._order)
            self._order[job.path] = order
            self._futures[job.path] = self._pool.submit(exact_equities, replace(job, order=order))

    def before_import(self, path: str) -> None:
        """Make the file's equities available if a worker has finished it; never wait.

        A file not finished yet is left to the import, which computes its
        equities as before. Waiting would rarely pay: the import parses and
        derives the file again anyway, so for a file without an expensive
        all-in the wait is pure loss, and the pool cannot even tell a job a
        worker is on from one merely queued. Workers skip every file up to
        this one from now on.
        """
        future = self._futures.pop(path, None)
        if future is None:
            return
        self._reached.value = self._order[path]
        if not future.done():
            future.cancel()
            return
        if future.cancelled() or future.exception() is not None:
            log.debug("Equity prefetch for %s failed", path, exc_info=future.exception())
            return
        equity.remember_exact(future.result())

    def close(self) -> None:
        """Stop the workers without waiting for them to exit.

        Every file has been reached by now, so a job still queued only skips:
        no equity is computed after the import is over, and waiting for the
        processes to end would only delay the import's result.
        """
        self._reached.value = len(self._order)
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._futures.clear()
        equity.forget_exact()
        self._directory.cleanup()
