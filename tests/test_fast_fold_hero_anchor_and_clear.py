"""Unit tests for hero seat anchoring and FastFold HUD seat clearing on new hand start."""

from unittest.mock import MagicMock

from fpdb_3_legacy.fast_fold_engine import FastFoldEngine


def test_pin_hero_seat_defaults_to_seat_3_for_winamax():
    """Verify that pin_hero_seat defaults to seat 3 (Winamax bottom-center seat)."""
    engine = FastFoldEngine()
    mock_hud = MagicMock()
    mock_hud.fast_fold_hero_seat = None
    mock_hud.stat_dict = {}
    mock_hud.aux_windows = []

    hero_seat = engine.pin_hero_seat(mock_hud)
    assert hero_seat == 3


def test_clear_seats_empties_hud_seat_dictionaries():
    """Verify that FastFoldEngine.clear_seats empties HUD seat dictionaries."""
    mock_hud = MagicMock()
    mock_hud.stat_dict = {1: {"seat": 1}}
    mock_hud.seat_players = {1: "player1"}
    mock_aux = MagicMock()
    mock_hud.aux_windows = [mock_aux]

    FastFoldEngine.clear_seats(mock_hud)

    assert mock_hud.stat_dict == {}
    assert mock_hud.seat_players == {}
    mock_aux.refresh_stats.assert_called_once_with(None)
