"""One hand must not cost a database round trip per player named.

The client log names a player only once they have acted, so a six-handed
Fast-Fold table grows its ring a name at a time. Every growth was its own stats
request, round trip and redraw. Measured on a real session, two tables:

    stats-requested ... request=1   seats={4: 'jejellyroll', 5: 'ded40'}
    stats-requested ... request=2   seats={1: ..., 2: ..., 3: ..., 4: ..., 5: ..., 6: ...}
    ... fourteen of them in one hand

each repainting blocks the player was already reading. The first answer must
still be immediate -- that is the one they are waiting for -- so this is a
leading-edge burst with a single trailing send carrying the newest map.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fpdb_3_legacy import HUD_main  # noqa: E402

COALESCE_MS = HUD_main.HudMain.FF_STATS_COALESCE_MS


class _FakeTimer:
    """Stands in for the QTimer the coalescer arms.

    These tests drive the trailing send themselves, so the timer only has to
    remember whether it is armed. Creating real QTimers here, parented to
    throwaway QObjects that are never destroyed, aborted the interpreter several
    hundred files later inside an unrelated Qt teardown test -- and only when
    this file was collected.
    """

    def __init__(self, _parent=None) -> None:
        self.started_with: int | None = None
        self.timeout = self

    def setSingleShot(self, _single: bool) -> None:  # noqa: N802 - Qt API
        pass

    def connect(self, _slot) -> None:
        pass

    def isActive(self) -> bool:  # noqa: N802 - Qt API
        return self.started_with is not None

    def start(self, ms: int) -> None:
        self.started_with = ms

    def stop(self) -> None:
        self.started_with = None

    def deleteLater(self) -> None:  # noqa: N802 - Qt API
        pass


class _Recorder(HUD_main.HudMain):
    """A HudMain with only the coalescing collaborators, recording what is sent."""

    def __init__(self) -> None:  # noqa: D107 - deliberately not HudMain.__init__
        self.sent: list[tuple[str, dict[int, str], str]] = []
        self._ff_last_request_at = {}
        self._ff_coalesced = {}
        self._ff_coalesce_timers = {}
        self._ff_trace = lambda *_a, **_k: None
        self.hud_dict = {}

    def _request_fast_fold_stats(self, temp_key, hud, seat_map, hand_id) -> None:
        self.sent.append((temp_key, dict(seat_map), hand_id))


@pytest.fixture
def app(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(HUD_main.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(HUD_main, "QTimer", _FakeTimer)
    recorder = _Recorder()
    recorder._clock = clock
    return recorder


def _ask(app, seats, hand_id="hand-1", key="Colorado 11", hud=None):
    hud = hud if hud is not None else object()
    app.hud_dict[key] = hud
    app._request_fast_fold_stats_coalesced(key, hud, seats, hand_id)
    return hud


def test_the_first_map_of_a_burst_is_sent_at_once(app) -> None:
    _ask(app, {4: "jejellyroll", 5: "ded40"})

    assert len(app.sent) == 1
    assert app.sent[0][1] == {4: "jejellyroll", 5: "ded40"}


def test_maps_chasing_it_are_held_back(app) -> None:
    hud = _ask(app, {4: "hero"})
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b"}, hud=hud)
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b", 6: "c"}, hud=hud)

    assert len(app.sent) == 1


def test_only_the_newest_held_map_is_ever_sent(app) -> None:
    """An intermediate ring that was already superseded is not worth a round trip."""
    hud = _ask(app, {4: "hero"})
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b"}, hud=hud)
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b", 6: "c"}, hud=hud)

    app._flush_coalesced_fast_fold_stats("Colorado 11")

    assert len(app.sent) == 2
    assert app.sent[1][1] == {4: "hero", 5: "b", 6: "c"}


def test_a_map_arriving_after_the_window_is_sent_at_once(app) -> None:
    hud = _ask(app, {4: "hero"})
    app._clock["now"] += COALESCE_MS / 1000 + 0.01
    _ask(app, {4: "hero", 5: "b"}, hud=hud)

    assert len(app.sent) == 2


def test_a_table_torn_down_while_waiting_is_not_asked_about(app) -> None:
    """The answer would be applied to a HUD nobody is looking at."""
    hud = _ask(app, {4: "hero"})
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b"}, hud=hud)
    app.hud_dict["Colorado 11"] = object()  # rebuilt

    app._flush_coalesced_fast_fold_stats("Colorado 11")

    assert len(app.sent) == 1


def test_forgetting_a_table_drops_what_was_held(app) -> None:
    hud = _ask(app, {4: "hero"})
    app._clock["now"] += 0.05
    _ask(app, {4: "hero", 5: "b"}, hud=hud)

    app._forget_coalesced_fast_fold_stats("Colorado 11")
    app._flush_coalesced_fast_fold_stats("Colorado 11")

    assert len(app.sent) == 1
    assert "Colorado 11" not in app._ff_coalesce_timers


def test_two_tables_do_not_hold_each_other_back(app) -> None:
    """Each table's burst is its own; one busy table must not mute the other."""
    _ask(app, {4: "hero"}, key="Colorado 11")
    _ask(app, {4: "hero"}, key="Colorado 12")

    assert len(app.sent) == 2
