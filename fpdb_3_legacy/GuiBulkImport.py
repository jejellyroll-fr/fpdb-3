"""GuiBulkImport module for FPDB bulk import functionality.

Copyright 2008-2011 Steffen Schaumburg
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

#    Standard Library modules
from __future__ import annotations

import os
import sys
from pathlib import Path
from time import time
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration, Database, Importer, interlocks
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_number
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.RegressionFileComparator import compare_importer_sidecars

#    fpdb/FreePokerTools modules


if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("gui_bulk_import")


class BulkImportThread(QThread):
    """Worker thread to run bulk import off the main GUI thread."""
    # Signal emitted when the import is complete, returning (file_count, results tuple)
    finished = Signal(tuple)
    # Signal emitted when an error occurs
    error = Signal(str)
    # Thread-safe progress signals
    progress_started = Signal(int)
    progress_updated = Signal(str, str)
    progress_completed = Signal()

    def __init__(self, importer, import_sources) -> None:
        super().__init__()
        self.importer = importer
        self.import_sources = import_sources

    def run(self) -> None:
        try:
            self.importer.clearFileList()
            for import_dir, site in self.import_sources:
                self.importer.addBulkImportImportFileOrDir(import_dir, site=site)

            # Number of importable files actually discovered in the selected
            # sources. When this is 0 the directories were empty (or only held
            # ignored files such as archives), which otherwise looks exactly
            # like a broken importer to the user.
            file_count = len(getattr(self.importer, "filelist", {}) or {})
            if file_count == 0:
                log.warning(
                    "Bulk import found no importable files in the selected sources: %s",
                    [src for src, _ in self.import_sources],
                )

            # Configure progress callbacks
            self.importer.set_progress_callbacks(
                start_cb=self.progress_started.emit,
                update_cb=self.progress_updated.emit,
                end_cb=self.progress_completed.emit
            )

            # Run the actual import
            res = self.importer.runImport()
            self.finished.emit((file_count, res))
        except Exception as e:  # intentional broad catch: Qt worker thread surfaces any failure via the error signal
            log.exception("Bulk import background thread failed")
            self.error.emit(str(e))


class GuiBulkImport(QWidget):
    """Widget for bulk importing hand history files."""

    # Configuration  -  update these as preferred:
    allow_threads = False  # set to True to try out the threads field

    def load_clicked(self) -> None:
        """Handle load button click event by spawning a background thread."""
        # Does the lock acquisition need to be more sophisticated for multiple dirs?
        # (see comment above about what to do if pipe already open)
        if self.settings["global_lock"].acquire(
            wait=False,
            source="GuiBulkImport",
        ):  # returns false immediately if lock not acquired
            import_sources = []
            root = self.import_tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                if item.checkState(0) == Qt.CheckState.Checked:
                    site_name = item.text(0).removesuffix(" (Tourney)")
                    path = item.text(1)  # Path is in the second column
                    import_sources.append((path, site_name))

            custom_dir = self.importDir.text()
            if custom_dir:
                import_sources.append((custom_dir, "auto"))

            if not import_sources:
                log.warning("No import directories selected.")
                self.settings["global_lock"].release()
                return

            self.load_button.setEnabled(False)
            self.load_button.setText(_("Importing..."))
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)

            self.importer.setHandsInDB(self.n_hands_in_db)
            self.importer.setMode("bulk")
            self.importer.setCallHud(False)
            self._apply_move_settings()

            self.starttime = time()

            # Create progress dialog on Main Thread (safe for UI)
            self.progress_dialog = Importer.ImportProgressDialog(0, self)
            self.progress_dialog.resize(500, 200)

            # Create and start worker thread to do import off UI thread
            self.import_thread = BulkImportThread(self.importer, import_sources)
            self.import_thread.finished.connect(self.import_finished)
            self.import_thread.error.connect(self.import_error)

            # Connect thread-safe progress signals to Main Thread slots
            self.import_thread.progress_started.connect(self.on_progress_started)
            self.import_thread.progress_updated.connect(self.on_progress_updated)
            self.import_thread.progress_completed.connect(self.on_progress_completed)

            self.import_thread.start()
        else:
            log.warning("bulk import aborted - global lock not available")

    def on_progress_started(self, total: int) -> None:
        """Initialize and show progress dialog on the main thread."""
        self.progress_dialog.total = total
        if hasattr(self.progress_dialog, 'pbar'):
            self.progress_dialog.pbar.setRange(0, total)
        self.progress_dialog.show()

    def on_progress_updated(self, filename: str, handcount: str) -> None:
        """Update progress dialog display on the main thread."""
        self.progress_dialog.progress_update(filename, handcount)

    def on_progress_completed(self) -> None:
        """Close progress dialog on the main thread."""
        self.progress_dialog.accept()

    def import_finished(self, payload: tuple) -> None:
        """Handle successful import completion in background thread."""
        file_count, results = payload
        stored, dups, partial, skipped, errs, ttime = results
        elapsed = time() - self.starttime
        if elapsed == 0:
            elapsed = 1

        completion_message = (
            f"Bulk import done: Files: {file_count}, Stored: {stored}, Duplicates: {dups}, "
            f"Partial: {partial}, Skipped: {skipped}, Errors: {errs}, "
            f"Time: {elapsed:.2f} seconds, Stored/second: {stored / elapsed:.0f}"
        )
        log.info(completion_message)

        self.importer.clearFileList()
        self.settings["global_lock"].release()

        self.load_button.setEnabled(True)
        self.load_button.setText(_("Bulk Import"))
        self.progress_bar.setVisible(False)

        # Always give the user explicit feedback. Without this, a run that finds
        # no importable files (empty history folders, archives only, etc.) looks
        # identical to a broken importer.
        if file_count == 0:
            QMessageBox.warning(
                self,
                _("Bulk Import"),
                _(
                    "No importable hand-history files were found in the selected "
                    "directories.\n\nCheck that the configured paths contain hand "
                    "histories (plain text files), not just archives or exports.",
                ),
            )
        else:
            QMessageBox.information(
                self,
                _("Bulk Import"),
                _(
                    "Import complete.\n\n"
                    "Files processed: {files}\n"
                    "Stored: {stored}\n"
                    "Duplicates: {dups}\n"
                    "Partial: {partial}\n"
                    "Skipped: {skipped}\n"
                    "Errors: {errs}\n"
                    "Time: {elapsed}s",
                ).format(
                    files=format_number(file_count, 0),
                    stored=format_number(stored, 0),
                    dups=format_number(dups, 0),
                    partial=format_number(partial, 0),
                    skipped=format_number(skipped, 0),
                    errs=format_number(errs, 0),
                    elapsed=format_number(elapsed),
                ),
            )

        main_window = getattr(self, "main_window", None) or self.parent()
        if main_window is not None and hasattr(main_window, "refresh_after_import"):
            main_window.refresh_after_import()

    def import_error(self, error_msg: str) -> None:
        """Handle error from background import thread."""
        log.error(f"Bulk import background thread failed: {error_msg}")
        if hasattr(self, "progress_dialog"):
            self.progress_dialog.reject()
        self.importer.clearFileList()
        self.settings["global_lock"].release()

        self.load_button.setEnabled(True)
        self.load_button.setText(_("Bulk Import"))
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, _("Bulk Import Error"), error_msg)

    def get_vbox(self) -> QVBoxLayout:
        """Return the main widget container."""
        return self.main_layout

    def __init__(self, settings: Any, config: Any, sql: Any = None, parent: Any = None) -> None:
        """Initialize the bulk import widget."""
        QWidget.__init__(self, parent)
        # Keep an explicit handle on the main window: once this widget is added to
        # the tab notebook, Qt reparents it, so self.parent() no longer returns it.
        self.main_window = parent
        self.settings = settings
        self.config = config

        self.importer = Importer.Importer(self, self.settings, config, sql, self)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Configured import directories
        self.import_tree = QTreeWidget()
        self.import_tree.setColumnCount(2)
        self.import_tree.setHeaderLabels([_("Site"), _("Path")])
        self.import_tree.setColumnWidth(0, 200)

        # The project icons directory is located at the root of the project (parent of fpdb_3_legacy)
        icons_dir = Path(__file__).parent.parent / "icons"

        for site_name, site in self.config.supported_sites.items():
            if site.enabled:
                icon_path = icons_dir / f"{site_name.lower()}.png"
                icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()

                if site.HH_path and site.HH_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [site_name, site.HH_path])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setIcon(0, icon)

                if site.TS_path and site.TS_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [f"{site_name} (Tourney)", site.TS_path])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setIcon(0, icon)

        self.main_layout.addWidget(QLabel(_("Configured Import Directories:")))
        self.main_layout.addWidget(self.import_tree)

        # Custom import directory
        custom_dir_layout = QHBoxLayout()
        self.importDir = QLineEdit(self.settings.get("bulkImport-defaultPath", ""))
        custom_dir_layout.addWidget(self.importDir)
        self.chooseButton = QPushButton(_("Browse..."))

        browse_icon_path = icons_dir / "16x16" / "cil-folder-open.png"
        self.chooseButton.setIcon(QIcon(str(browse_icon_path)) if browse_icon_path.exists() else QIcon())
        self.chooseButton.clicked.connect(self.browseClicked)
        custom_dir_layout.addWidget(self.chooseButton)
        self.main_layout.addLayout(custom_dir_layout)

        # Optional: relocate files once processed (backend in Importer).
        self.moveImportedCheck, self.moveImportedDir = self._build_move_row(
            _("Move imported files to:"),
            checked=bool(self.settings.get("moveimportedfiles")),
            directory=self.settings.get("moveImportedFilesDir", ""),
        )
        self.moveFailedCheck, self.moveFailedDir = self._build_move_row(
            _("Move failed files to:"),
            checked=bool(self.settings.get("movefailedfiles")),
            directory=self.settings.get("moveFailedFilesDir", ""),
        )

        self.load_button = QPushButton(_("Bulk Import"))

        download_icon_path = icons_dir / "16x16" / "cil-cloud-download.png"
        self.load_button.setIcon(QIcon(str(download_icon_path)) if download_icon_path.exists() else QIcon())
        self.load_button.clicked.connect(self.load_clicked)
        self.main_layout.addWidget(self.load_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

        #    see how many hands are in the db and adjust accordingly
        tcursor = self.importer.database.cursor
        tcursor.execute("Select count(1) from Hands")
        row = tcursor.fetchone()
        tcursor.close()
        self.importer.database.rollback()
        self.n_hands_in_db = row[0]

    def browseClicked(self) -> None:
        """Handle browse button click to select import directory."""
        newdir = QFileDialog.getExistingDirectory(
            self,
            _("Please choose the path that you want to Auto Import"),
            self.importDir.text(),
        )
        if newdir:
            self.importDir.setText(newdir)

    def _build_move_row(self, label: str, *, checked: bool, directory: str) -> tuple[QCheckBox, QLineEdit]:
        """Build a "move files to <dir>" row (checkbox + path field + Browse) and add it.

        Returns the checkbox and line edit so load_clicked can read them.
        """
        row = QHBoxLayout()
        checkbox = QCheckBox(label)
        checkbox.setChecked(checked)
        row.addWidget(checkbox)
        line_edit = QLineEdit(directory)
        row.addWidget(line_edit)
        browse = QPushButton(_("Browse..."))
        browse.clicked.connect(lambda: self._browse_into(line_edit))
        row.addWidget(browse)
        self.main_layout.addLayout(row)
        return checkbox, line_edit

    def _browse_into(self, line_edit: QLineEdit) -> None:
        """Open a directory chooser and write the result into ``line_edit``."""
        newdir = QFileDialog.getExistingDirectory(self, _("Choose a destination directory"), line_edit.text())
        if newdir:
            line_edit.setText(newdir)

    def _apply_move_settings(self) -> None:
        """Push the move-files widget state into the importer before running an import."""
        self.importer.setMoveImportedFiles(self.moveImportedCheck.isChecked(), self.moveImportedDir.text())
        self.importer.setMoveFailedFiles(self.moveFailedCheck.isChecked(), self.moveFailedDir.text())


def _compare_regression_sidecars(filename: str, importer, *, quiet: bool) -> int:
    """Compare each imported file with its THP sidecars; return the mismatch count."""
    paths = [Path(filename)]
    if paths[0].is_dir():
        paths = [p for p in paths[0].rglob("*") if p.suffix.lower() in {".txt", ".xml"}]
    mismatches = 0
    for path in paths:
        try:
            report = compare_importer_sidecars(path, importer)
        except (OSError, ValueError) as exc:
            # An unreadable sidecar is a problem with that file, not a reason to
            # abandon the rest of the comparison.
            mismatches += 1
            log.warning("Regression compare %s: could not read sidecars: %s", path, exc)
            continue
        mismatches += len(report.issues)
        if not quiet and report.compared:
            status = "ok" if report.passed else f"{len(report.issues)} mismatch(es)"
            print(f"Regression compare {path}: {status}")
    return mismatches


def main(argv=None) -> int:
    """CLI entry point for headless bulk import.

    This restores the command-line entry point required by the TestHandsPlayers
    (THP) regression workflow (GitHub issue #106). Example:

        ./GuiBulkImport.py -x -C HUD_config.test.xml -c PokerStars -f hands.txt

    Returns a process exit code: 0 on success, 1 if the import reported
    errors, 2 on a usage/argument problem.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="GuiBulkImport.py",
        description="FPDB bulk hand-history importer.",
    )
    parser.add_argument("-x", "--xtables", action="store_true", help="run a headless (no-GUI) bulk import")
    parser.add_argument("-c", "--site", default="auto", help="site name for the files (default: auto-detect)")
    parser.add_argument("-f", "--file", dest="filename", help="hand-history file or directory to import")
    parser.add_argument("-C", "--config", dest="config", help="path to the HUD config XML file")
    parser.add_argument(
        "--recreate-tables",
        action="store_true",
        help="drop and recreate all DB tables before importing (THP clean slate)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only print the final summary line")
    parser.add_argument(
        "--compare-regression",
        action="store_true",
        help="compare imported hands with adjacent .hands/.hp/.gt THP sidecar files",
    )
    args = parser.parse_args(argv)

    Configuration.set_logfile("fpdb-log.txt")
    config = Configuration.Config(file=args.config) if args.config else Configuration.Config()

    if not args.xtables:
        # Interactive GUI mode is launched by fpdb.pyw; there is nothing to do
        # when this module is run directly without the CLI flag.
        parser.print_help()
        return 0

    if not args.filename:
        log.error("CLI bulk import (-x) requires -f <file|dir>")
        return 2
    if not os.path.exists(args.filename):
        log.error("Import path does not exist: %s", args.filename)
        return 2

    settings = {"os": "windows" if os.name == "nt" else "linuxmac"}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    settings["global_lock"] = interlocks.InterProcessLock(name="fpdb_global_lock")
    settings["cl_options"] = ".".join(sys.argv[1:])

    if args.recreate_tables:
        Database.Database(config).recreate_tables()
        if not args.quiet:
            print("Database tables recreated.")

    importer = Importer.Importer(caller=None, settings=settings, config=config)
    importer.setThreads(-1)
    importer.setCallHud(False)
    if args.compare_regression:
        # The comparison reads the parsed hands back off the converter, which the
        # importer only keeps when this is on; without it the flag crashed.
        importer.setFakeCacheHHC(True)
    importer.addBulkImportImportFileOrDir(args.filename, site=args.site)

    starttime = time()
    (stored, dups, partial, skipped, errs, _ttime) = importer.runImport()
    elapsed = (time() - starttime) or 1

    comparison_errors = 0
    if args.compare_regression:
        comparison_errors = _compare_regression_sidecars(args.filename, importer, quiet=args.quiet)

    importer.clearFileList()

    print(
        f"Bulk import done: Stored: {format_number(stored, 0)}, "
        f"Duplicates: {format_number(dups, 0)}, Partial: {format_number(partial, 0)}, "
        f"Skipped: {format_number(skipped, 0)}, Errors: {format_number(errs, 0)}, "
        f"Regression mismatches: {format_number(comparison_errors, 0)}, "
        f"Time: {format_number(elapsed, 3)}s, Stored/second: {format_number(stored / elapsed, 0)}",
    )
    return 0 if errs == 0 and comparison_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
