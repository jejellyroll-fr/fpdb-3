from __future__ import annotations

import logging
import threading
import time

from fpdb_3_legacy import work_priority
from fpdb_3_legacy.work_priority import background_checkpoint, background_work, interactive_work


def test_interactive_task_runs_at_the_next_import_file_boundary() -> None:
    file_started = threading.Event()
    interactive_started = threading.Event()
    import_resumed = threading.Event()

    def import_one_file() -> None:
        with background_work("test-import-file"):
            file_started.set()
            time.sleep(0.03)
        background_checkpoint("test-import-file")
        import_resumed.set()

    def open_page() -> None:
        assert file_started.wait(1)
        with interactive_work("test-page"):
            interactive_started.set()
            time.sleep(0.04)

    importer = threading.Thread(target=import_one_file)
    page = threading.Thread(target=open_page)
    importer.start()
    page.start()
    importer.join(1)
    page.join(1)

    assert not importer.is_alive()
    assert not page.is_alive()
    assert interactive_started.is_set()
    assert import_resumed.is_set()


def test_import_gets_a_bounded_turn_during_a_long_interactive_operation(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="work_priority")
    page_started = threading.Event()
    import_resumed = threading.Event()
    page_saw_import_turn = threading.Event()

    def open_page() -> None:
        with interactive_work("test-long-page"):
            page_started.set()
            if import_resumed.wait(1):
                page_saw_import_turn.set()

    def import_one_file() -> None:
        assert page_started.wait(1)
        background_checkpoint("test-fairness")
        import_resumed.set()

    page = threading.Thread(target=open_page)
    importer = threading.Thread(target=import_one_file)
    page.start()
    importer.start()
    importer.join(2)
    page.join(2)

    assert not importer.is_alive()
    assert not page.is_alive()
    assert import_resumed.is_set()
    assert page_saw_import_turn.is_set()
    assert any("background-checkpoint name=test-fairness yielded=" in record.getMessage() for record in caplog.records)
    assert any("interactive-work name=test-long-page queue_wait=" in record.getMessage() for record in caplog.records)


def test_interactive_metrics_separate_queue_wait_from_work_duration(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="work_priority")
    operation_started = threading.Event()

    def open_page() -> None:
        with interactive_work("queued-page"):
            operation_started.set()
            time.sleep(0.01)

    with background_work("blocking-import-file"):
        page = threading.Thread(target=open_page)
        page.start()
        with work_priority._condition:
            assert work_priority._condition.wait_for(lambda: work_priority._INTERACTIVE_WAITERS > 0, timeout=1)

    page.join(1)
    assert not page.is_alive()
    assert operation_started.is_set()
    record = next(record for record in caplog.records if "interactive-work name=queued-page" in record.getMessage())
    assert "queue_wait=" in record.getMessage()
    assert "duration=" in record.getMessage()
