"""A burst of new hands must cost one database read, not one per hand (#680).

When several tables report a new hand while a batch read is still waiting in
HudReadWorker's queue, the newer batches are folded into the waiting one: the
worker runs the merged request (union of hands and tables, highest sequence)
instead of executing each queued batch in turn and having the GUI discard all
but the last answer.
"""

from __future__ import annotations

import threading
from queue import Queue

from fpdb_3_legacy import HUD_main  # pylint: disable=no-name-in-module
from fpdb_3_legacy.hud_read_service import HudBatchReadRequest, HudTableReadContext
from fpdb_3_legacy.hud_workers import _merge_batch_requests

HudReadWorker = HUD_main.HudReadWorker


def _worker() -> HudReadWorker:
    worker = HudReadWorker.__new__(HudReadWorker)
    worker._requests = Queue()
    worker._latest_fast_fold = {}
    worker._latest_lock = threading.Lock()
    worker._pending_batch = None
    worker._batch_lock = threading.Lock()
    return worker


def _context(temp_key: str, last_hand_id: str) -> HudTableReadContext:
    return HudTableReadContext(
        temp_key=temp_key,
        last_hand_id=last_hand_id,
        hud_params={"hud_days": 30},
        poker_game="holdem",
        game_type="ring",
        site_id=1,
        num_seats=6,
    )


def _batch(sequence: int, hand_ids: tuple[str, ...], tables: tuple[HudTableReadContext, ...]) -> HudBatchReadRequest:
    return HudBatchReadRequest(sequence=sequence, hand_ids=hand_ids, hud_params={"hud_days": 30}, tables=tables)


def test_a_second_batch_is_folded_into_the_waiting_one_instead_of_queued() -> None:
    worker = _worker()
    first = _batch(1, ("101",), (_context("table-a", "100"),))
    second = _batch(2, ("102",), (_context("table-a", "101"), _context("table-b", "201")))

    worker.submit(first)
    worker.submit(second)

    # Only the first batch entered the queue; the second lives in the merged one.
    assert worker._requests.qsize() == 1
    merged = worker._pending_batch
    assert merged is not None
    assert merged.sequence == 2
    assert merged.hand_ids == ("101", "102")
    assert {context.temp_key for context in merged.tables} == {"table-a", "table-b"}
    # The newer context wins for a shared table.
    assert next(c for c in merged.tables if c.temp_key == "table-a").last_hand_id == "101"


def test_draining_the_queued_batch_runs_the_merged_version() -> None:
    worker = _worker()
    first = _batch(1, ("101",), (_context("table-a", "100"),))
    second = _batch(2, ("102",), (_context("table-b", "201"),))
    worker.submit(first)
    worker.submit(second)

    queued = worker._requests.get_nowait()
    resolved = worker._resolve_pending_batch(queued)

    assert resolved.sequence == 2
    assert resolved.hand_ids == ("101", "102")
    # The pending slot is consumed, so the next batch starts a fresh queue entry.
    assert worker._pending_batch is None


def test_a_lone_batch_resolves_to_itself() -> None:
    worker = _worker()
    only = _batch(7, ("101",), ())
    worker.submit(only)
    assert worker._requests.qsize() == 1
    resolved = worker._resolve_pending_batch(worker._requests.get_nowait())
    assert resolved is only


def test_merge_keeps_every_hand_and_table_of_both_batches() -> None:
    older = _batch(3, ("1", "2"), (_context("a", "1"),))
    newer = _batch(9, ("2", "3"), (_context("b", "2"),))
    merged = _merge_batch_requests(older, newer)
    assert merged.hand_ids == ("1", "2", "3")
    assert merged.sequence == 9
    assert {c.temp_key for c in merged.tables} == {"a", "b"}


def test_fast_fold_requests_do_not_touch_the_batch_coalescing() -> None:
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest

    worker = _worker()
    worker.submit(FastFoldStatsRequest(temp_key="t", request_id=1))
    worker.submit(FastFoldStatsRequest(temp_key="t", request_id=2))
    assert worker._requests.qsize() == 2
    assert worker._pending_batch is None
