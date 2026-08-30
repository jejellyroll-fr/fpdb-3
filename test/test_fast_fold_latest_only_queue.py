"""A superseded seat map must be dropped before the database reads for it.

The client log names a player at a time, so several reads for one table can be
waiting at once and every one but the last describes a table that has already
changed. They were executed in full and discarded on arrival by request id: the
database did the work, the GUI threw the answer away.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fpdb_3_legacy.HUD_main import HudReadWorker  # noqa: E402

from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest  # noqa: E402


@pytest.fixture
def worker() -> HudReadWorker:
    return HudReadWorker.__new__(HudReadWorker)


@pytest.fixture(autouse=True)
def _bare_queue(worker):
    import threading
    from queue import Queue

    worker._requests = Queue()
    worker._latest_fast_fold = {}
    worker._latest_lock = threading.Lock()


def _request(temp_key: str, request_id: int) -> FastFoldStatsRequest:
    return FastFoldStatsRequest(temp_key=temp_key, request_id=request_id)


def test_the_newest_request_for_a_table_survives(worker) -> None:
    worker.submit(_request("Colorado 11", 1))
    worker.submit(_request("Colorado 11", 2))

    assert worker._is_superseded(_request("Colorado 11", 2)) is False


def test_an_overtaken_request_is_dropped(worker) -> None:
    worker.submit(_request("Colorado 11", 1))
    worker.submit(_request("Colorado 11", 2))

    assert worker._is_superseded(_request("Colorado 11", 1)) is True


def test_a_lone_request_is_never_dropped(worker) -> None:
    worker.submit(_request("Colorado 11", 1))

    assert worker._is_superseded(_request("Colorado 11", 1)) is False


def test_tables_do_not_supersede_each_other(worker) -> None:
    """Multitabling: a busy table must not cancel a quiet one's read."""
    worker.submit(_request("Colorado 11", 1))
    worker.submit(_request("Colorado 12", 2))
    worker.submit(_request("Colorado 12", 3))

    assert worker._is_superseded(_request("Colorado 11", 1)) is False
    assert worker._is_superseded(_request("Colorado 12", 2)) is True


def test_a_request_for_an_unknown_table_is_kept(worker) -> None:
    """Nothing is known about it, which is not evidence that it is stale."""
    assert worker._is_superseded(_request("Colorado 99", 7)) is False


def test_forgetting_a_table_stops_it_superseding_anything(worker) -> None:
    worker.submit(_request("Colorado 11", 1))
    worker.submit(_request("Colorado 11", 2))

    worker.forget_fast_fold_table("Colorado 11")

    assert worker._is_superseded(_request("Colorado 11", 1)) is False
