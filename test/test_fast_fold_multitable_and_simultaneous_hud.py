"""Unit tests for FastFold multi-tabling key uniqueness and simultaneous ring rendering."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fpdb_3_legacy import HUD_main


def test_unique_temp_key_for_multitabling():
    """Verify that _ensure_fast_fold_hud creates distinct keys per window_id/table_no."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main.FAST_FOLD_MAX_SEATS = 6
    hud_main._winamax_site_id = 1
    hud_main._prepared_hands = {}
    hud_main._fast_fold_tables = set()
    hud_main._ff_trace = MagicMock()
    hud_main._create_new_hud = MagicMock()
    hud_main.winamax_pool_games = {}

    def mock_create(hand, key, info, site_id, max_seats, site_name, **kwargs):
        hud_main.hud_dict[key] = MagicMock()

    hud_main._create_new_hud.side_effect = mock_create

    update = SimpleNamespace(hand_id="hand123", table_no="3")

    mock_window = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592342,
        poker_game="holdem",
        description="Escape",
    )
    mock_reader = MagicMock()
    mock_reader.find_table_window.return_value = mock_window
    hud_main.winamax_ax_seats = mock_reader

    # First window
    res = hud_main._ensure_fast_fold_hud(update)
    assert res is not None
    key1 = res[0]
    assert key1 == "Colorado 8 #592342"

    # Second window (same pool / table_name, different window_id)
    mock_window2 = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592343,
        poker_game="holdem",
        description="Escape",
    )
    mock_reader.find_table_window.return_value = mock_window2
    update2 = SimpleNamespace(hand_id="hand124", table_no="4")

    res2 = hud_main._ensure_fast_fold_hud(update2)
    assert res2 is not None
    key2 = res2[0]
    assert key2 == "Colorado 8 #592343"

    # Keys must be distinct so multi-tabling does not collide!
    assert key1 != key2
