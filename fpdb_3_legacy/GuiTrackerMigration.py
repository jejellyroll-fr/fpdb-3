"""Import ▸ From another tracker: a wizard that brings PT4 / HM3 hands over (#612).

Five pages: pick the tracker, find its hand histories, see what the folder holds
room by room, import it, read what came over. The scan and the import both run
off the GUI thread. The tracker's own files are read, never moved: the import
runs with the move-imported / move-failed options switched off whatever the
Bulk Import tab is set to, so the tracker keeps a complete archive.
"""

from __future__ import annotations

import os
from contextlib import suppress
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from fpdb_3_legacy import tracker_migration
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.tracker_migration import TRACKERS, ExportScan, RoomSummary

log = get_logger("tracker_migration")

__all__ = ["GuiTrackerMigration"]

# How many unsupported files the scan page names before saying "and N more".
_UNSUPPORTED_SHOWN = 50


class ScanThread(QThread):
    """Sorts a folder's files by room without blocking the window."""

    scanned = Signal(object)  # ExportScan
    failed = Signal(str)

    def __init__(self, config: Any, folder: str) -> None:
        super().__init__()
        self.config = config
        self.folder = folder

    def run(self) -> None:
        try:
            self.scanned.emit(tracker_migration.scan_folder(self.config, self.folder))
        except Exception as exc:  # intentional broad catch: surfaced on the page instead of lost in the thread
            log.exception("Scanning the tracker folder failed")
            self.failed.emit(str(exc))


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _fill(table: QTableWidget, rows: list[list[str]]) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(value))


class TrackerPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle(_("Which tracker are you coming from?"))
        self.setSubTitle(_("fpdb imports the hands it kept. Stats, HUD and notes come over separately."))
        layout = QVBoxLayout(self)
        self.group = QButtonGroup(self)
        for index, tracker in enumerate(TRACKERS):
            button = QRadioButton(tracker.name)
            button.setChecked(index == 0)
            self.group.addButton(button, index)
            layout.addWidget(button)

    def tracker(self) -> tracker_migration.Tracker:
        return TRACKERS[max(self.group.checkedId(), 0)]


class SourcePage(QWizardPage):
    def __init__(self, tracker_page: TrackerPage) -> None:
        super().__init__()
        self.tracker_page = tracker_page
        self.setTitle(_("Find the hand histories"))
        layout = QVBoxLayout(self)
        self.steps = QLabel()
        self.steps.setWordWrap(True)
        layout.addWidget(self.steps)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText(_("Folder holding the hand histories"))
        self.folder.textChanged.connect(self.completeChanged)
        browse = QPushButton(_("Browse..."))
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder)
        row.addWidget(browse)
        layout.addLayout(row)

    def initializePage(self) -> None:
        tracker = self.tracker_page.tracker()
        self.setSubTitle(tracker.name)
        self.steps.setText("\n\n".join(f"{n}. {_(step)}" for n, step in enumerate(tracker.steps, 1)))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Choose the folder holding the hand histories"))
        if folder:
            self.folder.setText(folder)

    def isComplete(self) -> bool:
        return os.path.isdir(self.folder.text().strip())


class ScanPage(QWizardPage):
    """What the folder holds, before anything is written."""

    def __init__(self, config: Any, source_page: SourcePage) -> None:
        super().__init__()
        self.config = config
        self.source_page = source_page
        self.scan: ExportScan | None = None
        self.thread: ScanThread | None = None
        # Every scan still running, current or not: a QThread dropped while it runs
        # takes the application down, so each is kept until it has finished.
        self.running: list[ScanThread] = []
        self.setTitle(_("What the folder holds"))
        self.setSubTitle(_("Nothing is imported yet."))
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rooms = _table([_("Room"), _("Files"), _("Hero in the files"), _("Hero in fpdb")])
        layout.addWidget(self.rooms)
        self.unsupported_label = QLabel()
        self.unsupported_label.setWordWrap(True)
        layout.addWidget(self.unsupported_label)
        self.unsupported = QListWidget()
        layout.addWidget(self.unsupported)

    def initializePage(self) -> None:
        self.scan = None
        _fill(self.rooms, [])
        self.unsupported.clear()
        self.unsupported_label.clear()
        self.status.setText(_("Reading the folder…"))
        thread = ScanThread(self.config, self.source_page.folder.text().strip())
        self.thread = thread
        self.running.append(thread)
        # A scan the user has moved past (Back, another folder, Next) may still
        # answer; only the current one gets to fill the page.
        thread.scanned.connect(lambda scan: self.show_scan(scan) if self.thread is thread else None)
        thread.failed.connect(
            lambda message: (
                self.status.setText(_("The folder could not be read:\n%s") % message) if self.thread is thread else None
            )
        )
        thread.finished.connect(lambda: self.running.remove(thread) if thread in self.running else None)
        thread.start()
        self.completeChanged.emit()

    def cleanupPage(self) -> None:
        # Back from this page: whatever is still being read is no longer what the user will import.
        self.thread = None
        self.scan = None
        super().cleanupPage()

    def stop(self, wait_ms: int = 5000) -> None:
        """Let running scans finish before the wizard goes away; they only read files."""
        self.thread = None
        for thread in list(self.running):
            thread.wait(wait_ms)

    def show_scan(self, scan: ExportScan) -> None:
        self.scan = scan
        rows = []
        warnings = []
        for site in sorted(scan.rooms, key=lambda s: (-len(scan.rooms[s]), s)):
            seen = ", ".join(sorted(scan.heroes.get(site, set()))) or "—"
            configured = tracker_migration.configured_hero(self.config, site)
            rows.append([site, str(len(scan.rooms[site])), seen, configured or _("not set")])
            if configured is None or (scan.heroes.get(site) and configured not in scan.heroes[site]):
                warnings.append(site)
        _fill(self.rooms, rows)
        if not scan.rooms:
            self.status.setText(_("No hand history fpdb can read was found in this folder."))
        else:
            text = _("%(files)d files from %(rooms)d rooms will be imported.") % {
                "files": scan.file_count,
                "rooms": len(scan.rooms),
            }
            if warnings:
                text += "\n" + _(
                    "Set your screen name for %s in Configure > Site Settings before importing, "
                    "or your own stats will not be told apart from your opponents'."
                ) % ", ".join(warnings)
            self.status.setText(text)
        if scan.unsupported:
            self.unsupported_label.setText(
                _("%d files are not hand histories fpdb can read; they will be left out:") % len(scan.unsupported)
            )
            shown = scan.unsupported[:_UNSUPPORTED_SHOWN]
            self.unsupported.addItems(shown)
            if len(scan.unsupported) > len(shown):
                self.unsupported.addItem(_("… and %d more") % (len(scan.unsupported) - len(shown)))
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self.scan is not None and self.scan.file_count > 0


class ImportPage(QWizardPage):
    def __init__(self, wizard: GuiTrackerMigration) -> None:
        super().__init__()
        self.owner = wizard
        self.done = False
        self.setTitle(_("Importing"))
        self.setSubTitle(_("Large archives take a while. The tracker's files are read, never moved."))
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.current = QLabel()
        self.current.setWordWrap(True)
        layout.addWidget(self.current)

    def initializePage(self) -> None:
        self.done = False
        self.progress.setRange(0, 0)
        self.current.clear()
        self.owner.start_import()

    def on_started(self, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(0)

    def on_file(self, filename: str, _handcount: str) -> None:
        self.progress.setValue(min(self.progress.value() + 1, self.progress.maximum()))
        self.current.setText(os.path.basename(filename))

    def finish(self, message: str) -> None:
        self.done = True
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.current.setText(message)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self.done


class SummaryPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle(_("What came over"))
        layout = QVBoxLayout(self)
        self.headline = QLabel()
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)
        self.rooms = _table([_("Room"), _("Hero"), _("Files"), _("Hands"), _("Duplicates"), _("Partial"), _("Errors")])
        layout.addWidget(self.rooms)
        self.note = QLabel(
            _("Stats, the HUD and player notes are not part of this import; see the migration guide in the docs.")
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def show_summary(self, rooms: list[RoomSummary], unsupported: int) -> None:
        _fill(
            self.rooms,
            [
                [
                    room.site,
                    room.hero or _("not set"),
                    str(room.files),
                    str(room.stored),
                    str(room.duplicates),
                    str(room.partial),
                    str(room.errors),
                ]
                for room in rooms
            ],
        )
        stored = sum(room.stored for room in rooms)
        text = _("%(hands)d hands imported from %(rooms)d rooms.") % {"hands": stored, "rooms": len(rooms)}
        if unsupported:
            text += " " + _("%d files were left out: fpdb cannot read them.") % unsupported
        self.headline.setText(text)


class GuiTrackerMigration(QWizard):
    """The wizard; ``settings`` and ``sql`` are the main window's, as for Bulk Import."""

    def __init__(self, settings: Any, config: Any, sql: Any = None, parent: Any = None, importer: Any = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.config = config
        self.sql = sql
        self.importer = importer
        self.import_thread: Any = None
        self.lock_held = False
        self.setWindowTitle(_("Import from another tracker"))
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.tracker_page = TrackerPage()
        self.source_page = SourcePage(self.tracker_page)
        self.scan_page = ScanPage(config, self.source_page)
        self.import_page = ImportPage(self)
        self.summary_page = SummaryPage()
        for page in (self.tracker_page, self.source_page, self.scan_page, self.import_page, self.summary_page):
            self.addPage(page)
        self.resize(760, 560)

    # --- import ------------------------------------------------------------

    def _make_importer(self) -> Any:
        from fpdb_3_legacy import Importer

        return Importer.Importer(self, self.settings, self.config, self.sql, self)

    def start_import(self) -> None:
        from fpdb_3_legacy.GuiBulkImport import BulkImportThread

        lock = self.settings.get("global_lock") if isinstance(self.settings, dict) else None
        if lock is not None:
            if not lock.acquire(wait=False, source="GuiTrackerMigration"):
                self.import_page.finish(_("Another import is running. Try again once it has finished."))
                self.import_page.done = False
                self.import_page.completeChanged.emit()
                return
            self.lock_held = True
        if self.importer is None:
            self.importer = self._make_importer()
        importer = self.importer
        with suppress(Exception):
            importer.setHandsInDB(importer.database.getHandCount())
        importer.setMode("bulk")
        importer.setThreads(-1)
        importer.setCallHud(False)
        # Read the tracker's archive, never move it.
        importer.setMoveImportedFiles(False)
        importer.setMoveFailedFiles(False)
        self.button(QWizard.WizardButton.BackButton).setEnabled(False)
        # Exactly the files the preview showed: walking the folder again would also take
        # what the scan leaves out on purpose (symlinks, which can point outside the archive).
        scan = self.scan_page.scan
        sources = [(path, "auto") for files in (scan.rooms.values() if scan else ()) for path in files]
        self.import_thread = BulkImportThread(importer, sources)
        self.import_thread.progress_started.connect(self.import_page.on_started)
        self.import_thread.progress_updated.connect(self.import_page.on_file)
        self.import_thread.finished.connect(self.import_finished)
        self.import_thread.error.connect(self.import_error)
        self.import_thread.start()

    def _release_lock(self) -> None:
        if self.lock_held:
            with suppress(Exception):
                self.settings["global_lock"].release()
            self.lock_held = False

    def import_finished(self, _payload: tuple) -> None:
        self._release_lock()
        rooms = tracker_migration.summarize(getattr(self.importer, "file_results", {}), self.config)
        scan = self.scan_page.scan
        self.summary_page.show_summary(rooms, len(scan.unsupported) if scan else 0)
        self.import_page.finish(_("Import finished."))

    def import_error(self, message: str) -> None:
        self._release_lock()
        self.import_page.finish(_("The import stopped on an error:\n%s") % message)
        self.import_page.done = False
        self.import_page.completeChanged.emit()

    def import_running(self) -> bool:
        return self.import_thread is not None and self.import_thread.isRunning()

    # --- closing -----------------------------------------------------------

    def reject(self) -> None:
        if self.import_running():
            return  # an import in progress is not abandoned halfway
        self._close_importer()
        super().reject()

    def accept(self) -> None:
        self._close_importer()
        super().accept()

    def _close_importer(self) -> None:
        self.scan_page.stop()
        self._release_lock()
        importer = self.importer
        if importer is not None and not self.import_running():
            with suppress(Exception):
                importer.close()
