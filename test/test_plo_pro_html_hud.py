"""Unit tests for the new ultra-modern PLO HTML HUD (plo_pro_html) and street popups."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from fpdb_3_legacy.Aux_Classic_Hud import _compact_stat_html

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "HUD_config.xml"


def test_plo_pro_html_stat_set_exists_in_config() -> None:
    """Verify that plo_pro_html is correctly declared with rich_text and 5x4 stats."""
    tree = ET.parse(CONFIG_FILE)
    root = tree.getroot()
    stat_set = root.find("./stat_sets/ss[@name='plo_pro_html']")

    assert stat_set is not None
    assert stat_set.get("rich_text") == "True"
    assert stat_set.get("font_size") == "10"
    assert stat_set.get("rows") == "5"
    assert stat_set.get("cols") == "4"

    stats = stat_set.findall("stat")
    assert len(stats) == 20

    stat_names = {stat.get("_stat_name") for stat in stats}
    expected_stats = {
        "playershort",
        "player_note",
        "n",
        "profit100",
        "vpip",
        "pfr",
        "three_B",
        "f_3bet",
        "cold_call",
        "four_B",
        "fold_vs_4bet",
        "squeeze",
        "cb1",
        "f_cb1",
        "dbr1",
        "cr1",
        "cb2",
        "f_cb2",
        "cb3",
        "wtsd",
    }
    assert expected_stats.issubset(stat_names)


def test_plo_street_popups_exist_and_categorized() -> None:
    """Verify that per-street CategorizedPopup entries exist with proper categories."""
    tree = ET.parse(CONFIG_FILE)
    root = tree.getroot()

    popups = [
        "plo_popup_preflop",
        "plo_popup_flop",
        "plo_popup_turn",
        "plo_popup_river",
        "plo_popup_showdown",
        "plo_popup_full",
    ]

    for popup_name in popups:
        pu = root.find(f"./popup_windows/pu[@pu_name='{popup_name}']")
        assert pu is not None, f"Popup '{popup_name}' should exist in HUD_config.xml"
        assert pu.get("pu_class") == "CategorizedPopup"
        assert pu.get("pu_theme") == "hud_dark"
        assert pu.get("pu_icon_provider") == "emoji"

        stats = pu.findall("pu_stat")
        assert len(stats) > 0, f"Popup '{popup_name}' must contain pu_stat entries"
        for stat in stats:
            assert stat.get("pu_stat_category"), f"pu_stat in {popup_name} must have a category"
            assert stat.get("pu_stat_label"), f"pu_stat in {popup_name} must have a label"


def test_omaha_supported_games_bound_to_plo_pro_html() -> None:
    """Verify that Omaha ring game bindings use plo_pro_html."""
    tree = ET.parse(CONFIG_FILE)
    root = tree.getroot()

    omaha_games = ["omahahi", "omahahilo", "5_omahahi", "5_omaha8", "cour_hi", "cour_hilo", "6_omahahi"]
    for game_name in omaha_games:
        game = root.find(f"./supported_games/game[@game_name='{game_name}']")
        assert game is not None, f"Game '{game_name}' must be in supported_games"
        ring_stat_set = game.find("./game_stat_set[@game_type='ring']")
        assert ring_stat_set is not None
        assert ring_stat_set.get("stat_set") == "plo_pro_html"


def test_compact_stat_html_rendering() -> None:
    """Verify HTML rendering format generated for rich_text HUD stats."""
    html = _compact_stat_html("VP ", "28", "%", "#4CC9F0")
    assert '<span style="white-space:nowrap;">' in html
    assert "VP&nbsp;" in html
    assert "28" in html
    assert "#4CC9F0" in html
