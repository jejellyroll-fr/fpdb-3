"""Phase 5 - deterministic cycle: reposition only on a real geometry change.

A per-hand HUD refresh must show/hide windows but never move them; windows are
placed at create() and re-placed only on resize/move. The move is gated on the
hud's geometry generation, so nothing drifts between hands.
"""

from __future__ import annotations

import types

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import Aux_Classic_Hud, Aux_Hud


class _Win:
    """Minimal stand-in bound to the real _position_and_show_block."""

    def __init__(self, aw, block_key):
        self.aw = aw
        self.block_key = block_key
        self.moves: list[tuple[int, int]] = []
        self.shown = 0

    def move(self, x, y):
        self.moves.append((x, y))

    def setWindowOpacity(self, _o):
        pass

    def show(self):
        self.shown += 1

    _position_and_show_block = Aux_Classic_Hud.ClassicStatWindow._position_and_show_block


def _make_aw(generation=0):
    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    hud = types.SimpleNamespace(
        table=types.SimpleNamespace(width=792, height=546, x=100, y=200),
        layout=types.SimpleNamespace(width=792, height=546, name="L"),
        ref_layout_width=792,
        ref_layout_height=546,
        site="Winamax",
        max=3,
        geometry_generation=generation,
    )
    aw.hud = hud
    aw.game_params = types.SimpleNamespace(name="SS")
    aw.block_positions = {(1, 0): (50, 60)}
    aw._seat_anchor_ref = {1: (50, 60)}
    aw.block_layouts = [{"x": 0, "y": 0}]
    aw.params = {"opacity": 1.0}
    return aw


@pytest.fixture(autouse=True)
def _stub_store_and_clamp(monkeypatch):
    import fpdb_3_legacy.Aux_Base as AB

    monkeypatch.setattr(AB, "clamp_to_screen", lambda x, y, *a, **k: (x, y))
    store = types.SimpleNamespace(get_position=lambda *a, **k: None, set_position=lambda *a, **k: None)
    monkeypatch.setattr(Aux_Hud, "get_positions_store", lambda: store)


def test_first_show_positions_then_reuses_without_moving():
    aw = _make_aw(generation=0)
    win = _Win(aw, (1, 0))

    win._position_and_show_block(1)
    assert len(win.moves) == 1          # placed once
    first_pos = win.moves[0]
    assert win.shown == 1

    # same geometry generation -> subsequent hands only show, never move
    win._position_and_show_block(1)
    win._position_and_show_block(1)
    assert len(win.moves) == 1          # no extra moves
    assert win.shown == 3              # but shown every time


def test_geometry_change_triggers_one_reposition():
    aw = _make_aw(generation=0)
    win = _Win(aw, (1, 0))
    win._position_and_show_block(1)
    assert len(win.moves) == 1

    # a real geometry change bumps the generation
    aw.hud.geometry_generation = 1
    win._position_and_show_block(1)
    assert len(win.moves) == 2          # repositioned once for the new geometry

    # and then stays put again on further hands
    win._position_and_show_block(1)
    assert len(win.moves) == 2


def test_reposition_after_table_move_follows_new_origin():
    aw = _make_aw(generation=0)
    win = _Win(aw, (1, 0))
    win._position_and_show_block(1)
    placed_at = win.moves[-1]

    # table dragged to a new origin + geometry generation bumped
    aw.hud.table.x, aw.hud.table.y = 400, 500
    aw.hud.geometry_generation = 1
    win._position_and_show_block(1)
    assert win.moves[-1] != placed_at   # window followed the table
    # canonical (50,60) at scale 1 + new origin (400,500)
    assert win.moves[-1] == (450, 560)
