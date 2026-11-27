"""Platform-specific HUD drag behavior."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPoint

from fpdb_3_legacy import Aux_Base
from fpdb_3_legacy.Aux_Base import SeatWindow


class _Handle:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls = 0

    def startSystemMove(self) -> bool:  # pylint: disable=invalid-name
        self.calls += 1
        return self.result


def test_windows_does_not_use_native_move_when_qt_reports_success(monkeypatch) -> None:
    """Windows must keep the Qt mouse grab so release persists the drop."""
    handle = _Handle()
    grabbed: list[bool] = []
    window = SimpleNamespace(windowHandle=lambda: handle)
    monkeypatch.setattr(Aux_Base.sys, "platform", "win32")

    assert not Aux_Base._try_start_native_move(window)
    assert handle.calls == 0

    class FakeSeat:
        seat = 2
        _system_move_active = False

        def pos(self) -> QPoint:
            return QPoint(100, 200)

        def windowHandle(self) -> _Handle:  # pylint: disable=invalid-name
            return handle

        def grabMouse(self) -> None:  # pylint: disable=invalid-name
            grabbed.append(True)

    event = SimpleNamespace(globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(120, 220)))
    SeatWindow.button_press_left(FakeSeat(), event)

    assert grabbed == [True]
    assert handle.calls == 0


def test_windows_manual_drag_release_reaches_layout_callback(monkeypatch) -> None:
    """The Windows fallback must persist the final position on release."""
    handle = _Handle()
    grabbed: list[bool] = []
    released: list[bool] = []
    callbacks: list[tuple[object, object]] = []
    monkeypatch.setattr(Aux_Base.sys, "platform", "win32")

    class FakeSeat:
        seat = 2
        _system_move_active = False
        _pos = QPoint(100, 200)
        aw = SimpleNamespace(configure_event_cb=lambda widget, seat: callbacks.append((widget, seat)))

        def pos(self) -> QPoint:
            return self._pos

        def windowHandle(self) -> _Handle:  # pylint: disable=invalid-name
            return handle

        def grabMouse(self) -> None:  # pylint: disable=invalid-name
            grabbed.append(True)

        def releaseMouse(self) -> None:  # pylint: disable=invalid-name
            released.append(True)

    seat = FakeSeat()
    press = SimpleNamespace(globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(120, 220)))
    SeatWindow.button_press_left(seat, press)
    seat._pos = QPoint(140, 240)
    SeatWindow.button_release_left(seat, None)

    assert grabbed == [True]
    assert released == [True]
    assert callbacks == [(seat, 2)]


def test_non_windows_still_uses_native_move(monkeypatch) -> None:
    handle = _Handle()
    window = SimpleNamespace(windowHandle=lambda: handle)
    monkeypatch.setattr(Aux_Base.sys, "platform", "linux")

    assert Aux_Base._try_start_native_move(window)
    assert handle.calls == 1
