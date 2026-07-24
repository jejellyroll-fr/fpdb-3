"""The shipped HUD_config.xml must stay in step with the code.

It is the config a fresh install starts from, and nothing checked that its stat
names still exist, that its layout references resolve, or that it declares the
sites the database seeds. All three had drifted.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from fpdb_3_legacy import Stats
from fpdb_3_legacy.stat_registry import get_registry

TEMPLATE = Path("HUD_config.xml")

# Names that are not stats: the player row, a submenu title, a separator.
NOT_A_STAT = {"playername", "general", "default", "hline", ""}


@pytest.fixture(scope="module")
def config_root() -> ET.Element:
    return ET.parse(TEMPLATE).getroot()


def _resolves(name: str) -> bool:
    """Whether the HUD can render that stat name."""
    if name in NOT_A_STAT or name.startswith("~"):  # "~Title" is a popup heading
        return True
    return name in set(Stats.get_valid_stats()) or get_registry().get(name) is not None


def test_every_stat_of_the_shipped_config_exists(config_root: ET.Element) -> None:
    """A renamed stat leaves an empty HUD cell, silently.

    Stats.py resolves a native name, stat_registry a declarative one; anything
    else renders nothing. 98 cells of the template still named pre-rename stats
    (cbet_river, fold_cbet_turn, af, 3B, total_hands, win_7th...).
    """
    unknown = sorted(
        {
            name
            for element, attribute in ((config_root.iter("stat"), "_stat_name"), (config_root.iter("pu_stat"), "pu_stat_name"))
            for node in element
            if (name := node.get(attribute)) and not node.get("pu_stat_submenu") and not _resolves(name)
        },
    )

    assert unknown == []


def test_every_layout_reference_resolves(config_root: ET.Element) -> None:
    """A site pointing at a layout set that does not exist gets no HUD at all."""
    layouts = {node.get("name") for node in config_root.findall("layout_sets/ls")}

    dangling = [
        (site.get("site_name"), layout.get("ls"))
        for site in config_root.findall("supported_sites/site")
        for layout in site.findall("layout_set")
        if layout.get("ls") not in layouts
    ]

    assert dangling == []


def _seeded_sites() -> set[str]:
    """The sites Database.fillDefaultData inserts into the Sites table."""
    source = Path("fpdb_3_legacy/Database.py").read_text(encoding="utf-8")
    body = source[source.index("def fillDefaultData") : source.index("# end def fillDefaultData")]
    return {
        match.group(1)
        for match in re.finditer(r"INSERT INTO Sites \(id,name,code\) VALUES \('\d+',\s*'([^']+)'", body)
    }


def test_the_shipped_config_declares_every_seeded_site(config_root: ET.Element) -> None:
    """Without a <site> entry the site cannot be configured at all.

    No hand-history folder to watch, no screen name, no HUD layout - the site
    simply is not in the list the GUI shows.
    """
    declared = {site.get("site_name") for site in config_root.findall("supported_sites/site")}

    assert sorted(_seeded_sites() - declared) == []


def test_the_shipped_config_declares_no_unknown_site(config_root: ET.Element) -> None:
    """The reverse: an entry for a site the database knows nothing about."""
    declared = {site.get("site_name") for site in config_root.findall("supported_sites/site")}

    assert sorted(declared - _seeded_sites()) == []
