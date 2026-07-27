"""Configuration and runtime tests for editable modern-popup options."""

from __future__ import annotations

import xml.dom.minidom as minidom
from unittest.mock import patch

from fpdb_3_legacy import Configuration
from fpdb_3_legacy import Popup as PopupModule
from fpdb_3_legacy.ModernPopup import ModernSubmenu, resolve_popup_stat_category


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
