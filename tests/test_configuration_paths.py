"""The folders fpdb offers when a player opens the import window.

get_default_paths answers with where a room's hands are, where a bulk import
should start, and where its tournament summaries are. Those are the paths the
GUI puts in front of someone who has just installed fpdb, so a wrong one sends
them browsing, and a missing key is a window that cannot draw itself.

The paths a site is configured with usually do not exist on the machine
running the tests, which is the interesting half of this: what happens then is
detection, and detection is driven here rather than observed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

MISSING = "/nowhere/this/path/does/not/exist"


def config_xml(hh_path: str, ts_path: str, *, bulk: str = "") -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        "<supported_sites>"
        f'<site site_name="PokerStars" enabled="True" screen_name="hero"'
        f' HH_path="{hh_path}" TS_path="{ts_path}" converter="PokerStarsToFpdb"/>'
        "</supported_sites>\n"
        f'<import hhBulkPath="{bulk}"/>\n'
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    """A configuration with one site, whose paths the test decides."""
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(hh_path: str = "", ts_path: str = "", *, bulk: str = "") -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(config_xml(hh_path, ts_path, bulk=bulk), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def hands(tmp_path) -> Path:
    folder = tmp_path / "hands"
    folder.mkdir()
    return folder


@pytest.fixture
def summaries(tmp_path) -> Path:
    folder = tmp_path / "summaries"
    folder.mkdir()
    return folder


def detecting(*, hh: str | None = None, ts: str | None = None) -> Any:
    """Stand in for looking the client's folders up on this machine."""
    return patch.multiple(
        Config,
        detect_hh_path=lambda self, site: hh,
        detect_ts_path=lambda self, site: ts,
    )


# --------------------------------------------------------------------------
# Paths the configuration already holds
# --------------------------------------------------------------------------


def test_the_configured_folder_is_offered_for_hands_and_for_bulk_import(build, hands) -> None:
    paths = build(str(hands)).get_default_paths()

    assert paths["hud-defaultPath"] == str(hands)
    assert paths["bulkImport-defaultPath"] == str(hands)


def test_a_bulk_import_folder_of_its_own_is_used_for_that_alone(build, hands, tmp_path) -> None:
    # Someone who files their histories elsewhere before importing sets this,
    # and it must not move where the HUD looks.
    elsewhere = tmp_path / "to-import"

    paths = build(str(hands), bulk=str(elsewhere)).get_default_paths()

    assert paths["bulkImport-defaultPath"] == str(elsewhere)
    assert paths["hud-defaultPath"] == str(hands)


def test_the_summary_folder_is_offered_when_the_site_has_one(build, hands, summaries) -> None:
    paths = build(str(hands), str(summaries)).get_default_paths()

    assert paths["hud-defaultTSPath"] == str(summaries)


def test_a_site_with_no_summary_folder_is_offered_none(build, hands) -> None:
    # The key is absent rather than empty, so anything reading it has to say
    # what it wants when there is nothing.
    paths = build(str(hands), "").get_default_paths()

    assert "hud-defaultTSPath" not in paths


def test_a_home_relative_folder_is_expanded(build, monkeypatch, tmp_path) -> None:
    # Configurations are shared between machines and between users, so the
    # paths in them are written with a ~.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "hands").mkdir()

    paths = build("~/hands").get_default_paths()

    assert paths["hud-defaultPath"] == str(tmp_path / "hands")


def test_the_site_is_the_default_one_unless_asked_otherwise(build, hands) -> None:
    config = build(str(hands))

    assert config.getDefaultSite() == "PokerStars"
    assert config.get_default_paths() == config.get_default_paths("PokerStars")


# --------------------------------------------------------------------------
# Paths the configuration holds but the machine does not
# --------------------------------------------------------------------------


def test_a_folder_that_is_not_there_gives_way_to_the_one_found(build, hands) -> None:
    # The usual case for a configuration carried over from another machine.
    config = build(MISSING)

    with detecting(hh=str(hands)):
        paths = config.get_default_paths()

    assert paths["hud-defaultPath"] == str(hands)


def test_nothing_configured_and_nothing_found_says_so(build) -> None:
    # The GUI shows this string, which is uglier than it is useless: it tells
    # the player the configuration is the thing to fix.
    config = build(MISSING)

    with detecting(hh=None):
        paths = config.get_default_paths()

    assert paths["hud-defaultPath"] == "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **"
    assert paths["bulkImport-defaultPath"] == paths["hud-defaultPath"]


def test_no_summary_path_is_offered_when_the_hand_path_could_not_be_settled(build, summaries) -> None:
    # The summary lookup sits after the failure, so it never runs.
    config = build(MISSING, str(summaries))

    with detecting(hh=None):
        paths = config.get_default_paths()

    assert "hud-defaultTSPath" not in paths


def test_a_summary_folder_that_is_not_there_gives_way_to_the_one_found(build, hands, summaries) -> None:
    config = build(str(hands), MISSING)

    with detecting(ts=str(summaries)):
        paths = config.get_default_paths()

    assert paths["hud-defaultTSPath"] == str(summaries)


def test_the_hand_folder_stands_in_when_no_summary_folder_is_found(build, hands) -> None:
    # Several rooms write both into one directory, so it is a better guess
    # than nothing.
    config = build(str(hands), MISSING)

    with detecting(hh=str(hands), ts=None):
        paths = config.get_default_paths()

    assert paths["hud-defaultTSPath"] == str(hands)


def test_the_configured_summary_folder_is_kept_when_nothing_is_found(build, hands) -> None:
    # Offering a path that does not exist beats offering none: it is where the
    # player said their summaries were, and it shows them what to correct.
    config = build(str(hands), MISSING)

    with detecting(hh=None, ts=None):
        paths = config.get_default_paths()

    assert paths["hud-defaultTSPath"] == MISSING


def test_a_file_rather_than_a_folder_is_accepted(build, tmp_path) -> None:
    # Some rooms write every hand into one file, so the configured path is
    # that file and detection must not be reached for it.
    single = tmp_path / "all-hands.txt"
    single.write_text("", encoding="utf-8")
    config = build(str(single))

    with detecting(hh=None):
        paths = config.get_default_paths()

    assert paths["hud-defaultPath"] == str(single)
