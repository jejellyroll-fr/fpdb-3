from __future__ import annotations

from decimal import Decimal
from threading import Event, current_thread

from fpdb_3_legacy.equity import EquityEngine, EquityResult, PlayerEquity
from fpdb_3_legacy.equity_async import (
    AsyncEquityService,
    EquityAnalysisJob,
    EquitySubmission,
)


def _result() -> EquityResult:
    return EquityResult(
        players=(
            PlayerEquity(Decimal("0.6"), 6, 0, 4),
            PlayerEquity(Decimal("0.4"), 4, 0, 6),
        ),
        samples=10,
        exhaustive=False,
    )


def test_the_equity_queue_is_bounded_non_blocking_and_deduplicated() -> None:
    started = Event()
    release = Event()
    second_done = Event()
    order = []

    def first_evaluation(_engine: EquityEngine) -> EquityResult:
        started.set()
        assert release.wait(2)
        return _result()

    def persist(label: str):
        def callback(_result: EquityResult) -> None:
            order.append((label, "persist", current_thread().name))

        return callback

    service = AsyncEquityService(EquityEngine(cache_size=0), max_queue=1, thread_name="equity-test")
    try:
        first = EquityAnalysisJob("first", first_evaluation, persist("first"))
        second = EquityAnalysisJob(
            "second",
            lambda _engine: _result(),
            persist("second"),
            lambda _result: (order.append(("second", "notify", current_thread().name)), second_done.set()),
        )

        assert service.submit(first) is EquitySubmission.QUEUED
        assert started.wait(2)
        assert service.submit(second) is EquitySubmission.QUEUED
        assert service.submit(second) is EquitySubmission.DUPLICATE
        assert (
            service.submit(EquityAnalysisJob("third", lambda _engine: _result(), persist("third")))
            is EquitySubmission.FULL
        )

        release.set()
        assert second_done.wait(2)
    finally:
        service.close()

    assert order == [
        ("first", "persist", "equity-test"),
        ("second", "persist", "equity-test"),
        ("second", "notify", "equity-test"),
    ]
    assert service.pending == 0
    assert service.submit(first) is EquitySubmission.CLOSED


def test_a_failed_equity_job_does_not_stop_the_following_job() -> None:
    completed = Event()
    persisted = []
    service = AsyncEquityService(EquityEngine(cache_size=0), max_queue=2)
    try:
        assert (
            service.submit(
                EquityAnalysisJob(
                    "broken",
                    lambda _engine: (_ for _ in ()).throw(RuntimeError("bad range")),
                    lambda _result: persisted.append("broken"),
                ),
            )
            is EquitySubmission.QUEUED
        )
        assert (
            service.submit(
                EquityAnalysisJob(
                    "sound",
                    lambda _engine: _result(),
                    lambda _result: persisted.append("sound"),
                    lambda _result: completed.set(),
                ),
            )
            is EquitySubmission.QUEUED
        )
        assert completed.wait(2)
    finally:
        service.close()

    assert persisted == ["sound"]
