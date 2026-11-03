"""No-op HUD window moves are skipped on the refresh path (#680).

A stats refresh used to call QWidget.move() on every seat window of every
open table even when the target position was identical -- the #680 logs
showed 35+ such moves for 5 tables within 2 s. These tests pin the skip.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint

from fpdb_3_legacy import Aux_Base
from fpdb_3_legacy.Aux_Base import AuxSeats


class FakeWindow:
    def __init__(self, x: int, y: int) -> None:
        self._pos = QPoint(x, y)
        self.moves: list[tuple[int, int]] = []

    def pos(self) -> QPoint:
        return self._pos

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))
        self._pos = QPoint(x, y)


def _aux(max_seats: int = 2) -> AuxSeats:
    """An AuxSeats with fake windows already at their target positions."""
    aux = object.__new__(AuxSeats)
    aux.hud = SimpleNamespace(
        max=max_seats,
        table=SimpleNamespace(x=100, y=200),
        layout=SimpleNamespace(common=(10, 20)),
    )
    aux.positions = {i: (i * 10, i * 5) for i in range(1, max_seats + 1)}
    aux.positions["common"] = (10, 20)
    aux.m_windows = {i: FakeWindow(100 + i * 10, 200 + i * 5) for i in range(1, max_seats + 1)}
    aux.m_windows["common"] = FakeWindow(110, 220)
    return aux


def test_move_windows_skips_windows_already_in_place() -> None:
    aux = _aux()
    aux.move_windows()
    assert all(w.moves == [] for w in aux.m_windows.values())


def test_move_windows_moves_only_windows_whose_target_changed() -> None:
    aux = _aux()
    aux.m_windows[1]._pos = QPoint(0, 0)  # table moved since the last pass
    aux.move_windows()
    assert aux.m_windows[1].moves == [(110, 205)]
    assert aux.m_windows[2].moves == []
    assert aux.m_windows["common"].moves == []


def test_move_if_needed_counts_skipped_and_real_moves(monkeypatch) -> None:
    counts: dict[str, int] = {}
    monkeypatch.setattr(Aux_Base.latency_profile, "count", lambda n, a=1: counts.__setitem__(n, counts.get(n, 0) + a))
    window = FakeWindow(5, 5)
    AuxSeats._move_if_needed(window, 5, 5)
    AuxSeats._move_if_needed(window, 7, 9)
    assert window.moves == [(7, 9)]
    assert counts == {"hud_window_moves_skipped": 1, "hud_window_moves": 1}


def test_idle_resize_runs_aux_resize_only_once() -> None:
    """Hud.resize_windows() already resizes every aux window; the extra loop in
    idle_resize used to run a second full pass over the same windows (#680)."""
    from fpdb_3_legacy.hud_main_tables import HudMainTablesMixin

    mgr = object.__new__(HudMainTablesMixin)
    mgr._position_loading_indicator = lambda hud: None
    hud = MagicMock()
    aux = MagicMock()
    hud.aux_windows = [aux]
    HudMainTablesMixin.idle_resize(mgr, hud)
    assert hud.resize_windows.call_count == 1
    aux.resize_windows.assert_not_called()


def test_check_tables_records_qt_event_loop_lag(monkeypatch) -> None:
    """The 800 ms check_tables timer's lateness is reported as qt_event_loop_lag."""
    from fpdb_3_legacy.hud_main_tables import HudMainTablesMixin

    mgr = object.__new__(HudMainTablesMixin)
    mgr.hud_dict = {}
    mgr.refresh_profiles_from_config = lambda: None
    mgr._topify_mac_windows = lambda: None
    recorded: list[tuple[str, float]] = []
    monkeypatch.setattr(
        "fpdb_3_legacy.hud_main_tables.latency_profile.record",
        lambda name, seconds: recorded.append((name, seconds)),
    )

    mgr._last_check_tables_ts = None
    HudMainTablesMixin.check_tables(mgr)
    assert recorded == []  # first tick only arms the clock

    mgr._last_check_tables_ts = time.monotonic() - 0.8 - 0.05
    HudMainTablesMixin.check_tables(mgr)
    assert recorded[0][0] == "qt_event_loop_lag"
    assert recorded[0][1] == pytest.approx(0.05, abs=0.02)
