"""The Basic, Advanced and Dynamic reference HUD packages (issue #332).

A HUD package is only a product if it imports cleanly, points at things that
exist, and does what its name says. These tests hold the issue's acceptance
criteria against the real shipped files:

* every reference package ships and is importable through the existing workflow;
* every stat name and every popup reference resolves, with no hand-editing of
  XML -- a broken reference is a permanently empty cell, which is the failure
  mode this exists to prevent;
* the Advanced package opens the shipped hierarchical popup library;
* the Dynamic packages carry a block for *every* panel the shipped resolver
  can select, and enables the rules for its own profile only, so importing it
  does not turn dynamic panels on for anybody else's HUD;
* no package binds itself to a game: importing one never silently replaces the
  profile a user already runs.
"""

from __future__ import annotations

from pathlib import Path

import defusedxml.minidom
import pytest

from fpdb_3_legacy import Stats, hud_situation, popup_packs
from fpdb_3_legacy.Configuration import parse_hud_panel_rules
from fpdb_3_legacy.hud_package import (
    install_missing_hud_package,
    merge_package_panel_rules,
)

PACKAGE_DIR = Path(__file__).parent.parent / "hud-packages"
BASIC = PACKAGE_DIR / "nlhe_6max_basic.fpdbhud"
ADVANCED = PACKAGE_DIR / "nlhe_6max_advanced.fpdbhud"
DYNAMIC = PACKAGE_DIR / "nlhe_6max_dynamic.fpdbhud"
PLO_DYNAMIC = PACKAGE_DIR / "plo_6max_dynamic.fpdbhud"
PACKAGES = (BASIC, ADVANCED, DYNAMIC, PLO_DYNAMIC)

# The profile each package installs as its primary block.
PRIMARY = {
    BASIC: "nlhe_6max_basic",
    ADVANCED: "nlhe_6max_advanced",
    DYNAMIC: "nlhe_6max_dynamic",
    PLO_DYNAMIC: "plo_6max_dynamic",
}

_VALID_STATS = frozenset(Stats.get_valid_stats().keys())


def _root(path: Path):
    return defusedxml.minidom.parse(str(path)).documentElement


def _profiles(root) -> list:
    """The stat sets a package installs, in document order."""
    return [node for node in root.childNodes if getattr(node, "tagName", "") == "ss"]


def _panels(profile) -> list:
    """The ``<block>`` panels of one profile, in document order."""
    return [node for node in profile.childNodes if getattr(node, "tagName", "") == "block"]


def _grids(root) -> list:
    """Every stat grid a package ships.

    A profile that groups its stats into ``<block>`` panels ships one grid per
    panel; a flat profile is a single grid. A resolver can only select a panel
    the *active* stat set contains (#298), so both shapes are checked the same
    way here rather than assuming one.
    """
    grids: list = []
    for profile in _profiles(root):
        grids.extend(_panels(profile) or [profile])
    return grids


def _defined_popups(root) -> set[str]:
    return {node.getAttribute("pu_name") for node in root.getElementsByTagName("pu")}


def _library_popup_names() -> set[str]:
    """Every popup the shipped popup-pack library defines (#299)."""
    registry = popup_packs.load_default_registry()
    names: set[str] = set()
    for pack_name in registry.names():
        names |= set(registry.packs[pack_name].nodes)
    return names


# ---------------------------------------------------------------------------
# The packages themselves.
# ---------------------------------------------------------------------------


def test_the_reference_packages_ship() -> None:
    assert {path.name for path in PACKAGES if path.exists()} == {
        "nlhe_6max_basic.fpdbhud",
        "nlhe_6max_advanced.fpdbhud",
        "nlhe_6max_dynamic.fpdbhud",
        "plo_6max_dynamic.fpdbhud",
    }


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_a_package_is_well_formed(path: Path) -> None:
    root = _root(path)
    assert root.tagName == "fpdb_hud_package"
    profiles = _profiles(root)
    assert profiles, "a package must carry at least one profile"
    # The first profile is the one the importer installs as the user's choice.
    assert profiles[0].getAttribute("name") == PRIMARY[path]
    for grid in _grids(root):
        rows, cols = int(grid.getAttribute("rows")), int(grid.getAttribute("cols"))
        cells = grid.getElementsByTagName("stat")
        where = grid.getAttribute("name") or grid.getAttribute("label")
        assert len(cells) == rows * cols, f"{where}: {len(cells)} cells for a {rows}x{cols} grid"
        coordinates = [cell.getAttribute("_rowcol") for cell in cells]
        assert len(set(coordinates)) == len(coordinates), f"{where}: two cells share a position"


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_every_stat_a_package_names_actually_exists(path: Path) -> None:
    root = _root(path)
    problems: list[str] = []
    for cell in root.getElementsByTagName("stat"):
        name = cell.getAttribute("_stat_name")
        if name not in _VALID_STATS:
            problems.append(name)
    for row in root.getElementsByTagName("pu_stat"):
        # A navigation row's "stat" is the text it shows, not a statistic.
        if row.getAttribute("pu_stat_submenu"):
            continue
        name = row.getAttribute("pu_stat_name")
        if name not in _VALID_STATS:
            problems.append(name)
    assert problems == []


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_every_popup_reference_resolves(path: Path) -> None:
    """A package may define its popups or link into the shipped library."""
    root = _root(path)
    available = _defined_popups(root) | _library_popup_names()
    referenced = {
        cell.getAttribute("popup") for cell in root.getElementsByTagName("stat") if cell.getAttribute("popup")
    }
    for row in root.getElementsByTagName("pu_stat"):
        submenu = row.getAttribute("pu_stat_submenu")
        if submenu:
            referenced.add(submenu)
    assert referenced <= available, f"unresolved: {sorted(referenced - available)}"


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_no_package_binds_itself_to_a_game(path: Path) -> None:
    """Safe defaults: a reference HUD never replaces the user's configuration."""
    root = _root(path)
    assert root.getElementsByTagName("game") == []
    assert root.getElementsByTagName("hud_profile_rule") == []


# ---------------------------------------------------------------------------
# The Basic package.
# ---------------------------------------------------------------------------


def test_basic_is_a_compact_native_only_block() -> None:
    """No analytics definition: the starter HUD must work on a fresh database."""
    root = _root(BASIC)
    (profile,) = _profiles(root)
    assert _panels(profile) == [], "the Basic package is one flat grid"
    (block,) = _grids(root)
    names = {cell.getAttribute("_stat_name") for cell in block.getElementsByTagName("stat")}
    assert {"n", "vpip", "pfr", "three_B", "f_3bet", "cb1", "f_cb1"} <= names
    assert all(cell.getAttribute("data_source") == "" for cell in block.getElementsByTagName("stat"))
    # Every cell carries a tooltip and a sample-aware colour, which is what
    # makes it readable rather than merely present.
    for cell in block.getElementsByTagName("stat"):
        assert cell.getAttribute("tip")
        assert cell.getAttribute("popup")


# ---------------------------------------------------------------------------
# The Advanced package.
# ---------------------------------------------------------------------------


def test_advanced_opens_the_shipped_popup_library() -> None:
    root = _root(ADVANCED)
    library = _library_popup_names()
    referenced = {
        cell.getAttribute("popup") for cell in root.getElementsByTagName("stat") if cell.getAttribute("popup")
    }
    # The headline entry points: preflop, single-raised, 3-bet and 4-bet pots.
    assert {"preflop_three_bet", "preflop_facing_three_bet", "srp", "threebet_pot", "fourbet_pot"} <= referenced
    assert referenced <= library | _defined_popups(root)


def test_advanced_navigates_between_pot_types_from_its_own_popup() -> None:
    root = _root(ADVANCED)
    core = next(
        pu for pu in root.getElementsByTagName("pu") if pu.getAttribute("pu_name") == "nlhe6_advanced_core"
    )
    submenus = {
        row.getAttribute("pu_stat_submenu")
        for row in core.getElementsByTagName("pu_stat")
        if row.getAttribute("pu_stat_submenu")
    }
    assert {"analytics", "preflop", "srp", "threebet_pot", "fourbet_pot"} <= submenus


def test_advanced_has_position_specific_preflop_analysis() -> None:
    root = _root(ADVANCED)
    opens = next(
        pu for pu in root.getElementsByTagName("pu") if pu.getAttribute("pu_name") == "nlhe6_advanced_opens"
    )
    names = {row.getAttribute("pu_stat_name") for row in opens.getElementsByTagName("pu_stat")}
    assert {"rfi_total", "rfi_early_position", "rfi_middle_position", "rfi_late_position"} <= names
    # And the core popup reaches it, rather than defining it into a dead end.
    core = next(
        pu for pu in root.getElementsByTagName("pu") if pu.getAttribute("pu_name") == "nlhe6_advanced_core"
    )
    assert "nlhe6_advanced_opens" in {
        row.getAttribute("pu_stat_submenu") for row in core.getElementsByTagName("pu_stat")
    }


# ---------------------------------------------------------------------------
# The Dynamic package.
# ---------------------------------------------------------------------------


def _shipped_panels() -> set[str]:
    """Every panel the shipped rule library can select, fallback included."""
    rules, fallback = hud_situation.load_directory(hud_situation.default_rules_dir())
    return {rule.panel for rule in rules} | {fallback}


def test_dynamic_ships_a_panel_for_every_panel_the_resolver_selects() -> None:
    """Every advertised rule has something to show, or it is not advertised.

    The panels are blocks of one profile and not profiles of their own: the
    renderer resolves against the *active* stat set's blocks, so a panel
    shipped as a separate stat set could never be selected at all.
    """
    root = _root(DYNAMIC)
    (profile,) = _profiles(root)
    assert profile.getAttribute("name") == PRIMARY[DYNAMIC]
    assert profile.parentNode is root
    ids = {panel.getAttribute("id") for panel in _panels(profile)}
    assert ids == _shipped_panels()
    # The resolver matches a rule against the block's id, which is why the
    # label is free to be a human title rather than a second copy of the id
    # (#370). Keying the panels by their ids is what makes that possible.
    assert all(panel.getAttribute("id") for panel in _panels(profile))
    section = root.getElementsByTagName("hud_panel_rules")[0]
    assert section.getAttribute("fallback") == "core"


def test_dynamic_panels_are_hidden_until_a_rule_names_them() -> None:
    """A panel that is not selected must not sit on screen for every seat.

    ``block_visible_for`` shows a block the selection names and otherwise keeps
    the position rule, and a block with no binding is always visible. So a
    panel carries a binding no seat can have, and the fallback carries none.
    """
    root = _root(DYNAMIC)
    (profile,) = _profiles(root)
    panels = {panel.getAttribute("id"): panel for panel in _panels(profile)}
    for label, panel in panels.items():
        position = panel.getAttribute("position")
        if label == "core":
            assert position == ""
            assert hud_situation.block_visible(position, "BTN")
            continue
        assert position == hud_situation.DYNAMIC_ONLY_POSITION
        # No seat reports it, so nothing but a naming rule can show the panel.
        for seat in ("BTN", "SB", "BB", "CO", "MP", "EP", "", 0, "S", "B"):
            assert not hud_situation.block_visible(position, seat), f"{label} shows for {seat!r}"


def test_dynamic_enables_the_shipped_rules_for_its_own_profile_only() -> None:
    section = _root(DYNAMIC).getElementsByTagName("hud_panel_rules")[0]
    assert section.getAttribute("enabled") == "true"
    assert section.getAttribute("source") == hud_situation.BUILTIN_SOURCE
    assert section.getAttribute("profile") == PRIMARY[DYNAMIC]


def test_plo_dynamic_uses_omaha_stats_and_scopes_rules_to_its_own_profile() -> None:
    root = _root(PLO_DYNAMIC)
    section = root.getElementsByTagName("hud_panel_rules")[0]
    assert section.getAttribute("profile") == PRIMARY[PLO_DYNAMIC]
    names = {cell.getAttribute("_stat_name") for cell in root.getElementsByTagName("stat")}
    assert {"limp", "cold_call", "a_freq1", "a_freq2", "a_freq3", "wwsf"} <= names
    assert PRIMARY[PLO_DYNAMIC] != PRIMARY[DYNAMIC]


def test_plo_dynamic_rules_select_omaha_profile_without_affecting_holdem() -> None:
    doc = _config_with_panel_section(PLO_DYNAMIC)
    rules, fallback, enabled = parse_hud_panel_rules(doc)
    resolver = hud_situation.HudSituationResolver(rules, fallback=fallback, enabled=enabled)
    context = hud_situation.HudSituationContext(
        street="flop", pot_type="single_raised", in_position=True, is_preflop_aggressor=True,
    )

    omaha = resolver.resolve(context, PRIMARY[PLO_DYNAMIC], samples={"n": 100})
    holdem = resolver.resolve(context, PRIMARY[DYNAMIC], samples={"n": 100})

    assert "srp_cbet_ip" in omaha.panels
    assert omaha.enabled
    assert holdem.panels == ()
    assert holdem.enabled is False


def test_plo_dynamic_panel_is_visible_with_a_small_sample() -> None:
    rules, fallback, enabled = parse_hud_panel_rules(_config_with_panel_section(PLO_DYNAMIC))
    resolver = hud_situation.HudSituationResolver(rules, fallback=fallback, enabled=enabled)
    context = hud_situation.HudSituationContext(
        street="flop", pot_type="single_raised", in_position=True, is_preflop_aggressor=True,
    )

    selection = resolver.resolve(context, PRIMARY[PLO_DYNAMIC], samples={"n": 5})
    assert "srp_cbet_ip" in selection.panels
    assert "srp_cbet_ip" not in selection.suppressed


def _config_with_panel_section(package: Path):
    doc = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    assert merge_package_panel_rules(doc, _root(package), overwrite=False) is True
    return doc


def test_the_dynamic_section_scopes_the_library_to_the_package_profile() -> None:
    """The whole point: another profile's table keeps its static grid."""
    doc = _config_with_panel_section(DYNAMIC)
    rules, fallback, enabled = parse_hud_panel_rules(doc)
    assert enabled is True and fallback == "core"
    assert rules, "the shipped library should have been loaded"
    assert {rule.profile for rule in rules} == {PRIMARY[DYNAMIC]}

    resolver = hud_situation.HudSituationResolver(rules, fallback=fallback, enabled=enabled)
    context = hud_situation.HudSituationContext(
        street="flop", pot_type="single_raised", in_position=True, is_preflop_aggressor=True,
    )
    mine = resolver.resolve(context, PRIMARY[DYNAMIC], samples={"n": 100})
    others = resolver.resolve(context, "someone_elses_profile")
    assert "srp_cbet_ip" in mine.panels
    assert mine.panels and mine.enabled
    assert others.panels == () and others.enabled is False


def test_the_dynamic_rules_actually_change_panels_with_the_context() -> None:
    """A block per panel is worthless if the rules never select one."""
    doc = _config_with_panel_section(DYNAMIC)
    rules, fallback, enabled = parse_hud_panel_rules(doc)
    resolver = hud_situation.HudSituationResolver(rules, fallback=fallback, enabled=enabled)
    profile = PRIMARY[DYNAMIC]
    flop_cbet = resolver.resolve(
        hud_situation.HudSituationContext(street="flop", pot_type="single_raised", is_preflop_aggressor=True, in_position=True),
        profile,
        samples={"n": 100},
    )
    facing_cbet = resolver.resolve(
        hud_situation.HudSituationContext(
            street="flop", pot_type="single_raised", facing_action="bets", in_position=False,
        ),
        profile,
        samples={"n": 100},
    )
    unknown = resolver.resolve(hud_situation.HudSituationContext(), profile)
    assert "srp_cbet_ip" in flop_cbet.panels
    assert "srp_face_cbet_oop" in facing_cbet.panels
    # Nothing known yet: the shipped `always` rule selects the core panel, so
    # the blocks are never empty and the user always has the headline numbers.
    assert unknown.panels == ("core",)
    assert unknown.enabled is True


def test_merging_panel_rules_is_additive() -> None:
    """A configuration that already has panel rules keeps them."""
    doc = _config_with_panel_section(DYNAMIC)
    before = doc.toxml()
    assert merge_package_panel_rules(doc, _root(DYNAMIC), overwrite=False) is False
    assert doc.toxml() == before
    # One section only, and the caller can still see it.
    assert len(doc.getElementsByTagName("hud_panel_rules")) == 1


def test_the_shipped_disabled_placeholder_does_not_block_the_import() -> None:
    """Every standard configuration already has the empty disabled section.

    It exists so the option is discoverable, not because the user chose it, so
    refusing to import over it left dynamic panels off on essentially every
    install.
    """
    doc = defusedxml.minidom.parseString(
        '<FreePokerToolsConfig><hud_panel_rules enabled="false"/></FreePokerToolsConfig>',
    )
    assert merge_package_panel_rules(doc, _root(DYNAMIC), overwrite=False) is True
    assert len(doc.getElementsByTagName("hud_panel_rules")) == 1
    _rules, _fallback, enabled = parse_hud_panel_rules(doc)
    assert enabled is True


@pytest.mark.parametrize(
    "section",
    [
        '<hud_panel_rules enabled="true"/>',
        '<hud_panel_rules enabled="false"><hud_panel_rule panel="mine" profile="p1"/></hud_panel_rules>',
    ],
    ids=["enabled", "disabled-but-carries-rules"],
)
def test_a_users_own_panel_rules_are_never_replaced(section: str) -> None:
    doc = defusedxml.minidom.parseString(f"<FreePokerToolsConfig>{section}</FreePokerToolsConfig>")
    before = doc.toxml()
    assert merge_package_panel_rules(doc, _root(DYNAMIC), overwrite=False) is False
    assert doc.toxml() == before


def test_a_renamed_import_rewrites_the_panel_rule_scope() -> None:
    """The scope names a profile, so a rename has to travel with it.

    Left behind, the section enables the panels for the profile that already
    existed -- the reason the import renamed at all -- and the profile the user
    just imported resolves no rule.
    """
    doc = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    renamed = {PRIMARY[DYNAMIC]: "nlhe_6max_dynamic (mine)"}
    assert merge_package_panel_rules(
        doc, _root(DYNAMIC), overwrite=False, profile_names=renamed,
    ) is True
    rules, _fallback, enabled = parse_hud_panel_rules(doc)
    assert enabled is True and rules
    assert {rule.profile for rule in rules} == {"nlhe_6max_dynamic (mine)"}


def test_a_package_without_panel_rules_changes_nothing() -> None:
    doc = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    assert merge_package_panel_rules(doc, _root(BASIC), overwrite=False) is False
    assert doc.getElementsByTagName("hud_panel_rules") == []


# ---------------------------------------------------------------------------
# Importing: what the user ends up with.
# ---------------------------------------------------------------------------


def _absent_config() -> object:
    return defusedxml.minidom.parseString("<FreePokerToolsConfig/>")


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_an_import_installs_the_package_without_touching_anything_else(path: Path) -> None:
    """Round trip through the same merge helpers the GUI import calls."""
    doc = _absent_config()
    doc.documentElement.appendChild(
        defusedxml.minidom.parseString(
            '<ss name="my_own_profile" rows="1" cols="1" style="default">'
            '<stat _rowcol="(1,1)" _stat_name="n"/></ss>',
        ).documentElement,
    )
    assert install_missing_hud_package(doc, _root(path)) is True

    installed = {node.getAttribute("name") for node in doc.getElementsByTagName("ss")}
    assert PRIMARY[path] in installed
    # The user's own profile is untouched.
    mine = next(node for node in doc.getElementsByTagName("ss") if node.getAttribute("name") == "my_own_profile")
    assert mine.getAttribute("rows") == "1"
    assert len(mine.getElementsByTagName("stat")) == 1


def test_importing_the_dynamic_package_twice_does_not_stack_sections() -> None:
    doc = _absent_config()
    install_missing_hud_package(doc, _root(DYNAMIC))
    first = len(doc.getElementsByTagName("ss"))
    merge_package_panel_rules(doc, _root(DYNAMIC), overwrite=False)
    assert len(doc.getElementsByTagName("hud_panel_rules")) == 1
    assert len(doc.getElementsByTagName("ss")) == first


def test_each_package_documents_itself_in_a_comment() -> None:
    """Who it is for, what it shows, what it does not do."""
    for path in PACKAGES:
        head = path.read_text(encoding="utf-8")[:4000]
        assert "Who it is for" in head or "Who it is for:" in head or "How it works" in head
        assert "Known limitations" in head or "Known limitation" in head or "deliberately does not use" in head
