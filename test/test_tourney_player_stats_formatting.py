"""Localized display contracts for tournament player statistics."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.GuiTourneyPlayerStats import GuiTourneyPlayerStats
from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale
from fpdb_3_legacy.stat_registry import build_descriptor


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


def test_merge_descriptor_columns_accepts_postgresql_lowercase_identifiers() -> None:
    descriptor = build_descriptor(
        {
            "name": "cbet_flop",
            "inputs": ["street1CBDone", "street1CBChance"],
            "boolean_inputs": ["street1CBDone", "street1CBChance"],
            "value": "100 * street1CBDone / street1CBChance",
            "format": "%0.1f",
        },
    )
    cursor = MagicMock()
    cursor.description = [
        ("tourneytypeid",),
        ("playerid",),
        ("cbet_flop__street1cbdone",),
        ("cbet_flop__street1cbchance",),
    ]
    cursor.fetchall.return_value = [(17, 42, 3, 4)]
    db = SimpleNamespace(rollback=MagicMock())
    stats = SimpleNamespace(
        _grid_descriptors=[descriptor],
        cursor=cursor,
        db=db,
        sql=SimpleNamespace(query={"tourneyChipEVByPositionGrid": "SELECT <chipev_columns>"}),
        refineQuery=lambda query, *_args: query,
    )

    rows, columns = GuiTourneyPlayerStats._merge_chipev_columns(
        stats,
        "tourneyPlayerDetailedStats",
        [(17, 42)],
        ["tourneyTypeId", "playerId"],
        0,
        None,
        [42],
        [15],
        None,
    )

    assert rows == [[17, 42, "75.0"]]
    assert columns == ["tourneyTypeId", "playerId", "cbet_flop"]
    db.rollback.assert_not_called()
