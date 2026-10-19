"""The hero of a data source: which players in PHH hands are you (#423).

A data source is not a poker room, so it has no ``<site>`` and no screen name.
Its hero is the list of names a ``<data_source>`` element gives, and every
caller that asks a room for its hero aliases gets that list for the source, so
the hero resolves the way a room's does.
"""

from __future__ import annotations

from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, DATA_SOURCES, Config
from fpdb_3_legacy.phh_import import PHH_SITE_NAME

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'
ROOM = '<supported_sites><site site_name="PokerStars" screen_name="jeje" enabled="True"/></supported_sites>'


def config_xml(sources: str = "") -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{ROOM}\n{sources}\n"
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"

    def make(sources: str = "") -> Config:
        path.write_text(config_xml(sources), encoding="utf-8")
        return Config(file=str(path))

    make.path = path
    return make


PHH_ALIASES = (
    '<data_sources><data_source name="PHH">'
    '<hero_alias name="jeje"/><hero_alias name="jeje76"/><hero_alias name="jeje"/>'
    "</data_source></data_sources>"
)


def test_the_built_in_source_is_the_one_phh_hands_are_stored_under() -> None:
    assert PHH_SITE_NAME in DATA_SOURCES


def test_a_data_source_names_its_hero_aliases(build) -> None:
    config = build(PHH_ALIASES)

    assert config.get_data_source_hero_aliases("PHH") == ["jeje", "jeje76"]
    # The question every hero resolver asks a room, answered for the source.
    assert config.get_hero_aliases("PHH") == ["jeje", "jeje76"]
    assert config.is_hero_name("PHH", "JEJE76")


def test_a_source_without_an_entry_has_no_hero(build) -> None:
    config = build()

    assert config.get_data_source_names() == list(DATA_SOURCES)
    assert config.get_hero_aliases("PHH") == []
    assert config.is_data_source("PHH")


def test_a_room_is_not_a_data_source_and_keeps_its_own_aliases(build) -> None:
    config = build(PHH_ALIASES)

    assert not config.is_data_source("PokerStars")
    assert not config.is_data_source("Unknown room")
    assert config.get_hero_aliases("PokerStars") == ["jeje"]


def test_aliases_are_saved_and_read_back(build) -> None:
    config = build()

    config.set_data_source_hero_aliases("PHH", ["jeje", "", "jeje76", "jeje"])
    config.save()
    reloaded = Config(file=str(build.path))

    assert reloaded.get_hero_aliases("PHH") == ["jeje", "jeje76"]
    assert len(reloaded.doc.getElementsByTagName("data_source")) == 1


def test_saving_again_replaces_the_previous_aliases(build) -> None:
    config = build(PHH_ALIASES)

    config.set_data_source_hero_aliases("PHH", ["other"])

    assert config.get_hero_aliases("PHH") == ["other"]
    assert [n.getAttribute("name") for n in config.doc.getElementsByTagName("data_source")] == ["PHH"]


def test_no_aliases_removes_the_entry(build) -> None:
    config = build(PHH_ALIASES)

    config.set_data_source_hero_aliases("PHH", [])

    assert config.get_hero_aliases("PHH") == []
    assert config.doc.getElementsByTagName("data_source") == []


def test_clearing_a_source_never_configured_writes_nothing(build) -> None:
    config = build()

    config.set_data_source_hero_aliases("PHH", [])

    assert config.doc.getElementsByTagName("data_sources") == []


def test_a_reload_reads_the_aliases_and_profiles_the_file_now_holds(build) -> None:
    """Config.reload() is what ConfigurationManager applies to the live configuration."""
    config = build(PHH_ALIASES)
    edited = Config(file=str(build.path))
    edited.set_data_source_hero_aliases("PHH", ["other"])
    edited.save_hero_profile("Me", [("PokerStars", "jeje"), ("PHH", "other")])
    edited.save()

    assert config.reload() is True

    assert config.get_hero_aliases("PHH") == ["other"]
    assert config.hero_profiles["Me"].links == [("PokerStars", "jeje"), ("PHH", "other")]


def test_the_manager_sees_an_identity_edit_as_a_change(build) -> None:
    """Otherwise an edit to them alone is "No changes detected", and nothing is reloaded."""
    from fpdb_3_legacy.ConfigurationManager import ConfigurationManager

    old = build(PHH_ALIASES)
    new = Config(file=str(build.path))
    new.set_data_source_hero_aliases("PHH", ["jeje"])
    new.save_hero_profile("Me", [("PHH", "jeje")])

    changes = ConfigurationManager._identity_changes(old, new)

    assert [(change.path, change.old_value, change.new_value) for change in changes] == [
        ("data_sources.PHH", ["jeje", "jeje76"], ["jeje"]),
        ("hero_profiles.Me", None, (False, [("PHH", "jeje")])),
    ]
    assert not any(ConfigurationManager()._requires_restart(change) for change in changes)
    assert ConfigurationManager._identity_changes(old, old) == []
