#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

from __future__ import division

from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

import queue

from PyQt5.QtGui import (QStandardItem, QStandardItemModel)
from PyQt5.QtWidgets import (QApplication, QDialog, QPushButton, QHBoxLayout, QRadioButton,
                             QTableView, QVBoxLayout, QWidget, QCheckBox)

import os
import traceback
import logging
from itertools import groupby
from functools import partial
import Configuration
if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("logview")

MAX_LINES = 100000         # max lines to display in window
EST_CHARS_PER_LINE = 150   # used to guesstimate number of lines in log file
# label, filename, start value, path
LOGFILES = [['Fpdb Errors',        'fpdb-errors.txt',   False, 'log'],
            ['Fpdb Log',           'fpdb-log.txt',      True,  'log'],
            ['HUD Errors',         'HUD-errors.txt',    False, 'log'],
            ['HUD Log',            'HUD-log.txt',       False, 'log'],
            ['fpdb.exe log',       'fpdb.exe.log',      False, 'pyfpdb'],
            ['HUD_main.exe Log',   'HUD_main.exe.log ', False, 'pyfpdb']
           ]

class GuiLogView(QWidget):
    def __init__(self, config, mainwin, closeq):
        QWidget.__init__(self)
        self.config = config
        self.main_window = mainwin
        self.closeq = closeq

        self.logfile = os.path.join(self.config.dir_log, LOGFILES[1][1])

        self.resize(700, 400)

        self.setLayout(QVBoxLayout())

        self.liststore = QStandardItemModel(0, 4)
        self.listview = QTableView()
        self.listview.setModel(self.liststore)
        self.listview.setSelectionBehavior(QTableView.SelectRows)
        self.listview.setShowGrid(False)
        self.listview.verticalHeader().hide()
        self.layout().addWidget(self.listview)

        hb1 = QHBoxLayout()
        for logf in LOGFILES:
            rb = QRadioButton(logf[0], self)
            rb.setChecked(logf[2])
            rb.clicked.connect(partial(self.__set_logfile, filename=logf[0]))
            hb1.addWidget(rb)
            
        hb2 = QHBoxLayout()
        refreshbutton = QPushButton("Refresh")
        refreshbutton.clicked.connect(self.refresh)
        hb2.addWidget(refreshbutton)
        
        copybutton = QPushButton("Selection Copy to Clipboard")
        copybutton.clicked.connect(self.copy_to_clipboard)
        hb2.addWidget(copybutton)

        # Add checkboxes for log levels
        self.filter_debug = QCheckBox("DEBUG", self)
        self.filter_info = QCheckBox("INFO", self)
        self.filter_warning = QCheckBox("WARNING", self)
        self.filter_error = QCheckBox("ERROR", self)

        # Connect checkboxes to the filter method
        self.filter_debug.stateChanged.connect(self.filter_log)
        self.filter_info.stateChanged.connect(self.filter_log)
        self.filter_warning.stateChanged.connect(self.filter_log)
        self.filter_error.stateChanged.connect(self.filter_log)

        # Add checkboxes to layout
        hb3 = QHBoxLayout()
        hb3.addWidget(self.filter_debug)
        hb3.addWidget(self.filter_info)
        hb3.addWidget(self.filter_warning)
        hb3.addWidget(self.filter_error)
        self.layout().addLayout(hb3)

        self.layout().addLayout(hb1)
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

        self.loadLog(selected_levels)
    
    def copy_to_clipboard(self, checkState):
        text = ""
        for row, indexes in groupby(self.listview.selectedIndexes(), lambda i: i.row()):
            text += " ".join([i.data() for i in indexes]) + "\n"
        # print(text)
        QApplication.clipboard().setText(text)
            
    def __set_logfile(self, checkState, filename):
        # print "w is", w, "file is", file, "active is", w.get_active()
        if checkState:
            for logf in LOGFILES:
                if logf[0] == filename:
                    if logf[3] == 'pyfpdb':
                        self.logfile = os.path.join(self.config.pyfpdb_path, logf[1])
                    else:
                        self.logfile = os.path.join(self.config.dir_log, logf[1])                        
            self.refresh(checkState)  # params are not used

    def dialog_response_cb(self, dialog, response_id):
        # this is called whether close button is pressed or window is closed
        self.closeq.put(self.__class__)
        dialog.destroy()

    def get_dialog(self):
        return self.dia

    def loadLog(self, selected_levels=None):
        self.liststore.clear()
        self.liststore.setHorizontalHeaderLabels(
            ["Date/Time", "Functionality", "Level", "Module", "Function", "Message"])

        if os.path.exists(self.logfile):
            with open(self.logfile, 'r') as log_file:
                for line in log_file:
                    parts = line.strip().split(' - ')
                    if len(parts) == 6:
                        date_time, functionality,  level, module, function, message = parts

                        # Filter log entries based on selected log levels
                        if selected_levels is None or level in selected_levels:
                            tablerow = [date_time, functionality,  level, module, function, message]
                            tablerow = [QStandardItem(i) for i in tablerow]
                            for item in tablerow:
                                item.setEditable(False)
                            self.liststore.appendRow(tablerow)

        self.listview.resizeColumnsToContents()

    def refresh(self, checkState):
        self.loadLog()



if __name__=="__main__":
    config = Configuration.Config()

    from PyQt5.QtWidgets import QApplication, QMainWindow
    app = QApplication([])
    main_window = QMainWindow()
    i = GuiLogView(config, main_window, None)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec_()
