"""GuiBulkImport module for FPDB bulk import functionality.

Copyright 2008-2011 Steffen Schaumburg add cli based on Carl's proposal.
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
import os
import sys
from optparse import OptionParser
from pathlib import Path
from time import time
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import Configuration
import Importer
from loggingFpdb import get_logger

#    fpdb/FreePokerTools modules


if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("gui_bulk_import")


class GuiBulkImport(QWidget):
    """Widget for bulk importing hand history files."""

    # Configuration  -  update these as preferred:
    allow_threads = False  # set to True to try out the threads field

    def load_clicked(self) -> None:
        """Handle load button click event."""
        stored = None
        dups = None
        partial = None
        skipped = None
        errs = None
        ttime = None
        # Does the lock acquisition need to be more sophisticated for multiple dirs?
        # (see comment above about what to do if pipe already open)
        if self.settings["global_lock"].acquire(
            wait=False,
            source="GuiBulkImport",
        ):  # returns false immediately if lock not acquired
            import_dirs = []
            root = self.import_tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                if item.checkState(0) == Qt.Checked:
                    path = item.text(1)  # Path is in the second column
                    import_dirs.append(path)

            custom_dir = self.importDir.text()
            if custom_dir:
                import_dirs.append(custom_dir)

            if not import_dirs:
                log.warning("No import directories selected.")
                self.settings["global_lock"].release()
                return

            self.importer.setHandsInDB(self.n_hands_in_db)
            self.importer.setMode("bulk")

            for import_dir in import_dirs:
                self.importer.addBulkImportImportFileOrDir(import_dir, site="auto")

            self.importer.setCallHud(False)

            starttime = time()

            (stored, dups, partial, skipped, errs, ttime) = self.importer.runImport()

            ttime = time() - starttime
            if ttime == 0:
                ttime = 1

            completion_message = (
                f"Bulk import done: Stored: {stored}, Duplicates: {dups}, "
                f"Partial: {partial}, Skipped: {skipped}, Errors: {errs}, "
                f"Time: {ttime} seconds, Stored/second: {(stored + 0.0) / ttime:.0f}"
            )
            log.info(completion_message)

            self.importer.clearFileList()

            self.settings["global_lock"].release()
        else:
            log.warning("bulk import aborted - global lock not available")

    def get_vbox(self) -> Any:
        """Return the main widget container."""
        """Returns the vbox of this thread."""
        return self.layout()

    def __init__(self, settings: Any, config: Any, sql: Any = None, parent: Any = None) -> None:
        """Initialize the bulk import widget."""
        QWidget.__init__(self, parent)
        self.settings = settings
        self.config = config

        self.importer = Importer.Importer(self, self.settings, config, sql, self)

        self.setLayout(QVBoxLayout())

        # Configured import directories
        self.import_tree = QTreeWidget()
        self.import_tree.setColumnCount(2)
        self.import_tree.setHeaderLabels(["Site", "Path"])
        self.import_tree.setColumnWidth(0, 200)

        for site_name, site in self.config.supported_sites.items():
            if site.enabled:
                icon_path = f"icons/{site_name.lower()}.png"
                icon = QIcon(icon_path) if Path(icon_path).exists() else QIcon()

                if site.HH_path and site.HH_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [site_name, site.HH_path])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setIcon(0, icon)

                if site.TS_path and site.TS_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [f"{site_name} (Tourney)", site.TS_path])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setIcon(0, icon)

        self.layout().addWidget(QLabel("Configured Import Directories:"))
        self.layout().addWidget(self.import_tree)

        # Custom import directory
        custom_dir_layout = QHBoxLayout()
        self.importDir = QLineEdit(self.settings.get("bulkImport-defaultPath", ""))
        custom_dir_layout.addWidget(self.importDir)
        self.chooseButton = QPushButton("Browse...")
        self.chooseButton.setIcon(QIcon("icons/16x16/cil-folder-open.png"))
        self.chooseButton.clicked.connect(self.browseClicked)
        custom_dir_layout.addWidget(self.chooseButton)
        self.layout().addLayout(custom_dir_layout)

        self.load_button = QPushButton("Bulk Import")
        self.load_button.setIcon(QIcon("icons/16x16/cil-cloud-download.png"))
        self.load_button.clicked.connect(self.load_clicked)
        self.layout().addWidget(self.load_button)

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
            caption=("Please choose the path that you want to Auto Import"),
            directory=self.importDir.text(),
        )
        if newdir:
            self.importDir.setText(newdir)


def main(argv=None):
    """Main function for CLI usage, compatible with TestHandsPlayers regression tests."""
    if argv is None:
        argv = sys.argv[1:]
    
    parser = OptionParser()
    parser.add_option(
        "-C", "--config", dest="config", default=None,
        help="Configuration file to use (default: HUD_config.xml)"
    )
    parser.add_option(
        "-c", "--converter", dest="converter", default="auto",
        help="Site converter to use (default: auto)"
    )
    parser.add_option(
        "-f", "--file", dest="filename", default=None,
        help="Hand history file or directory to import"
    )
    parser.add_option(
        "-q", "--quiet", action="store_true", dest="quiet", default=False,
        help="Reduce output verbosity"
    )
    
    (options, args) = parser.parse_args(argv)
    
    if not options.filename:
        if args:
            options.filename = args[0]
        else:
            parser.error("You must specify a file or directory to import with -f or as an argument")
    
    # Initialize configuration
    config_file = options.config or "HUD_config.xml"
    config = Configuration.Config(file=config_file)
    
    # Set up settings similar to GUI mode
    settings = {}
    if os.name == "nt":
        settings["os"] = "windows"
    else:
        settings["os"] = "linuxmac"
    
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    import interlocks
    settings["global_lock"] = interlocks.InterProcessLock(name="fpdb_global_lock")
    settings["cl_options"] = ".".join(argv)
    
    if not options.quiet:
        log.info(f"Starting bulk import with config: {config_file}")
        log.info(f"Import target: {options.filename}")
        log.info(f"Converter: {options.converter}")
    
    # Initialize importer
    importer = Importer.Importer(False, settings, config, None)
    
    # Acquire lock and perform import
    if settings["global_lock"].acquire(wait=False, source="GuiBulkImport-CLI"):
        try:
            # Count existing hands
            tcursor = importer.database.cursor
            tcursor.execute("Select count(1) from Hands")
            row = tcursor.fetchone()
            tcursor.close()
            importer.database.rollback()
            n_hands_in_db = row[0]
            
            importer.setHandsInDB(n_hands_in_db)
            importer.setMode("bulk")
            importer.addBulkImportImportFileOrDir(options.filename, site=options.converter)
            importer.setCallHud(False)
            
            starttime = time()
            (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
            ttime = time() - starttime
            
            if ttime == 0:
                ttime = 1
            
            if not options.quiet:
                completion_message = (
                    f"CLI bulk import completed: Stored: {stored}, Duplicates: {dups}, "
                    f"Partial: {partial}, Skipped: {skipped}, Errors: {errs}, "
                    f"Time: {ttime:.2f} seconds, Stored/second: {(stored + 0.0) / ttime:.0f}"
                )
                log.info(completion_message)
                print(completion_message)
            
            importer.clearFileList()
            
            # Return results for testing purposes
            return (stored, dups, partial, skipped, errs, ttime)
            
        finally:
            settings["global_lock"].release()
    else:
        error_msg = "CLI bulk import aborted - global lock not available"
        log.warning(error_msg)
        print(error_msg, file=sys.stderr)
        return (0, 0, 0, 0, 1, 0)


if __name__ == "__main__":
    # Check if we have command line arguments (CLI mode) or should run GUI
    if len(sys.argv) > 1:
        # CLI mode
        main()
    else:
        # GUI mode - original code
        config = Configuration.Config()
        settings = {}
        if os.name == "nt":
            settings["os"] = "windows"
        else:
            settings["os"] = "linuxmac"

        settings.update(config.get_db_parameters())
        settings.update(config.get_import_parameters())
        settings.update(config.get_default_paths())
        import interlocks

        settings["global_lock"] = interlocks.InterProcessLock(name="fpdb_global_lock")
        settings["cl_options"] = ".".join(sys.argv[1:])
        
        # GUI mode would continue here with QApplication setup if needed
        print("GUI mode not implemented in standalone script. Use from main FPDB application.")
