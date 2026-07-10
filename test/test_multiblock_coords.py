"""Phase 2 - single coordinate model for multi-block HUD windows.

These tests pin the invariants that the three previously-divergent placement
paths (create, move-on-table-move, per-seat show) now share one canonical space:

* canonical = unscaled, reference-layout coordinates, relative to the table's
  top-left corner; stored in block_positions and the on-disk positions store;
* a single converter canonical<->screen, scaled by table/reference only;
* dragging one (seat, block) never disturbs another key;
* a resize A->B->A restores a window to exactly A.
"""

from __future__ import annotations

import types

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import Aux_Base, Aux_Hud


@pytest.fixture(autouse=True)
def _no_display_clamp(monkeypatch):
    # The screen clamp is display-only; disable it so the tests exercise the
    # pure coordinate math without a headless-screen dependency.
    monkeypatch.setattr(Aux_Base, "clamp_to_screen", lambda x, y, *a, **k: (x, y))


@pytest.fixture
def store():
    saved: dict = {}

    class FakeStore:
        def get_position(self, site, layout, ss, mx, seat, bi):
            return saved.get((seat, bi))

        def set_position(self, site, layout, ss, mx, seat, bi, x, y):
            saved[(seat, bi)] = (x, y)

    return saved, FakeStore()


@pytest.fixture
def aw(monkeypatch, store):
    saved, fake_store = store
    monkeypatch.setattr(Aux_Hud, "get_positions_store", lambda: fake_store)

    obj = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    hud = types.SimpleNamespace(
        table=types.SimpleNamespace(width=792, height=546, x=100, y=200),
        layout=types.SimpleNamespace(width=792, height=546, name="L"),
        ref_layout_width=None,
        ref_layout_height=None,
        site="Winamax",
        max=3,
    )
    obj.hud = hud
    obj.game_params = types.SimpleNamespace(name="SS")
    obj.block_positions = {}
    obj._seat_anchor_ref = {1: (50, 60), 2: (300, 60), 3: (600, 60)}
    # block 0 at seat anchor, block 1 offset 54px down (villain info style).
    obj.block_layouts = [{"x": 0, "y": 0}, {"x": 0, "y": 54}]
    obj._saved = saved
    return obj


def test_default_canonical_is_anchor_plus_offset(aw):
    assert aw._canonical_for((1, 0)) == (50, 60)
    assert aw._canonical_for((1, 1)) == (50, 114)
    assert aw._canonical_for((2, 1)) == (300, 114)


def test_table_block_default_is_offset_only(aw):
    assert aw._canonical_for(("table", 1)) == (0, 54)


def test_canonical_to_screen_at_unit_scale(aw):
    # scale 1: screen = canonical + table origin (100, 200)
    assert aw.scale_factors == (1.0, 1.0)
    assert aw._canonical_to_screen((50, 114)) == (150, 314)


def test_screen_canonical_round_trip(aw):
    for abs_pt in [(150, 314), (400, 500), (733, 289)]:
        canon = aw._screen_to_canonical(*abs_pt)
        assert aw._canonical_to_screen(canon) == abs_pt


def test_resize_A_B_A_is_pixel_exact(aw):
    # user drags seat1/block1 to (400,500); canonical is stored once
    canon = aw._screen_to_canonical(400, 500)
    aw._saved[(1, 1)] = canon
    assert canon == (300, 300)

    # resize to 2x -> window follows proportionally
    aw.hud.table.width, aw.hud.table.height = 1584, 1092
    assert aw.scale_factors == (2.0, 2.0)
    assert aw._canonical_to_screen(aw._canonical_for((1, 1))) == (700, 800)

    # resize back to original -> exact original drop point
    aw.hud.table.width, aw.hud.table.height = 792, 546
    assert aw._canonical_to_screen(aw._canonical_for((1, 1))) == (400, 500)


def test_drag_one_block_leaves_other_seats_untouched(aw):
    before = {key: aw._canonical_for(key) for key in [(1, 0), (2, 0), (2, 1), (3, 1)]}
    aw._saved[(1, 1)] = aw._screen_to_canonical(400, 500)  # drag seat1/block1
    after = {key: aw._canonical_for(key) for key in [(1, 0), (2, 0), (2, 1), (3, 1)]}
    assert before == after


def test_saved_position_wins_over_default(aw):
    aw._saved[(3, 0)] = (12, 34)
    assert aw._canonical_for((3, 0)) == (12, 34)


def test_reference_is_frozen_against_layout_mutation(aw):
    # touching scale_factors freezes the reference from the config layout
    assert aw.scale_factors == (1.0, 1.0)
    # simulating Hud.resize_windows mutating the live layout size must NOT
    # change the reference denominator
    aw.hud.layout.width = aw.hud.layout.height = 9999
    aw.hud.table.width, aw.hud.table.height = 1584, 1092
    assert aw.scale_factors == (2.0, 2.0)


def test_saved_positions_survive_a_restart(tmp_path):
    """A dragged position round-trips through the JSON store: a fresh store
    (a new process after restart) reads back the exact same coordinates, and a
    key that was never written stays unset."""
    path = str(tmp_path / "HUD_layout_positions.json")

    store = Aux_Hud.HUDLayoutPositionsStore()
    store.path = path
    store.set_position("Winamax", "L", "SS", 3, 1, 0, 317, 458)

    reopened = Aux_Hud.HUDLayoutPositionsStore()
    reopened.path = path
    reopened.load()
    assert reopened.get_position("Winamax", "L", "SS", 3, 1, 0) == (317, 458)
    # a different (seat, block) key was never written -> no bleed-over
    assert reopened.get_position("Winamax", "L", "SS", 3, 2, 0) is None
