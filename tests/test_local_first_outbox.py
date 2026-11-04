"""The local-first outbox under the importer's and the worker's threads (#680).

The importer marks hands while the worker marks them pushed, on one connection. A
hand whose mark is lost stays local for good: its import has already committed.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.local_first_sync import LocalFirstSync

HANDS = 3000


@pytest.fixture
def sync(tmp_path):
    local_db = SimpleNamespace(backend=4, sql=SimpleNamespace(query={"placeholder": "?"}))
    outbox = LocalFirstSync(local_db, MagicMock(), local_db_path=str(tmp_path / "local.sqlite3"))
    outbox._own_conn.execute("PRAGMA synchronous=OFF")
    yield outbox
    outbox.stop()


def _rows(sync: LocalFirstSync) -> list[tuple[int, int]]:
    cursor = sync._own_conn.execute("SELECT local_hand_id, pushed FROM fpdb_sync_outbox ORDER BY local_hand_id")
    return cursor.fetchall()


def test_marks_survive_the_worker_committing_at_the_same_time(sync) -> None:
    already_queued = list(range(HANDS))
    sync.mark(already_queued)
    newly_imported = range(HANDS, 2 * HANDS)
    errors: list[Exception] = []
    start = threading.Barrier(2)

    def run(action, values) -> None:
        start.wait()
        try:
            for value in values:
                action(value)
        except Exception as error:  # noqa: BLE001 - reported by the assertion below
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(lambda hand: sync.mark([hand]), newly_imported)),
        threading.Thread(target=run, args=(lambda hand: sync._mark_pushed(hand, hand), already_queued)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    rows = _rows(sync)
    assert [hand for hand, _pushed in rows] == list(range(2 * HANDS))
    assert all(pushed == 1 for _hand, pushed in rows[:HANDS])
    assert all(pushed == 0 for _hand, pushed in rows[HANDS:])


def test_a_failed_mark_leaves_nothing_for_the_next_commit(sync) -> None:
    with pytest.raises(OverflowError):
        sync.mark([1, 2**70])  # the first row is written before the second fails

    sync.mark([2])

    assert _rows(sync) == [(2, 0)]
