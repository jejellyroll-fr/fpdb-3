"""Tests for GuiAutoNotesWorkbench card rendering and evidence image widgets."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_cards_widget_creation(qtbot):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy.GuiAutoNotesWorkbench import GuiAutoNotesWorkbench

    QApplication.instance() or QApplication([])

    bench = GuiAutoNotesWorkbench(None)
    qtbot.addWidget(bench)

    # Test cards widget with valid card text
    widget = bench._cards_widget("8h 7h 7d 2s")
    assert widget is not None
    assert widget.layout().count() >= 4

    # Test evidence widget with valid evidence string containing cards
    evidence_str = "flop=Th 9s Jd; hole=8h 7h 7d 2s; river=5c 4s; flush_draw=nut_fd"
    ev_widget = bench._evidence_widget(evidence_str)
    assert ev_widget is not None
    assert ev_widget.layout().count() > 5


def test_get_card_pixmap_caching(qtbot):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy.GuiAutoNotesWorkbench import GuiAutoNotesWorkbench

    QApplication.instance() or QApplication([])

    bench = GuiAutoNotesWorkbench(None)
    qtbot.addWidget(bench)

    pix1 = bench._get_card_pixmap("A", "s", 25, 33)
    pix2 = bench._get_card_pixmap("A", "s", 25, 33)

    assert pix1 is not None
    assert pix1 == pix2
