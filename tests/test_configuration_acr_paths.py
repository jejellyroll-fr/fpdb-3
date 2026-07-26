"""Asking the Americas Cardroom client where it puts its hands.

The WPN client is an Electron application that records the folders it writes
to in its own local-storage JSON, so on macOS fpdb reads that instead of
guessing from a list of usual places. It is the one room whose configured path
can be recovered exactly rather than approximated.

Nothing here needs a Mac: the reader takes the platform check from its callers
rather than making it, so it can be driven anywhere by pointing HOME at the
test's own directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

# The key every WPN skin shares, and the room fpdb calls it under.
ACR_KEY = "AmericasCardroom"
ACR_SITE = "ACR Poker"

STORAGE = "Library/Application Support/Loading/storage"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A home directory the client's JSON can be written into."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    return tmp_path


def client_says(home: Path, kind: str, path: Path | str, *, key: str = ACR_KEY) -> None:
    """Write the file the Electron client keeps its chosen folder in."""
    prefix = "hhDirPath" if kind == "hh" else "tsDirPath"
    storage = home / STORAGE
    storage.mkdir(parents=True, exist_ok=True)
    (storage / f"{prefix}_{key}.json").write_text(json.dumps({"path": str(path)}), encoding="utf-8")


def read(kind: str, screen_name: str = "", *, key: str = ACR_KEY) -> str | None:
    return Config._read_acr_json_path(key, kind, screen_name)


# --------------------------------------------------------------------------
# Reading the client's own file
# --------------------------------------------------------------------------


def test_the_folder_the_client_recorded_is_returned(home) -> None:
    hands = home / "ACR" / "handHistory"
    hands.mkdir(parents=True)
    client_says(home, "hh", hands)

    assert read("hh") == str(hands)


def test_the_hero_s_own_folder_is_preferred(home) -> None:
    # The client files each account under its own name, and the hero's hands
    # are the ones fpdb wants rather than every account on the machine.
    hands = home / "ACR" / "handHistory"
    (hands / "jeje").mkdir(parents=True)
    client_says(home, "hh", hands)

    assert read("hh", "jeje") == str(hands / "jeje")


def test_the_recorded_folder_stands_in_when_the_hero_has_none(home) -> None:
    # An account that has not played yet has no folder of its own.
    hands = home / "ACR" / "handHistory"
    hands.mkdir(parents=True)
    client_says(home, "hh", hands)

    assert read("hh", "never-played") == str(hands)


def test_summaries_are_read_from_their_own_file(home) -> None:
    # Hands and summaries are recorded separately, and reading the wrong one
    # would point the summary importer at hand histories.
    hands = home / "ACR" / "handHistory"
    summaries = home / "ACR" / "TournamentSummary"
    hands.mkdir(parents=True)
    summaries.mkdir(parents=True)
    client_says(home, "hh", hands)
    client_says(home, "ts", summaries)

    assert read("ts") == str(summaries)
    assert read("hh") == str(hands)


# --------------------------------------------------------------------------
# When there is nothing usable to read
# --------------------------------------------------------------------------


def test_no_file_at_all_means_nothing_found(home) -> None:
    # The client is not installed, which is the normal case for most people.
    assert read("hh") is None


def test_a_folder_the_client_no_longer_has_means_nothing_found(home) -> None:
    # The file outlives an uninstall, so what it names has to be checked.
    client_says(home, "hh", home / "gone")

    assert read("hh") is None


def test_a_file_that_is_not_json_is_stepped_over(home) -> None:
    storage = home / STORAGE
    storage.mkdir(parents=True)
    (storage / f"hhDirPath_{ACR_KEY}.json").write_text("not json at all", encoding="utf-8")

    assert read("hh") is None


def test_json_without_a_path_in_it_is_stepped_over(home) -> None:
    storage = home / STORAGE
    storage.mkdir(parents=True)
    (storage / f"hhDirPath_{ACR_KEY}.json").write_text('{"something": "else"}', encoding="utf-8")

    assert read("hh") is None


def test_a_file_that_cannot_be_read_is_stepped_over(home) -> None:
    # A directory where the file should be: is_file says no, so it never gets
    # as far as opening it.
    storage = home / STORAGE
    (storage / f"hhDirPath_{ACR_KEY}.json").mkdir(parents=True)

    assert read("hh") is None


def test_another_room_s_file_is_not_read(home) -> None:
    hands = home / "somewhere"
    hands.mkdir()
    client_says(home, "hh", hands, key="SomeOtherRoom")

    assert read("hh") is None


# --------------------------------------------------------------------------
# What the rest of fpdb does with it
# --------------------------------------------------------------------------


@pytest.fixture
def config(home) -> Any:
    path = home / "HUD_config.xml"
    path.write_text(
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        "<supported_sites>"
        f'<site site_name="{ACR_SITE}" enabled="True" screen_name="jeje"'
        ' HH_path="" TS_path="" converter="WinningToFpdb"/>'
        "</supported_sites>\n</FreePokerToolsConfig>\n",
        encoding="utf-8",
    )
    return Config(file=str(path))


def on_macos(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "sysPlatform", "Darwin")


def test_the_hand_folder_comes_from_the_client_on_macos(config, home, monkeypatch) -> None:
    on_macos(monkeypatch)
    hands = home / "ACR" / "handHistory"
    (hands / "jeje").mkdir(parents=True)
    client_says(home, "hh", hands)

    assert config.detect_hh_path(ACR_SITE) == str(hands / "jeje")


def test_the_summary_folder_comes_from_the_client_on_macos(config, home, monkeypatch) -> None:
    on_macos(monkeypatch)
    summaries = home / "ACR" / "TournamentSummary"
    summaries.mkdir(parents=True)
    client_says(home, "ts", summaries)

    assert config.detect_ts_path(ACR_SITE) == str(summaries)


def test_no_summary_folder_is_looked_for_off_macos(config, home, monkeypatch) -> None:
    # The file is written by the macOS client and lives at a macOS path; there
    # is nothing to read anywhere else.
    monkeypatch.setattr(config_module, "sysPlatform", "Linux")
    summaries = home / "ACR" / "TournamentSummary"
    summaries.mkdir(parents=True)
    client_says(home, "ts", summaries)

    assert config.detect_ts_path(ACR_SITE) is None


def test_a_room_the_client_does_not_serve_is_not_looked_up(config, home, monkeypatch) -> None:
    on_macos(monkeypatch)

    assert config.detect_ts_path("PokerStars") is None


def test_the_client_saying_nothing_leaves_the_usual_places_to_try(config, home, monkeypatch) -> None:
    # Detection falls through to the static candidate list, which on this
    # machine holds nothing either.
    on_macos(monkeypatch)

    assert config.detect_hh_path(ACR_SITE) is None


# --------------------------------------------------------------------------
# Falling back to the usual places
# --------------------------------------------------------------------------
#
# Covered here because they are the two lines the ACR lookup exists to skip:
# reading the client's own answer is only worth doing if guessing is what
# happens otherwise.


def test_no_summary_folder_is_offered_when_the_client_recorded_none(config, monkeypatch) -> None:
    # An ACR site on macOS with nothing to read: there is no candidate list
    # for summaries at all, so the answer is nothing.
    on_macos(monkeypatch)

    assert config.detect_ts_path(ACR_SITE) is None


def test_the_usual_place_is_tried_when_the_client_recorded_nothing(config, home, monkeypatch) -> None:
    on_macos(monkeypatch)
    usual = home / "Downloads" / "AmericasCardroom" / "handHistory"
    usual.mkdir(parents=True)
    monkeypatch.setitem(config_module.HH_PATH_CANDIDATES, ACR_SITE, {"Darwin": (str(usual),)})

    assert config.detect_hh_path(ACR_SITE) == str(usual)


def test_the_hero_s_folder_in_the_usual_place_is_preferred(config, home, monkeypatch) -> None:
    on_macos(monkeypatch)
    usual = home / "Downloads" / "AmericasCardroom" / "handHistory"
    (usual / "jeje").mkdir(parents=True)
    monkeypatch.setitem(config_module.HH_PATH_CANDIDATES, ACR_SITE, {"Darwin": (str(usual),)})

    assert config.detect_hh_path(ACR_SITE) == str(usual / "jeje")


def test_the_first_of_the_usual_places_that_exists_wins(config, home, monkeypatch) -> None:
    second = home / "second-guess"
    second.mkdir()
    monkeypatch.setitem(
        config_module.HH_PATH_CANDIDATES,
        ACR_SITE,
        {"Darwin": (str(home / "first-guess"), str(second))},
    )
    on_macos(monkeypatch)

    assert config.detect_hh_path(ACR_SITE) == str(second)


def test_the_usual_places_are_tried_directly_off_macos(config, home, monkeypatch) -> None:
    # No client file to consult anywhere else, so detection is the guess list
    # and nothing more.
    monkeypatch.setattr(config_module, "sysPlatform", "Linux")
    usual = home / "linux-hands"
    usual.mkdir()
    monkeypatch.setitem(config_module.HH_PATH_CANDIDATES, ACR_SITE, {"Linux": (str(usual),)})

    assert config.detect_hh_path(ACR_SITE) == str(usual)


def test_a_room_with_no_client_file_goes_straight_to_the_usual_places(config, home, monkeypatch) -> None:
    # On macOS, but for a room the WPN client knows nothing about.
    on_macos(monkeypatch)
    usual = home / "stars-hands"
    usual.mkdir()
    monkeypatch.setitem(config_module.HH_PATH_CANDIDATES, "PokerStars", {"Darwin": (str(usual),)})

    assert config.detect_hh_path("PokerStars") == str(usual)
