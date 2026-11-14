#!/usr/bin/env python3
"""Rooms switched off or cut down to file import, while their code stays in the tree.

CoinPoker is import-only (#732): Bulk Import reads its exported hand histories,
and nothing runs beside its client -- no HUD, no auto-import, no live capture.
The *disabled* level has no room today; its mechanism is checked with a
stand-in so that switching a room off stays a one-line change.
"""

from __future__ import annotations

from xml.dom.minidom import parseString

import pytest

from fpdb_3_legacy import disabled_sites
from fpdb_3_legacy.Configuration import HHC, Site
from fpdb_3_legacy.disabled_sites import (
    DISABLED_SITES,
    IMPORT_ONLY_SITES,
    allows_live_use,
    is_site_disabled,
    is_site_import_only,
)
from fpdb_3_legacy.menu_layout import menu_layout


def _node(xml: str):
    return parseString(xml).documentElement


def _write_config(tmp_path, sites: str, hhcs: str) -> str:
    xml = (
        "<FreePokerToolsConfig>"
        "<supported_databases>"
        '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_selected="True"/>'
        "</supported_databases>"
        f"<supported_sites>{sites}</supported_sites>"
        f"<hhcs>{hhcs}</hhcs>"
        "</FreePokerToolsConfig>"
    )
    path = tmp_path / "HUD_config.xml"
    path.write_text(xml, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Import-only: CoinPoker
# ---------------------------------------------------------------------------


def test_coinpoker_is_import_only_not_disabled() -> None:
    assert IMPORT_ONLY_SITES == frozenset({"CoinPoker"})
    assert DISABLED_SITES == frozenset()
    assert is_site_import_only("CoinPoker")
    assert not is_site_disabled("CoinPoker")
    assert not allows_live_use("CoinPoker")
    assert allows_live_use("PokerStars")


def test_an_import_only_room_can_be_enabled_but_never_gets_a_hud() -> None:
    # An older HUD_config.xml may still say aux_enabled="True" for the room.
    site = Site(node=_node('<site site_name="CoinPoker" enabled="True" aux_enabled="True" screen_name="Hero"/>'))

    assert site.enabled is True  # its files can be bulk-imported
    assert site.aux_enabled is False  # but no HUD runs at its tables


def test_other_sites_keep_their_configured_hud() -> None:
    assert Site(node=_node('<site site_name="PokerStars" aux_enabled="True"/>')).aux_enabled is True


def test_config_load_keeps_the_import_only_converter_binding(tmp_path) -> None:
    from fpdb_3_legacy.Configuration import Config

    path = _write_config(
        tmp_path,
        '<site site_name="CoinPoker" enabled="True" aux_enabled="True"/><site site_name="PokerStars" enabled="True"/>',
        '<hhc site="CoinPoker" converter="CoinPokerToFpdb" summaryImporter=""/>'
        '<hhc site="PokerStars" converter="PokerStarsToFpdb" summaryImporter="PokerStarsSummary"/>',
    )

    config = Config(file=path)

    assert config.hhcs["CoinPoker"].converter == "CoinPokerToFpdb"  # IdentifySite builds its parser
    assert sorted(config.get_supported_sites()) == ["CoinPoker", "PokerStars"]
    assert config.get_site_parameters("CoinPoker")["aux_enabled"] is False


def test_live_capture_tab_is_not_offered_in_the_menu() -> None:
    handlers = [item.handler for menu in menu_layout() for item in menu.items]
    assert "tab_coinpoker_capture" not in handlers
    assert "tab_bulk_import" in handlers  # the Import menu is otherwise intact


def test_the_converter_identifies_coinpoker_text_files() -> None:
    from fpdb_3_legacy.CoinPokerToFpdb import CoinPoker
    from fpdb_3_legacy.parser_registry import get_parser_class

    assert get_parser_class("CoinPoker") is CoinPoker
    assert CoinPoker.re_identify.search("CoinPoker Hand #91198200457: PLO 4 (₮0.01/₮0.02) 2026/07/17 22:15:58 CEST")


# ---------------------------------------------------------------------------
# Disabled: the mechanism, with a stand-in room
# ---------------------------------------------------------------------------


@pytest.fixture
def switched_off(monkeypatch) -> str:
    monkeypatch.setattr(disabled_sites, "DISABLED_SITES", frozenset({"PokerStars"}))
    return "PokerStars"


def test_disabled_site_stays_off_even_when_the_config_enables_it(switched_off) -> None:
    site = Site(node=_node(f'<site site_name="{switched_off}" enabled="True" screen_name="hero"/>'))
    assert site.enabled is False
    assert not allows_live_use(switched_off)


def test_config_load_drops_a_disabled_converter_binding(tmp_path, switched_off) -> None:
    from fpdb_3_legacy.Configuration import Config

    path = _write_config(
        tmp_path,
        f'<site site_name="{switched_off}" enabled="True"/><site site_name="Winamax" enabled="True"/>',
        f'<hhc site="{switched_off}" converter="PokerStarsToFpdb" summaryImporter=""/>'
        '<hhc site="Winamax" converter="WinamaxToFpdb" summaryImporter=""/>',
    )

    config = Config(file=path)

    assert switched_off not in config.hhcs  # IdentifySite builds no parser for it
    assert config.get_supported_sites() == ["Winamax"]


def test_hhc_binding_itself_is_untouched(switched_off) -> None:
    # Only the wiring is dropped; the converter entry parses as it always did.
    hhc = HHC(node=_node(f'<hhc site="{switched_off}" converter="PokerStarsToFpdb" summaryImporter=""/>'))
    assert hhc.converter == "PokerStarsToFpdb"
