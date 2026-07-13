"""Regression tests for installed-site directory detection."""

from types import SimpleNamespace

from fpdb_3_legacy.DetectInstalledSites import SiteDetector


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
