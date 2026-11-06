#!/usr/bin/env python3
"""Tests for the GuiBulkImport "move imported/failed files" widgets.

The Importer backend (setMoveImportedFiles/setMoveFailedFiles) is covered by
test_importer_move_files.py; these tests cover the GUI wiring: that the widgets
are built from settings and that load_clicked pushes their state into the
importer via _apply_move_settings. The Importer is mocked so no DB is needed.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


def _make_config():
    config = MagicMock()
    config.supported_sites = {}  # no enabled sites -> empty import tree
    return config


def _make_widget(settings):
    from fpdb_3_legacy import GuiBulkImport

    with patch.object(GuiBulkImport.Importer, "Importer", return_value=MagicMock()):
        return GuiBulkImport.GuiBulkImport(settings, _make_config())


@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


def test_widgets_built_from_settings(_qapp):
    """Checkboxes and path fields reflect the persisted settings."""
    settings = {
        "moveimportedfiles": True,
        "moveImportedFilesDir": "/data/imported",
        "movefailedfiles": False,
        "moveFailedFilesDir": "/data/failed",
    }
    w = _make_widget(settings)

    assert w.moveImportedCheck.isChecked() is True
    assert w.moveImportedDir.text() == "/data/imported"
    assert w.moveFailedCheck.isChecked() is False
    assert w.moveFailedDir.text() == "/data/failed"


def test_defaults_when_settings_absent(_qapp):
    """With no move settings the checkboxes are off and paths empty."""
    w = _make_widget({})
    assert w.moveImportedCheck.isChecked() is False
    assert w.moveFailedCheck.isChecked() is False
    assert w.moveImportedDir.text() == ""
    assert w.moveFailedDir.text() == ""


def test_apply_move_settings_pushes_widget_state_to_importer(_qapp):
    """_apply_move_settings forwards the current widget state to the importer setters."""
    w = _make_widget({})
    w.moveImportedCheck.setChecked(True)
    w.moveImportedDir.setText("/out/imported")
    w.moveFailedCheck.setChecked(True)
    w.moveFailedDir.setText("/out/failed")

    w._apply_move_settings()

    w.importer.setMoveImportedFiles.assert_called_once_with(True, "/out/imported")
    w.importer.setMoveFailedFiles.assert_called_once_with(True, "/out/failed")


def test_browse_into_updates_line_edit(_qapp):
    """_browse_into writes the chosen directory into the given field."""
    from PySide6.QtWidgets import QLineEdit

    from fpdb_3_legacy import GuiBulkImport

    w = _make_widget({})
    field = QLineEdit()
    with patch.object(GuiBulkImport.QFileDialog, "getExistingDirectory", return_value="/picked/dir"):
        w._browse_into(field)
    assert field.text() == "/picked/dir"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
