"""A worker thread no longer destroys Qt objects of the main thread (#707).

Python collects on whichever thread crosses the allocation threshold, so a Qt
object caught in a reference cycle was destroyed by HudReadWorker: the HUD and
the Qt suite deadlocked on it, ~QObject holding a Qt mutex while it waited for
the GIL the main thread held.
"""

from __future__ import annotations

import gc
import threading
import weakref

import pytest
from PySide6.QtCore import QObject

from fpdb_3_legacy.main_thread_gc import MainThreadGarbageCollector, install_main_thread_gc

pytestmark = pytest.mark.qt


@pytest.fixture
def automatic_gc():
    """Automatic collection on, as a process starts, whatever the suite does between tests."""
    was_enabled = gc.isenabled()
    gc.collect()
    gc.enable()
    yield
    if not was_enabled:
        gc.disable()


def _abandon_a_cycle_holding_a_qobject() -> list[str]:
    """Leave a QObject that only the cyclic collector can free; return the threads that free it."""
    freed_on: list[str] = []
    obj = QObject()
    holder = {"obj": obj}
    holder["self"] = holder
    weakref.finalize(obj, lambda: freed_on.append(threading.current_thread().name))
    return freed_on


def _allocate_on_a_worker_thread() -> list[list[object]]:
    """Allocate past the threshold on a worker, and keep it: the collector counts what is still alive."""
    kept: list[list[object]] = []

    def churn() -> None:
        kept.extend([] for _ in range(gc.get_threshold()[0] * 20))

    worker = threading.Thread(target=churn, name="worker")
    worker.start()
    worker.join()
    return kept


@pytest.mark.usefixtures("qapp", "automatic_gc")
def test_without_it_a_worker_thread_frees_the_qobject() -> None:
    """What the deadlock started from: the worker's allocations run the collection."""
    freed_on = _abandon_a_cycle_holding_a_qobject()

    _allocate_on_a_worker_thread()

    assert freed_on == ["worker"]


@pytest.mark.usefixtures("automatic_gc")
def test_with_it_the_qobject_is_freed_on_the_main_thread(qtbot) -> None:
    collector = MainThreadGarbageCollector(interval_ms=10)
    try:
        freed_on = _abandon_a_cycle_holding_a_qobject()

        kept = _allocate_on_a_worker_thread()
        assert not freed_on

        qtbot.waitUntil(lambda: bool(freed_on), timeout=5_000)
        assert freed_on == ["MainThread"]
        del kept
    finally:
        collector.stop()


@pytest.mark.usefixtures("qapp", "automatic_gc")
def test_stopping_gives_collection_back_to_python() -> None:
    collector = MainThreadGarbageCollector()
    assert not gc.isenabled()

    collector.stop()

    assert gc.isenabled()


@pytest.mark.usefixtures("automatic_gc")
def test_it_lives_as_long_as_the_application(qapp) -> None:
    collector = install_main_thread_gc(qapp)
    try:
        assert collector.parent() is qapp
        assert not gc.isenabled()
    finally:
        collector.stop()
        collector.setParent(None)
