"""Offscreen GUI checks for the spot-first Study Explorer (#360)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
from fpdb_3_legacy.research_studies import builtin_studies

pytestmark = pytest.mark.qt


@pytest.fixture
def explorer(qtbot, tmp_path):
    widget = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(widget)
    return widget


def _select(explorer: GuiStudyExplorer, study_id: str) -> None:
    for row in range(explorer.study_list.count()):
        if explorer.study_list.item(row).data(256) == study_id:
            explorer.study_list.setCurrentRow(row)
            return
    raise AssertionError(f"study {study_id} is not visible")


def test_landing_page_exposes_spot_categories_and_no_metric_builder(explorer) -> None:
    labels = [button.text().split("\n", 1)[0] for button in explorer.category_box.findChildren(type(explorer.open_button))]

    assert "Preflop" in labels
    assert "Single-Raised Pots" in labels
    assert explorer.search_edit.placeholderText().startswith("Try:")
    assert not hasattr(explorer, "metric_combo")


def test_search_finds_common_poker_alias(explorer, qtbot) -> None:
    explorer.search_edit.setText("c-bet")
    qtbot.waitUntil(lambda: explorer.study_list.count() > 0)

    assert any("c-bet" in explorer.study_list.item(row).text().lower() for row in range(explorer.study_list.count()))


def test_category_navigation_is_generated_from_registry(explorer) -> None:
    explorer.game_combo.setCurrentIndex(explorer.game_combo.findData("holdem"))
    buttons = explorer.category_box.findChildren(type(explorer.open_button))
    next(button for button in buttons if button.text().startswith("3-bet Pots")).click()

    assert explorer.study_list.count() == 2
    assert all("3-bet pot" in explorer.study_list.item(row).text().lower() for row in range(explorer.study_list.count()))


def test_choosing_omaha_lists_plo_studies_and_no_holdem_only_ones(explorer) -> None:
    """A PLO player sees a PLO hierarchy, not an empty Hold'em one (#368)."""
    explorer.game_combo.setCurrentIndex(explorer.game_combo.findData("omahahi"))
    listed = [
        explorer.model.registry.get(str(explorer.study_list.item(row).data(256)))
        for row in range(explorer.study_list.count())
    ]

    assert listed
    assert all(study.game == "omahahi" for study in listed)
    assert any(study.id.startswith("plo_srp") for study in listed)
    spots = {
        button.text().split("\n", 1)[0]
        for button in explorer.category_box.findChildren(type(explorer.open_button))
        if button.isEnabled()
    }
    assert {"Preflop", "Single-Raised Pots", "3-bet Pots"} <= spots


def test_the_game_list_offers_the_tokens_the_database_stores(explorer) -> None:
    """The old list offered 'omaha', which no hand is ever categorised as."""
    values = [explorer.game_combo.itemData(index) for index in range(explorer.game_combo.count())]

    assert None in values
    assert "holdem" in values
    assert "omahahi" in values
    assert "omaha" not in values


def test_open_emits_study_with_inherited_context_and_adds_recent(explorer, qtbot) -> None:
    _select(explorer, "srp_pfr_ip_flop")
    explorer.game_combo.setCurrentText("Hold'em")
    explorer.format_combo.setCurrentText("Cash games")
    explorer.subject_combo.setCurrentText("Hero")
    explorer.player_edit.setText("Hero")
    explorer.stake_min_edit.setText("10")
    explorer.date_from_edit.setText("2026-01-01")

    with qtbot.waitSignal(explorer.study_opened, timeout=1000) as signal:
        explorer.open_button.click()

    selection = signal.args[0]
    assert selection.study.id == "srp_pfr_ip_flop"
    assert selection.effective_filters["hero"] is True
    assert selection.effective_filters["tournament"] is False
    assert selection.effective_filters["player"] == "Hero"
    assert selection.effective_filters["stake_bb"] == [10.0, None]
    assert selection.effective_filters["date_from"] == "2026-01-01"
    assert explorer.recent_list.count() == 1


def test_recent_studies_restore_in_a_new_widget(explorer, qtbot, tmp_path) -> None:
    _select(explorer, "preflop_rfi")
    explorer.open_button.click()
    qtbot.waitUntil(lambda: explorer.recent_list.count() == 1)

    restored = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(restored)
    assert restored.recent_list.count() == 1
    assert restored.recent_list.item(0).text() == "Preflop · First in"


def test_choosing_a_recent_study_reveals_detail_when_stacked(explorer, qtbot) -> None:
    _select(explorer, "preflop_rfi")
    explorer.open_button.click()
    qtbot.waitUntil(lambda: explorer.recent_list.count() == 1)
    explorer.show()
    explorer.resize(700, 640)
    qtbot.wait(20)
    explorer.pane_switcher.set_active(0)
    item = explorer.recent_list.item(0)
    explorer.recent_list.setCurrentItem(item)

    explorer.recent_list.itemClicked.emit(item)

    assert explorer.pane_switcher.active() == 2


def test_custom_advanced_research_remains_reachable(explorer, qtbot) -> None:
    called = []
    explorer.advanced_requested.connect(lambda: called.append(True))

    explorer.advanced_button.click()

    assert called == [True]


def test_biggest_differences_entry_point_is_reachable(explorer, qtbot) -> None:
    called = []
    explorer.differences_requested.connect(lambda: called.append(True))

    explorer.differences_button.click()

    assert called == [True]
