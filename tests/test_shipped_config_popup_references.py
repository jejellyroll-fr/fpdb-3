"""Every popup a shipped stat set points at has to exist in that same file.

The two configurations are shipped independently: `HUD_config.xml` is what the
packaged builds carry, and `HUD_config.xml.example` is what a fresh install is
copied from. A stat set added to one and its popups added only to the other
leaves dangling references, and `Aux_Hud` looks popups up with a plain
`config.popup_windows[name]` -- so the first right-click on that stat raises
KeyError rather than degrading.

Checking both files with the same rule is what keeps them from drifting apart.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import defusedxml.ElementTree
import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ("HUD_config.xml", "HUD_config.xml.example")


def _popups(root: ET.Element) -> tuple[set[str], dict[str, set[str]]]:
    defined = {pu.get("pu_name") for pu in root.findall(".//pu") if pu.get("pu_name")}
    referenced: dict[str, set[str]] = {}
    for stat_set in root.findall(".//stat_sets/ss"):
        name = stat_set.get("name") or "<unnamed>"
        for stat in stat_set.iter("stat"):
            popup = stat.get("popup")
            if popup:
                referenced.setdefault(name, set()).add(popup)
    return defined, referenced


@pytest.mark.parametrize("config_name", CONFIGS)
def test_no_stat_set_points_at_a_missing_popup(config_name: str) -> None:
    root = defusedxml.ElementTree.parse(ROOT / config_name).getroot()
    defined, referenced = _popups(root)

    dangling = {
        stat_set: sorted(popups - defined) for stat_set, popups in referenced.items() if popups - defined
    }

    assert not dangling, f"{config_name} references popups it does not define: {dangling}"


@pytest.mark.parametrize("config_name", CONFIGS)
def test_every_bound_stat_set_and_aux_window_exists(config_name: str) -> None:
    root = defusedxml.ElementTree.parse(ROOT / config_name).getroot()
    stat_sets = {ss.get("name") for ss in root.findall(".//stat_sets/ss")}
    aux_windows = {aw.get("name") for aw in root.findall(".//aw")}

    missing_stat_sets: list[str] = []
    missing_aux: list[str] = []
    for game in root.findall(".//supported_games/game"):
        for bound in game.findall("./game_stat_set"):
            name = bound.get("stat_set")
            if name and name not in stat_sets:
                missing_stat_sets.append(f"{game.get('game_name')} -> {name}")
        for aux in (game.get("aux") or "").split(","):
            aux = aux.strip()
            if aux and aux not in aux_windows:
                missing_aux.append(f"{game.get('game_name')} -> {aux}")

    assert not missing_stat_sets, f"{config_name} binds unknown stat sets: {missing_stat_sets}"
    assert not missing_aux, f"{config_name} binds unknown aux windows: {missing_aux}"
