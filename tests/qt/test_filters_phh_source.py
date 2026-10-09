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
