"""A second ``create`` must not leave the first set of blocks on screen.

The reported symptom was two stat blocks over every player, and the second
set outliving the session: it stayed while the seats were cleared between
hands, and it was still there after the HUD had been killed and every table
logged as destroyed.

The cause was one line. ``AuxSeats.create`` began by rebinding ``m_windows``
to a fresh dict, and every other method -- update, refresh, clear, destroy,
kill -- reaches the windows only through that dict. So a second ``create``
left the first generation unreachable while Qt kept showing it: frozen at
whatever numbers it last had, and impossible to take down. It did not even
appear in the diagnostics, which count ``m_windows`` and therefore reported
seven overlays while fourteen were on screen.

These pin the property that makes the whole class of bug impossible:
whatever the caller does, only the windows of the latest ``create`` exist,
and destroying the aux leaves nothing behind.
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

from fpdb_3_legacy.Aux_Base import AuxSeats  # noqa: E402

MAX_SEATS = 6
#: Six seats plus the common window, which is what the log reports as 7.
WINDOWS_PER_CREATE = MAX_SEATS + 1


class FakeSeatWindow:
    """A seat window that records whether it was ever taken down.

    Only the four calls ``AuxSeats.destroy`` makes are modelled; a window is
    "still on screen" until at least one of them reaches it.
    """

    created: list[FakeSeatWindow] = []

    def __init__(self, aw=None, seat=None) -> None:
        self.seat = seat
        self.torn_down = False
        self.shown = False
        FakeSeatWindow.created.append(self)

    def _tear_down(self) -> None:
        self.torn_down = True

    hide = close = destroy = deleteLater = _tear_down

    # Everything below is what create() happens to call on a window.
    def create(self) -> None:
        pass

    def show(self) -> None:
        self.shown = True

    def move(self, x: int = 0, y: int = 0) -> None:
        self._pos = (x, y)

    def pos(self):
        from types import SimpleNamespace

        x, y = getattr(self, "_pos", (0, 0))
        return SimpleNamespace(x=lambda: x, y=lambda: y)

    def setWindowOpacity(self, *_args) -> None:  # noqa: N802 - mirrors the Qt API
        pass

    def update_contents(self, *_args) -> None:
        pass


def _hud() -> Mock:
    hud = Mock()
    hud.max = MAX_SEATS
    hud.table.width, hud.table.height = 757, 592
    hud.table.x, hud.table.y = 0, 33
    hud.layout.location = {seat: (10 * seat, 20 * seat) for seat in range(0, MAX_SEATS + 1)}
    hud.layout.common = (100, 100)
    hud.layout.width, hud.layout.height = 757, 592
    hud.stat_dict = {}
    hud.is_fast_fold = True  # keeps adj_seats on the identity mapping
    return hud


@pytest.fixture
def aux() -> AuxSeats:
    """An aux window whose seat windows are all recorded on creation."""
    FakeSeatWindow.created = []
    seats = AuxSeats(_hud(), Mock(), {})
    # The seat ring comes from configuration, which is not what these test.
    seats._effective_hh_seats = lambda: list(range(MAX_SEATS + 1))
    seats.aw_class_window = FakeSeatWindow
    seats.create_common = lambda x, y: FakeSeatWindow(seats, "common")
    seats.create_contents = lambda *_a: None
    seats.update_contents = lambda *_a: None
    seats.create_scale_position = lambda x, y: (x, y)
    return seats


def on_screen() -> list[FakeSeatWindow]:
    """Every window ever created that nobody has taken down."""
    return [window for window in FakeSeatWindow.created if not window.torn_down]


# ---------------------------------------------------------------------------
# The property itself
# ---------------------------------------------------------------------------


def test_one_create_puts_one_set_of_windows_on_screen(aux: AuxSeats) -> None:
    aux.create()

    assert len(FakeSeatWindow.created) == WINDOWS_PER_CREATE
    assert len(on_screen()) == WINDOWS_PER_CREATE
    assert len(aux.m_windows) == WINDOWS_PER_CREATE


def test_a_second_create_takes_the_first_set_down(aux: AuxSeats) -> None:
    """The reported bug: two sets of blocks over every seat."""
    aux.create()
    first = list(aux.m_windows.values())

    aux.create()

    assert all(window.torn_down for window in first), "the first generation was left on screen"
    assert len(on_screen()) == WINDOWS_PER_CREATE
    assert not set(map(id, first)) & set(map(id, aux.m_windows.values()))


def test_repeated_creates_never_accumulate(aux: AuxSeats) -> None:
    """Every hand of a Fast-Fold session could otherwise add seven windows."""
    for _ in range(5):
        aux.create()

    assert len(FakeSeatWindow.created) == 5 * WINDOWS_PER_CREATE
    assert len(on_screen()) == WINDOWS_PER_CREATE


def test_destroying_after_two_creates_leaves_nothing(aux: AuxSeats) -> None:
    """What "persists at the end of the session" meant: unreachable windows.

    The aux is destroyed when the HUD is killed. Before the fix that reached
    only the newest generation, so the older one stayed on screen after fpdb
    had reported every table destroyed.
    """
    aux.create()
    aux.create()

    aux.destroy()

    assert on_screen() == []
    assert aux.m_windows == {}


def test_destroying_once_is_enough_after_any_number_of_creates(aux: AuxSeats) -> None:
    for _ in range(3):
        aux.create()

    aux.destroy()

    assert on_screen() == []


# ---------------------------------------------------------------------------
# The diagnostic that missed it
# ---------------------------------------------------------------------------


def test_a_repeated_create_is_reported(aux: AuxSeats, caplog) -> None:
    """A caller creating twice is still doing something it did not mean to.

    The windows are no longer leaked, but the duplicate call is now visible
    instead of silent -- the original was invisible in every log, because the
    diagnostics count m_windows and m_windows had just been emptied.
    """
    aux.create()

    with caplog.at_level("WARNING"):
        aux.create()

    messages = [record.getMessage() for record in caplog.records]
    assert any("re-created while it still owned 7 window(s)" in message for message in messages), messages


def test_a_first_create_says_nothing(aux: AuxSeats, caplog) -> None:
    """The ordinary case must not cry wolf."""
    with caplog.at_level("WARNING"):
        aux.create()

    assert not [r for r in caplog.records if "re-created" in r.getMessage()]


def test_a_create_after_a_destroy_says_nothing(aux: AuxSeats, caplog) -> None:
    """Switching stat set destroys first; that is the correct sequence."""
    aux.create()
    aux.destroy()

    with caplog.at_level("WARNING"):
        aux.create()

    assert not [r for r in caplog.records if "re-created" in r.getMessage()]
    assert len(on_screen()) == WINDOWS_PER_CREATE


# ---------------------------------------------------------------------------
# The multi-block HUD takes the same path
# ---------------------------------------------------------------------------


def test_the_multi_block_hud_shares_the_guard() -> None:
    """SimpleHUD has its own create; it must not reintroduce the leak.

    Checked in the source rather than by driving it: the block path needs a
    configured stat set and a layout store, and what matters here is that
    neither create rebinds m_windows behind the guard's back.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    for relative, class_name in (("fpdb_3_legacy/Aux_Base.py", "AuxSeats"), ("fpdb_3_legacy/Aux_Hud.py", "SimpleHUD")):
        tree = ast.parse((repo / relative).read_text(encoding="utf-8"))
        klass = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name)
        create = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == "create")
        rebinds = [
            node
            for node in ast.walk(create)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "m_windows" and isinstance(t.value, ast.Name)
                for t in node.targets
            )
        ]
        assert not rebinds, (
            f"{class_name}.create assigns self.m_windows directly, which orphans the previous "
            f"generation on screen. Call self._discard_previous_windows() instead."
        )
        calls = [
            node
            for node in ast.walk(create)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("_discard_previous_windows", "create")
        ]
        assert any(c.func.attr == "_discard_previous_windows" for c in calls) or any(
            c.func.attr == "create" for c in calls
        ), f"{class_name}.create must go through the guard"
