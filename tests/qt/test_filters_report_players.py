"""The reports read the players the filters and the Hand Viewer read (#434).

Graphs, sessions, the opponents report, the tourney graph and statistics and the
ring statistics all resolve their players through ``Filters.get_selected_players``.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Filters import Filters

pytestmark = pytest.mark.qt


@pytest.fixture
def rooms(fresh_db) -> tuple[str, str]:
    """Two configured rooms, whichever the test configuration enables."""
    sites = fresh_db.config.get_supported_sites()
    if len(sites) < 2:
        pytest.skip("the test configuration enables fewer than two rooms")
    return sites[0], sites[1]


def player(db, name: str, site: str) -> int:
    """Insert a player, committed: building the filters ends their read transaction."""
    player_id = int(db.insertPlayer(name, db.get_site_id(site)[0][0], False))
    db.commit()
    return player_id


def make_filters(qtbot, db) -> Filters:
    filters = Filters(db, {"Heroes": True, "Sites": True})
    qtbot.addWidget(filters)
    return filters


def select(filters: Filters, label: str) -> None:
    entries = [filters.heroList.itemText(index) for index in range(filters.heroList.count())]
    filters.heroList.setCurrentIndex(entries.index(label))
    filters.update_filters_for_hero()


def player_test_ids(filters: Filters) -> set[int]:
    """The players the Hand Viewer's ``<player_test>`` reads."""
    clause = filters.replace_placeholders_with_filter_values("<player_test>")
    return {int(pid) for pid in clause.partition("IN (")[2].rstrip(")").split(",") if pid}


def test_a_room_alias_reads_the_whole_alias_group(qtbot, fresh_db, rooms) -> None:
    room, _ = rooms
    current = player(fresh_db, "alice", room)
    old = player(fresh_db, "alice_old", room)
    player(fresh_db, "bob", room)
    fresh_db.config.set_hero_aliases(room, ["alice", "alice_old"])
    filters = make_filters(qtbot, fresh_db)

    select(filters, f"alice_old on {room}")

    assert filters.get_selected_players() == [(room, current), (room, old)]
    assert player_test_ids(filters) == {current, old}


def test_a_hero_profile_reaches_the_reports(qtbot, fresh_db, rooms) -> None:
    """getHeroes() is empty for a profile: the reports used to skip every site."""
    first, second = rooms
    alice = player(fresh_db, "alice", first)
    alice2 = player(fresh_db, "alice2", second)
    player(fresh_db, "bob", first)
    fresh_db.config.set_hero_aliases(first, ["alice"])
    fresh_db.config.save_hero_profile("Me", [(first, "alice"), (second, "alice2")])
    filters = make_filters(qtbot, fresh_db)
    select(filters, f"alice on {first}")  # leaves only the first room checked

    select(filters, "[Profile] Me")

    assert filters.getHeroes() == {}
    assert sorted(filters.getSites()) == sorted([first, second])
    assert sorted(filters.get_selected_players()) == sorted([(first, alice), (second, alice2)])
    assert player_test_ids(filters) == {alice, alice2}


def test_a_profile_reads_only_the_sites_still_checked(qtbot, fresh_db, rooms) -> None:
    first, second = rooms
    alice = player(fresh_db, "alice", first)
    player(fresh_db, "alice2", second)
    fresh_db.config.save_hero_profile("Me", [(first, "alice"), (second, "alice2")])
    filters = make_filters(qtbot, fresh_db)
    select(filters, "[Profile] Me")

    filters.cbSites[second].setChecked(False)

    assert filters.get_selected_players() == [(first, alice)]
