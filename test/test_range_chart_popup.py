#!/usr/bin/env python3
"""Tests for fpdb_3_legacy.RangeChartPopup — the range-chart HUD widget.

Covers the hand->matrix mapping, the contrast-text helper, and the rendered
13x13 grid built from charts extracted out of the real .pt4hud fixture.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from fpdb_3_legacy import RangeChartPopup as R
from fpdb_3_legacy import pt4hud

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "generationpoker_3h.pt4hud")


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# pure logic
# ---------------------------------------------------------------------------
def test_hand_to_rowcol_pairs_on_diagonal():
    assert R.hand_to_rowcol("AA") == (0, 0)
    assert R.hand_to_rowcol("KK") == (1, 1)
    assert R.hand_to_rowcol("22") == (12, 12)


def test_hand_to_rowcol_suited_upper_offsuit_lower():
    assert R.hand_to_rowcol("AKs") == (0, 1)  # suited -> upper-right
    assert R.hand_to_rowcol("AKo") == (1, 0)  # offsuit -> lower-left
    assert R.hand_to_rowcol("72o") == (R.RANKS.index("2"), R.RANKS.index("7"))


def test_contrast_text():
    assert R._contrast_text("#000000") == "#ffffff"
    assert R._contrast_text("#ffffff") == "#000000"
    assert R._contrast_text("#009393") == "#ffffff"  # dark teal -> white text


# ---------------------------------------------------------------------------
# widget rendering from the real fixture
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="pt4hud fixture missing")
class TestGridWidget:
    @pytest.fixture(scope="class")
    def charts(self):
        return pt4hud.extract_charts(FIXTURE)

    def test_build_grid_widget_has_169_cells(self, charts):
        push = next(c for c in charts if c.name == "Push Nash")
        w = R.build_grid_widget(push)
        labels = w.findChildren(QLabel)
        # 169 hand cells + 1 title label
        hand_labels = [lb for lb in labels if lb.text() in {c.hand for c in push.cells}]
        assert len(hand_labels) == 169
        assert any(lb.text() == push.name for lb in labels)  # title present

    def test_cells_carry_their_fill_colour(self, charts):
        push = next(c for c in charts if c.name == "Push Nash")
        w = R.build_grid_widget(push)
        by_hand = {c.hand: c.fill for c in push.cells}
        aa = next(lb for lb in w.findChildren(QLabel) if lb.text() == "AA")
        assert by_hand["AA"][1:] in aa.styleSheet().lower()


def test_load_charts_logic_via_pop_params():
    # build a bare instance (skip the Qt-heavy Popup.__init__)
    inst = R.RangeChartPopup.__new__(R.RangeChartPopup)
    chart = pt4hud.Chart(name="X", cells=[pt4hud.ChartCell(hand="AA", fill="#009393")])

    class _Pop:
        pu_class_params = {"charts": [chart]}

    inst.pop = _Pop()
    assert inst._load_charts() == [chart]

    class _PopBad:
        pu_class_params = {"source": "/nonexistent/file.pt4hud"}

    inst.pop = _PopBad()
    assert inst._load_charts() == []  # load failure handled gracefully

    class _PopNone:
        pu_class_params = None

    inst.pop = _PopNone()
    assert inst._load_charts() == []


def test_rangechartpopup_is_popup_subclass():
    from fpdb_3_legacy.Popup import Popup

    assert issubclass(R.RangeChartPopup, Popup)


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="pt4hud fixture missing")
def test_load_charts_from_pt4hud_and_json(tmp_path):
    charts = R.load_charts(FIXTURE)
    assert {c.name for c in charts} >= {"Push Nash", "Call Nash"}
    # round-trip through the JSON export
    import json

    jpath = tmp_path / "layout.json"
    jpath.write_text(json.dumps(pt4hud.to_dict(pt4hud.parse(FIXTURE))), encoding="utf-8")
    jcharts = R.load_charts(str(jpath))
    assert {c.name for c in jcharts} >= {"Push Nash", "Call Nash"}
    assert len(next(c for c in jcharts if c.name == "Push Nash").cells) == 169
