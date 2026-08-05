from __future__ import annotations

from fpdb_3_legacy.swc_poker_console import clean_game_name


def test_clean_game_name_maps_captured_swc_game() -> None:
    assert clean_game_name(" Poker (Type 79) ") == "Omaha"


def test_clean_game_name_preserves_unknown_game() -> None:
    assert clean_game_name("Mixed Pineapple") == "Mixed Pineapple"
