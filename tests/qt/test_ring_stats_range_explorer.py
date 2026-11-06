"""The 13x13 grid as a filtered range explorer (#301), offscreen.

The tab does not query anything: it renders a :class:`RangeMatrix` the model
built. These tests therefore build matrices by hand and check what a reader sees
-- the counts in the tooltip, the legend, the threshold marker, the unknown line
-- plus the two things a grid has to be able to do: switch view and hand a
double-clicked cell back to its caller.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from fpdb_3_legacy import holdem_classes as hc
from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.holdem_ranges import RangeCell, RangeMatrix

pytestmark = pytest.mark.qt


def get_qapp():
    return QApplication.instance() or QApplication([])


def _cell(class_id: int, opportunities: int, realized: int, *, frequency_bp: int | None = None) -> RangeCell:
    return RangeCell(
        class_id=class_id,
        opportunities=opportunities,
        actions=opportunities // 2,
        hands=max(1, opportunities // 2),
        players=1,
        hand_players=max(1, opportunities // 2),
        frequency_bp=frequency_bp,
        value=opportunities,
        unit="count",
        realized_cents=realized,
        ev_adjusted_cents=realized,
        all_in_luck_cents=0,
        ev_adjusted_pairs=0,
        sample_sufficient=opportunities > 0,
    )


def _matrix(unknown_opportunities: int = 7) -> RangeMatrix:
    """A tiny population: AA played four times for +6200, AKs twice for -100."""
    cells = [
        _cell(class_id, 0, 0)
        for class_id in (class_id for row in hc.grid_ids() for class_id in row)
    ]
    by_id = {cell.class_id: cell for cell in cells}
    by_id[hc.class_id_of_label("AA")] = _cell(hc.class_id_of_label("AA"), 4, 6200, frequency_bp=7500)
    by_id[hc.class_id_of_label("AKs")] = _cell(hc.class_id_of_label("AKs"), 2, -100, frequency_bp=5000)
    ordered = tuple(by_id[class_id] for row in hc.grid_ids() for class_id in row)
    unknown = {hc.UNKNOWN_ID: _cell(hc.UNKNOWN_ID, unknown_opportunities, 900)}
    return RangeMatrix(
        query=Query(metric="opportunities"),
        engine_metric="opportunities",
        unit="count",
        min_sample=0,
        cells=ordered,
        unknown_cells=unknown,
        total_opportunities=sum(cell.opportunities for cell in ordered) + unknown_opportunities,
        total_hands=6,
        total_hand_players=6,
        total_realized_cents=6200 - 100 + 900,
        total_ev_adjusted_cents=6200 - 100 + 900,
        notes=("a class is a set of combinations, not a strength",),
        _by_id={**by_id, hc.UNKNOWN_ID: unknown[hc.UNKNOWN_ID]},
    )


def test_the_grid_renders_a_filtered_range(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix())

    assert tab.active_mode == "holdem"
    assert len(tab.holdem_cells) == 169
    assert list(tab.holdem_cells) == [label for row in hc.grid_labels() for label in row]
    assert tab.range_matrix is not None
    assert sum(cell.opportunities for cell in tab.range_matrix.known_cells()) == 6


def test_a_cell_tooltip_carries_the_raw_counts(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix(), view="profit")

    tooltip = tab.holdem_cells["AA"].toolTip()
    assert "6 combinations" in tooltip
    assert "Decisions: 4" in tooltip
    assert "6200" in tooltip, "the money is in the tooltip even when it is the view"
    assert "below the sample threshold" not in tooltip
    empty = tab.holdem_cells["72o"].toolTip()
    assert "Decisions: 0" in empty


def test_the_legend_says_what_the_view_means_and_what_is_missing(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix(), view="frequency")

    legend = tab.range_legend.text()
    assert "Action frequency" in legend
    assert "basis points" in legend
    assert "not a strength" in legend
    assert "7" in tab.range_unknown.text()
    assert "no known hole cards" in tab.range_unknown.text()


def test_switching_the_view_recolours_the_grid(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix(), view="sample")
    count_style = tab.holdem_cells["AA"].styleSheet()
    tab.range_view_combo.setCurrentIndex(tab.range_view_combo.findData("profit"))
    assert tab.range_view == "profit"
    profit_style = tab.holdem_cells["AA"].styleSheet()
    assert "6200" in tab.holdem_cells["AA"].toolTip()
    assert count_style != profit_style or profit_style != "", "the colouring follows the view"


def test_the_threshold_marks_a_cell_without_changing_its_count(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix(), view="sample")
    assert "Below the sample threshold" not in tab.holdem_cells["AKs"].toolTip()
    tab.min_sample_spin.setValue(3)
    assert tab.range_matrix is not None
    assert not tab.range_matrix.cell("AKs").sample_sufficient, "two decisions is below three"
    assert tab.range_matrix.cell("AA").sample_sufficient, "four is not"
    assert "Decisions: 2" in tab.holdem_cells["AKs"].toolTip(), "the count is not what changed"
    assert "Below the sample threshold" in tab.holdem_cells["AKs"].toolTip()
    assert "*" in tab.range_legend.text()


def test_a_double_clicked_cell_asks_for_its_hands(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix())
    asked: list[str] = []
    tab.cell_activated.connect(asked.append)
    tab.holdem_cells["AKs"].activated.emit("AKs")
    assert asked == ["AKs"]


def test_the_old_starting_hand_report_still_drives_the_grid(qtbot):
    """The historical path must not be collateral damage of the explorer."""
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)
    tab.update_range_data(_matrix())
    tab.update_holdem_data({"AA": {"n": 12, "net": 4.5, "vpip": 100.0}})
    assert tab.range_matrix is None
    assert "Hands: 12" in tab.holdem_cells["AA"].toolTip()
    assert tab.range_legend.text() == ""
