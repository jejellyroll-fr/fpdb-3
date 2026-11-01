"""The reports read the players the filters read (#434), on a real database.

A room's alias selected in a report stands for every hero alias configured there,
as it already did in the filters and the Hand Viewer, and a hero profile reaches
the reports through ``get_hero_player_ids_by_site``.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.phh_import import PHH_SITE_NAME, ensure_phh_site


@pytest.fixture
def db(fresh_db):
    ensure_phh_site(fresh_db)
    return fresh_db


@pytest.fixture
def room(db) -> str:
    """A configured room, whichever the test configuration enables."""
    sites = db.config.get_supported_sites()
    if not sites:
        pytest.skip("the test configuration enables no room")
    return sites[0]


def player(db, name: str, site: str, hero: bool = False) -> int:
    site_id = db.get_site_id(site)[0][0]
    return int(db.insertPlayer(name, site_id, hero))


def test_a_room_alias_stands_for_every_alias_configured_there(db, room) -> None:
    current = player(db, "alice", room)
    old = player(db, "alice_old", room)
    player(db, "bob", room)
    db.config.set_hero_aliases(room, ["alice", "alice_old"])

    assert db.get_selected_player_ids(room, "alice") == sorted([current, old])
    assert db.get_selected_player_ids(room, "alice_old") == sorted([current, old])


def test_a_room_whose_aliases_are_not_imported_reads_the_name_selected(db, room) -> None:
    """Variant-aware: the hero's account under a site skin still shows."""
    db.config.set_hero_aliases(room, ["yourname"])
    skin = db.get_site_id(PHH_SITE_NAME)[0][0]  # any other site holding the name alone
    elsewhere = int(db.insertPlayer("yourname", skin, False))

    assert db.get_selected_player_ids(room, "yourname") == [elsewhere]


def test_an_unknown_phh_player_is_no_one(db) -> None:
    db.config.set_data_source_hero_aliases(PHH_SITE_NAME, ["koko"])
    player(db, "koko", PHH_SITE_NAME)

    assert db.get_selected_player_ids(PHH_SITE_NAME, "nobody") == []


def test_a_profile_lists_its_players_by_site(db, room) -> None:
    alice = player(db, "alice", room)
    alice_phh = player(db, "alice_phh", PHH_SITE_NAME)
    player(db, "bob", room)
    db.config.save_hero_profile("Me", [(room, "alice"), (PHH_SITE_NAME, "alice_phh"), (room, "never_imported")])

    assert db.get_hero_player_ids_by_site("Me") == {room: [alice], PHH_SITE_NAME: [alice_phh]}
    assert db.get_hero_player_ids(profile="Me") == sorted([alice, alice_phh])
    assert db.get_hero_player_ids_by_site("No such profile") == {}
