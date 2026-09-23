"""The reference HUDs can be inspected without a poker table (#370)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.hud_presentation import PANEL_TITLES, describe_package, reference_packages
from fpdb_3_legacy.modern_hud_preferences.reference_preview import (
    PACKAGE_ORDER,
    ReferenceHudPreview,
)

pytestmark = pytest.mark.qt


@pytest.fixture
def preview(qtbot) -> ReferenceHudPreview:
    widget = ReferenceHudPreview()
    qtbot.addWidget(widget)
    return widget


def test_all_reference_packages_are_offered(preview) -> None:
    offered = [preview.package_combo.itemData(index) for index in range(preview.package_combo.count())]

    assert offered == [name for name, _label in PACKAGE_ORDER]
    assert set(offered) == set(reference_packages())


def test_a_static_package_previews_its_block_and_has_no_contexts(preview) -> None:
    preview.select_package("basic")

    assert preview.context_ids == ("",)
    assert not preview.context_combo.isEnabled()
    assert "no contextual panels" in preview.description_label.text()
    assert preview.preview.blocks
    assert preview.preview.blocks[0]["stats"]


def test_the_dynamic_package_offers_every_context_by_its_title(preview) -> None:
    preview.select_package("dynamic")
    package = describe_package(reference_packages()["dynamic"])

    contexts = [panel_id for panel_id in preview.context_ids if panel_id]
    assert contexts == [panel.id for panel in package.dynamic_panels]
    labels = [preview.context_combo.itemText(index) for index in range(1, preview.context_combo.count())]
    assert labels == [PANEL_TITLES[panel_id] for panel_id in contexts]


def test_the_plo_dynamic_package_previews_omaha_panels(preview) -> None:
    preview.select_package("plo_dynamic")
    package = describe_package(reference_packages()["plo_dynamic"])

    assert package.name == "plo_6max_dynamic"
    hold_em = {panel.id for panel in describe_package(reference_packages()["dynamic"]).dynamic_panels}
    assert {panel.id for panel in package.dynamic_panels} == hold_em | {
        "postflop_flop", "postflop_turn", "postflop_river",
    }
    assert {stat.name for stat in package.stats} >= {"limp", "cold_call", "a_freq1", "wwsf"}

    preview.select_context("postflop_flop")
    assert [block["label"] for block in preview.preview.blocks] == ["Core", "Flop · Overview"]


def test_choosing_a_context_shows_that_panel_and_says_why(preview) -> None:
    preview.select_package("dynamic")
    preview.select_context("srp_face_cbet_oop")

    title = PANEL_TITLES["srp_face_cbet_oop"]
    assert title in preview.description_label.text()
    assert "resolver has selected" in preview.description_label.text()
    # What a seat actually sees: the block that is always there, plus the one
    # the rule selected.
    assert [block["label"] for block in preview.preview.blocks] == ["Core", title]


def test_going_back_to_rest_hides_the_contextual_panel(preview) -> None:
    preview.select_package("dynamic")
    preview.select_context("fourbet_pot")
    assert [block["label"] for block in preview.preview.blocks] == ["Core", PANEL_TITLES["fourbet_pot"]]

    preview.select_context("")

    assert [block["label"] for block in preview.preview.blocks] == ["Core"]
    assert "no dynamic rule matched" in preview.description_label.text()


def test_the_popup_paths_are_listed_rather_than_clicked_through(preview) -> None:
    preview.select_package("advanced")

    paths = [preview.paths_list.item(row).text() for row in range(preview.paths_list.count())]
    assert paths
    assert any("Single-raised pot" in path for path in paths)
    assert any("->" in path for path in paths), "no path leaves into the shipped library"


def test_the_legend_explains_every_role_without_relying_on_colour(preview) -> None:
    from PySide6.QtWidgets import QLabel

    from fpdb_3_legacy.hud_presentation import ROLE_DESCRIPTIONS

    texts = " ".join(label.text() for label in preview.findChildren(QLabel))

    for role, description in ROLE_DESCRIPTIONS.items():
        assert role in texts
        assert description in texts
    assert "prefix" in texts and "tooltip" in texts


def test_an_unknown_package_or_context_is_refused(preview) -> None:
    with pytest.raises(KeyError):
        preview.select_package("nonexistent")
    preview.select_package("basic")
    with pytest.raises(KeyError):
        preview.select_context("srp_cbet_ip")
