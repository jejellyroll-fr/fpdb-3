"""An overlay window nobody owns must not stay on the table.

Two rounds of this bug were chased by reasoning about which code path might
create a window twice, and both times the diagnostics agreed with the code
and disagreed with the screen: the per-HUD ``overlays=`` field counts
``m_windows``, so it can only ever report what is owned. It said seven
overlays per table while fourteen were visible.

So the invariant is stated directly instead. A ``SeatWindow`` exists only to
be an overlay owned by an aux window; every path that updates, clears or
destroys one reaches it through its aux's ``m_windows``. A seat window on
screen that no live HUD references is therefore unreachable by definition --
frozen at whatever numbers it had, surviving the seats being cleared between
hands, and surviving the HUD being killed. It is taken down, and reported,
whatever created it.

These tests do not care how the leak happens, which is the point: the
previous fix addressed one way of producing it and the screen still showed
two HUDs per table.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Aux_Base, HUD_main


class Overlay:
    """A stand-in for one overlay window.

    ``_live_seat_windows`` is the seam that decides what counts as an overlay
    -- it filters Qt's top-level widgets by ``isinstance(..., SeatWindow)``
    and is covered on its own below. Everything downstream of it only needs
    something that records being taken down, and a real QWidget here would
    need a QApplication per test for no added truth.
    """

    def __init__(self) -> None:
        self.taken_down: list[str] = []

    def hide(self) -> None:
        self.taken_down.append("hide")

    def close(self) -> None:
        self.taken_down.append("close")

    def destroy(self) -> None:
        self.taken_down.append("destroy")

    def deleteLater(self) -> None:  # noqa: N802 - mirrors the Qt API
        self.taken_down.append("deleteLater")


def _hud_with(*windows: Overlay) -> MagicMock:
    """A HUD whose single aux owns exactly these windows."""
    aux = MagicMock()
    aux.m_windows = dict(enumerate(windows))
    aux.container = None
    hud = MagicMock()
    hud.aux_windows = [aux]
    return hud


@pytest.fixture
def hud_main(monkeypatch):
    """A HudMain whose "process" contains only the windows a test declares."""
    main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    main.hud_dict = {}
    on_screen: list[Overlay] = []
    monkeypatch.setattr(HUD_main.HudMain, "_live_seat_windows", staticmethod(lambda: list(on_screen)))
    main._on_screen = on_screen
    return main


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_a_window_a_hud_owns_is_left_alone(hud_main) -> None:
    owned = Overlay()
    hud_main.hud_dict = {"Colorado 1 #76304": _hud_with(owned)}
    hud_main._on_screen.append(owned)

    hud_main._reap_orphan_overlay_windows()

    assert owned.taken_down == []


def test_a_window_no_hud_owns_is_taken_down(hud_main) -> None:
    """The reported bug: a second, frozen set of blocks over every seat."""
    owned, orphan = Overlay(), Overlay()
    hud_main.hud_dict = {"Colorado 1 #76304": _hud_with(owned)}
    hud_main._on_screen.extend([owned, orphan])

    hud_main._reap_orphan_overlay_windows()

    assert orphan.taken_down == ["hide", "close", "destroy", "deleteLater"]
    assert owned.taken_down == []


def test_an_aux_container_counts_as_owned(hud_main) -> None:
    """Single-window aux types hold their widget in ``container``, not m_windows."""
    contained = Overlay()
    aux = MagicMock()
    aux.m_windows = {}
    aux.container = contained
    hud = MagicMock()
    hud.aux_windows = [aux]
    hud_main.hud_dict = {"Colorado 1 #76304": hud}
    hud_main._on_screen.append(contained)

    hud_main._reap_orphan_overlay_windows()

    assert contained.taken_down == []


def test_every_window_is_orphaned_once_the_last_hud_is_gone(hud_main) -> None:
    """What "persists at the end of the session" means, stated as a test."""
    first, second = Overlay(), Overlay()
    hud_main._on_screen.extend([first, second])

    hud_main._reap_orphan_overlay_windows()

    assert first.taken_down and second.taken_down


def test_windows_of_other_tables_are_not_reaped(hud_main) -> None:
    """Four tables, four HUDs: none of them may take another's overlays down."""
    windows = [Overlay() for _ in range(4)]
    hud_main.hud_dict = {f"Colorado {i} #7630{i}": _hud_with(w) for i, w in enumerate(windows, 1)}
    hud_main._on_screen.extend(windows)

    hud_main._reap_orphan_overlay_windows()

    assert not any(window.taken_down for window in windows)


def test_a_hud_with_no_aux_windows_owns_nothing(hud_main) -> None:
    """A loading placeholder holds no overlays, so any on screen are orphans."""
    orphan = Overlay()
    hud = MagicMock()
    hud.aux_windows = []
    hud_main.hud_dict = {"Colorado 1 #76304": hud}
    hud_main._on_screen.append(orphan)

    hud_main._reap_orphan_overlay_windows()

    assert orphan.taken_down


def test_nothing_on_screen_is_not_an_error(hud_main) -> None:
    hud_main._reap_orphan_overlay_windows()


def test_a_window_that_refuses_to_close_does_not_stop_the_others(hud_main) -> None:
    """One stuck widget must not leave the rest of the leak on screen."""
    stubborn, ordinary = Overlay(), Overlay()
    stubborn.close = MagicMock(side_effect=RuntimeError("already deleted"))
    hud_main._on_screen.extend([stubborn, ordinary])

    hud_main._reap_orphan_overlay_windows()

    assert ordinary.taken_down == ["hide", "close", "destroy", "deleteLater"]


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def test_a_leak_is_reported_with_its_size_and_class(hud_main, caplog) -> None:
    """Cleaning up after a defect does not make it stop being one.

    The class name and count are what point at whichever path leaked, which
    is the question two rounds of diagnostics could not answer.
    """
    hud_main._on_screen.extend([Overlay(), Overlay()])

    with caplog.at_level("WARNING"):
        hud_main._reap_orphan_overlay_windows()

    message = " ".join(record.getMessage() for record in caplog.records)
    assert "HUD overlay leak: 2 window(s)" in message
    assert "Overlayx2" in message


def test_no_leak_says_nothing(hud_main, caplog) -> None:
    owned = Overlay()
    hud_main.hud_dict = {"Colorado 1 #76304": _hud_with(owned)}
    hud_main._on_screen.append(owned)

    with caplog.at_level("WARNING"):
        hud_main._reap_orphan_overlay_windows()

    assert "overlay leak" not in " ".join(r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# The census that the per-HUD count could not give
# ---------------------------------------------------------------------------


def test_the_census_counts_what_qt_has_not_what_a_hud_claims(hud_main) -> None:
    """``overlays=`` reported 7 per table while 14 were on screen."""
    owned = [Overlay() for _ in range(7)]
    leaked = [Overlay() for _ in range(7)]
    hud_main.hud_dict = {"Colorado 1 #76304": _hud_with(*owned)}
    hud_main._on_screen.extend(owned + leaked)

    assert hud_main._describe_window_census() == "14(owned=7)"


def test_the_census_agrees_with_itself_when_nothing_leaked(hud_main) -> None:
    owned = [Overlay() for _ in range(7)]
    hud_main.hud_dict = {"Colorado 1 #76304": _hud_with(*owned)}
    hud_main._on_screen.extend(owned)

    assert hud_main._describe_window_census() == "7(owned=7)"


# ---------------------------------------------------------------------------
# It runs on its own, without anyone remembering to call it
# ---------------------------------------------------------------------------


def test_the_reaper_is_on_the_cleanup_timer() -> None:
    """A leak has to be cleaned up while the player is looking at it."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "HUD_main.pyw").read_text(encoding="utf-8")
    tree = ast.parse(source)
    connected = {
        node.args[0].attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and node.args
        and isinstance(node.args[0], ast.Attribute)
    }

    assert "_reap_orphan_overlay_windows" in connected, "nothing calls the reaper periodically"


def test_tearing_a_hud_down_reaps_what_it_left_behind() -> None:
    """kill_hud is the moment a leak becomes permanent, so it checks there too."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "HUD_main.pyw").read_text(encoding="utf-8")
    tree = ast.parse(source)
    kill = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "idle_kill")
    calls = {
        node.func.attr
        for node in ast.walk(kill)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "_reap_orphan_overlay_windows" in calls


# ---------------------------------------------------------------------------
# The seam: what counts as an overlay
# ---------------------------------------------------------------------------


def test_only_seat_windows_are_treated_as_overlays(qtbot) -> None:
    """The reaper destroys what this returns, so it must not over-reach.

    The HUD process also owns its main window, dialogs and popups. A filter
    that caught those would close the application instead of a stale block,
    so it is pinned against real Qt widgets rather than assumed.
    """
    from PySide6.QtWidgets import QLabel, QWidget

    overlay = Aux_Base.SeatWindow(aw=MagicMock(), seat=1)
    qtbot.addWidget(overlay)
    overlay.show()
    plain = QWidget()
    qtbot.addWidget(plain)
    plain.show()
    label = QLabel("Loading HUD…")
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(overlay)

    found = HUD_main.HudMain._live_seat_windows()

    assert overlay in found
    assert plain not in found
    assert label not in found


def test_no_application_means_nothing_to_reap(monkeypatch) -> None:
    """The census runs during teardown, when the application may be gone."""
    monkeypatch.setattr(HUD_main.QApplication, "instance", staticmethod(lambda: None))

    assert HUD_main.HudMain._live_seat_windows() == []


def test_a_window_being_torn_down_is_not_a_leak(qtbot) -> None:
    """Qt keeps a closed window in topLevelWidgets until it processes the delete.

    Reaping on that basis reported the HUD that had just been killed as a
    leak, on every single teardown -- seven windows, four times a session.
    Visibility is what separates "still on screen" from "on its way out".
    """
    overlay = Aux_Base.SeatWindow(aw=MagicMock(), seat=1)
    qtbot.addWidget(overlay)
    overlay.show()
    qtbot.waitExposed(overlay)
    assert overlay in HUD_main.HudMain._live_seat_windows()

    overlay.hide()

    assert overlay not in HUD_main.HudMain._live_seat_windows()


def test_the_full_widget_census_names_every_visible_class(qtbot) -> None:
    """The question the seat-window count cannot answer: is it even ours?"""
    from PySide6.QtWidgets import QLabel

    overlay = Aux_Base.SeatWindow(aw=MagicMock(), seat=1)
    qtbot.addWidget(overlay)
    overlay.show()
    label = QLabel("Loading HUD…")
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(overlay)
    qtbot.waitExposed(label)

    census = HUD_main.HudMain._describe_all_top_level_widgets()

    assert "SeatWindowx1" in census
    assert "QLabelx1" in census


def test_the_full_census_survives_having_no_application(monkeypatch) -> None:
    monkeypatch.setattr(HUD_main.QApplication, "instance", staticmethod(lambda: None))

    assert HUD_main.HudMain._describe_all_top_level_widgets() == "none"
