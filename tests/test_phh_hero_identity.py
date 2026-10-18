"""A PHH hero resolves through the room machinery (#423), on a real database.

PHH hands are stored under their own ``Sites`` row. Its configured hero
aliases are read by ``get_hero_player_ids`` the way a room's are, and a hero
profile may link a PHH name with a room's, so the reports group them as one
player. Without configured aliases a PHH hero is no one: each file's ``_hero``
is flagged hero, and those are not one player.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.phh_import import PHH_SITE_NAME, ensure_phh_site


@pytest.fixture
def db(fresh_db):
    ensure_phh_site(fresh_db)
    return fresh_db


def player(db, name: str, site: str, hero: bool = False) -> int:
    site_id = db.get_site_id(site)[0][0]
    return int(db.insertPlayer(name, site_id, hero))


def test_configured_phh_aliases_are_its_hero(db) -> None:
    jeje = player(db, "jeje", PHH_SITE_NAME)
    jeje76 = player(db, "jeje76", PHH_SITE_NAME)
    player(db, "villain", PHH_SITE_NAME)
    db.config.set_data_source_hero_aliases(PHH_SITE_NAME, ["jeje", "jeje76", "never_imported"])

    assert db.get_hero_player_ids(PHH_SITE_NAME) == sorted([jeje, jeje76])


def test_without_aliases_the_files_heroes_are_not_one_hero(db) -> None:
    db.config.set_data_source_hero_aliases(PHH_SITE_NAME, [])
    player(db, "alice", PHH_SITE_NAME, hero=True)  # one file's _hero
    player(db, "bob", PHH_SITE_NAME, hero=True)  # another file's

    assert db.get_hero_player_ids(PHH_SITE_NAME) == []


def test_aliases_name_players_exactly(db) -> None:
    """Names compare byte for byte (#417): an alias is not a case-folded pattern."""
    player(db, "Jeje", PHH_SITE_NAME)
    db.config.set_data_source_hero_aliases(PHH_SITE_NAME, ["jeje"])

    assert db.get_hero_player_ids(PHH_SITE_NAME) == []


def test_a_profile_groups_a_phh_name_with_a_room_name(db) -> None:
    stars = player(db, "jeje", "PokerStars")
    phh = player(db, "jeje_phh", PHH_SITE_NAME)
    player(db, "jeje", "Winamax")  # same name elsewhere, not linked
    db.config.save_hero_profile("Me", [("PokerStars", "jeje"), (PHH_SITE_NAME, "jeje_phh")])

    assert db.get_hero_player_ids(profile="Me") == sorted([stars, phh])
