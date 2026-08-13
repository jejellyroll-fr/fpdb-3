"""Tests for Hand Viewer splash-pot filtering and display."""

from unittest.mock import MagicMock

from fpdb_3_legacy.GuiHandViewer import GuiHandViewer


def test_splash_filter_conditions_include_legacy_null_rows() -> None:
    viewer = GuiHandViewer.__new__(GuiHandViewer)
    selector = MagicMock()
    viewer.flagSplashPot = selector

    selector.currentData.return_value = "all"
    assert viewer._splash_filter_condition() is None

    selector.currentData.return_value = "only"
    assert viewer._splash_filter_condition() == "h.splashPot > 0"

    selector.currentData.return_value = "exclude"
    assert viewer._splash_filter_condition() == "(h.splashPot = 0 OR h.splashPot IS NULL)"


def test_splash_display_contains_drop_and_hero_share() -> None:
    display = GuiHandViewer._format_splash(20, 0.20, "EUR")

    assert "0.20" in display
    assert "won" in display

