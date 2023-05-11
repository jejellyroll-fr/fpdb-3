#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Steffen Schaumburg
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

from __future__ import print_function
from __future__ import division
from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

#    Standard Library modules
import os
import sys
from time import time
from optparse import OptionParser
import traceback
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt



#    fpdb/FreePokerTools modules

import Options

import Importer

import Configuration

import Exceptions

import logging
if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("importer")

class GuiBulkImport(QWidget):
    """
    A widget for importing hands into the database.
    """
    def __init__(self, settings, config, sql=None, parent=None):
        """
        Initializes the ImportWidget.

        :param settings: A dictionary of settings.
        :param config: A dictionary of configuration options.
        :param sql: The SQL database to use.
        :param parent: The parent widget.
        """
        # Call the constructor of the parent class.
        QWidget.__init__(self, parent)

        # Save the settings and config as class variables.
        self.settings = settings
        self.config = config

        # Set the default value for the "allowThreads" checkbox.
        self.allowThreads = False

        # Create the Importer object.
        self.importer = Importer.Importer(self, self.settings, config, sql, self)

        # Set the layout of the widget to a QVBoxLayout.
        self.setLayout(QVBoxLayout())

        # Add a QLineEdit for the import directory.
        self.importDir = QLineEdit(self.settings['bulkImport-defaultPath'])
        hbox = QHBoxLayout()
        hbox.addWidget(self.importDir)

        # Add a QPushButton to browse for the import directory.
        self.chooseButton = QPushButton('Browse...')
        self.chooseButton.clicked.connect(self.browseClicked)
        hbox.addWidget(self.chooseButton)
        self.layout().addLayout(hbox)

        # Add a QPushButton to start the import process.
        self.load_button = QPushButton(('Bulk Import'))
        self.load_button.clicked.connect(self.load_clicked)
        self.layout().addWidget(self.load_button)

        # Add a QCheckBox to allow thread usage during the import process.
        self.threads_checkbox = QCheckBox('Allow Threads')
        self.threads_checkbox.stateChanged.connect(self.threads_checkbox_changed)
        self.layout().addWidget(self.threads_checkbox)

        # Get the number of hands already in the database.
        tcursor = self.importer.database.cursor
        tcursor.execute("Select count(1) from Hands")
        row = tcursor.fetchone()
        tcursor.close()

        # Rollback the transaction and save the number of hands in the database.
        self.importer.database.rollback()
        self.n_hands_in_db = row[0]

    def threads_checkbox_changed(self, state):
        """
        Function to handle the state change of the threads checkbox.

        Args:
            state (Qt.CheckState): The new state of the checkbox.

        Returns:
            None
        """
        # Set the allowThreads attribute to True if the state is checked, False otherwise
        self.allowThreads = state == Qt.Checked


    def load_clicked(self):
        """
        Handler function for the load button click event. Loads a directory of hands into the importer.

        Returns:
            None
        """
        if not self.settings['global_lock'].tryLock():
            # If global lock is not available, print error message and return
            print("bulk import aborted - global lock not available")
            return

        selected = self.importDir.text()
        self.importer.setHandsInDB(self.n_hands_in_db)
        self.importer.setMode('bulk')
        self.importer.addBulkImportImportFileOrDir(selected, site='auto')
        self.importer.setCallHud(False)
        self.importer.allowThreads = self.allowThreads

        starttime = time()
        stored, dups, partial, skipped, errs, ttime = self.importer.runImport()
        ttime = time() - starttime

        if ttime == 0:
            ttime = 1

        # Build completion message with import statistics
        completionMessage = ('Bulk import done: Stored: %d, Duplicates: %d, Partial: %d, Skipped: %d, Errors: %d, Time: %s seconds, Stored/second: %.0f') \
            % (stored, dups, partial, skipped, errs, ttime, old_div((stored + 0.0), ttime))

        # Print completion message and log it
        print(completionMessage)
        log.info(completionMessage)

        self.importer.clearFileList()
        self.settings['global_lock'].unlock()




    def browseClicked(self):
        """
        Opens a QFileDialog to allow the user to select a directory to import files from.
        Sets the import directory to the selected directory, if one is chosen.
        """
        # Open a QFileDialog to get the path of the directory to import from
        newdir = QFileDialog.getExistingDirectory(self, caption=("Please choose the path that you want to Auto Import"),
                                            directory=self.importDir.text())

        # If a directory was selected, update the import directory text field
        if newdir:
            self.importDir.setText(newdir)


if __name__ == '__main__':
    config = Configuration.Config()
    settings = {}
    if os.name == 'nt': settings['os'] = 'windows'
    else:               settings['os'] = 'linuxmac'

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    import interlocks
    settings['global_lock'] = interlocks.InterProcessLock(name="fpdb_global_lock")
    settings['cl_options'] = '.'.join(sys.argv[1:])

