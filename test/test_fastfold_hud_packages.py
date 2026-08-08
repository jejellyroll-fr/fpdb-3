"""The shipped Fast-Fold HUD packages, and the rule merging that installs them.

A package is only useful if it imports cleanly and then selects itself for the
right tables. These check both, against the real package files.
"""

from __future__ import annotations

from pathlib import Path

import defusedxml.minidom
import pytest

from fpdb_3_legacy import Stats
from fpdb_3_legacy.hud_package import merge_package_profile_rules
from fpdb_3_legacy.hud_profiles import HudContext, HudProfileResolver, HudProfileRule

PACKAGES = sorted((Path(__file__).parent.parent / "hud-packages").glob("*.fpdbhud"))


def _root(path: Path):
    return defusedxml.minidom.parse(str(path)).documentElement


def _rules(doc) -> HudProfileResolver:
    return HudProfileResolver(
        [
            HudProfileRule.from_mapping({n: node.getAttribute(n) for n in node.attributes.keys()}, order)
            for order, node in enumerate(doc.getElementsByTagName("hud_profile_rule"))
        ]
    )


def test_the_packages_are_shipped() -> None:
    assert {p.name for p in PACKAGES} == {"fastfold_nlhe.fpdbhud", "fastfold_plo.fpdbhud"}


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_a_package_is_a_well_formed_importable_profile(path: Path) -> None:
    root = _root(path)
    assert root.tagName == "fpdb_hud_package"

    # The importer takes the first stat set and nothing else, so there must be
    # exactly one, and its grid must be filled.
    stat_sets = root.getElementsByTagName("ss")
    assert len(stat_sets) == 1
    ss = stat_sets[0]
    rows, cols = int(ss.getAttribute("rows")), int(ss.getAttribute("cols"))
    cells = ss.getElementsByTagName("stat")
    assert len(cells) == rows * cols
    assert len({c.getAttribute("_rowcol") for c in cells}) == len(cells)


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_every_stat_a_package_names_actually_exists(path: Path) -> None:
    """A misspelt stat renders as a permanently empty cell, silently."""
    valid = set(Stats.get_valid_stats().keys())
    root = _root(path)

    named = {c.getAttribute("_stat_name") for c in root.getElementsByTagName("stat")}
    in_popups = {s.getAttribute("pu_stat_name") for s in root.getElementsByTagName("pu_stat")}

    assert not (named - valid)
    assert not (in_popups - valid)


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_every_popup_a_package_points_at_is_defined_in_it(path: Path) -> None:
    root = _root(path)
    defined = {p.getAttribute("pu_name") for p in root.getElementsByTagName("pu")}
    referenced = {c.getAttribute("popup") for c in root.getElementsByTagName("stat") if c.getAttribute("popup")}

    assert referenced <= defined


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_a_package_selects_itself_by_speed_not_by_game(path: Path) -> None:
    """Binding to the game instead would take over every ordinary cash table."""
    root = _root(path)
    rules = root.getElementsByTagName("hud_profile_rule")
    assert rules, "a Fast-Fold package must carry the rule that scopes it"
    for rule in rules:
        assert rule.getAttribute("speed") == "fast"
    # And it must not quietly repoint the game's own binding.
    assert not root.getElementsByTagName("game")


def _merged_doc() -> object:
    doc = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    for path in PACKAGES:
        merge_package_profile_rules(doc, _root(path), overwrite=True)
    return doc


def test_merged_rules_pick_the_fast_fold_profiles_only_for_fast_tables() -> None:
    resolver = _rules(_merged_doc())

    def resolve(game: str, speed: str):
        return resolver.resolve(HudContext(site="Winamax", game=game, game_type="ring", speed=speed))

    assert resolve("holdem", "fast") == "fastfold_nlhe"
    assert resolve("omahahi", "fast") == "fastfold_plo"
    assert resolve("omahahilo", "fast") == "fastfold_plo"
    # An ordinary table matches no rule, so it keeps its configured binding.
    assert resolve("holdem", "normal") is None
    assert resolve("omahahi", "normal") is None


def test_importing_a_package_twice_does_not_stack_rules() -> None:
    doc = _merged_doc()
    before = len(doc.getElementsByTagName("hud_profile_rule"))

    for path in PACKAGES:
        merge_package_profile_rules(doc, _root(path), overwrite=True)

    assert len(doc.getElementsByTagName("hud_profile_rule")) == before


def test_a_renamed_profile_is_followed_by_its_rule() -> None:
    """The importer renames on conflict; a rule pointing at the old name is dead."""
    doc = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    merge_package_profile_rules(
        doc,
        _root(PACKAGES[0]),
        profile_names={"fastfold_nlhe": "fastfold_nlhe_imported"},
        overwrite=True,
    )

    profiles = {n.getAttribute("profile") for n in doc.getElementsByTagName("hud_profile_rule")}
    assert profiles == {"fastfold_nlhe_imported"}


def test_an_existing_rule_is_kept_when_not_overwriting() -> None:
    doc = _merged_doc()
    for node in doc.getElementsByTagName("hud_profile_rule"):
        node.setAttribute("profile", "my_own_profile")

    merge_package_profile_rules(doc, _root(PACKAGES[0]), overwrite=False)

    profiles = {n.getAttribute("profile") for n in doc.getElementsByTagName("hud_profile_rule")}
    assert profiles == {"my_own_profile"}
