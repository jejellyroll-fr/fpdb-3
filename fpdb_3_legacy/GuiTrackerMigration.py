"""Import ▸ From another tracker: a wizard that brings PT4 / HM3 hands over (#612).

Five pages: pick the tracker, find its hand histories, see what the folder holds
room by room, import it, read what came over. The scan and the import both run
off the GUI thread. The tracker's own files are read, never moved: the import
runs with the move-imported / move-failed options switched off whatever the
Bulk Import tab is set to, so the tracker keeps a complete archive.

PokerTracker 4's database is a third source (#814): its hands are written out,
room by room, to a temporary folder that is then scanned and imported like any
other, and removed when the wizard closes. The database is only read.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from fpdb_3_legacy import ipoker_rooms, pt4_database, tracker_migration
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.pt4_database import DatabaseExport, Pt4Database
from fpdb_3_legacy.tracker_migration import TRACKERS, ExportScan, RoomSummary

log = get_logger("tracker_migration")

__all__ = ["GuiTrackerMigration"]

# How many unsupported files the scan page names before saying "and N more".
_UNSUPPORTED_SHOWN = 50


class ScanThread(QThread):
    """Sorts a folder's files by room without blocking the window.

    With ``export``, the folder is first filled from the tracker's database:
    ``export(thread)`` writes it and returns what it wrote.
    """

    scanned = Signal(object)  # ExportScan
    failed = Signal(str)
    reading = Signal(int, int)  # hands read from the database so far, of how many

    def __init__(
        self,
        config: Any,
        folder: str,
        export: Callable[[ScanThread], DatabaseExport] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.folder = folder
        self.export = export
        self.database_export: DatabaseExport | None = None

    def run(self) -> None:
        try:
            if self.export is not None:
                self.database_export = self.export(self)
                if self.isInterruptionRequested():
                    return
                self.folder = self.database_export.folder
            self.scanned.emit(tracker_migration.scan_folder(self.config, self.folder))
        except Exception as exc:  # intentional broad catch: surfaced on the page instead of lost in the thread
            log.exception("Reading the tracker's hands failed")
            self.failed.emit(str(exc))


def export_pt4(database: Pt4Database, password: str, folder: str, marks: dict[str, int]) -> Callable:
    """What a scan thread runs to fill ``folder`` from PT4's database, read-only."""

    def run(thread: ScanThread) -> DatabaseExport:
        conn = database.connect(password)
        try:
            return pt4_database.export_database(
                conn,
                folder,
                marks,
                progress=thread.reading.emit,
                should_stop=thread.isInterruptionRequested,
            )
        finally:
            conn.close()

    return run


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

        # PokerTracker 4 only: its database is a source too.
        self.source_choice = QWidget()
        choice_layout = QVBoxLayout(self.source_choice)
        choice_layout.setContentsMargins(0, 0, 0, 0)
        self.from_folder = QRadioButton(_("From a folder: the tracker's archive or an export"))
        self.from_database = QRadioButton(_("From the PokerTracker 4 database"))
        self.from_folder.setChecked(True)
        self.source_group = QButtonGroup(self)
        for button in (self.from_folder, self.from_database):
            self.source_group.addButton(button)
            choice_layout.addWidget(button)
            button.toggled.connect(self._show_source)
        layout.addWidget(self.source_choice)

        layout.addWidget(self._folder_box())
        layout.addWidget(self._database_box())
        layout.addStretch(1)
        self._show_source()

    def _folder_box(self) -> QWidget:
        """The tracker's steps to its archive, and the folder to read."""
        self.folder_box = QWidget()
        folder_layout = QVBoxLayout(self.folder_box)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.steps = QLabel()
        self.steps.setWordWrap(True)
        folder_layout.addWidget(self.steps)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText(_("Folder holding the hand histories"))
        self.folder.textChanged.connect(self.completeChanged)
        browse = QPushButton(_("Browse..."))
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder)
        row.addWidget(browse)
        folder_layout.addLayout(row)
        return self.folder_box

    def _database_box(self) -> QWidget:
        """Where PT4's database is; the password stays in this field and is never saved."""
        self.database_box = QWidget()
        database_layout = QVBoxLayout(self.database_box)
        database_layout.setContentsMargins(0, 0, 0, 0)
        explanation = QLabel(
            _(
                "fpdb reads the hands PokerTracker 4 keeps in its PostgreSQL database. The connection is "
                "read-only: fpdb never writes to it. PokerTracker 4 shows these settings in "
                "Database > Database Management. The password is used for this import only and is not saved."
            )
        )
        explanation.setWordWrap(True)
        database_layout.addWidget(explanation)
        defaults = Pt4Database()
        form = QFormLayout()
        self.host = QLineEdit(defaults.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(defaults.port)
        self.database_name = QLineEdit(defaults.database)
        self.user = QLineEdit(defaults.user)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for label, widget in (
            (_("Server"), self.host),
            (_("Port"), self.port),
            (_("Database"), self.database_name),
            (_("User"), self.user),
            (_("Password"), self.password),
        ):
            form.addRow(label, widget)
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.completeChanged)
        database_layout.addLayout(form)
        self.only_new = QCheckBox(_("Only the hands added since the last import from this database"))
        self.only_new.setChecked(True)
        database_layout.addWidget(self.only_new)
        return self.database_box

    def initializePage(self) -> None:
        tracker = self.tracker_page.tracker()
        self.setSubTitle(tracker.name)
        self.steps.setText("\n\n".join(f"{n}. {_(step)}" for n, step in enumerate(tracker.steps, 1)))
        self.source_choice.setVisible(tracker.key == "pt4")
        if tracker.key != "pt4":
            self.from_folder.setChecked(True)
        self._show_source()

    def _show_source(self) -> None:
        database = self.uses_database()
        self.folder_box.setVisible(not database)
        self.database_box.setVisible(database)
        self.completeChanged.emit()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Choose the folder holding the hand histories"))
        if folder:
            self.folder.setText(folder)

    def uses_database(self) -> bool:
        return self.from_database.isChecked() and self.tracker_page.tracker().key == "pt4"

    def database(self) -> Pt4Database:
        return Pt4Database(
            self.host.text().strip(),
            self.port.value(),
            self.database_name.text().strip(),
            self.user.text().strip(),
        )

    def isComplete(self) -> bool:
        if self.uses_database():
            database = self.database()
            return bool(database.host and database.database and database.user)
        return os.path.isdir(self.folder.text().strip())


class ScanPage(QWizardPage):
    """What the folder holds, before anything is written."""

    def __init__(self, config: Any, source_page: SourcePage) -> None:
        super().__init__()
        self.config = config
        self.source_page = source_page
        self.scan: ExportScan | None = None
        self.database_export: DatabaseExport | None = None
        # Folders written from the tracker's database; removed when the wizard closes.
        self.export_folders: list[str] = []
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
        self.room_question = QLabel(
            _(
                "The files do not say which iPoker room these names played on. Choose the room of each one. "
                "Setting the name as that room's screen name in Configure > Site Settings spares you this question."
            )
        )
        self.room_question.setWordWrap(True)
        self.room_question.hide()
        layout.addWidget(self.room_question)
        self.room_answers = QFormLayout()
        layout.addLayout(self.room_answers)
        self.room_choices: dict[str, QComboBox] = {}
        self.unsupported_label = QLabel()
        self.unsupported_label.setWordWrap(True)
        layout.addWidget(self.unsupported_label)
        self.unsupported = QListWidget()
        layout.addWidget(self.unsupported)

    def initializePage(self) -> None:
        self.scan = None
        self.database_export = None
        _fill(self.rooms, [])
        self._ask_rooms([])
        self.unsupported.clear()
        self.unsupported_label.clear()
        if self.source_page.uses_database():
            self.setTitle(_("What the database holds"))
            thread = self._database_scan()
            failure = _("The PokerTracker 4 database could not be read:\n%s")
        else:
            self.setTitle(_("What the folder holds"))
            self.status.setText(_("Reading the folder…"))
            thread = ScanThread(self.config, self.source_page.folder.text().strip())
            failure = _("The folder could not be read:\n%s")
        self.thread = thread
        self.running.append(thread)
        # A scan the user has moved past (Back, another folder, Next) may still
        # answer; only the current one gets to fill the page.
        thread.scanned.connect(
            lambda scan: self.show_scan(scan, thread.database_export) if self.thread is thread else None
        )
        thread.failed.connect(lambda message: self.status.setText(failure % message) if self.thread is thread else None)
        thread.reading.connect(lambda done, total: self._show_reading(done, total) if self.thread is thread else None)
        thread.finished.connect(lambda: self.running.remove(thread) if thread in self.running else None)
        thread.start()
        self.completeChanged.emit()

    def _database_scan(self) -> ScanThread:
        """A scan that first writes the PT4 database's hands to a folder of its own."""
        database = self.source_page.database()
        marks = pt4_database.load_marks(self.config, database) if self.source_page.only_new.isChecked() else {}
        folder = tempfile.mkdtemp(prefix="fpdb-pt4-")
        self.export_folders.append(folder)
        self.status.setText(_("Connecting to the PokerTracker 4 database…"))
        export = export_pt4(database, self.source_page.password.text(), folder, marks)
        return ScanThread(self.config, folder, export)

    def _show_reading(self, done: int, total: int) -> None:
        self.status.setText(
            _("Reading the PokerTracker 4 database: %(done)d of %(total)d hands…") % {"done": done, "total": total}
        )

    def cleanupPage(self) -> None:
        # Back from this page: whatever is still being read is no longer what the user will import.
        if self.thread is not None:
            self.thread.requestInterruption()  # a database export stops at the next hand
        self.thread = None
        self.scan = None
        self.database_export = None
        super().cleanupPage()

    def remove_exports(self) -> None:
        """Delete the folders written from the database; the wizard is closing."""
        for folder in self.export_folders:
            shutil.rmtree(folder, ignore_errors=True)
        self.export_folders = []

    def stop(self, wait_ms: int = 5000) -> None:
        """Let running scans finish before the wizard goes away; they only read files.

        The wait is bounded, since it runs on the UI thread. A scan of a large
        archive that overruns it is handed to the importer's orphan keeper,
        which holds it until it has really finished: dropping a running QThread
        takes the application down. Its signals are cut first, because the page
        they would reach is about to be deleted.
        """
        from fpdb_3_legacy.Importer import adopt_orphaned_import

        self.thread = None
        for thread in list(self.running):
            thread.requestInterruption()
            if thread.wait(wait_ms):
                continue
            # PySide warns when a signal has nothing left to disconnect; that is fine here.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                for signal in (thread.scanned, thread.failed, thread.reading, thread.finished):
                    with suppress(RuntimeError, TypeError):
                        signal.disconnect()
            self.running.remove(thread)
            adopt_orphaned_import(thread, lambda: None)  # nothing to clean up: a scan only reads

    def _ask_rooms(self, heroes: list[str]) -> None:
        """Ask which room each of these iPoker heroes played on; nobody is placed by default."""
        while self.room_answers.rowCount():
            self.room_answers.removeRow(0)
        self.room_choices = {}
        self.room_question.setVisible(bool(heroes))
        rooms = ipoker_rooms.room_choices(self.config)
        for hero in heroes:
            choice = QComboBox()
            choice.addItem(_("Choose a room…"), None)
            for room in rooms:
                choice.addItem(room, room)
            choice.currentIndexChanged.connect(self.completeChanged)
            self.room_answers.addRow(hero, choice)
            self.room_choices[hero] = choice

    def chosen_rooms(self) -> dict[str, str]:
        """The room the user chose for each iPoker hero the configuration could not place."""
        return {hero: choice.currentData() for hero, choice in self.room_choices.items() if choice.currentData()}

    @staticmethod
    def _database_text(database_export: DatabaseExport | None) -> str:
        """What was read from the database, as the first lines of the page; nothing for a folder."""
        if database_export is None:
            return ""
        read = _("%(hands)d hands and %(summaries)d tournament summaries read from the database.") % {
            "hands": database_export.hand_count,
            "summaries": database_export.summaries,
        }
        if database_export.repaired:
            read += (
                " "
                + _(
                    "%d of them were stored with the wrong character set (a euro sign read as Ä); "
                    "fpdb restores the room's own text."
                )
                % database_export.repaired
            )
        return read + "\n"

    def _nothing_to_import(self, database_export: DatabaseExport | None) -> str:
        if database_export is None:
            return _("No hand history fpdb can read was found in this folder.")
        if database_export.hand_count == 0 and self.source_page.only_new.isChecked():
            return _("No hand was added to the database since the last import.")
        return _("None of them is a hand history fpdb can read.")

    def show_scan(self, scan: ExportScan, database_export: DatabaseExport | None = None) -> None:
        self.scan = scan
        self.database_export = database_export
        rows = []
        warnings = []
        for site in sorted(scan.rooms, key=lambda s: (-len(scan.rooms[s]), s)):
            seen = ", ".join(sorted(scan.heroes.get(site, set()))) or "—"
            configured = tracker_migration.configured_hero(self.config, site)
            rows.append([site, str(len(scan.rooms[site])), seen, configured or _("not set")])
            if site == ipoker_rooms.GENERIC_ROOM and scan.undecided:
                continue  # the question below settles these; there is no screen name to set for "iPoker"
            if configured is None or (scan.heroes.get(site) and configured not in scan.heroes[site]):
                warnings.append(site)
        _fill(self.rooms, rows)
        self._ask_rooms(sorted(scan.undecided, key=str.casefold))
        read = self._database_text(database_export)
        if not scan.rooms:
            self.status.setText(read + self._nothing_to_import(database_export))
        else:
            text = read + _("%(files)d files from %(rooms)d rooms will be imported.") % {
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
        return self.scan is not None and self.scan.file_count > 0 and len(self.chosen_rooms()) == len(self.room_choices)


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
        importer.setIpokerRooms(self.scan_page.chosen_rooms())
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
        export = self.scan_page.database_export
        if export is not None and self.source_page.uses_database():
            # The next import from this database starts after these hands.
            try:
                pt4_database.save_marks(self.config, self.source_page.database(), export.marks)
            except OSError:
                log.exception("Could not remember what the PT4 import brought over")
        self.import_page.finish(_("Import finished."))
        # Open stats tabs built their filters before these games, limits and currencies existed.
        main_window = self.parent()
        if main_window is not None and hasattr(main_window, "refresh_after_import"):
            main_window.refresh_after_import()

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
        if not self.import_running():
            self.scan_page.remove_exports()
