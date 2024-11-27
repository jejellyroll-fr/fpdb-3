#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

from __future__ import division

from PyQt5.QtGui import QStandardItem, QStandardItemModel, QColor, QPalette


from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QPushButton,
    QHBoxLayout,
    QRadioButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QHeaderView,
    QStyledItemDelegate,
    QStyle,
    QLineEdit,
    QLabel,
)
from PyQt5.QtCore import Qt, QRect, QSize

import os
from loggingFpdb import get_logger
from itertools import groupby
from functools import partial
import Configuration

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")

log = get_logger("logview")

MAX_LINES = 100000
EST_CHARS_PER_LINE = 150

# Only include "HUD Log" and "Fpdb Log" in the radio box
LOGFILES = [
    ["Fpdb Log", "fpdb-log.txt", True, "log"],
    ["HUD Log", "HUD-log.txt", False, "log"],
]


class LogItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(LogItemDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        # Get the column
        column = index.column()

        # Get the log level from the model
        level_index = index.sibling(index.row(), 0)
        level = index.model().data(level_index, Qt.DisplayRole)

        # Get the icon from the level column
        icon = index.model().data(level_index, Qt.DecorationRole)

        # Get the text for the current cell
        text = index.model().data(index, Qt.DisplayRole)

        # Define the color based on the log level
        if level == "DEBUG":
            color = QColor("green")
        elif level == "INFO":
            color = QColor("white")
        elif level == "WARNING":
            color = QColor("orange")
        elif level == "ERROR":
            color = QColor("red")
        else:
            color = option.palette.color(QPalette.Text)

        painter.save()

        # Draw selection background if item is selected
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # For the Level column, draw the icon and text
        if column == 0:
            # Set up the icon and text rectangles
            iconSize = QSize(16, 16)  # Or get from icon.actualSize()

            iconRect = QRect(option.rect)
            iconRect.setWidth(iconSize.width())
            iconRect.setHeight(iconSize.height())
            iconRect.moveTop(option.rect.top() + (option.rect.height() - iconSize.height()) // 2)
            iconRect.moveLeft(option.rect.left() + 5)

            textRect = QRect(option.rect)
            textRect.setLeft(iconRect.right() + 5)

            # Draw the icon
            if icon:
                icon.paint(painter, iconRect, Qt.AlignCenter)

            # Draw the text
            painter.setPen(color)
            painter.drawText(textRect, Qt.AlignLeft | Qt.AlignVCenter, text)
        else:
            # For other columns, draw the text
            painter.setPen(color)
            painter.drawText(option.rect.adjusted(5, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()


class GuiLogView(QWidget):
    def __init__(self, config, mainwin, closeq):
        super().__init__()
        self.config = config
        self.main_window = mainwin
        self.closeq = closeq

        # Set default logfile to "Fpdb Log"
        self.logfile = os.path.join(self.config.dir_log, LOGFILES[0][1])

        self.resize(700, 400)
        self.setWindowTitle("Log Viewer")

        self.setLayout(QVBoxLayout())

        # Adjusted the number of columns to 5 (removed "Functionality")
        self.liststore = QStandardItemModel(0, 5)
        self.listview = QTableView()
        self.listview.setModel(self.liststore)
        self.listview.setSelectionBehavior(QTableView.SelectRows)
        self.listview.setShowGrid(False)
        self.listview.verticalHeader().hide()
        self.listview.setSortingEnabled(True)
        self.listview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.listview.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listview.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # Apply the custom delegate
        self.listview.setItemDelegate(LogItemDelegate(self.listview))

        self.layout().addWidget(self.listview)

        # Radio buttons for selecting log file
        hb1 = QHBoxLayout()
        for logf in LOGFILES:
            rb = QRadioButton(logf[0], self)
            rb.setChecked(logf[2])
            rb.clicked.connect(partial(self.__set_logfile, filename=logf[0]))
            hb1.addWidget(rb)
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

        # Add a second filter by "Module"
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

        self.loadLog()
        self.show()

    def filter_log(self):
        selected_levels = []
        if self.filter_debug.isChecked():
            selected_levels.append("DEBUG")
        if self.filter_info.isChecked():
            selected_levels.append("INFO")
        if self.filter_warning.isChecked():
            selected_levels.append("WARNING")
        if self.filter_error.isChecked():
            selected_levels.append("ERROR")

        module_filter_text = self.module_filter_edit.text()
        self.loadLog(selected_levels, module_filter_text)

    def copy_to_clipboard(self):
        text = ""
        for row, indexes in groupby(self.listview.selectedIndexes(), lambda i: i.row()):
            text += " ".join([i.data() for i in indexes]) + "\n"
        QApplication.clipboard().setText(text)

    def __set_logfile(self, checkState, filename):
        if checkState:
            for logf in LOGFILES:
                if logf[0] == filename:
                    if logf[3] == "pyfpdb":
                        self.logfile = os.path.join(self.config.pyfpdb_path, logf[1])
                    else:
                        self.logfile = os.path.join(self.config.dir_log, logf[1])
            self.refresh()

    def dialog_response_cb(self, dialog, response_id):
        self.closeq.put(self.__class__)
        dialog.destroy()

    def get_dialog(self):
        return self.dia

    def loadLog(self, selected_levels=None, module_filter_text=""):
        self.liststore.clear()
        self.liststore.setHorizontalHeaderLabels(["Level", "Date/Time", "Module", "Function", "Message"])

        if os.path.exists(self.logfile):
            with open(self.logfile, "r") as log_file:
                for line in log_file:
                    parts = line.strip().split(" - ")
                    if len(parts) == 6:
                        date_time, functionality, level, module, function, message = parts

                        # Apply filters for log level and module
                        if (selected_levels is None or level in selected_levels) and (
                            module_filter_text == "" or module_filter_text.lower() in module.lower()
                        ):
                            level_item = QStandardItem(level)

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
                            if icon:
                                level_item.setIcon(icon)
                            level_item.setEditable(False)

                            date_item = QStandardItem(date_time)
                            module_item = QStandardItem(module)
                            function_item = QStandardItem(function)
                            message_item = QStandardItem(message)

                            # Make items non-editable
                            for item in [date_item, module_item, function_item, message_item]:
                                item.setEditable(False)

                            self.liststore.appendRow([level_item, date_item, module_item, function_item, message_item])

        self.listview.resizeColumnsToContents()

    def refresh(self):
        self.filter_log()


if __name__ == "__main__":
    config = Configuration.Config()

    app = QApplication([])
    main_window = QWidget()
    layout = QVBoxLayout()
    main_window.setLayout(layout)
    i = GuiLogView(config, main_window, None)
    layout.addWidget(i)
    main_window.resize(1400, 800)
    main_window.setWindowTitle("Log Viewer")
    main_window.show()
    app.exec_()
