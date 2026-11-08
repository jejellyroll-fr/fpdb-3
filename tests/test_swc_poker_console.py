from __future__ import annotations

from fpdb_3_legacy.capture.swc_poker_console import clean_game_name
from fpdb_3_legacy.http_capture_models import SWC_GAME_DEFINITIONS


def test_clean_game_name_maps_captured_swc_game() -> None:
    assert clean_game_name(" Poker (Type 79) ") == "Omaha"


def test_clean_game_name_preserves_unknown_game() -> None:
    assert clean_game_name("Mixed Pineapple") == "Mixed Pineapple"


def test_clean_game_name_covers_all_observed_swc_game_codes() -> None:
    for game_code, definition in SWC_GAME_DEFINITIONS.items():
        assert clean_game_name(f"Poker (Type {game_code})") == definition.label
