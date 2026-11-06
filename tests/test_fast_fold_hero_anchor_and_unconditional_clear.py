"""Unit test verifying exact bottom-center hero seat anchoring and unconditional HUD clearing."""

from unittest.mock import MagicMock

from fpdb_3_legacy import HUD_main
from fpdb_3_legacy.fast_fold_engine import FastFoldEngine


def test_window_slot_mapping_anchors_hero_at_seat_3():
    """Verify that slot 0 maps to seat 3 (bottom-center anchor seat for 6-max Winamax)."""
    engine = FastFoldEngine()
    mock_hud = MagicMock()
    mock_hud.max = 6

    anchor_seat = engine._anchor_slot(mock_hud) or 3
    slots = {0: "hero", 1: "p1", 2: "p2", 3: "p3", 4: "p4", 5: "p5"}
    max_seats = 6

    seat_map = {((slot + anchor_seat - 1) % max_seats) + 1: login for slot, login in slots.items()}

    # Slot 0 (hero) must be mapped to seat 3 (bottom-center)
    assert seat_map[3] == "hero"
    assert seat_map[4] == "p1"
    assert seat_map[5] == "p2"
    assert seat_map[6] == "p3"
    assert seat_map[1] == "p4"
    assert seat_map[2] == "p5"


def test_unconditional_clear_fast_fold_table():
    """Verify that _clear_fast_fold_table clears HUD seats unconditionally."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main._fast_fold_pending = {"key1": {}}
    hud_main._ff_trace = MagicMock()

    mock_hud = MagicMock()
    mock_hud.stat_dict = {}  # stat_dict is empty

    # Call _clear_fast_fold_table
    hud_main._clear_fast_fold_table("key1", mock_hud, "hand1", "fold")

    # Pending map must be popped and FastFoldEngine.clear_seats called
    assert "key1" not in hud_main._fast_fold_pending
    assert mock_hud.stat_dict == {}
    assert mock_hud.seat_players == {}
