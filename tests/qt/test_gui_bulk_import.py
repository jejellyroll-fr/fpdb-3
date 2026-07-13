from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget


class FakeLock:
    def __init__(self):
        self.acquired = False
        self.released = False

    def acquire(self, wait=False, source=None):
        self.acquired = True
        return True

    def release(self):
        self.released = True


class FakeCursor:
    def execute(self, sql):
        self.sql = sql

    def fetchone(self):
        return (7,)

    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self):
        self.cursor = FakeCursor()
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


class FakeImporter:
    result = (3, 1, 0, 0, 0, 0.1)
    error: Exception | None = None
    delay = 0

    def __init__(self, *args, **kwargs):
        self.database = FakeDatabase()
        self.files = []
        self.filelist = {}
        self.run_called = False
        self.cleared = 0
        self.mode = None
        self.call_hud = None
        self.hands_in_db = None
        self.progress_callbacks = None
        self.move_imported = None
        self.move_failed = None

    def clearFileList(self):
        self.cleared += 1
        self.filelist = {}

    def addBulkImportImportFileOrDir(self, path, site="auto"):
        self.files.append((path, site))
        self.filelist[path] = (path, site)

    def set_progress_callbacks(self, start_cb, update_cb, end_cb):
        self.progress_callbacks = (start_cb, update_cb, end_cb)

    def runImport(self):
        self.run_called = True
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result

    def setHandsInDB(self, value):
        self.hands_in_db = value

    def setMode(self, value):
        self.mode = value

    def setCallHud(self, value):
        self.call_hud = value

    def setMoveImportedFiles(self, enabled, target_dir=None):
        self.move_imported = (enabled, target_dir)

    def setMoveFailedFiles(self, enabled, target_dir=None):
        self.move_failed = (enabled, target_dir)


class FakeConfig:
    supported_sites = {}


class RefreshParent(QWidget):
    def __init__(self):
        super().__init__()
        self.refreshed = False

    def refresh_after_import(self):
        self.refreshed = True


@pytest.fixture
def bulk_import_widget(qtbot, monkeypatch):
    from fpdb_3_legacy import GuiBulkImport

    FakeImporter.result = (3, 1, 0, 0, 0, 0.1)
    FakeImporter.error = None
    FakeImporter.delay = 0
    monkeypatch.setattr(GuiBulkImport.Importer, "Importer", FakeImporter)
    monkeypatch.setattr(GuiBulkImport.QMessageBox, "information", lambda *a, **k: None)

    lock = FakeLock()
    widget = GuiBulkImport.GuiBulkImport({"global_lock": lock}, FakeConfig(), sql=None)
    qtbot.addWidget(widget)
    widget.show()
    return widget, lock


@pytest.mark.qt
def test_import_button_triggers_use_case(qtbot, bulk_import_widget, tmp_path):
    widget, lock = bulk_import_widget
    widget.importDir.setText(str(tmp_path))

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert lock.acquired is True
    assert lock.released is True
    assert widget.importer.run_called is True
    assert widget.importer.files == [(str(tmp_path), "auto")]
    assert widget.importer.progress_callbacks is not None
    assert widget.importer.hands_in_db == 7
    assert widget.importer.mode == "bulk"
    assert widget.importer.call_hud is False


@pytest.mark.qt
def test_configured_import_uses_selected_site(qtbot, monkeypatch, tmp_path):
    from fpdb_3_legacy import GuiBulkImport

    class FakeSite:
        enabled = True
        HH_path = str(tmp_path)
        TS_path = ""

    class ConfigWithSite:
        supported_sites = {"Unibet": FakeSite()}

    FakeImporter.result = (1, 0, 0, 0, 0, 0.1)
    FakeImporter.error = None
    FakeImporter.delay = 0
    monkeypatch.setattr(GuiBulkImport.Importer, "Importer", FakeImporter)
    monkeypatch.setattr(GuiBulkImport.QMessageBox, "information", lambda *a, **k: None)

    lock = FakeLock()
    widget = GuiBulkImport.GuiBulkImport({"global_lock": lock}, ConfigWithSite(), sql=None)
    qtbot.addWidget(widget)
    widget.show()
    widget.import_tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert widget.importer.files == [(str(tmp_path), "Unibet")]


@pytest.mark.qt
def test_progress_bar_tracks_running_import(qtbot, bulk_import_widget, tmp_path):
    widget, _lock = bulk_import_widget
    FakeImporter.delay = 0.2
    widget.importDir.setText(str(tmp_path))

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.progress_bar.isVisible(), timeout=1_000)

    assert widget.load_button.isEnabled() is False
    assert widget.load_button.text() == "Importing..."
    assert widget.progress_bar.minimum() == 0
    assert widget.progress_bar.maximum() == 0

    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert widget.load_button.text() == "Bulk Import"
    assert widget.progress_bar.isVisible() is False


@pytest.mark.qt
def test_error_dialog_releases_ui_and_lock(qtbot, bulk_import_widget, monkeypatch, tmp_path):
    from fpdb_3_legacy import GuiBulkImport

    widget, lock = bulk_import_widget
    captured_warning = {}
    FakeImporter.error = RuntimeError("partial hand")
    widget.importDir.setText(str(tmp_path))

    def capture_warning(parent, title, message):
        captured_warning["parent"] = parent
        captured_warning["title"] = title
        captured_warning["message"] = message

    monkeypatch.setattr(GuiBulkImport.QMessageBox, "warning", capture_warning)

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert lock.released is True
    assert widget.importer.cleared == 2
    assert widget.progress_bar.isVisible() is False
    assert captured_warning == {
        "parent": widget,
        "title": "Bulk Import Error",
        "message": "partial hand",
    }


@pytest.mark.qt
def test_successful_import_refreshes_parent(qtbot, monkeypatch, tmp_path):
    from fpdb_3_legacy import GuiBulkImport

    FakeImporter.result = (3, 1, 0, 0, 0, 0.1)
    FakeImporter.error = None
    FakeImporter.delay = 0
    monkeypatch.setattr(GuiBulkImport.Importer, "Importer", FakeImporter)
    monkeypatch.setattr(GuiBulkImport.QMessageBox, "information", lambda *a, **k: None)

    lock = FakeLock()
    parent = RefreshParent()
    qtbot.addWidget(parent)
    parent.show()
    widget = GuiBulkImport.GuiBulkImport({"global_lock": lock}, FakeConfig(), sql=None, parent=parent)
    widget.show()
    widget.importDir.setText(str(tmp_path))

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert parent.refreshed is True


@pytest.mark.qt
def test_ui_event_loop_remains_responsive_during_import(qtbot, bulk_import_widget, tmp_path):
    widget, _lock = bulk_import_widget
    FakeImporter.delay = 0.3
    widget.importDir.setText(str(tmp_path))
    marker = []

    widget.load_clicked()
    QTimer.singleShot(20, lambda: marker.append("tick"))

    qtbot.waitUntil(lambda: bool(marker), timeout=1_000)

    assert widget.load_button.isEnabled() is False
    assert widget.importer.run_called is True

    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)


@pytest.mark.qt
def test_no_importable_files_warns_user(qtbot, monkeypatch, tmp_path):
    """When the selected sources hold no importable files, the user is told."""
    from fpdb_3_legacy import GuiBulkImport

    class EmptyImporter(FakeImporter):
        def addBulkImportImportFileOrDir(self, path, site="auto"):
            # Simulate a directory with no importable hand-history files.
            self.files.append((path, site))

    EmptyImporter.result = (0, 0, 0, 0, 0, 0.0)
    EmptyImporter.error = None
    EmptyImporter.delay = 0
    monkeypatch.setattr(GuiBulkImport.Importer, "Importer", EmptyImporter)

    captured = {}

    def capture_warning(parent, title, message):
        captured["title"] = title
        captured["message"] = message

    monkeypatch.setattr(GuiBulkImport.QMessageBox, "warning", capture_warning)
    monkeypatch.setattr(GuiBulkImport.QMessageBox, "information", lambda *a, **k: None)

    lock = FakeLock()
    widget = GuiBulkImport.GuiBulkImport({"global_lock": lock}, FakeConfig(), sql=None)
    qtbot.addWidget(widget)
    widget.show()
    widget.importDir.setText(str(tmp_path))

    widget.load_clicked()
    qtbot.waitUntil(lambda: widget.load_button.isEnabled(), timeout=10_000)

    assert captured["title"] == "Bulk Import"
    assert "No importable" in captured["message"]
    assert lock.released is True
