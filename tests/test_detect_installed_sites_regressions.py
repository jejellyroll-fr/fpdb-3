"""Regression tests for installed-site directory detection."""

import logging
import os
from types import SimpleNamespace

from fpdb_3_legacy import DetectInstalledSites
from fpdb_3_legacy.DetectInstalledSites import SiteDetector, WinamaxDetector


def _detector() -> SiteDetector:
    return SiteDetector(SimpleNamespace(os_family="linux"))


def test_check_path_exists_returns_first_existing_path(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert _detector()._check_path_exists(str(first), str(second)) == str(first)


def test_find_heroes_ignores_archives_and_hidden_directories(tmp_path) -> None:
    for directory in ("HeroOne", "HeroTwo", "archive", ".cache"):
        (tmp_path / directory).mkdir()

    assert sorted(_detector()._find_heroes_in_path(str(tmp_path))) == ["HeroOne", "HeroTwo"]


def _winamax_detector() -> WinamaxDetector:
    detector = WinamaxDetector(SimpleNamespace(os_family="windows"))
    detector.platform = "Windows"
    return detector


def _winamax_history(root, *segments: str):
    """Create <root>/<segments>/Dyvinitos/history and return it."""
    history = root.joinpath(*segments) / "Dyvinitos" / "history"
    history.mkdir(parents=True)
    return history


def test_windows_winamax_is_found_under_documents(tmp_path, monkeypatch) -> None:
    """The current client keeps its accounts under a "documents" folder.

    Only "Winamax/accounts" was probed, so a Windows player of the current
    client was told the site was not installed and had to type the path in by
    hand -- and, one level being easy to miss, sometimes typed the parent of the
    history folder, which imports nothing.
    """
    history = _winamax_history(tmp_path, "Winamax", "documents", "accounts")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    result = _winamax_detector().detect()

    assert result["detected"] is True
    assert result["hhpath"] == str(history)
    assert result["heroname"] == "Dyvinitos"


def test_windows_winamax_still_found_in_the_older_layout(tmp_path, monkeypatch) -> None:
    history = _winamax_history(tmp_path, "Winamax", "accounts")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert _winamax_detector().detect()["hhpath"] == str(history)


def test_windows_winamax_documents_wins_over_the_older_layout(tmp_path, monkeypatch) -> None:
    """A client upgraded in place leaves the old folder behind, empty of hands."""
    _winamax_history(tmp_path, "Winamax", "accounts")
    current = _winamax_history(tmp_path, "Winamax", "documents", "accounts")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert _winamax_detector().detect()["hhpath"] == str(current)


def test_windows_winamax_is_found_under_local_appdata(tmp_path, monkeypatch) -> None:
    history = _winamax_history(tmp_path / "local", "Winamax", "documents", "accounts")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert _winamax_detector().detect()["hhpath"] == str(history)


def test_windows_winamax_absent_is_reported_as_not_detected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert _winamax_detector().detect() == {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


def test_windows_winamax_falls_back_when_the_preferred_root_holds_no_history(tmp_path, monkeypatch) -> None:
    """A root that exists is not proof the hands are in it.

    The client creates its "documents" tree as soon as it runs. Stopping at the
    first root that merely exists hid a real history left in the older layout,
    and reported a client that is plainly installed as not detected.
    """
    (tmp_path / "Winamax" / "documents" / "accounts").mkdir(parents=True)
    history = _winamax_history(tmp_path, "Winamax", "accounts")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert _winamax_detector().detect()["hhpath"] == str(history)


def test_windows_winamax_skips_an_account_with_no_history_folder(tmp_path, monkeypatch) -> None:
    """An account directory alone is not a history; the next one may be."""
    accounts = tmp_path / "Winamax" / "documents" / "accounts"
    (accounts / "LoggedInOnce").mkdir(parents=True)
    history = accounts / "Dyvinitos" / "history"
    history.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    result = _winamax_detector().detect()

    assert result["hhpath"] == str(history)
    assert result["heroname"] == "Dyvinitos"


def test_windows_winamax_falls_back_past_an_unreadable_root(tmp_path, monkeypatch, caplog) -> None:
    """A root that cannot be listed must not end the search, but must be logged."""
    _winamax_history(tmp_path, "Winamax", "accounts")
    preferred = tmp_path / "Winamax" / "documents" / "accounts"
    preferred.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    real_listdir = os.listdir

    def listdir(path, *args, **kwargs):
        if str(path) == str(preferred):
            raise PermissionError(13, "Permission denied")
        return real_listdir(path, *args, **kwargs)

    monkeypatch.setattr(DetectInstalledSites.os, "listdir", listdir)

    with caplog.at_level(logging.ERROR, logger="detect_installed_sites"):
        result = _winamax_detector().detect()

    assert result["detected"] is True
    assert "Error detecting Winamax" in caplog.text


def test_a_missing_root_is_not_logged_as_an_error(tmp_path, monkeypatch, caplog) -> None:
    """Most candidate roots do not exist on any one machine; that is not news."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    with caplog.at_level(logging.ERROR, logger="detect_installed_sites"):
        assert _winamax_detector().detect()["detected"] is False

    assert caplog.text == ""
