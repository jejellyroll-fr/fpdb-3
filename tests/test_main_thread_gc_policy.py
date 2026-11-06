"""The main thread collects what the automatic collector would have (#707)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy import main_thread_gc


@pytest.fixture
def gc_state(monkeypatch):
    collected: list[int] = []
    state = {"counts": (0, 0, 0)}
    monkeypatch.setattr(main_thread_gc.gc, "get_threshold", lambda: (2000, 10, 10))
    monkeypatch.setattr(main_thread_gc.gc, "get_count", lambda: state["counts"])
    monkeypatch.setattr(main_thread_gc.gc, "collect", lambda generation=2: collected.append(generation) or 3)
    return state, collected


@pytest.mark.parametrize(
    ("counts", "generation"),
    [((2001, 0, 0), 0), ((2001, 11, 0), 1), ((2001, 11, 11), 2), ((2001, 10, 11), 0)],
)
def test_the_oldest_generation_due_is_collected(gc_state, counts, generation) -> None:
    state, collected = gc_state
    state["counts"] = counts

    assert main_thread_gc.collect_if_due() == 3
    assert collected == [generation]


def test_nothing_is_collected_below_the_threshold(gc_state) -> None:
    state, collected = gc_state
    state["counts"] = (2000, 50, 50)

    assert main_thread_gc.collect_if_due() == 0
    assert not collected
