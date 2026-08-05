"""One player, several rooms, one identity.

A hero profile ties the screen names someone uses on different sites together
so their hands can be reported as one player's. It lives in the configuration
as a named list of (site, alias) pairs, and saving one has to survive being
saved again under the same name -- which is how the preferences window edits
it -- without leaving the previous version behind.

`delete_hero_profile` is covered alongside, since a profile that cannot be
removed cannot be tested as it is actually used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'


def config_xml(profiles: str = "") -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{profiles}\n"
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(profiles: str = "") -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(config_xml(profiles), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def config(build) -> Any:
    return build()


def saved_profiles(config: Any) -> list[str]:
    """The profile names the document holds, which is what gets written out."""
    return [node.getAttribute("name") for node in config.doc.getElementsByTagName("hero_profile")]


# --------------------------------------------------------------------------
# Saving a profile
# --------------------------------------------------------------------------


def test_a_profile_is_remembered_by_name(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje"), ("Winamax", "jeje76")])

    profile = config.hero_profiles["Me"]
    assert profile.links == [("PokerStars", "jeje"), ("Winamax", "jeje76")]
    assert profile.sites() == ["PokerStars", "Winamax"]


def test_the_profile_reaches_the_document_too(config) -> None:
    # The dictionary is what fpdb reads now; the document is what it reads
    # next time.
    config.save_hero_profile("Me", [("PokerStars", "jeje")])

    assert saved_profiles(config) == ["Me"]


def test_a_configuration_with_no_profiles_section_gains_one(config) -> None:
    assert config.doc.getElementsByTagName("hero_profiles") == []

    config.save_hero_profile("Me", [("PokerStars", "jeje")])

    assert len(config.doc.getElementsByTagName("hero_profiles")) == 1


def test_a_profile_is_not_the_default_unless_asked(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])

    assert config.hero_profiles["Me"].default is False


def test_a_profile_can_be_made_the_default(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")], default=True)

    assert config.hero_profiles["Me"].default is True


def test_the_order_the_rooms_were_given_in_is_kept(config) -> None:
    # Reports list the rooms in this order, so it is the player's choice and
    # not the dictionary's.
    links = [("Winamax", "a"), ("PokerStars", "b"), ("iPoker", "c")]

    config.save_hero_profile("Me", links)

    assert config.hero_profiles["Me"].links == links


def test_the_same_pair_given_twice_is_stored_once(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje"), ("PokerStars", "jeje")])

    assert config.hero_profiles["Me"].links == [("PokerStars", "jeje")]


def test_two_names_on_one_room_are_both_kept(config) -> None:
    # Someone with two accounts on the same room is the reason profiles group
    # by pair rather than by site.
    config.save_hero_profile("Me", [("PokerStars", "day"), ("PokerStars", "night")])

    assert config.hero_profiles["Me"].aliases_by_site() == {"PokerStars": ["day", "night"]}


@pytest.mark.parametrize(
    "incomplete",
    [("", "jeje"), ("PokerStars", ""), ("", "")],
    ids=["no site", "no alias", "neither"],
)
def test_a_link_missing_half_of_itself_is_dropped(config, incomplete) -> None:
    # A pair with a hole in it cannot match a hand to a player.
    config.save_hero_profile("Me", [("Winamax", "kept"), incomplete])

    assert config.hero_profiles["Me"].links == [("Winamax", "kept")]


def test_a_profile_with_no_usable_link_is_still_saved(config) -> None:
    # It is a name someone typed before filling it in, and losing it silently
    # would look like the save failed.
    config.save_hero_profile("Empty", [])

    assert config.hero_profiles["Empty"].links == []
    assert saved_profiles(config) == ["Empty"]


# --------------------------------------------------------------------------
# Saving it again
# --------------------------------------------------------------------------


def test_saving_under_the_same_name_replaces_rather_than_adds(config) -> None:
    # This is what the preferences window does on every edit; keeping both
    # would leave the file growing a copy per save.
    config.save_hero_profile("Me", [("PokerStars", "old")])

    config.save_hero_profile("Me", [("PokerStars", "new")])

    assert saved_profiles(config) == ["Me"]
    assert config.hero_profiles["Me"].links == [("PokerStars", "new")]


def test_replacing_one_profile_leaves_the_others_alone(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])
    config.save_hero_profile("Someone else", [("Winamax", "other")])

    config.save_hero_profile("Me", [("PokerStars", "renamed")])

    assert sorted(saved_profiles(config)) == ["Me", "Someone else"]
    assert config.hero_profiles["Someone else"].links == [("Winamax", "other")]


def test_a_profile_saved_over_an_existing_file_replaces_that_one(build) -> None:
    # The profile came from the file rather than from an earlier save, which
    # is the case on the first edit after fpdb starts.
    existing = (
        "<hero_profiles>"
        '<hero_profile name="Me" default="True"><link site_name="PokerStars" alias="old"/></hero_profile>'
        "</hero_profiles>"
    )
    config = build(existing)
    assert config.hero_profiles["Me"].links == [("PokerStars", "old")]

    config.save_hero_profile("Me", [("PokerStars", "new")])

    assert saved_profiles(config) == ["Me"]
    assert config.hero_profiles["Me"].links == [("PokerStars", "new")]


def test_a_saved_profile_is_read_back_from_the_file(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje"), ("Winamax", "jeje76")], default=True)
    config.save()

    assert config.reload() is True

    profile = config.hero_profiles["Me"]
    assert profile.links == [("PokerStars", "jeje"), ("Winamax", "jeje76")]
    assert profile.default is True


# --------------------------------------------------------------------------
# Removing one
# --------------------------------------------------------------------------


def test_a_profile_can_be_removed(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])

    config.delete_hero_profile("Me")

    assert "Me" not in config.hero_profiles
    assert saved_profiles(config) == []


def test_removing_one_profile_leaves_the_others(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])
    config.save_hero_profile("Someone else", [("Winamax", "other")])

    config.delete_hero_profile("Me")

    assert saved_profiles(config) == ["Someone else"]


def test_removing_a_profile_that_is_not_there_is_quiet(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])

    config.delete_hero_profile("no such profile")

    assert saved_profiles(config) == ["Me"]


def test_removing_from_a_configuration_that_has_no_profiles_is_quiet(config) -> None:
    # Nothing has created the section yet, so there is not even a node to look
    # through.
    assert config.doc.getElementsByTagName("hero_profiles") == []

    config.delete_hero_profile("Me")

    assert config.hero_profiles == {}


def test_a_removal_survives_being_saved(config) -> None:
    config.save_hero_profile("Me", [("PokerStars", "jeje")])
    config.save_hero_profile("Someone else", [("Winamax", "other")])
    config.save()

    config.delete_hero_profile("Me")
    config.save()

    assert config.reload() is True
    assert list(config.hero_profiles) == ["Someone else"]
    assert "Me" not in Path(config.file).read_text(encoding="utf-8")
