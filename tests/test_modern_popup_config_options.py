"""Configuration and runtime tests for editable modern-popup options."""

from __future__ import annotations

import xml.dom.minidom as minidom
from unittest.mock import patch

from fpdb_3_legacy import Configuration
from fpdb_3_legacy import Popup as PopupModule
from fpdb_3_legacy.ModernPopup import CategorizedPopup, ModernSubmenu, resolve_popup_stat_category
from fpdb_3_legacy.PopupThemes import get_theme


def _popup(xml: str) -> Configuration.Popup:
    return Configuration.Popup(minidom.parseString(xml).documentElement)


def test_popup_parses_theme_icon_provider_and_section_overrides():
    popup = _popup(
        '<pu pu_name="plo" pu_class="ModernSubmenu" '
        'pu_theme="classic" pu_icon_provider="text">'
        '<pu_stat pu_stat_name="vpip" pu_stat_category="general"/>'
        '<pu_stat pu_stat_name="cb1"/>'
        "</pu>"
    )

    assert popup.pu_class_params["theme"] == "classic"
    assert popup.pu_class_params["icon_provider"] == "text"
    assert popup.pu_stats_category == ["general", ""]


def test_popup_parses_rich_text_presentation_metadata():
    popup = _popup(
        '<pu pu_name="rich" pu_class="CategorizedPopup" pu_title="Profile: {player}" '
        'pu_width="520" pu_max_height="800">'
        '<pu_stat pu_stat_name="vpip" pu_stat_category="Preflop" '
        'pu_stat_label="VPIP volontaire" pu_stat_color="#00E59B"/>'
        "</pu>"
    )

    assert popup.pu_class_params["title"] == "Profile: {player}"
    assert popup.pu_class_params["width"] == "520"
    assert popup.pu_class_params["max_height"] == "800"
    assert popup.pu_stats_label == ["VPIP volontaire"]
    assert popup.pu_stats_color == ["#00E59B"]


ROWS = [
    ("⚡ EV", "Decision <EV>", "+2.34", "(96 modeled)", "#00E59B"),
    ("🃏 Made", "Two pair", "25.8", "(63/244)", ""),
]


def _renderer(theme_name: str = "hud_dark") -> CategorizedPopup:
    """A CategorizedPopup with just enough state to render, without Qt."""
    renderer = CategorizedPopup.__new__(CategorizedPopup)
    renderer.theme = get_theme(theme_name)
    return renderer


def test_categorized_popup_html_has_sections_columns_and_escaped_values():
    html = _renderer()._rich_html(ROWS)

    assert "⚡ EV" in html
    assert "🃏 Made" in html
    assert "Decision &lt;EV&gt;" in html
    assert "+2.34" in html
    assert "(63/244)" in html
    assert "#00E59B" in html, "a colour set on the stat must survive the theme"


def test_categorized_popup_colours_come_from_the_theme():
    """The renderer must carry no palette of its own."""
    dark = _renderer("hud_dark")._rich_html(ROWS)
    light = _renderer("material_light")._rich_html(ROWS)

    assert get_theme("hud_dark").get_color("window_bg") in dark
    assert get_theme("material_light").get_color("window_bg") in light
    assert dark != light


def test_a_theme_missing_a_newer_colour_never_renders_white():
    """Older themes predate text_muted/scrollbar_bg; white would be a band."""
    classic = get_theme("classic")

    assert classic.get_color("text_muted") != "#FFFFFF"
    assert classic.get_color("scrollbar_bg") != "#FFFFFF"


def test_signed_values_are_coloured_by_the_themes_scale():
    theme = get_theme("hud_dark")
    renderer = _renderer()

    assert renderer._value_color("+2.34") == theme.get_color("stat_low")
    assert renderer._value_color("-2.34") == theme.get_color("stat_high")
    assert renderer._value_color("25.8") == theme.get_color("stat_neutral")


def test_section_accents_cycle_and_belong_to_the_theme():
    theme = get_theme("hud_dark")

    assert theme.get_section_accent(0) == theme.section_accents[0]
    assert theme.get_section_accent(len(theme.section_accents)) == theme.section_accents[0]
    assert get_theme("material_dark").section_accents != theme.section_accents


def test_modern_popup_uses_xml_theme_and_icon_provider():
    popup = _popup(
        '<pu pu_name="plo" pu_class="ModernSubmenu" '
        'pu_theme="classic" pu_icon_provider="text">'
        '<pu_stat pu_stat_name="vpip"/>'
        "</pu>"
    )

    with patch.object(PopupModule.Popup, "__init__", return_value=None):
        modern = ModernSubmenu(None, None, None, popup, None, None)

    assert modern.theme_name == "classic"
    assert modern.theme.name == "classic"
    assert modern.icon_provider_name == "text"
    assert modern.icon_provider.name == "text"


def test_popup_section_override_falls_back_to_automatic_category():
    popup = _popup(
        '<pu pu_name="plo" pu_class="ModernSubmenu">'
        '<pu_stat pu_stat_name="vpip" pu_stat_category="general"/>'
        '<pu_stat pu_stat_name="cb1"/>'
        "</pu>"
    )

    assert resolve_popup_stat_category(popup, 0, "vpip") == "general"
    assert resolve_popup_stat_category(popup, 1, "cb1") == "flop"
