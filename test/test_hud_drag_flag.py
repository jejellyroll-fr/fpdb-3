"""A drag whose release never arrived must not keep every HUD alive.

``HUD_main.check_tables`` polls ``Aux_Base.is_drag_active()`` *before* looking
at any table, and returns immediately while a HUD block is being dragged -- on
macOS the geometry scan and the window re-raise both re-order the dragged
window and make the drag stutter.

The flag was cleared only by SeatWindow's mouse release, and that release is not
guaranteed to arrive: ``startSystemMove()`` hands the drag to the window
manager, which runs its own modal loop and does not deliver it, and the widget
can be destroyed mid-drag when the table it belongs to is the one being closed.
One such drag left the flag set for the rest of the process's life, so no HUD
was ever taken down again -- closing a table, or quitting the client, left its
blocks on screen until FPDB was restarted.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fpdb_3_legacy import Aux_Base  # noqa: E402


@pytest.fixture(autouse=True)
def _no_drag_left_behind():
    """The flag is module state; a test must not leak it into the next one."""
    Aux_Base.set_drag_active(False)
    yield
    Aux_Base.set_drag_active(False)


def test_a_drag_in_progress_still_suspends_the_table_check(monkeypatch) -> None:
    """The behaviour being protected: a real drag must not stutter."""
    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: True)
    Aux_Base.set_drag_active(True)

    assert Aux_Base.is_drag_active() is True


def test_a_released_button_ends_a_drag_whose_release_was_never_delivered(monkeypatch) -> None:
    """The window manager's modal move loop swallows the release."""
    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: False)
    Aux_Base.set_drag_active(True)

    assert Aux_Base.is_drag_active() is False


def test_the_flag_is_cleared_and_not_merely_reported_as_false(monkeypatch) -> None:
    """Left set, it would be re-tested on every one of the 800ms ticks."""
    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: False)
    Aux_Base.set_drag_active(True)
    Aux_Base.is_drag_active()

    assert Aux_Base._drag_active is False


def test_a_drag_older_than_the_timeout_is_over(monkeypatch) -> None:
    """Belt and braces: the button state can be stale too, after a native move."""
    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: True)
    Aux_Base.set_drag_active(True)
    monkeypatch.setattr(
        Aux_Base.time,
        "monotonic",
        lambda: Aux_Base._drag_started_at + Aux_Base.DRAG_ACTIVE_TIMEOUT_S + 1,
    )

    assert Aux_Base.is_drag_active() is False


def test_an_unaskable_button_state_leaves_the_timeout_in_charge(monkeypatch) -> None:
    """Cancelling a drag that is really in progress is the worse way to be wrong."""
    monkeypatch.setattr(
        Aux_Base.QGuiApplication,
        "mouseButtons",
        MagicMock(side_effect=RuntimeError("no application")),
    )
    Aux_Base.set_drag_active(True)

    assert Aux_Base.is_drag_active() is True


def test_the_release_path_still_clears_the_flag() -> None:
    Aux_Base.set_drag_active(True)
    Aux_Base.set_drag_active(False)

    assert Aux_Base.is_drag_active() is False


def test_check_tables_looks_at_the_tables_once_the_drag_flag_goes_stale(monkeypatch) -> None:
    """The regression itself, at the level it was reported: HUDs stopped closing."""
    from fpdb_3_legacy import HUD_main

    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: False)
    Aux_Base.set_drag_active(True)

    hud = SimpleNamespace(table=SimpleNamespace())
    hud_main = SimpleNamespace(
        refresh_profiles_from_config=MagicMock(),
        hud_dict={"Nice 18": hud},
        _handle_table_status=MagicMock(),
        _topify_mac_windows=MagicMock(),
    )

    HUD_main.HudMain.check_tables(hud_main)

    hud_main._handle_table_status.assert_called_once_with(hud)
