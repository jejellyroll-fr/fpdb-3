"""Local-first outbox reconciliation (#684).

A hand reaches the server only if it has an outbox row. Two ways a stored hand
used to miss one:

* a crash between the import's commit and its mark;
* a hand stored outside ``Importer`` -- the HTTP and SwC captures write to the
  same local database but never mark.

The worker now gives an outbox row to every local hand stored since the outbox
began: in full when it starts, then over the recent hands every few polls.
Hands stored before local-first was turned on are never pushed by surprise.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import local_first_sync
from fpdb_3_legacy.local_first_sync import LocalFirstSync


@pytest.fixture
def start(tmp_path):
    """Open the local database holding ``before`` hands, then start its worker."""
    path = tmp_path / "local.sqlite3"
    opened: list[SimpleNamespace] = []

    def _start(*before: int) -> SimpleNamespace:
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE IF NOT EXISTS Hands (id INTEGER PRIMARY KEY)")
        connection.executemany("INSERT INTO Hands (id) VALUES (?)", [(h,) for h in before])
        connection.commit()
        sync = LocalFirstSync(SimpleNamespace(backend=4), MagicMock(), local_db_path=str(path))
        local = SimpleNamespace(sync=sync, connection=connection)
        opened.append(local)
        return local

    yield _start
    for local in opened:
        local.sync.stop()
        local.connection.close()


@pytest.fixture
def local(start):
    return start()


def _store(local, *hand_ids: int) -> None:
    local.connection.executemany("INSERT INTO Hands (id) VALUES (?)", [(h,) for h in hand_ids])
    local.connection.commit()


def _outbox(local) -> list[int]:
    rows = local.sync._own_conn.execute("SELECT local_hand_id FROM fpdb_sync_outbox ORDER BY local_hand_id")
    return [row[0] for row in rows.fetchall()]


def test_a_hand_lost_to_a_crash_between_commit_and_mark_is_queued(local) -> None:
    _store(local, 1, 2, 3, 4, 5)
    local.sync.mark([1, 2, 4, 5])  # 3 committed, then the process died before its mark

    assert local.sync.reconcile() == 1
    assert _outbox(local) == [1, 2, 3, 4, 5]


def test_hands_from_before_local_first_are_not_pushed_by_surprise(start) -> None:
    local = start(*range(1, 11))  # a local database used on its own before

    assert local.sync.reconcile() == 0
    assert _outbox(local) == []


def test_a_capture_stored_hand_is_queued_by_the_next_pass(start) -> None:
    local = start(*range(1, 11))
    local.sync.reconcile()
    _store(local, 11)
    local.sync.mark([11])  # imported
    _store(local, 12, 13)  # written by a capture, no mark

    assert local.sync.reconcile() == 2
    assert _outbox(local) == [11, 12, 13]


def test_a_late_commit_below_the_newest_hand_is_still_found(local) -> None:
    _store(local, 1)
    local.sync.mark([1])
    local.sync.reconcile()
    _store(local, *range(2, 50))
    local.sync.mark(list(range(2, 50)))
    local.sync.reconcile()  # saw 49 as the newest
    local.connection.execute("DELETE FROM Hands WHERE id = 30")
    local.connection.commit()
    local.sync._own_conn.execute("DELETE FROM fpdb_sync_outbox WHERE local_hand_id = 30")
    local.sync._own_conn.commit()
    _store(local, 30)  # an older transaction commits its hand only now

    assert local.sync.reconcile() == 1
    assert 30 in _outbox(local)


def test_the_margin_never_reaches_below_the_first_floor(start, monkeypatch) -> None:
    monkeypatch.setattr(local_first_sync, "RECONCILE_MARGIN", 1000)
    local = start(*range(1, 6))  # before local-first
    local.sync.reconcile()
    _store(local, 6)

    assert local.sync.reconcile() == 1
    assert _outbox(local) == [6]


def test_a_first_hand_lost_to_a_crash_survives_a_restart(start) -> None:
    first = start(*range(1, 6))  # before local-first, empty outbox
    _store(first, 6)  # the first import commits, then the process dies
    first.sync.stop()

    again = start()

    assert again.sync.reconcile() == 1
    assert _outbox(again) == [6]


def test_the_floor_is_kept_from_one_worker_to_the_next(start) -> None:
    first = start(*range(1, 6))
    first.sync.stop()
    _store(first, 6, 7)  # captures write while no worker runs

    again = start()

    assert again.sync.reconcile() == 2
    assert _outbox(again) == [6, 7]


def test_a_database_without_hands_yet_is_left_alone(tmp_path) -> None:
    sync = LocalFirstSync(SimpleNamespace(backend=4), MagicMock(), local_db_path=str(tmp_path / "empty.sqlite3"))
    try:
        assert sync.reconcile() == 0
    finally:
        sync.stop()


def test_the_worker_reconciles_before_its_first_push(local, monkeypatch) -> None:
    _store(local, 1, 2)
    local.sync.mark([1])
    local.sync.reconcile()  # floor set by an earlier pass
    _store(local, 3)
    seen: list[list[int]] = []

    def push_once() -> int:
        seen.append(_outbox(local))
        local.sync._stop.set()
        return 0

    monkeypatch.setattr(local.sync, "push_once", push_once)
    local.sync._loop()

    assert seen == [[1, 2, 3]]
