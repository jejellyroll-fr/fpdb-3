"""The reference HUDs keep one presentation contract between them (#370).

Three packages that each work and each look like a different product is three
products. These tests pin the shared rules -- what a colour means, what a thin
sample looks like, what a panel calls itself, what order navigation runs in --
so a package cannot drift away from the other two quietly.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import hud_situation
from fpdb_3_legacy.hud_presentation import (
    PANEL_TITLES,
    POPUP_CONTEXT_STATS,
    ROLE_BACKGROUNDS,
    ROLE_DESCRIPTIONS,
    ROLES,
    SAMPLE_HIGH,
    SAMPLE_LOW,
    SPOT_ORDER,
    describe_package,
    navigation_rows_in_order,
    panel_title,
    popup_paths,
    preview_blocks,
    reference_packages,
    sample_attributes,
    spot_rank,
)

PACKAGES = reference_packages()
NAMES = sorted(PACKAGES)


@pytest.fixture(scope="module", params=NAMES)
def package(request):
    return describe_package(PACKAGES[request.param])


@pytest.fixture(scope="module")
def dynamic():
    return describe_package(PACKAGES["dynamic"])


# -- the contract itself -------------------------------------------------------


def test_every_role_has_a_background_and_an_explanation() -> None:
    assert set(ROLE_BACKGROUNDS) == set(ROLES)
    assert set(ROLE_DESCRIPTIONS) == set(ROLES)
    assert all(description.strip() for description in ROLE_DESCRIPTIONS.values())


def test_a_role_is_never_told_by_colour_alone(package) -> None:
    """Colour is one channel; the prefix and the tooltip are the other two.

    A reader with a colour-blind palette, a screenshot in black and white, or
    a HUD themed by hand still has to be able to tell a sample from a
    frequency.
    """
    for stat in package.stats:
        if stat.name == "playername":
            continue
        assert stat.prefix.strip(), f"{package.name}.{stat.name} has no prefix"
        assert stat.tip.strip(), f"{package.name}.{stat.name} has no tooltip"


def test_the_sample_rule_is_the_same_in_all_three_packages(package) -> None:
    attributes = sample_attributes()
    samples = [stat for stat in package.stats if stat.name == "n"]

    assert samples, f"{package.name} shows no sample at all"
    for stat in samples:
        assert stat.low_threshold == attributes["stat_loth"]
        assert stat.high_threshold == attributes["stat_hith"]
    assert SAMPLE_LOW < SAMPLE_HIGH


def test_every_visible_abbreviation_can_be_expanded(package) -> None:
    assert package.undocumented_stats() == ()


def test_a_cell_that_opens_a_popup_says_so_in_its_tip(package) -> None:
    """A link that looks like a number is a number that never answers."""
    for stat in package.stats:
        if not stat.popup or stat.name == "playername":
            continue
        assert stat.tip.strip(), f"{package.name}.{stat.name} opens {stat.popup} silently"


# -- navigation ----------------------------------------------------------------


def test_navigation_runs_in_the_order_a_hand_is_played(package) -> None:
    for popup in package.popups:
        labels = popup.navigation_labels
        if not labels:
            continue
        assert navigation_rows_in_order(labels), f"{package.name}.{popup.name}: {list(labels)}"


CORE_POPUPS = {
    "nlhe_6max_advanced": "nlhe6_advanced_core",
    "nlhe_6max_dynamic": "nlhe6_dynamic_core",
}


def test_the_spot_menu_names_only_spots_the_contract_ranks(package) -> None:
    """The menu a reader learns is the one that has to be predictable.

    The core popup is the table of contents: every row of it is one of the
    spots in :data:`SPOT_ORDER`, so the reader learns the order once. Rows
    deeper in -- "Flop aggression, Turn, River" -- are a street order inside
    one spot, and the spot table has nothing to say about them.
    """
    name = CORE_POPUPS.get(package.name)
    if name is None:
        pytest.skip(f"{package.name} has no spot menu: its popups are leaves")
    core = package.popup(name)
    assert core is not None
    unknown = [label for label in core.navigation_labels if spot_rank(label) == len(SPOT_ORDER)]

    assert core.navigation_labels
    assert unknown == [], f"{package.name} navigates to unranked spots: {unknown}"


def test_every_popup_link_inside_a_package_resolves(package) -> None:
    for popup in package.popups:
        for label, target in popup.submenus:
            # A target the package does not define is a link into the shipped
            # popup library, which fpdb installs; what must never happen is a
            # link to a popup that exists nowhere.
            assert target.strip(), f"{package.name}.{popup.name}: {label!r} links nowhere"


def test_a_popup_path_never_loops(package) -> None:
    for path in popup_paths(package):
        assert len(set(path)) == len(path), f"{package.name}: {path} revisits a popup"


def test_sibling_popups_do_not_repeat_each_other(dynamic) -> None:
    """Depth is only depth if the next page says something new.

    The core popup's own rows are the headline; a child that repeats them has
    spent a click to show what was already on screen.
    """
    core = dynamic.popup("nlhe6_dynamic_core")
    assert core is not None
    for _label, target in core.submenus:
        child = dynamic.popup(target)
        if child is None:
            continue
        repeated = (set(child.stats) & set(core.stats)) - POPUP_CONTEXT_STATS
        assert not repeated, f"{target} repeats {sorted(repeated)} from the popup above it"


# -- dynamic panels ------------------------------------------------------------


def test_every_dynamic_panel_says_which_spot_it_is_about(dynamic) -> None:
    """``srp_cbet_ip`` names the rule; the reader needs the spot."""
    for panel in dynamic.dynamic_panels:
        assert panel.has_context_label, f"{panel.id} still shows its rule id"
        assert panel.label == PANEL_TITLES[panel.id]


def test_a_panel_title_reads_as_a_path_through_the_hand(dynamic) -> None:
    for panel in dynamic.dynamic_panels:
        # A title, not an identifier: no snake_case, and the parts of the path
        # are separated the way the contract writes them.
        assert "_" not in panel.label, panel.label
        assert panel.label == panel.label.strip()
        assert panel.label[0].isalnum(), panel.label


def test_the_resolver_still_finds_a_renamed_panel(dynamic) -> None:
    """The label became a title, so the id has to carry the identity."""
    for panel in dynamic.dynamic_panels:
        block = {"id": panel.id, "label": panel.label, "position": panel.position}
        assert hud_situation.panel_matches_block(panel.id, block)
        assert not hud_situation.panel_matches_block("not-a-panel", block)


def test_every_shipped_rule_names_a_panel_that_exists(dynamic) -> None:
    ids = {panel.id for panel in dynamic.panels}
    rules, fallback = hud_situation.load_directory(hud_situation.default_rules_dir())

    assert fallback in ids
    for rule in rules:
        assert rule.panel in ids, f"a shipped rule names the missing panel {rule.panel!r}"


def test_no_contextual_panel_is_accidentally_always_visible(dynamic) -> None:
    for panel in dynamic.dynamic_panels:
        assert panel.position == hud_situation.DYNAMIC_ONLY_POSITION
        for seat in ("BTN", "SB", "BB", "CO", "MP", "EP", "", 0):
            assert not hud_situation.block_visible(panel.position, seat)


def test_panel_titles_cover_every_shipped_panel(dynamic) -> None:
    assert {panel.id for panel in dynamic.panels} <= set(PANEL_TITLES)
    assert panel_title("something_new") == "Something New"


# -- the preview ---------------------------------------------------------------


def test_the_resting_preview_shows_no_contextual_panel(package) -> None:
    blocks = preview_blocks(package)

    assert blocks, f"{package.name} previews as nothing at all"
    dynamic_ids = {panel.id for panel in package.dynamic_panels}
    assert all(block["label"] not in dynamic_ids for block in blocks)


def test_a_previewed_context_adds_exactly_one_panel(dynamic) -> None:
    """A seat sees what is always there plus the one panel the rule picked."""
    resting = [panel.id for panel in dynamic.panels if not panel.is_dynamic]
    with_context = preview_blocks(dynamic, [*resting, "srp_cbet_ip"])

    assert len(with_context) == len(resting) + 1
    assert with_context[-1]["label"] == PANEL_TITLES["srp_cbet_ip"]
    assert [block["label"] for block in preview_blocks(dynamic)] == ["Core"]


def test_a_preview_cell_carries_the_tip_the_table_would_show(package) -> None:
    for block in preview_blocks(package):
        for cell in block["stats"]:
            if cell["stat"] == "playername":
                continue
            assert cell["tip"].strip(), f"{package.name}.{cell['stat']} previews without a tip"


def test_preview_rows_are_zero_based_for_the_widget(package) -> None:
    for block in preview_blocks(package):
        for cell in block["stats"]:
            assert cell["row"] >= 0
            assert cell["col"] >= 0


# -- import and export ---------------------------------------------------------


def test_every_package_documents_its_own_hierarchy(package) -> None:
    """A package explains itself to whoever opens the file."""
    assert package.comment.strip()
    assert len(package.comment.splitlines()) > 5


# -- the screenshots -----------------------------------------------------------


def test_every_featured_context_is_a_panel_that_exists(dynamic) -> None:
    """A screenshot of a panel the package does not have is a stale document."""
    from tools.render_reference_huds import FEATURED_CONTEXTS

    ids = {panel.id for panel in dynamic.dynamic_panels}
    assert set(FEATURED_CONTEXTS) <= ids


def test_the_design_system_shows_a_picture_that_exists() -> None:
    """Every image the design system references is on disk under its own name."""
    import re
    from pathlib import Path

    docs = Path(__file__).resolve().parents[1] / "docs"
    referenced = set(
        re.findall(
            r"\(images/(reference-huds/[^)]+\.png)\)",
            (docs / "hud-design-system.md").read_text(encoding="utf-8"),
        )
    )

    assert referenced, "the design system shows no pictures at all"
    missing = sorted(name for name in referenced if not (docs / "images" / name).exists())
    assert missing == []


def test_the_design_system_documents_every_role_and_the_sample_rule() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs" / "hud-design-system.md").read_text(encoding="utf-8")

    for role in ROLES:
        assert role in text, f"the design system does not explain the {role!r} role"
    assert str(SAMPLE_LOW) in text
    assert str(SAMPLE_HIGH) in text
    for spot in SPOT_ORDER:
        assert spot in text, f"the navigation order omits {spot!r}"
