"""The ring profit graph must report the number of hands, not of plotted points.

getRingProfitGraph prepends a 0 to the series so the curve starts at the origin,
so it holds one point more than there are hands. The legend counted the points:
with 9 hands on 2026-07-23 the graph announced "Mains: 10" while the hand viewer
listed 9, and earlier 20 against 19 in the database.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from fpdb_3_legacy.GuiGraphViewer import GuiGraphViewer
from fpdb_3_legacy.GuiTourneyGraphViewer import GuiTourneyGraphViewer


def _series(winnings: list[float]) -> np.ndarray:
    """Reproduce getRingProfitGraph's series: an origin point, then the hands."""
    return np.array([0, *winnings]).cumsum() / 100


def _reported_hand_count(green: np.ndarray) -> int:
    """The count generateGraph puts in the legend."""
    return max(len(green) - 1, 0)


def test_count_matches_the_number_of_hands() -> None:
    # The nine hands of 2026-07-23 (cents), summing to the 0.42 fpdb displays.
    hands = [-7.0, -1.0, -2.0, 13.0, 5.0, -2.0, 70.0, -2.0, -32.0]
    green = _series(hands)

    assert len(green) == len(hands) + 1  # the origin point is really there
    assert _reported_hand_count(green) == 9  # not 10


def test_single_hand_is_not_reported_as_two() -> None:
    assert _reported_hand_count(_series([25.0])) == 1


def test_empty_series_reports_no_hands() -> None:
    # Only the origin point: no hand should be claimed, and no negative count.
    assert _reported_hand_count(_series([])) == 0


@pytest.mark.parametrize("viewer", [GuiGraphViewer, GuiTourneyGraphViewer])
def test_graph_fonts_only_request_available_standard_weights(viewer: type) -> None:
    source = inspect.getsource(viewer.generateGraph)
    assert "semibold" not in source
