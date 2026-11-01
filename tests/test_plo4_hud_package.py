"""Regression checks for the distributable PLO4 HUD package."""

from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plo4_6max_pro.xml"
SHIPPED_CONFIG = ROOT / "HUD_config.xml"
PROFILE_NAME = "plo4_6max_pro"
POPUP_NAMES = {
    "plo4_full",
    "plo4_postflop",
    "plo4_preflop",
    "plo4_showdown",
}


def _normalized_element(element: ET.Element) -> tuple:
    """Return an indentation-independent representation of an XML element."""
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        tuple(_normalized_element(child) for child in element),
    )


def _named_element(root: ET.Element, xpath: str, attribute: str, name: str) -> ET.Element:
    element = next((node for node in root.findall(xpath) if node.get(attribute) == name), None)
    assert element is not None, f"{name!r} is missing from {xpath!r}"
    return element


def test_plo4_hud_package_matches_fpdb_import_contract() -> None:
    root = ET.parse(PACKAGE).getroot()

    assert root.tag == "fpdb_hud_package"
    assert root.get("version") == "1.0"

    profiles = root.findall("./ss")
    assert len(profiles) == 1
    assert profiles[0].get("name") == PROFILE_NAME
    # Older FPDB HUD processes still index the flat compatibility union before
    # switching to block rendering, so the root grid must contain every block
    # coordinate even though the modern renderer uses each block's own size.
    rows = int(profiles[0].get("rows", "0"))
    cols = int(profiles[0].get("cols", "0"))
    for stat in profiles[0].iter("stat"):
        row, col = (int(value) for value in stat.get("_rowcol", "(0,0)").strip("()").split(","))
        assert 1 <= row <= rows
        assert 1 <= col <= cols

    popups = root.findall("./popup_windows/pu")
    assert {popup.get("pu_name") for popup in popups} == POPUP_NAMES

    referenced_popups = {
        stat.get("popup")
        for stat in profiles[0].iter("stat")
        if stat.get("popup") not in (None, "", "default")
    }
    assert referenced_popups == POPUP_NAMES


def test_plo4_hud_package_stays_in_sync_with_shipped_config() -> None:
    package_root = ET.parse(PACKAGE).getroot()
    config_root = ET.parse(SHIPPED_CONFIG).getroot()

    package_profile = _named_element(package_root, "./ss", "name", PROFILE_NAME)
    config_profile = _named_element(config_root, "./stat_sets/ss", "name", PROFILE_NAME)
    assert _normalized_element(package_profile) == _normalized_element(config_profile)

    for popup_name in POPUP_NAMES:
        package_popup = _named_element(package_root, "./popup_windows/pu", "pu_name", popup_name)
        config_popup = _named_element(config_root, "./popup_windows/pu", "pu_name", popup_name)
        assert _normalized_element(package_popup) == _normalized_element(config_popup)
