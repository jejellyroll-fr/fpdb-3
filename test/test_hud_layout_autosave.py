"""Classic HUD drags auto-persist to the config (no "Save HUD Layout" needed).

The block-window (PT4) HUD already writes each drag to the positions store, but
the classic one-window-per-seat HUD only updated in-memory state, so drags were
lost on restart unless the user opened the Save HUD Layout menu. configure_event_cb
fires exactly once per real drag-release, so persisting there saves once per drag.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.Aux_Base import AuxSeats


class _Point:
    def __init__(self, x: int, y: int) -> None:
        self._x, self._y = x, y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class _Widget:
    def __init__(self, x: int, y: int) -> None:
        self._p = _Point(x, y)

    def pos(self) -> _Point:
        return self._p


def _make_aux(save_calls: list, *, raising: bool = False) -> AuxSeats:
    aux = object.__new__(AuxSeats)

    def save_layout() -> None:
        save_calls.append(True)
        if raising:
            msg = "disk full"
            raise OSError(msg)

    layout = SimpleNamespace(location=[None, (10, 10), (20, 20), (30, 30)], common=(0, 0))
    hud = SimpleNamespace(
        table=SimpleNamespace(x=100, y=200, width=920, height=652),
        layout=layout,
        layout_set=None,  # -> _propagate_to_shared_layout returns early
        max=3,
        site="TestSite",
        save_layout=save_layout,
    )
    aux.hud = hud
    aux.positions = {}
    aux.adj = [0, 1, 2, 3]  # identity
    return aux


def test_drag_of_a_seat_autosaves_once() -> None:
    calls: list = []
    aux = _make_aux(calls)

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert calls == [True]
    assert aux.positions[2] == (50, 60)  # abs(150,260) - table(100,200)


def test_drag_of_common_autosaves() -> None:
    calls: list = []
    aux = _make_aux(calls)

    aux.configure_event_cb(_Widget(130, 230), "common")

    assert calls == [True]
    assert aux.hud.layout.common == (30, 30)


def test_unexpected_identifier_does_not_autosave() -> None:
    calls: list = []
    aux = _make_aux(calls)

    aux.configure_event_cb(_Widget(150, 260), ("weird", 1))

    assert calls == []


def test_autosave_failure_never_breaks_the_drag() -> None:
    calls: list = []
    aux = _make_aux(calls, raising=True)

    # Must not raise even though save_layout blows up.
    aux.configure_event_cb(_Widget(150, 260), 2)

    assert calls == [True]
    assert aux.positions[2] == (50, 60)  # in-memory update still applied
