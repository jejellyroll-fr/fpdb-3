"""Localized display contracts for tournament player statistics."""

from collections.abc import Iterator

import pytest

from fpdb_3_legacy.GuiTourneyPlayerStats import GuiTourneyPlayerStats
from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale


@pytest.fixture(autouse=True)
def restore_format_locale() -> Iterator[None]:
    previous = get_format_locale()
    yield
    set_format_locale(previous)


def test_tournament_grid_values_follow_active_locale() -> None:
    set_format_locale("fr_FR")

    assert GuiTourneyPlayerStats._format_grid_value("buyIn", 12.5, "EUR", "%3.2f") == "12,50\u00a0€"
    assert GuiTourneyPlayerStats._format_grid_value("roi", 25.5, "EUR", "%3.2f") == "25,50%"
    assert GuiTourneyPlayerStats._format_grid_value("tourneyCount", 1234, "EUR", "%1.0f") == "1\u202f234"
    assert GuiTourneyPlayerStats._format_grid_value("category", "holdem", "EUR", "%s") == "holdem"
