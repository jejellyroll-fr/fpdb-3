#!/usr/bin/env python3
"""CoinPoker support is switched off while its code stays in the tree.

The room is disabled at the configuration boundary rather than by deleting
files, so these tests check the three doors it used to come through: the site
list the GUI and HUD read, the converter binding bulk import identifies files
with, and the live-capture menu entry.
"""

from __future__ import annotations

import os
import sys
from xml.dom.minidom import parseString

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.Configuration import HHC, Site
from fpdb_3_legacy.disabled_sites import DISABLED_SITES, is_site_disabled
from fpdb_3_legacy.menu_layout import menu_layout


def _node(xml: str):
    return parseString(xml).documentElement


def test_coinpoker_is_the_disabled_room() -> None:
    assert is_site_disabled("CoinPoker")
    assert not is_site_disabled("PokerStars")
    assert DISABLED_SITES == frozenset({"CoinPoker"})


def test_disabled_site_stays_off_even_when_the_config_enables_it() -> None:
    # An existing HUD_config.xml written before the room was disabled still
    # carries enabled="True"; the runtime must not honour it.
    site = Site(node=_node('<site site_name="CoinPoker" enabled="True" screen_name="hero"/>'))
    assert site.enabled is False


def test_other_sites_keep_their_configured_state() -> None:
    assert Site(node=_node('<site site_name="PokerStars" enabled="True"/>')).enabled is True
    assert Site(node=_node('<site site_name="PokerStars" enabled="False"/>')).enabled is False


def test_config_load_drops_the_converter_binding(tmp_path) -> None:
    from fpdb_3_legacy.Configuration import Config

    xml = (
        "<FreePokerToolsConfig>"
        "<supported_databases>"
        '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_selected="True"/>'
        "</supported_databases>"
        "<supported_sites>"
        '<site site_name="CoinPoker" enabled="True"/>'
        '<site site_name="PokerStars" enabled="True"/>'
        "</supported_sites>"
        "<hhcs>"
        '<hhc site="CoinPoker" converter="CoinPokerToFpdb" summaryImporter=""/>'
        '<hhc site="PokerStars" converter="PokerStarsToFpdb" summaryImporter="PokerStarsSummary"/>'
        "</hhcs>"
        "</FreePokerToolsConfig>"
    )
    path = tmp_path / "HUD_config.xml"
    path.write_text(xml, encoding="utf-8")

    config = Config(file=str(path))

    assert "CoinPoker" not in config.hhcs  # IdentifySite builds no parser for it
    assert "PokerStars" in config.hhcs
    assert config.get_supported_sites() == ["PokerStars"]


def test_hhc_binding_itself_is_untouched() -> None:
    # Only the wiring is dropped; the converter entry parses as it always did.
    hhc = HHC(node=_node('<hhc site="CoinPoker" converter="CoinPokerToFpdb" summaryImporter=""/>'))
    assert hhc.converter == "CoinPokerToFpdb"


def test_live_capture_tab_is_not_offered_in_the_menu() -> None:
    handlers = [item.handler for menu in menu_layout() for item in menu.items]
    assert "tab_coinpoker_capture" not in handlers
    assert "tab_bulk_import" in handlers  # the Import menu is otherwise intact


def test_the_coinpoker_code_is_still_importable() -> None:
    # Disabling must not amount to a deletion: the converter still loads and
    # the parser registry still knows it.
    from fpdb_3_legacy.CoinPokerToFpdb import CoinPoker
    from fpdb_3_legacy.parser_registry import get_parser_class

    assert get_parser_class("CoinPoker") is CoinPoker
