#!/usr/bin/env python3
"""Tests for the multi-panel HUD preview (coloured, titled boxes).

Covers HudPreviewWidget.set_blocks: each block renders as a bordered box with a
coloured title header and a grid of cells using per-stat hudcolor/hudbgcolor.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from fpdb_3_legacy import ModernHudPreferences as M

_app = None


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication([])
    return _app


def _blocks():
    return [
        {"label": "SB 3h", "position": "SB", "rows": 1, "cols": 2,
         "bordercolor": "#d7b500", "title_bgcolor": "#d7b500", "title_fgcolor": "#111111",
         "stats": [{"row": 0, "col": 0, "stat": "vpip", "hudcolor": "#ffffff", "hudbgcolor": "#232323"},
                   {"row": 0, "col": 1, "stat": "pfr", "hudcolor": "#ffffff", "hudbgcolor": "#232323"}]},
        {"label": "Villain Info 3H", "position": "", "rows": 1, "cols": 1,
         "bordercolor": "#9a9a9a", "title_bgcolor": "#9a9a9a", "title_fgcolor": "#111111",
         "stats": [{"row": 0, "col": 0, "stat": "n", "hudcolor": "#0069d2", "hudbgcolor": "#a2a28a"}]},
    ]


def test_set_blocks_renders_titled_boxes():
    pv = M.HudPreviewWidget()
    pv.set_blocks(_blocks())
    assert len(pv.blocks) == 2
    labels = [w.text() for w in pv.findChildren(QLabel)]
    # both panel title headers present
    assert "SB 3h" in labels
    assert "Villain Info 3H" in labels


def test_title_header_uses_block_colours():
    pv = M.HudPreviewWidget()
    pv.set_blocks(_blocks())
    title = next(w for w in pv.findChildren(QLabel) if w.text() == "SB 3h")
    qss = title.styleSheet().lower()
    assert "#d7b500" in qss  # gold title background
    assert "#111111" in qss  # title text colour


def test_cell_uses_per_stat_colours():
    pv = M.HudPreviewWidget()
    pv.set_blocks(_blocks())
    # the 'n' cell carries blue text on tan bg
    cell = next(w for w in pv.findChildren(QLabel)
                if w.toolTip() == "n")
    qss = cell.styleSheet().lower()
    assert "#0069d2" in qss  # text colour
    assert "#a2a28a" in qss  # bg colour


def test_set_stats_clears_blocks_and_vice_versa():
    pv = M.HudPreviewWidget()
    pv.set_blocks(_blocks())
    assert pv.blocks
    pv.set_stats([{"row": 0, "col": 0, "stat": "vpip"}])
    assert pv.blocks == []  # switching back to flat clears blocks


# ---------------------------------------------------------------------------
# PT4-style design canvas (typed coloured chips)
# ---------------------------------------------------------------------------
def _canvas_block():
    return {
        "label": "BB 3h", "rows": 3, "cols": 4,
        "stats": [{"row": 1, "col": 1, "stat": "vpip", "colspan": 1},
                  {"row": 1, "col": 2, "stat": "pfr"}],
        "texts": [{"rowcol": (0, 0), "label": "BB", "colspan": 1},
                  {"rowcol": (2, 0), "label": "POST FLOP", "colspan": 4},
                  {"rowcol": (1, 0), "label": "", "colspan": 1}],  # empty placeholder
        "hlines": [{"rowcol": (0, 2), "colspan": 0, "color": "#d7b500"}],
    }


def test_canvas_renders_typed_chips():
    cv = M.HudDesignCanvas()
    cv.set_block(0, _canvas_block())
    kinds = sorted(c.kind for c in cv.chips)
    # 2 stats + 2 non-empty texts (BB, POST FLOP) + 1 hline; empty label skipped
    assert kinds == ["hline", "stat", "stat", "text", "text"]
    {ch.findChild(QLabel) for ch in cv.chips}  # at least chips exist
    assert len(cv.chips) == 5


def test_canvas_chip_click_emits_selection():
    cv = M.HudDesignCanvas()
    cv.set_block(2, _canvas_block())
    received = []
    cv.item_selected.connect(lambda payload: received.append(payload))
    stat_chip = next(c for c in cv.chips if c.kind == "stat")
    stat_chip.clicked.emit()
    assert received and received[0][0] == 2  # block index
    assert received[0][1] == "stat"


def test_canvas_empty_block_is_safe():
    cv = M.HudDesignCanvas()
    cv.set_block(0, None)
    assert cv.chips == []


def test_preview_grows_to_content_so_a_large_hud_can_scroll():
    """A large panel makes the preview widget grow to its natural size (so a
    wrapping scroll area shows scrollbars) instead of clamping/overlapping."""
    pv = M.HudPreviewWidget()
    pv.resize(360, 300)
    big = {"label": "Pre Flop", "position": "", "rows": 20, "cols": 5,
           "stats": [{"row": r, "col": c, "stat": "vpip"} for r in range(20) for c in range(5)],
           "texts": [], "hlines": []}
    pv.set_blocks([big])
    _app.processEvents()
    _app.processEvents()
    # the HUD keeps its full height (not clamped to the 300px viewport) and the
    # widget's minimum height grows past it, which is what drives the scrollbar.
    assert pv.hud_window.height() > 300
    assert pv.minimumHeight() >= pv.hud_window.height()


def test_popup_design_canvas_mirrors_stats(tmp_path):
    """The popup tab's WYSIWYG canvas shows the popup's stats as chips, synced."""
    import os
    import shutil

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M

    example = os.path.join(os.path.dirname(__file__), "..", "HUD_config.xml.example")
    if not os.path.exists(example):
        import pytest
        pytest.skip("example config missing")
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(example, cfg)
    dlg = M.ModernHudPreferences(Conf.Config(file=str(cfg)), None)

    target = next(n for n, d in dlg.popup_windows.items() if d.get("stats"))
    n_stats = len(dlg.popup_windows[target]["stats"])
    ci = dlg.popup_combo.findText(target)
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    assert len(dlg.popup_canvas.chips) == n_stats           # one chip per stat
    assert dlg.popup_stats_list.count() == n_stats          # list mirrors it
    dlg.popup_canvas.chips[1].clicked.emit()                # chip click -> list row
    assert dlg.popup_stats_list.currentRow() == 1
    assert dlg.pi_props_box.isEnabled()
    assert dlg.pi_text.text() == dlg.popup_windows[target]["stats"][1]["stat_name"]
    dlg.pi_text.setText("vpip")
    dlg.pi_submenu.setText("Preflop")
    dlg._popup_item_changed()
    assert dlg.popup_windows[target]["stats"][1] == {"stat_name": "vpip", "submenu": "Preflop"}
    assert "vpip → Preflop" in dlg.popup_stats_list.item(1).text()
    dlg._popup_canvas_remove_row(0)                          # canvas - removes a stat
    assert len(dlg.popup_windows[target]["stats"]) == n_stats - 1


def test_canvas_compact_mode_packs_grid_cells():
    """Compact mode renders a dense matrix: no per-row +/- buttons, tight chips."""
    from PySide6.QtWidgets import QPushButton

    cv = M.HudDesignCanvas()
    cv.compact = True
    block = {"label": "", "rows": 3, "cols": 3, "texts": [], "hlines": [],
             "stats": [{"row": r, "col": c, "stat": f"{r}{c}"} for r in range(3) for c in range(3)]}
    cv.set_block(0, block)
    assert len(cv.chips) == 9
    # compact grids drop the per-row add/remove buttons
    assert not cv._host.findChildren(QPushButton)
    # non-compact keeps them
    cv2 = M.HudDesignCanvas()
    cv2.set_block(0, block)
    assert cv2._host.findChildren(QPushButton)
