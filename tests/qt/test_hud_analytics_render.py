"""An analytics-backed HUD cell renders on the label it is bound to (#335).

The model half lives in ``tests/test_hud_analytics_stats.py``; this is the GUI
half: that a seat's label reads its own session value, that a bound cell with no
value yet shows the no-data convention instead of a same-named native stat, and
that a native cell never enters the analytics path at all.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import analytics_definitions as dsl
from fpdb_3_legacy import hud_analytics_stats as stats
from fpdb_3_legacy.Aux_Hud import SimpleLabel, SimpleStat


def _aw(session: stats.AnalyticsStatSession | None) -> MagicMock:
    aw = MagicMock()
    aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0}
    aw.font_size = 10
    aw.aw_class_label = SimpleLabel
    aw.hud.hand_instance = None
    aw.hud.stat_dict = {}
    if session is not None:
        aw.analytics_session = lambda: session
    else:
        aw.analytics_session = lambda: None
    return aw


def _binding(definition: str = "fold_to_cbet_flop") -> stats.AnalyticsStatBinding:
    return stats.AnalyticsStatBinding(stat_name=definition, definition=definition)


def _value(text: str, sample: int = 25) -> stats.AnalyticsStatValue:
    return stats.AnalyticsStatValue(
        stat_name="fold_to_cbet_flop",
        definition="fold_to_cbet_flop",
        state=stats.STATE_OK,
        raw=40.0,
        sample=sample,
        rendered=text,
    )


class TestSimpleStatRender:
    def test_a_bound_cell_shows_its_own_seat_value(self, qtbot) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding()])
        session.publish({7: {"fold_to_cbet_flop": _value("40%")}})
        stat = SimpleStat("fold_to_cbet_flop", 1, "popup", _aw(session))
        qtbot.addWidget(stat.lab)

        stat.update(7, {7: {"screen_name": "Cara"}})

        assert stat.lab.text() == "40%"

    def test_another_seat_does_not_show_the_first_seat_value(self, qtbot) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding()])
        session.publish({7: {"fold_to_cbet_flop": _value("40%")}})
        stat = SimpleStat("fold_to_cbet_flop", 1, "popup", _aw(session))
        qtbot.addWidget(stat.lab)

        stat.update(9, {9: {"screen_name": "Bob"}})

        assert stat.lab.text() == dsl.NO_DATA

    def test_a_bound_cell_with_no_value_yet_shows_no_data(self, qtbot) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding()])
        stat = SimpleStat("fold_to_cbet_flop", 1, "popup", _aw(session))
        qtbot.addWidget(stat.lab)

        stat.update(7, {7: {"screen_name": "Cara"}})

        assert stat.lab.text() == dsl.NO_DATA

    def test_an_unbound_cell_keeps_the_native_path(self, qtbot) -> None:
        """A profile with no analytics cell must be exactly what it was."""
        stat = SimpleStat("vpip", 1, "popup", _aw(None))
        qtbot.addWidget(stat.lab)

        stat.update(7, {7: {"screen_name": "Cara", "vpip": 50, "vpip_opp": 100}})

        assert stat.lab.text() == "50.0"

    def test_a_table_with_no_analytics_session_is_safe(self, qtbot) -> None:
        aw = MagicMock()
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0}
        aw.font_size = 10
        aw.aw_class_label = SimpleLabel
        aw.hud.hand_instance = None
        aw.hud.stat_dict = {}
        del aw.analytics_session
        stat = SimpleStat("vpip", 1, "popup", aw)
        qtbot.addWidget(stat.lab)

        stat.update(7, {7: {"screen_name": "Cara", "vpip": 25, "vpip_opp": 100}})

        assert stat.lab.text() == "25.0"

    def test_the_value_carries_its_tooltip(self, qtbot) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding()])
        session.publish({7: {"fold_to_cbet_flop": _value("40%")}})
        stat = SimpleStat("fold_to_cbet_flop", 1, "popup", _aw(session))
        qtbot.addWidget(stat.lab)

        stat.update(7, {7: {"screen_name": "Cara"}})

        assert stat.number[1] == "40%"
        assert "Sample: 25 decisions" in stat.number[5]
