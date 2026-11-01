"""Localized display contracts for the opponents report."""

from collections.abc import Iterator

import pytest

from fpdb_3_legacy.GuiOpponentsReport import format_preflop_rates
from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale


@pytest.fixture(autouse=True)
def restore_format_locale() -> Iterator[None]:
    previous = get_format_locale()
    yield
    set_format_locale(previous)


def test_preflop_triplet_follows_active_locale() -> None:
    set_format_locale("fr_FR")

    assert format_preflop_rates(25.5, 18.5, 7.5) == "26/19/8"
