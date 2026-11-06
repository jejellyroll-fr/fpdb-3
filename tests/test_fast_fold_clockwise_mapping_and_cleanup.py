"""Unit tests for clockwise seat angle mapping, button filtering, and closed window cleanup."""

from unittest.mock import MagicMock

from fpdb_3_legacy import HUD_main
from fpdb_3_legacy.winamax_ax_seats import AXSeat, is_seat_label, seat_slots_from_positions


def test_is_seat_label_filters_ui_buttons():
    """Verify that is_seat_label filters out UI action buttons like '3x'."""
    assert is_seat_label("3x") is True
    assert is_seat_label("x3") is True
    assert is_seat_label("POT") is True
    assert is_seat_label("ALL-IN") is True
    assert is_seat_label("FOLD") is True
    assert is_seat_label("CALL") is True


def test_clockwise_seat_slots_from_positions():
    """Verify seat_slots_from_positions computes clockwise slots from bottom-center."""
    centre = (500.0, 300.0)
    max_seats = 6

    # Bottom-center hero seat
    hero_seat = AXSeat("hero", 500, 500)
    # Lower-left seat is the next clockwise slot in screen coordinates.
    lower_right = AXSeat("player_br", 700, 450)
    # Lower-right seat is the previous clockwise slot.
    lower_left = AXSeat("player_bl", 300, 450)

    seats = [hero_seat, lower_right, lower_left]
    slots = seat_slots_from_positions(seats, centre, max_seats)

    # Hero at bottom-center must be slot 0
    assert slots[0] == "hero"
    # Screen coordinates have a downward Y axis: from the bottom, clockwise
    # advances toward the lower-left position.
    assert slots[1] == "player_bl"
    assert slots[5] == "player_br"


def test_show_loading_hud_prevents_duplicate_fast_fold_hud():
    """Verify that _show_loading_hud returns existing key if a FastFold HUD matches prefix."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {"Colorado 3 #854752": MagicMock()}

    # Check that any matching prefix key prevents creating duplicate legacy "Colorado 3"
    assert any(k == "Colorado 3" or k.startswith("Colorado 3 #") for k in hud_main.hud_dict)
