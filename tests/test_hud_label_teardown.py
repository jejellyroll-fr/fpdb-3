#!/usr/bin/env python3
"""Regression tests for disposing of a HUD's label in the main window.

idle_kill() detached the label with setParent(None). That does not destroy a
widget -- it makes it top-level, i.e. its own window, captioned with its text
("SealsWithClubs - 298243657 Table 3"). In a tournament the hero is moved from
table to table, and every move left one more of these on screen next to the HUD
main window.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window():
    window = QWidget()
    layout = QVBoxLayout()
    window.setLayout(layout)
    window.show()
    QApplication.processEvents()
    return window, layout


def _labelled(layout, text="SealsWithClubs - 298243657 Table 3"):
    label = QLabel(text)
    layout.addWidget(label)
    QApplication.processEvents()
    return label


def _drain():
    QApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_the_label_is_destroyed_not_detached(main_window):
    _, layout = main_window
    label = _labelled(layout)

    # What idle_kill() now does.
    layout.removeWidget(label)
    label.hide()
    label.deleteLater()
    _drain()

    assert not shiboken6.isValid(label)


def test_detaching_alone_would_leave_a_window_behind(main_window):
    # The old behaviour, kept as a test: setParent(None) is what turned the label
    # into a window of its own rather than getting rid of it.
    _, layout = main_window
    label = _labelled(layout)

    layout.removeWidget(label)
    label.setParent(None)
    _drain()

    assert shiboken6.isValid(label)
    assert label.isWindow()


def test_removing_from_the_layout_keeps_the_label_a_child(main_window):
    # removeWidget() only drops it from the layout; the label stays parented, which
    # is why it must be deleted explicitly and must not be reparented to None.
    window, layout = main_window
    label = _labelled(layout)

    layout.removeWidget(label)

    assert label.parent() is window
    assert not label.isWindow()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
