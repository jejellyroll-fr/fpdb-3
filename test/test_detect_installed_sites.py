"""Regression tests for installed-site directory detection."""

from types import SimpleNamespace

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
