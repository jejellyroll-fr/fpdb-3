"""An aux window that was never created must not crash when the table moves.

A loading HUD is put on screen deliberately without creating its aux windows --
``idle_create`` returns early for it, so the seat map and the window objects that
``create()`` builds do not exist yet. The table watcher keeps reporting moves and
resizes the whole time, and Fast-Fold puts a loading HUD up on every new table,
which is how ``'ClassicHud' object has no attribute 'adj'`` reached the log.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules.setdefault("PySide6", Mock())
sys.modules.setdefault("PySide6.QtWidgets", Mock())
sys.modules.setdefault("PySide6.QtCore", Mock())
sys.modules.setdefault("PySide6.QtGui", Mock())

from fpdb_3_legacy import Aux_Base  # noqa: E402
from fpdb_3_legacy.Aux_Base import AuxSeats  # noqa: E402


def _hud() -> Mock:
    hud = Mock()
    hud.max = 6
    hud.table.width, hud.table.height = 757, 592
    hud.table.x, hud.table.y = 0, 33
    # Empty on purpose: a HUD whose aux windows were never created has no seat
    # map, so any lookup here would be the bug this guards against.
    hud.layout.location = {}
    hud.layout.common = (0, 0)
    return hud


@pytest.fixture
def uncreated() -> AuxSeats:
    """An aux exactly as it is between ``__init__`` and ``create()``."""
    return AuxSeats(_hud(), Mock(), {})


class TestBeforeCreate:
    def test_the_seat_map_exists_and_is_empty(self, uncreated: AuxSeats) -> None:
        assert uncreated.adj == {}
        assert uncreated.m_windows == {}

    def test_resizing_is_a_no_op(self, uncreated: AuxSeats) -> None:
        uncreated.resize_windows()

        assert uncreated.positions == {}

    def test_moving_is_a_no_op(self, uncreated: AuxSeats) -> None:
        uncreated.move_windows()

    def test_updating_is_a_no_op(self, uncreated: AuxSeats) -> None:
        uncreated.update_gui("some-hand")

    def test_destroying_is_a_no_op(self, uncreated: AuxSeats) -> None:
        uncreated.destroy()

        assert uncreated.displayed is False


class TestAfterCreate:
    def test_resizing_still_places_every_seat(self, monkeypatch) -> None:
        """The guard must not silence a resize for an aux that does exist."""
        monkeypatch.setattr(Aux_Base, "clamp_to_screen", lambda x, y: (x, y))
        hud = _hud()
        hud.layout.location = {seat: (seat * 10, seat * 20) for seat in range(1, 7)}
        hud.layout.common = (5, 6)
        aux = AuxSeats(hud, Mock(), {})
        aux.adj = dict.fromkeys(range(1, 7), 1) | {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        aux.m_windows = {seat: Mock() for seat in range(1, 7)} | {"common": Mock()}

        aux.resize_windows()

        assert aux.positions[1] == (10, 20)
        assert aux.positions[6] == (60, 120)
        assert aux.positions["common"] == (5, 6)
        aux.m_windows[1].move.assert_called_once()
