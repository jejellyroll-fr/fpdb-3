"""Telling the user when a newer fpdb release is out (#445).

Which tag counts as newer, which archive fits the running build, at most one
automatic check a day, and the setting that switches it off. Nothing here
touches the network -- every read goes through a fake reader -- and the
configuration is a throwaway copy.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fpdb_3_legacy import update_check
from fpdb_3_legacy.update_check import (
    LATEST_RELEASE_URL,
    RELEASES_URL,
    asset_for,
    check_due,
    fetch_release,
    is_newer,
    newer_release,
    parse_version,
    record_check,
)

ROOT = Path(__file__).resolve().parents[1]

ASSETS = [
    {"name": f"fpdb-{packager}-{suffix}.tar.gz", "browser_download_url": f"https://dl/{packager}-{suffix}"}
    for packager, suffix in (
        ("pyinstaller", "linux-x64"),
        ("pyinstaller", "windows-x64"),
        ("pyoxidizer", "linux-x64"),
        ("pyoxidizer", "macos-arm64"),
        ("pyoxidizer", "windows-x64"),
    )
]


def release(tag: str, *, prerelease: bool = False, draft: bool = False) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/jejellyroll-fr/fpdb-3/releases/tag/{tag}",
        "prerelease": prerelease,
        "draft": draft,
        "assets": ASSETS,
    }


def serving(answers: dict):
    """A reader that answers from ``answers`` and remembers which URLs were asked."""
    asked: list[str] = []

    def reader(url: str, _timeout: float):
        asked.append(url)
        return answers[url]

    reader.asked = asked  # type: ignore[attr-defined]
    return reader


def failing(exc: Exception):
    def reader(_url: str, _timeout: float):
        raise exc

    return reader


# --- which release is newer ---------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "current"),
    [
        ("v3.10.0", "3.9.1"),
        ("3.9.2", "3.9.1"),
        ("v4.0", "3.99.99"),
        ("3.10.0", "3.10.0-alpha2"),
        ("3.10.0rc1", "3.10.0-beta.3"),
        ("3.10.0-beta1", "3.10.0a5"),
    ],
)
def test_a_later_release_is_newer(candidate, current) -> None:
    assert is_newer(candidate, current)
    assert not is_newer(current, candidate)


@pytest.mark.parametrize(("candidate", "current"), [("v3.9.1", "3.9.1"), ("3.9", "3.9.0"), ("V3.9.1", "3.9.1")])
def test_the_same_release_is_not_newer(candidate, current) -> None:
    assert not is_newer(candidate, current)


def test_a_pre_release_of_the_next_number_is_newer_than_the_current_release() -> None:
    assert is_newer("v3.10.0-alpha1", "3.9.1")
    assert not is_newer("3.10.0-alpha1", "3.10.0")


@pytest.mark.parametrize("unreadable", ["3.9.1-12-gabc1234", "nightly", "", "3.9.1-dirty"])
def test_what_is_not_a_release_number_is_never_newer_nor_older(unreadable) -> None:
    assert parse_version(unreadable) is None
    assert not is_newer(unreadable, "3.9.1")
    assert not is_newer("v99.0.0", unreadable)


# --- what GitHub answers --------------------------------------------------------


def test_stable_users_read_the_latest_release_only() -> None:
    reader = serving({LATEST_RELEASE_URL: release("v3.10.0")})

    assert fetch_release(reader=reader)["tag_name"] == "v3.10.0"
    assert reader.asked == [LATEST_RELEASE_URL]


def test_pre_release_users_get_the_highest_published_tag() -> None:
    reader = serving(
        {
            RELEASES_URL: [
                release("v3.10.0"),
                release("v3.11.0-alpha1", prerelease=True),
                release("v3.12.0", draft=True),
                release("nightly"),
            ]
        }
    )

    assert fetch_release(include_prereleases=True, reader=reader)["tag_name"] == "v3.11.0-alpha1"
    assert reader.asked == [RELEASES_URL]


@pytest.mark.parametrize(
    "reader",
    [
        failing(urllib.error.URLError("offline")),
        failing(TimeoutError()),
        failing(urllib.error.HTTPError(LATEST_RELEASE_URL, 403, "rate limit exceeded", {}, None)),
        failing(json.JSONDecodeError("captive portal page", "<html>", 0)),
        serving({LATEST_RELEASE_URL: {"message": "Not Found"}}),
        serving({LATEST_RELEASE_URL: ["not", "a", "release"]}),
    ],
    ids=["offline", "timeout", "rate-limited", "not-json", "no-tag", "not-an-object"],
)
def test_no_answer_from_github_is_silence(reader) -> None:
    assert fetch_release(reader=reader) is None
    assert newer_release("3.9.1", "PyOxidizer", reader=reader) is None


# --- what gets announced --------------------------------------------------------


def test_an_older_or_equal_release_is_not_announced() -> None:
    reader = serving({LATEST_RELEASE_URL: release("v3.9.1")})

    assert newer_release("3.9.1", "PyOxidizer", reader=reader) is None
    assert newer_release("3.10.0", "PyOxidizer", reader=reader) is None


def test_a_newer_release_comes_with_the_archive_built_like_the_running_fpdb(monkeypatch) -> None:
    monkeypatch.setattr(update_check, "_platform_suffix", lambda: "macos-arm64")
    reader = serving({LATEST_RELEASE_URL: release("v3.10.0")})

    found = newer_release("3.9.1", "PyOxidizer", reader=reader)

    assert found is not None
    assert found.tag == "v3.10.0"
    assert found.page_url.endswith("/releases/tag/v3.10.0")
    assert found.asset_name == "fpdb-pyoxidizer-macos-arm64.tar.gz"
    assert found.asset_url == "https://dl/pyoxidizer-macos-arm64"


def test_a_source_checkout_only_gets_the_release_page(monkeypatch) -> None:
    monkeypatch.setattr(update_check, "_platform_suffix", lambda: "linux-x64")
    reader = serving({LATEST_RELEASE_URL: release("v3.10.0")})

    found = newer_release("3.9.1", "Source", reader=reader)

    assert found is not None
    assert found.asset_name is None
    assert found.asset_url is None


@pytest.mark.parametrize(
    ("sys_platform", "machine", "packaging", "expected"),
    [
        ("linux", "x86_64", "PyInstaller", "fpdb-pyinstaller-linux-x64.tar.gz"),
        ("win32", "AMD64", "PyInstaller", "fpdb-pyinstaller-windows-x64.tar.gz"),
        ("win32", "AMD64", "PyOxidizer", "fpdb-pyoxidizer-windows-x64.tar.gz"),
        ("darwin", "arm64", "PyOxidizer", "fpdb-pyoxidizer-macos-arm64.tar.gz"),
        ("darwin", "x86_64", "PyOxidizer", None),  # no Intel macOS build is published
        ("linux", "aarch64", "PyInstaller", None),
        ("linux", "x86_64", "AppImage", None),
    ],
)
def test_the_archive_matches_the_packager_the_os_and_the_architecture(
    monkeypatch, sys_platform, machine, packaging, expected
) -> None:
    monkeypatch.setattr(update_check.sys, "platform", sys_platform)
    monkeypatch.setattr(update_check.platform, "machine", lambda: machine)

    found = asset_for(ASSETS, packaging)

    assert (found[0] if found else None) == expected


# --- at most once a day -----------------------------------------------------------


def test_the_first_check_is_due(tmp_path) -> None:
    assert check_due(tmp_path / "update_check.json")


def test_a_check_within_a_day_is_not_repeated(tmp_path) -> None:
    state = tmp_path / "update_check.json"
    now = datetime(2026, 10, 21, 9, 0)
    record_check(state, now)

    assert not check_due(state, now + timedelta(hours=23))
    assert check_due(state, now + timedelta(days=1, minutes=1))


@pytest.mark.parametrize("content", ["", "{}", "not json", '{"last_check": "yesterday"}', '{"last_check": 3}'])
def test_an_unreadable_record_does_not_silence_the_check(tmp_path, content) -> None:
    state = tmp_path / "update_check.json"
    state.write_text(content, encoding="utf-8")

    assert check_due(state)


def test_a_record_from_the_future_does_not_silence_the_check(tmp_path) -> None:
    state = tmp_path / "update_check.json"
    now = datetime(2026, 10, 21, 9, 0)
    record_check(state, now + timedelta(days=30))

    assert check_due(state, now)


def test_a_record_that_cannot_be_written_is_not_an_error(tmp_path) -> None:
    record_check(tmp_path / "missing-dir" / "update_check.json")


# --- the setting ------------------------------------------------------------------


@pytest.fixture
def config_copy(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(ROOT / "HUD_config.xml.example"))
    path = tmp_path / "HUD_config.xml"
    path.write_text((ROOT / "HUD_config.xml.example").read_text(encoding="utf-8"), encoding="utf-8")
    return configuration, path


def test_a_new_configuration_has_not_decided_so_the_first_start_asks(config_copy) -> None:
    configuration, path = config_copy

    config = configuration.Config(file=str(path))

    assert config.get_check_for_updates() is None
    assert config.get_update_prereleases() is False


def test_the_answer_is_saved_in_the_configuration(config_copy) -> None:
    configuration, path = config_copy

    configuration.Config(file=str(path)).set_check_for_updates(False)
    reloaded = configuration.Config(file=str(path))
    assert reloaded.get_check_for_updates() is False
    assert not reloaded.wrongConfigVersion

    reloaded.set_check_for_updates(True)
    assert configuration.Config(file=str(path)).get_check_for_updates() is True


def test_the_shipped_templates_leave_the_question_open() -> None:
    for template in ROOT.glob("**/HUD_config.xml.example"):
        if ".venv" in template.parts or ".claude" in template.parts:
            continue
        assert "check_for_updates" not in template.read_text(encoding="utf-8"), template
