"""test_ring_stats_views.py

Unit tests verifying pyqtgraph views instantiation and plot updates.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.qt


def get_qapp():
    return QApplication.instance() or QApplication([])


def test_dashboard_tab_pyqtgraph_plot(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.dashboard_view import DashboardTab

    tab = DashboardTab()
    qtbot.addWidget(tab)

    summary_stats = {
        "hands": 1500,
        "net": 250.50,
        "currency": "EUR",
        "vpip": 24.5,
        "pfr": 19.2,
        "pf3": 8.1,
        "aggfac": 2.75,
    }
    profits = (
        np.array([10.0, 25.0, 50.0, 100.0]),
        np.array([5.0, 15.0, 30.0, 60.0]),
        np.array([5.0, 10.0, 20.0, 40.0]),
        np.array([12.0, 28.0, 55.0, 105.0]),
    )

    tab.update_data(summary_stats, profits)
    from fpdb_3_legacy.localized_formats import format_number
    assert tab.card_hands.value_label.text() == format_number(1500, 0)


def test_positional_tab_pyqtgraph_plot(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.positional_view import PositionalTab

    tab = PositionalTab()
    qtbot.addWidget(tab)

    position_stats = {
        "SB": {"vpip": 35.0, "pfr": 25.0, "net": -50.0, "currency": "EUR"},
        "BB": {"vpip": 40.0, "pfr": 15.0, "net": -120.0, "currency": "EUR"},
        "Btn": {"vpip": 28.0, "pfr": 22.0, "net": 340.0, "currency": "EUR"},
        "CO": {"vpip": 24.0, "pfr": 19.0, "net": 180.0, "currency": "EUR"},
    }

    tab.update_position_data(position_stats)
    assert tab.poker_table.table_size == 6


def test_starting_hands_tab_pyqtgraph_plot(qtbot):
    get_qapp()
    from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab

    tab = StartingHandsTab()
    qtbot.addWidget(tab)

    omaha_stats = [
        {"hand": "AAKKds", "n": 10},
        {"hand": "QJT9ss", "n": 25},
        {"hand": "8765r", "n": 15},
    ]

    tab.update_omaha_data(omaha_stats, "omaha4")
    assert tab.active_mode == "omaha"
