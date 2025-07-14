#!/usr/bin/env python

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

import glob
import json
import os
from collections import deque
from datetime import datetime

from PyQt5.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QVariant,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
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

import Configuration
from loggingFpdb import get_logger

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")

log = get_logger("logview")

MAX_LOG_ENTRIES = 1000  # Adjust this number as needed

# Only include "HUD Log" and "Fpdb Log" in the radio box
LOGFILES = [
    ["Fpdb Log", "fpdb-log.txt", True, "log"],
    ["HUD Log", "HUD-log.txt", False, "log"],
]


class LogTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.headers = ["Level", "Date/Time", "Module", "Function", "Message"]
        self.log_entries = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.log_entries)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if not (0 <= index.row() < len(self.log_entries)):
            return QVariant()
        entry = self.log_entries[index.row()]
        if role == Qt.DisplayRole:
            return entry[index.column()]
        if role == Qt.DecorationRole and index.column() == 0:
            level = entry[0]
            style = QApplication.style()
            icon = None
            if level == "DEBUG":
                icon = style.standardIcon(QStyle.SP_ArrowRight)
            elif level == "INFO":
                icon = style.standardIcon(QStyle.SP_MessageBoxInformation)
            elif level == "WARNING":
                icon = style.standardIcon(QStyle.SP_MessageBoxWarning)
            elif level == "ERROR":
                icon = style.standardIcon(QStyle.SP_MessageBoxCritical)
            return icon
        if role == Qt.ForegroundRole:
            level = entry[0]
            if level == "DEBUG":
                color = QColor("green")
            elif level == "INFO":
                color = QColor("white")
            elif level == "WARNING":
                color = QColor("orange")
            elif level == "ERROR":
                color = QColor("red")
            else:
                color = QApplication.palette().color(QPalette.Text)
            return color
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == Qt.Horizontal:
            return self.headers[section]
        return QVariant()


class LogFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.selected_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
        self.module_filter_text = ""

    def setLevelFilter(self, levels) -> None:
        self.selected_levels = set(levels)
        self.invalidateFilter()

    def setModuleFilter(self, text) -> None:
        self.module_filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        level_index = model.index(source_row, 0, source_parent)
        level = model.data(level_index, Qt.DisplayRole)
        if level is None:
            return False
        level = level.strip().upper()
        module_index = model.index(source_row, 2, source_parent)
        module = model.data(module_index, Qt.DisplayRole)
        module = "" if module is None else module.lower()
        if level not in self.selected_levels:
            return False
        return not (self.module_filter_text and self.module_filter_text not in module)


class LogLoaderThread(QThread):
    log_entries_loaded = pyqtSignal(list)

    def __init__(self, logfile, max_entries) -> None:
        super().__init__()
        self.logfile = logfile
        self.max_entries = max_entries

    def run(self) -> None:
        entries = []
        if os.path.exists(self.logfile):
            with open(self.logfile, encoding="utf-8") as log_file:
                lines = deque(log_file, maxlen=self.max_entries)
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record_dict = json.loads(line)
                        level = record_dict.get("levelname", "").strip().upper()
                        date_time = record_dict.get("asctime", "").strip()
                        module = record_dict.get("module", "").strip()
                        function = record_dict.get("funcName", "").strip()
                        message = record_dict.get("message", "").strip()
                        entries.append([level, date_time, module, function, message])
                    except json.JSONDecodeError:
                        # Line is not valid JSON
                        log.debug(f"Line is not valid JSON: {line}")
                        continue
        self.log_entries_loaded.emit(entries)


class GuiLogView(QWidget):
    def __init__(self, config, mainwin, closeq) -> None:
        super().__init__()
        self.config = config
        self.main_window = mainwin
        self.closeq = closeq

        # Increase the default window size
        self.resize(1200, 800)
        self.setWindowTitle("Log Viewer")

        self.setLayout(QVBoxLayout())

        # Initialize the custom model and proxy model
        self.model = LogTableModel(self)
        self.proxy_model = LogFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        self.listview = QTableView()
        self.listview.setModel(self.proxy_model)
        self.listview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.listview.setShowGrid(False)
        self.listview.verticalHeader().hide()
        self.listview.setSortingEnabled(True)
        self.listview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents,
        )
        self.listview.horizontalHeader().setStretchLastSection(False)
        self.listview.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listview.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.layout().addWidget(self.listview)

        # Combobox for selecting log file
        hb1 = QHBoxLayout()
        hb1.addWidget(QLabel("Select Log File:"))
        self.logfile_combo = QComboBox(self)
        self.update_logfile_list()
        self.logfile_combo.currentIndexChanged.connect(self.__set_logfile)
        hb1.addWidget(self.logfile_combo)
        self.layout().addLayout(hb1)

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
        self.layout().addLayout(hb3)

        # Add a filter by "Module"
        hb4 = QHBoxLayout()
        hb4.addWidget(QLabel("Filter by Module:"))
        self.module_filter_edit = QLineEdit()
        self.module_filter_edit.textChanged.connect(self.filter_log)
        hb4.addWidget(self.module_filter_edit)
        self.layout().addLayout(hb4)

        # Buttons for refreshing and copying
        hb2 = QHBoxLayout()
        refreshbutton = QPushButton("Refresh")
        refreshbutton.clicked.connect(self.refresh)
        hb2.addWidget(refreshbutton)

        copybutton = QPushButton("Copy selection to clipboard")
        copybutton.clicked.connect(self.copy_to_clipboard)
        hb2.addWidget(copybutton)
        self.layout().addLayout(hb2)

        # Load the initial log file
        self.loadLog()
        self.show()

    def update_logfile_list(self) -> None:
        log_dir = self.config.dir_log
        log_pattern = os.path.join(log_dir, "fpdb-log*.txt")
        log_files = glob.glob(log_pattern)
        # Sort log files by modification time, newest first
        log_files.sort(key=os.path.getmtime, reverse=True)
        self.logfile_combo.blockSignals(True)  # Prevent signals while updating
        current_selection = self.logfile_combo.currentText()
        self.logfile_combo.clear()
        self.logfile_paths = []
        selected_index = 0
        for index, logfile in enumerate(log_files):
            # Format display name with date
            mod_time = datetime.fromtimestamp(os.path.getmtime(logfile))
            display_name = f"{os.path.basename(logfile)} ({mod_time.strftime('%Y-%m-%d %H:%M:%S')})"
            self.logfile_combo.addItem(display_name)
            self.logfile_paths.append(logfile)
            if display_name == current_selection:
                selected_index = index
        self.logfile_combo.setCurrentIndex(selected_index)
        self.logfile_combo.blockSignals(False)
        if self.logfile_paths:
            self.logfile = self.logfile_paths[
                selected_index
            ]  # Keep the selected log file
        else:
            self.logfile = None

    def filter_log(self) -> None:
        selected_levels = []
        if self.filter_debug.isChecked():
            selected_levels.append("DEBUG")
        if self.filter_info.isChecked():
            selected_levels.append("INFO")
        if self.filter_warning.isChecked():
            selected_levels.append("WARNING")
        if self.filter_error.isChecked():
            selected_levels.append("ERROR")

        # Ensure levels are uppercase
        selected_levels = [level.upper() for level in selected_levels]

        module_filter_text = self.module_filter_edit.text()
        self.proxy_model.setLevelFilter(selected_levels)
        self.proxy_model.setModuleFilter(module_filter_text)

    def copy_to_clipboard(self) -> None:
        selected_indexes = self.listview.selectionModel().selectedRows()
        text = ""
        for index in selected_indexes:
            row_data = []
            for column in range(self.proxy_model.columnCount()):
                data = self.proxy_model.data(
                    self.proxy_model.index(index.row(), column), Qt.DisplayRole,
                )
                row_data.append(str(data))
            text += "\t".join(row_data) + "\n"
        QApplication.clipboard().setText(text)

    def __set_logfile(self, index) -> None:
        if index >= 0 and index < len(self.logfile_paths):
            self.logfile = self.logfile_paths[index]
            self.loadLog()  # Call loadLog instead of refresh

    def loadLog(self) -> None:
        if self.logfile:
            self.thread = LogLoaderThread(self.logfile, MAX_LOG_ENTRIES)
            self.thread.log_entries_loaded.connect(self.on_log_entries_loaded)
            self.thread.start()

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


if __name__ == "__main__":
    config = Configuration.Config()

    app = QApplication([])
    main_window = QWidget()
    layout = QVBoxLayout()
    main_window.setLayout(layout)
    i = GuiLogView(config, main_window, None)
    layout.addWidget(i)
    # Increase the size of the main window
    main_window.resize(1600, 900)
    main_window.setWindowTitle("Log Viewer")
    main_window.show()
    app.exec_()
