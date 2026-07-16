from __future__ import annotations

import pytest

from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab


@pytest.mark.qt
def test_holdem_grid_updates_known_hand(qtbot) -> None:
    tab = StartingHandsTab()
    qtbot.addWidget(tab)

    tab.update_holdem_data({"AA": {"n": 12, "net": 4.5, "vpip": 100.0}})

    assert tab.active_mode == "holdem"
    assert len(tab.holdem_cells) == 169
    assert "Nombre de mains : 12" in tab.holdem_cells["AA"].toolTip()
