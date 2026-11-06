"""PHH hands reach the report filters (#381).

PHH is a data source, not a configured room: no ``supported_sites`` entry, no configured
hero. Once its hands are stored, the filters offer it as a site and its players -- the
files' ``_hero`` first -- so the statistics, graphs and viewers can select them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fpdb_3_legacy.Filters import Filters
from fpdb_3_legacy.phh_import import PHH_SITE_ID, PHH_SITE_NAME

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phh"


def test_a_stored_phh_hand_is_selectable_in_the_filters(qtbot, importer, fresh_db, tmp_path) -> None:
    shutil.copy(FIXTURES / "nl_holdem_heads_up.phh", tmp_path / "heads_up.phh")
    assert importer.addImportFile(str(tmp_path / "heads_up.phh"))
    importer.runImport()

    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    assert filters.getSiteIds()[PHH_SITE_NAME] == PHH_SITE_ID
    assert PHH_SITE_NAME in filters.cbSites
    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    assert "Alice on PHH" in entries

    filters.heroList.setCurrentIndex(entries.index("Alice on PHH"))
    assert filters.getSites() == [PHH_SITE_NAME]
    assert filters.getHeroes() == {PHH_SITE_NAME: "Alice"}
    # What the statistics and graph tabs then resolve the selection to.
    player_id = fresh_db.get_player_id(fresh_db.config, PHH_SITE_NAME, "Alice")
    assert player_id is not None
    assert fresh_db.get_player_site_id(int(player_id)) == PHH_SITE_ID


def test_without_phh_hands_the_filters_are_unchanged(qtbot, fresh_db) -> None:
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    assert PHH_SITE_NAME not in filters.getSiteIds()
    assert PHH_SITE_NAME not in filters.cbSites


def test_a_phh_player_who_is_no_hero_is_the_one_the_viewer_filters_on(qtbot, importer, fresh_db, tmp_path) -> None:
    for fixture in ("nl_holdem_heads_up.phh", "nl_holdem_dwan_ivey.phh"):
        shutil.copy(FIXTURES / fixture, tmp_path / fixture)
        assert importer.addImportFile(str(tmp_path / fixture))
    importer.runImport()
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    filters.heroList.setCurrentIndex(entries.index("Tom Dwan on PHH"))
    dwan = int(fresh_db.get_player_id(fresh_db.config, PHH_SITE_NAME, "Tom Dwan"))
    # Not Alice, the file's hero: the Hand Viewer's player filter is the selected player.
    assert filters.get_hero_ids(filters.getHeroes()) == [dwan]
    assert f"hp.playerId IN ({dwan})" in filters.replace_placeholders_with_filter_values("<player_test>")


def test_the_filters_refresh_for_the_phh_player_selected(qtbot, importer, fresh_db, tmp_path) -> None:
    """Alice, a file's hero, plays hold'em; Bryce Yockey triple draw: his games are offered."""
    for fixture in ("nl_holdem_heads_up.phh", "triple_draw_yockey_arieh.phh"):
        shutil.copy(FIXTURES / fixture, tmp_path / fixture)
        assert importer.addImportFile(str(tmp_path / fixture))
    importer.runImport()
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True, "Games": True, "Currencies": True})
    qtbot.addWidget(filters)

    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    filters.heroList.setCurrentIndex(entries.index("Bryce Yockey on PHH"))
    filters.update_filters_for_hero()

    assert filters.games == ["27_3draw"]
    assert filters.getGames() == ["27_3draw"]


def test_a_player_name_containing_on_is_still_selectable(qtbot, importer, fresh_db, tmp_path) -> None:
    """A player's name is an arbitrary string: "Alice on Call" is not a "name on site" label.

    The refresh parsed the combo's display text, so "Alice on Call on PHH" split into three
    parts and raised before any filter was updated.
    """
    text = (FIXTURES / "nl_holdem_heads_up.phh").read_text(encoding="utf-8")
    text = text.replace('players = ["Alice", "Bob"]', 'players = ["Alice on Call", "Bob"]')
    text = text.replace('_hero = "Alice"', '_hero = "Alice on Call"')
    (tmp_path / "on_call.phh").write_text(text, encoding="utf-8")
    assert importer.addImportFile(str(tmp_path / "on_call.phh"))
    importer.runImport()

    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    filters.heroList.setCurrentIndex(entries.index("Alice on Call on PHH"))
    filters.update_filters_for_hero()

    assert filters.getHeroes() == {PHH_SITE_NAME: "Alice on Call"}
    assert filters.getSites() == [PHH_SITE_NAME]


def _import(importer, tmp_path, *fixtures: str) -> None:
    for fixture in fixtures:
        shutil.copy(FIXTURES / fixture, tmp_path / fixture)
        assert importer.addImportFile(str(tmp_path / fixture))
    importer.runImport()


def _select(filters: Filters, text: str) -> None:
    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    filters.heroList.setCurrentIndex(entries.index(text))


def test_configured_phh_aliases_come_first_and_select_one_hero(qtbot, importer, fresh_db, tmp_path) -> None:
    """#423: the PHH names configured as you are one hero, as a room's aliases are."""
    _import(importer, tmp_path, "nl_holdem_heads_up.phh", "nl_holdem_dwan_ivey.phh")
    fresh_db.config.set_data_source_hero_aliases(PHH_SITE_NAME, ["Tom Dwan", "Alice"])
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    phh_entries = [
        filters.heroList.itemText(index)
        for index in range(filters.heroList.count())
        if filters.heroList.itemText(index).endswith(f" on {PHH_SITE_NAME}")
    ]
    assert phh_entries[:2] == ["Tom Dwan on PHH", "Alice on PHH"]
    assert phh_entries.count("Alice on PHH") == 1

    _select(filters, "Alice on PHH")
    alice = int(fresh_db.get_player_id(fresh_db.config, PHH_SITE_NAME, "Alice"))
    dwan = int(fresh_db.get_player_id(fresh_db.config, PHH_SITE_NAME, "Tom Dwan"))
    assert sorted(filters.get_hero_ids(filters.getHeroes())) == sorted([alice, dwan])
    assert sorted(filters._player_ids_for(PHH_SITE_NAME, "Alice")) == sorted([alice, dwan])


def test_a_phh_player_who_is_no_alias_is_still_read_by_name(qtbot, importer, fresh_db, tmp_path) -> None:
    _import(importer, tmp_path, "nl_holdem_heads_up.phh", "nl_holdem_dwan_ivey.phh")
    fresh_db.config.set_data_source_hero_aliases(PHH_SITE_NAME, ["Tom Dwan", "Alice"])
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)

    _select(filters, "Bob on PHH")
    bob = int(fresh_db.get_player_id(fresh_db.config, PHH_SITE_NAME, "Bob"))
    assert filters.get_hero_ids(filters.getHeroes()) == [bob]
    assert filters._player_ids_for(PHH_SITE_NAME, "Bob") == [bob]


def test_a_profile_link_names_the_hero_of_a_phh_hand(qtbot, importer, fresh_db, tmp_path) -> None:
    """A PHH profile link need not also be a PHH alias: the Hand Viewer keeps the hand.

    Selecting a profile empties getHeroes(), so the hero came only from the source's
    aliases: a hand naming the profile's PHH player got none and was dropped.
    """
    from types import SimpleNamespace

    _import(importer, tmp_path, "nl_holdem_dwan_ivey.phh")
    fresh_db.config.set_data_source_hero_aliases(PHH_SITE_NAME, [])
    fresh_db.config.save_hero_profile("Me", [(PHH_SITE_NAME, "Tom Dwan")])
    filters = Filters(fresh_db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)
    _select(filters, "[Profile] Me")
    hand = SimpleNamespace(players=[(1, "Phil Ivey", 0), (2, "Tom Dwan", 0)])

    assert filters.getHeroes() == {}
    assert filters.get_hero_for_site(PHH_SITE_NAME, hand) == "Tom Dwan"
