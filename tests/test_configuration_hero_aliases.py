"""The several names one player answers to on one room.

A room knows the hero by a screen name, and that is not always one name: people
change nickname, or hold two accounts. The configuration keeps the current one
as the site's `screen_name` and the rest as `<hero_alias>` children, and every
importer asks which names count as the hero before deciding whose hand it is
looking at. A name dropped here is a session of hands filed under a stranger.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'


def config_xml(sites: str) -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"<supported_sites>{sites}</supported_sites>\n"
        "</FreePokerToolsConfig>\n"
    )


def site(name: str = "PokerStars", screen_name: str = "jeje", aliases: str = "") -> str:
    return (
        f'<site site_name="{name}" enabled="True" screen_name="{screen_name}"'
        f' HH_path="" TS_path="" converter="PokerStarsToFpdb">{aliases}</site>'
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(sites: str = site()) -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(config_xml(sites), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def config(build) -> Any:
    return build()


def stored(config: Any, site_name: str = "PokerStars") -> tuple[str, list[str]]:
    """What the document holds: the primary name, then the extra ones."""
    node = config.get_site_node(site_name)
    return (
        node.getAttribute("screen_name"),
        [alias.getAttribute("name") for alias in node.getElementsByTagName("hero_alias")],
    )


# --------------------------------------------------------------------------
# Writing the names down
# --------------------------------------------------------------------------


def test_the_first_name_is_the_one_the_room_shows(config) -> None:
    # The rest are aliases: the primary is what fpdb displays and what an
    # older fpdb reading this file would see on its own.
    config.set_hero_aliases("PokerStars", ["current", "older", "oldest"])

    assert stored(config) == ("current", ["older", "oldest"])


def test_a_single_name_leaves_no_aliases_behind(config) -> None:
    config.set_hero_aliases("PokerStars", ["only"])

    assert stored(config) == ("only", [])


def test_the_order_given_is_the_order_kept(config) -> None:
    config.set_hero_aliases("PokerStars", ["c", "a", "b"])

    assert config.get_hero_aliases("PokerStars") == ["c", "a", "b"]


def test_a_name_given_twice_is_written_once(config) -> None:
    config.set_hero_aliases("PokerStars", ["jeje", "other", "jeje"])

    assert stored(config) == ("jeje", ["other"])


def test_an_empty_name_is_dropped(config) -> None:
    # The preferences window sends a blank row for anything not filled in.
    config.set_hero_aliases("PokerStars", ["jeje", "", "other"])

    assert stored(config) == ("jeje", ["other"])


def test_giving_no_name_at_all_clears_the_hero(config) -> None:
    # This is how a player says the room has no hero of theirs; the site stays
    # configured, it just answers to nobody.
    config.set_hero_aliases("PokerStars", [])

    assert stored(config) == ("", [])
    assert config.get_hero_aliases("PokerStars") == []


def test_writing_again_replaces_the_previous_aliases(config) -> None:
    # The old children are removed first; keeping them would have the room
    # answering to names the player has just taken off the list.
    config.set_hero_aliases("PokerStars", ["a", "b", "c"])

    config.set_hero_aliases("PokerStars", ["a", "d"])

    assert stored(config) == ("a", ["d"])


def test_aliases_already_in_the_file_are_replaced_too(build) -> None:
    config = build(site(aliases='<hero_alias name="from-the-file"/>'))
    assert config.get_hero_aliases("PokerStars") == ["jeje", "from-the-file"]

    config.set_hero_aliases("PokerStars", ["jeje"])

    assert stored(config) == ("jeje", [])


def test_the_site_in_use_is_kept_in_step(config) -> None:
    # The importer reads the loaded Site, not the document, so a write that
    # only reached the file would take effect one restart late.
    config.set_hero_aliases("PokerStars", ["current", "older"])

    loaded = config.supported_sites["PokerStars"]
    assert loaded.screen_name == "current"
    assert loaded.hero_aliases == ["current", "older"]


def test_the_names_survive_being_saved_and_read_again(config) -> None:
    config.set_hero_aliases("PokerStars", ["current", "older"])
    config.save()

    assert config.reload() is True

    assert config.get_hero_aliases("PokerStars") == ["current", "older"]


def test_a_room_that_is_not_configured_cannot_be_given_names(config) -> None:
    # Observed: the lookup answers None and the caller uses it straight away,
    # so this is an AttributeError rather than something naming the room.
    assert config.get_site_node("A Room That Is Not There") is None

    with pytest.raises(AttributeError):
        config.set_hero_aliases("A Room That Is Not There", ["someone"])


# --------------------------------------------------------------------------
# Reading them back
# --------------------------------------------------------------------------


def test_a_room_with_no_aliases_answers_to_its_screen_name(config) -> None:
    # Configurations written before aliases existed have only the one name,
    # and must keep working unchanged.
    assert config.get_hero_aliases("PokerStars") == ["jeje"]


def test_a_room_with_no_hero_answers_to_nobody(build) -> None:
    config = build(site(screen_name=""))

    assert config.get_hero_aliases("PokerStars") == []


def test_the_room_can_be_named_in_any_case(config) -> None:
    # Site names reach this from hand histories and from window titles, which
    # do not agree with the configuration on capitalisation.
    assert config.get_hero_aliases("pokerstars") == ["jeje"]
    assert config.get_hero_aliases("POKERSTARS") == ["jeje"]


def test_the_exact_name_is_preferred_over_one_differing_in_case(build) -> None:
    config = build(site(name="Winamax", screen_name="exact") + site(name="WINAMAX", screen_name="shouting"))

    assert config.get_hero_aliases("Winamax") == ["exact"]


@pytest.mark.parametrize("unknown", ["A Room That Is Not There", ""])
def test_a_room_that_is_not_configured_answers_with_nothing(config, unknown) -> None:
    # Returning an empty list rather than raising is what lets an importer ask
    # about every room it meets, configured or not.
    assert config.get_hero_aliases(unknown) == []


def test_reading_back_what_was_just_written(config) -> None:
    config.set_hero_aliases("PokerStars", ["current", "older", "oldest"])

    assert config.get_hero_aliases("PokerStars") == ["current", "older", "oldest"]
    assert config.get_hero_aliases("pokerstars") == ["current", "older", "oldest"]


def test_a_saved_alias_list_reaches_the_file(config) -> None:
    config.set_hero_aliases("PokerStars", ["current", "older"])
    config.save()

    written = Path(config.file).read_text(encoding="utf-8")
    assert 'screen_name="current"' in written
    assert 'hero_alias name="older"' in written
