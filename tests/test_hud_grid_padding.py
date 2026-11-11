"""A profile's xpad / ypad widen the HUD's stat grid (#770), and nothing changes until they do."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import defusedxml.minidom
import pytest

from fpdb_3_legacy.config_hud_layouts import (
    GRID_COLUMN_GAP,
    GRID_COLUMN_GAP_MULTI_PANEL,
    GRID_ROW_GAP,
    grid_spacing,
)
from fpdb_3_legacy.config_migrations import upgrade_document
from fpdb_3_legacy.Configuration import CONFIG_VERSION

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = sorted(
    [
        ROOT / "HUD_config.xml",
        ROOT / "HUD_config.xml.example",
        ROOT / "fpdb_3_legacy" / "HUD_config.xml.example",
        ROOT / "aof_omaha.fpdbhud",
        ROOT / "plo4_6max_pro.xml",
        *(ROOT / "hud-packages").glob("*.fpdbhud"),
    ]
)


# --- The rule ----------------------------------------------------------------
@pytest.mark.parametrize("multi_panel", [False, True])
def test_zero_padding_draws_the_grid_as_it_always_was(multi_panel) -> None:
    column = GRID_COLUMN_GAP_MULTI_PANEL if multi_panel else GRID_COLUMN_GAP
    assert grid_spacing(0, 0, multi_panel=multi_panel) == (column, GRID_ROW_GAP)
    assert (GRID_COLUMN_GAP, GRID_COLUMN_GAP_MULTI_PANEL, GRID_ROW_GAP) == (4, 2, 1)


def test_padding_adds_to_the_default_gaps() -> None:
    assert grid_spacing(3, 2, multi_panel=False) == (7, 3)
    assert grid_spacing("3", "2", multi_panel=True) == (5, 3)


@pytest.mark.parametrize("value", [-2, "-2", "", "wide", None, True, 1.5, MagicMock()])
def test_an_unreadable_or_negative_padding_counts_as_zero(value) -> None:
    assert grid_spacing(value, value, multi_panel=False) == (GRID_COLUMN_GAP, GRID_ROW_GAP)


# --- What ships ----------------------------------------------------------------
@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: str(p.relative_to(ROOT)))
def test_shipped_profiles_keep_their_look(path) -> None:
    """Every shipped <ss> pads by 0, the spacing they were drawn with before #770."""
    nodes = defusedxml.minidom.parse(str(path)).getElementsByTagName("ss")
    assert nodes, path
    for node in nodes:
        for attr in ("xpad", "ypad"):
            assert node.getAttribute(attr) in ("", "0"), (node.getAttribute("name"), attr)


# --- Upgrading a configuration -------------------------------------------------
def _v92(stat_sets: str):
    return defusedxml.minidom.parseString(
        f"""<FreePokerToolsConfig><general version="92"/>
        <stat_sets>{stat_sets}</stat_sets>
        <supported_games/><aux_windows/></FreePokerToolsConfig>"""
    )


def _template():
    return defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))


def test_an_upgrade_zeroes_the_padding_the_hud_never_drew() -> None:
    old = _v92(
        '<ss name="a" rows="1" cols="1" xpad="1" ypad="0"/>'
        '<ss name="b" rows="1" cols="1" xpad="5" ypad="3"/>'
        '<ss name="c" rows="1" cols="1"/>'
    )
    updated = upgrade_document(old, _template(), CONFIG_VERSION)
    assert updated.getElementsByTagName("general")[0].getAttribute("version") == str(CONFIG_VERSION)
    pads = {
        n.getAttribute("name"): (n.getAttribute("xpad"), n.getAttribute("ypad"))
        for n in updated.getElementsByTagName("ss")
    }
    assert pads == {"a": ("0", "0"), "b": ("0", "0"), "c": ("", "")}
    # The configuration being upgraded is left alone; the upgrade is a copy.
    assert old.getElementsByTagName("ss")[1].getAttribute("xpad") == "5"


def test_a_current_configuration_keeps_the_padding_it_was_given() -> None:
    current = _v92('<ss name="a" rows="1" cols="1" xpad="4" ypad="2"/>')
    current.getElementsByTagName("general")[0].setAttribute("version", str(CONFIG_VERSION))
    updated = upgrade_document(current, _template(), CONFIG_VERSION)
    node = updated.getElementsByTagName("ss")[0]
    assert (node.getAttribute("xpad"), node.getAttribute("ypad")) == ("4", "2")
