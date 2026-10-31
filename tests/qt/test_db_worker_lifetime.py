"""A running DbWorker outlives the tab that drops it (#652).

Session Stats replaced its worker on every refresh and the stats controller
emptied its list; when that was the last reference to a query still running,
Python deleted a QThread mid-run and Qt aborted the process ("QThread:
Destroyed while thread is still running"). A second Refresh during a slow
query closed fpdb.
"""

from __future__ import annotations

import gc
import threading

import pytest

from fpdb_3_legacy.ring_stats.base import DbWorker

pytestmark = pytest.mark.qt


class BlockingCursor:
    """A shared cursor whose query runs until the test lets it finish."""

    description = (("n",),)

    def __init__(self) -> None:
        self.release = threading.Event()

    def execute(self, sql: str) -> None:
        self.release.wait(10)

    def fetchall(self) -> list:
        return [(1,)]


def test_a_running_worker_is_kept_after_its_owner_drops_it(qtbot) -> None:
    cursor = BlockingCursor()
    worker = DbWorker(cursor, "slow", "SELECT 1")
    worker.start()
    worker_id = id(worker)
    del worker  # what a superseded refresh does to the old worker
    gc.collect()

    try:
        assert worker_id in {id(running) for running in DbWorker._started}
    finally:
        cursor.release.set()
    kept = next(running for running in DbWorker._started if id(running) == worker_id)
    qtbot.waitUntil(kept.isFinished, timeout=10_000)


def test_finished_workers_are_let_go_at_the_next_start(qtbot) -> None:
    first_cursor = BlockingCursor()
    first_cursor.release.set()
    first = DbWorker(first_cursor, "fast", "SELECT 1")
    first.start()
    qtbot.waitUntil(first.isFinished, timeout=10_000)

    second_cursor = BlockingCursor()
    second_cursor.release.set()
    second = DbWorker(second_cursor, "next", "SELECT 1")
    second.start()

    assert first not in DbWorker._started
    assert second in DbWorker._started
    qtbot.waitUntil(second.isFinished, timeout=10_000)
