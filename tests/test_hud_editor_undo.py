"""The HUD editor's undo and redo history, without Qt."""

from __future__ import annotations

from fpdb_3_legacy.modern_hud_preferences.undo import History


def _profile(*names: str) -> dict:
    return {"rows": 1, "cols": len(names), "stats": [{"stat": n, "row": 0, "col": i} for i, n in enumerate(names)]}


def test_a_new_history_has_nothing_to_undo_or_redo() -> None:
    history = History(_profile("vpip"))
    assert not history.can_undo and not history.can_redo
    assert history.undo(_profile("vpip")) is None
    assert history.redo(_profile("vpip")) is None


def test_recording_the_same_state_is_not_a_step() -> None:
    history = History(_profile("vpip"))
    assert not history.record(_profile("vpip"))
    assert not history.can_undo


def test_undo_and_redo_walk_the_recorded_states() -> None:
    first, second, third = _profile("vpip"), _profile("vpip", "pfr"), _profile("vpip", "pfr", "wtsd")
    history = History(first)
    assert history.record(second)
    assert history.record(third)

    assert history.undo(third) == second
    assert history.undo(second) == first
    assert history.undo(first) is None
    assert history.can_redo
    assert history.redo(first) == second
    assert history.redo(second) == third
    assert history.redo(third) is None


def test_an_edit_not_yet_recorded_is_undone_first() -> None:
    first, edited = _profile("vpip"), _profile("vpip", "pfr")
    history = History(first)
    assert history.undo(edited) == first
    assert history.redo(first) == edited


def test_a_new_edit_drops_what_was_undone() -> None:
    first, second, other = _profile("vpip"), _profile("vpip", "pfr"), _profile("cb1")
    history = History(first)
    history.record(second)
    history.undo(second)
    assert history.record(other)
    assert not history.can_redo
    assert history.undo(other) == first


def test_redo_is_refused_once_the_profile_changed() -> None:
    first, second = _profile("vpip"), _profile("vpip", "pfr")
    history = History(first)
    history.record(second)
    history.undo(second)
    assert history.redo(_profile("cb1")) is None


def test_the_states_handed_out_are_copies() -> None:
    first, second = _profile("vpip"), _profile("vpip", "pfr")
    history = History(first)
    first["stats"].append({"stat": "late"})
    history.record(second)
    restored = history.undo(second)
    assert restored == _profile("vpip")
    restored["stats"].clear()
    assert history.redo(restored) is None
    assert history.redo(_profile("vpip")) == second


def test_the_oldest_steps_go_past_the_limit() -> None:
    history = History(_profile("s0"), limit=3)
    states = [_profile(f"s{i}") for i in range(1, 6)]
    for state in states:
        history.record(state)
    steps = []
    current = states[-1]
    while (previous := history.undo(current)) is not None:
        steps.append(previous["stats"][0]["stat"])
        current = previous
    assert steps == ["s4", "s3", "s2"]
    assert History(_profile("x"), limit=0).limit == 1
