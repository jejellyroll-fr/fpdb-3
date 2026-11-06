#!/usr/bin/env python
from __future__ import annotations

# Copyright 2008-2011 Carl Gherardi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
import sys
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration, log_view_model
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_datetime
from fpdb_3_legacy.loggingFpdb import get_logger

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")

log = get_logger("gui_log_view")

MAX_LOG_ENTRIES = log_view_model.MAX_LOG_ENTRIES


class LogTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.headers = ["Level", "Date/Time", "Module", "Function", "Message"]
        self.log_entries: list[Any] = []

    def rowCount(self, parent=None):
        return len(self.log_entries)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if not (0 <= index.row() < len(self.log_entries)):
            return None
        entry = self.log_entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return entry[index.column()]
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            level = entry[0]
            style = QApplication.style()
            icon = None
            if level == "DEBUG":
                icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight)
            elif level == "INFO":
                icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
            elif level == "WARNING":
                icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            elif level == "ERROR":
                icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
            return icon
        if role == Qt.ItemDataRole.ForegroundRole:
            colour = log_view_model.LEVEL_COLOURS.get(entry[0])
            return QColor(colour) if colour else QApplication.palette().color(QPalette.ColorRole.Text)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None


class LogFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.selected_levels = set(log_view_model.LEVELS)
        self.module_filter_text = ""

    def setLevelFilter(self, levels) -> None:
        self.selected_levels = set(levels)
        self.invalidateFilter()

    def setModuleFilter(self, text) -> None:
        self.module_filter_text = text
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        level = model.data(model.index(source_row, 0, source_parent), Qt.ItemDataRole.DisplayRole)
        module = model.data(model.index(source_row, 2, source_parent), Qt.ItemDataRole.DisplayRole)
        return log_view_model.matches(level, module, self.selected_levels, self.module_filter_text)


class LogLoaderThread(QThread):
    log_entries_loaded = Signal(list)

    def __init__(self, logfile, max_entries) -> None:
        super().__init__()
        self.logfile = logfile
        self.max_entries = max_entries

    def run(self) -> None:
        entries = log_view_model.read_tail(self.logfile, self.max_entries)
        self.log_entries_loaded.emit([entry.as_row() for entry in entries])


class GuiLogView(QWidget):
    def __init__(self, config, mainwin, closeq) -> None:
        super().__init__()
        self.config = config
        self.main_window = mainwin
        self.closeq = closeq
        self.logfile: str | None = None

        # Increase the default window size
        self.resize(1200, 800)
        self.setWindowTitle(_("Log Viewer"))

        self.setLayout(QVBoxLayout())
        layout = self.layout()
        assert layout is not None

        # Initialize the custom model and proxy model
        self.model = LogTableModel(self)
        self.proxy_model = LogFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        self.listview = QTableView()
        self.listview.setModel(self.proxy_model)
        self.listview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.listview.setShowGrid(False)
        self.listview.verticalHeader().hide()
        self.listview.setSortingEnabled(True)
        self.listview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.listview.horizontalHeader().setStretchLastSection(False)
        self.listview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.listview.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        layout.addWidget(self.listview)

        # Combobox for selecting log file
        hb1 = QHBoxLayout()
        hb1.addWidget(QLabel(_("Select Log File:")))
        self.logfile_combo = QComboBox(self)
        self.update_logfile_list()
        self.logfile_combo.currentIndexChanged.connect(self.__set_logfile)
        hb1.addWidget(self.logfile_combo)
        layout.addLayout(hb1)

        # Checkboxes for log levels
        hb3 = QHBoxLayout()
        self.filter_debug = QCheckBox("DEBUG", self)
        self.filter_info = QCheckBox("INFO", self)
        self.filter_warning = QCheckBox("WARNING", self)
        self.filter_error = QCheckBox("ERROR", self)

        # Set all log levels to checked by default
        self.filter_debug.setChecked(True)
        self.filter_info.setChecked(True)
        self.filter_warning.setChecked(True)
        self.filter_error.setChecked(True)

        self.filter_debug.stateChanged.connect(self.filter_log)
        self.filter_info.stateChanged.connect(self.filter_log)
        self.filter_warning.stateChanged.connect(self.filter_log)
        self.filter_error.stateChanged.connect(self.filter_log)

        hb3.addWidget(self.filter_debug)
        hb3.addWidget(self.filter_info)
        hb3.addWidget(self.filter_warning)
        hb3.addWidget(self.filter_error)
        layout.addLayout(hb3)

        # Add a filter by "Module"
        hb4 = QHBoxLayout()
        hb4.addWidget(QLabel(_("Filter by Module:")))
        self.module_filter_edit = QLineEdit()
        self.module_filter_edit.textChanged.connect(self.filter_log)
        hb4.addWidget(self.module_filter_edit)
        layout.addLayout(hb4)

        # Buttons for refreshing and copying
        hb2 = QHBoxLayout()
        refreshbutton = QPushButton(_("Refresh"))
        refreshbutton.clicked.connect(self.refresh)
        hb2.addWidget(refreshbutton)

        copybutton = QPushButton(_("Copy selection to clipboard"))
        copybutton.clicked.connect(self.copy_to_clipboard)
        hb2.addWidget(copybutton)
        layout.addLayout(hb2)

        # Load the initial log file
        self.loadLog()
        self.show()

    def update_logfile_list(self) -> None:
        self.logfile_combo.blockSignals(True)  # Prevent signals while updating
        current_selection = self.logfile_combo.currentText()
        self.logfile_combo.clear()
        self.logfile_paths = []
        selected_index = 0
        for index, logfile in enumerate(log_view_model.log_files(self.config.dir_log)):
            display_name = f"{logfile.name} ({format_datetime(logfile.modified)})"
            self.logfile_combo.addItem(display_name)
            self.logfile_paths.append(logfile.path)
            if display_name == current_selection:
                selected_index = index
        self.logfile_combo.setCurrentIndex(selected_index)
        self.logfile_combo.blockSignals(False)
        if self.logfile_paths:
            self.logfile = self.logfile_paths[selected_index]  # Keep the selected log file
        else:
            self.logfile = None

    def filter_log(self) -> None:
        boxes = (self.filter_debug, self.filter_info, self.filter_warning, self.filter_error)
        selected_levels = [level for level, box in zip(log_view_model.LEVELS, boxes) if box.isChecked()]

        module_filter_text = self.module_filter_edit.text()
        self.proxy_model.setLevelFilter(selected_levels)
        self.proxy_model.setModuleFilter(module_filter_text)

    def copy_to_clipboard(self) -> None:
        rows = [
            [
                self.proxy_model.data(self.proxy_model.index(index.row(), column), Qt.ItemDataRole.DisplayRole)
                for column in range(self.proxy_model.columnCount())
            ]
            for index in self.listview.selectionModel().selectedRows()
        ]
        QApplication.clipboard().setText(log_view_model.rows_as_text(rows))

    def __set_logfile(self, index) -> None:
        if index >= 0 and index < len(self.logfile_paths):
            self.logfile = self.logfile_paths[index]
            self.loadLog()  # Call loadLog instead of refresh

    def loadLog(self) -> None:
        if self.logfile:
            self.log_loader_thread = LogLoaderThread(self.logfile, MAX_LOG_ENTRIES)
            self.log_loader_thread.log_entries_loaded.connect(self.on_log_entries_loaded)
            self.log_loader_thread.start()

    def on_log_entries_loaded(self, entries) -> None:
        # Update the model in the main thread
        self.model.beginResetModel()
        self.model.log_entries = entries
        self.model.endResetModel()
        # Apply filters
        self.filter_log()

    def refresh(self) -> None:
        # Reload the current log file without resetting the selection
        self.loadLog()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the log viewer GUI like the original
    config = Configuration.Config()

    app = QApplication([])
    main_window = QWidget()
    layout = QVBoxLayout()
    main_window.setLayout(layout)
    i = GuiLogView(config, main_window, None)
    layout.addWidget(i)
    # Increase the size of the main window
    main_window.resize(1600, 900)
    main_window.setWindowTitle(_("Log Viewer"))
    main_window.show()
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
