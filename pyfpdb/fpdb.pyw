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

# Modifications made by jejellyroll on 2020-2023:
# refactor code for python 3

#Import statements come next
# Standard library imports
import codecs
import logging
import os
import queue
import re
import string
import subprocess
import sys
import threading
import traceback
from functools import partial
import time

# Third-party modules
import numpy
import qdarkstyle
import sqlite3

# PyQt5 modules
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

# fpdb/FreePokerTools modules
import interlocks
import Options
cl_options = '.'.join(sys.argv[1:])
(options, argv) = Options.fpdb_options()
import Card
import Configuration
import Database
import DetectInstalledSites
import Exceptions
import GuiAutoImport
import GuiBulkImport
import GuiDatabase
import GuiGraphViewer
import GuiHandViewer
import GuiLogView
import GuiOddsCalc
import GuiPositionalStats
import GuiPrefs
import GuiRingPlayerStats
import GuiSessionViewer
import GuiStove
import GuiTourneyGraphViewer
import GuiTourneyImport
import GuiTourneyPlayerStats
import GuiTourneyViewer
import SQL
import Stats

# Windows-only modules
if os.name == 'nt':
    import win32api
    import win32con


# these imports not required in this module, imported here to report version in About dialog
import numpy
numpy_version = numpy.__version__
import sqlite3
sqlite3_version = sqlite3.version
sqlite_version = sqlite3.sqlite_version
Configuration.set_logfile("fpdb-log.txt")
log = logging.getLogger("fpdb")

try:
    assert not hasattr(sys, 'frozen') # We're surely not in a git repo if this fails
    import subprocess
    VERSION = subprocess.Popen(["git", "describe", "--tags", "--dirty"], stdout=subprocess.PIPE).communicate()[0]
    VERSION = VERSION[:-1]
except Exception:
    VERSION = "0.40.4"




class fpdb(QMainWindow):
# Initializes the main window of the Free Poker DB application

    def __init__(self):
        super().__init__()
        # Sets the window icon
        self.setWindowIcon(QIcon('tribal.jpg'))

        # Initializes instance variables
        self.lock = interlocks.InterProcessLock(name="fpdb_global_lock")
        self.db = None
        self.status_bar = None
        self.quitting = False
        self.visible = False
        self.threads = []
        self.closeq = queue.Queue(20)

        # Sets display preferences
        self.display_config_created_dialogue = options.initialRun
        self.display_site_preferences = options.initialRun

        # Sets window position if specified in options
        if options.xloc is not None or options.yloc is not None:
            options.xloc = options.xloc if options.xloc is not None else 0
            options.yloc = options.yloc if options.yloc is not None else 0
            self.move(options.xloc, options.yloc)

        # Sets window title and size
        self.setWindowTitle("Free Poker DB 3")
        defx, defy = 1920, 1080
        sg = QApplication.primaryScreen().availableGeometry()
        if sg.width() < defx:
            defx = sg.width()
        if sg.height() < defy:
            defy = sg.height()
        self.resize(defx, defy)

        # Creates the menu bar
        self.createMenuBar()

        # Initializes the main tab widget
        self.nb = QTabWidget()
        self.setCentralWidget(self.nb)
        self.tabs = [None] * 10
        self.tab_names = [None] * 10
        self.pages = [None] * 10
        self.nb_tab_names = []

        # Creates the main help tab
        self.tab_main_help(None, None)

        # Shows or hides the window based on options
        if options.minimized:
            self.showMinimized()
        if options.hidden:
            self.hide()
        if not options.hidden:
            self.show()
            self.visible = True

        # Loads the profile and creates the database if necessary
        self.load_profile(create_db=True)

        # Displays a configuration created dialogue if necessary
        if self.config.install_method == 'app':
            for site in list(self.config.supported_sites.values()):
                if site.screen_name != "YOUR SCREEN NAME HERE":
                    break
            else:
                options.initialRun = True
                self.display_config_created_dialogue = True
                self.display_site_preferences = True

        # Displays the site preferences dialog if necessary
        if options.initialRun and self.display_site_preferences:
            self.dia_site_preferences(None, None)
            self.display_site_preferences = False

        # Redirects error output to the log file if necessary
        if not options.errorsToConsole:
            fileName = os.path.join(self.config.dir_log, 'fpdb-errors.txt')
            print(((("Note: error output is being diverted to %s.") % self.config.dir_log) + " " +
                ("Any major error will be reported there _only_.")))
            errorFile = codecs.open(fileName, 'w', 'utf-8')
            sys.stderr = errorFile

        # Automatically imports hands if necessary
        if options.autoimport:
            self.tab_auto_import(None)


            

    def launch_ppt(self):
        """
        Launches p2.jar file using Java subprocess.

        Args:
            None

        Returns:
            None
        """
        # Get current working directory
        path = os.getcwd()

        # Check OS type and set path accordingly
        pathcomp = os.path.join(path, "ppt", "p2.jar")

        # Launch Java subprocess with p2.jar file
        subprocess.Popen(['java', '-jar', pathcomp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def add_and_display_tab(self, new_page, new_tab_name):
        """
        Adds a new tab to the notebook and displays it. If the tab already exists, it simply displays it.

        Args:
            new_page: The page to be added to the new tab.
            new_tab_name: The name of the new tab.

        Returns:
            None
        """

        # Check if the tab already exists
        for name in self.nb_tab_names:
            if name == new_tab_name:
                # If so, display the tab and return
                self.display_tab(new_tab_name)
                return

        used_before = False
        # Check if the tab has been used before
        for i, name in enumerate(self.tab_names):
            if name == new_tab_name:
                used_before = True
                event_box = self.tabs[i]
                page = self.pages[i]
                break

        if not used_before:
            # If the tab has not been used before, create a new tab page
            page = new_page
            self.pages.append(new_page)
            self.tab_names.append(new_tab_name)

        # Add the tab page to the notebook
        index = self.nb.addTab(page, new_tab_name)
        self.nb_tab_names.append(new_tab_name)
        self.nb.setCurrentIndex(index)

    def display_tab(self, new_tab_name):
        """
        Display a tab with the given name.

        Args:
            new_tab_name (str): The name of the tab to be displayed.

        Raises:
            FpdbError: If the tab number is invalid.
        """

        # Find the index of the tab with the given name.
        try:
            tab_no = self.nb_tab_names.index(new_tab_name)
        except ValueError:
            raise FpdbError(f"{new_tab_name} tab not found")

        # Raise an error if the tab number is invalid.
        if tab_no >= self.nb.count():
            raise FpdbError(f"{new_tab_name} tab index {tab_no} out of range")
        else:
            # Set the current tab to the one with the given name.
            self.nb.setCurrentIndex(tab_no)

    def add_icon_to_button(self, button):
        """
        Adds an icon to a button.

        :param button: The button to add the icon to.
        """
        # Create a QHBoxLayout to hold the icon and add it to the button.
        iconBox = QHBoxLayout(button)

        # Create a QLabel to hold the image and add it to the iconBox.
        image = QLabel(button)
        image.setPixmap(QPixmap.fromTheme("window-close").scaled(16, 16))
        iconBox.addWidget(image)

        # Set the button to be flat and give it a fixed size.
        button.setFlat(True)
        (w, h) = (16, 16)  # size of the icon
        button.setFixedSize(w + 4, h + 4)

        # Set the iconBox as the button's layout.
        button.setLayout(iconBox)
  
    def remove_tab(self, button, data):
        """
        Remove a tab from the notebook.

        Args:
            button: The button that triggered the removal.
            data: The data associated with the tab to remove.
        """
        (nb, text) = data
        page = self.nb_tab_names.index(text) if text in self.nb_tab_names else -1
        # Check if the tab exists and is within the bounds of the notebook
        if page >= 0 and page < self.nb.count():
            # Remove the tab and update the notebook
            self.nb_tab_names.pop(page)
            self.nb.removeTab(page)
            self.nb.update()

    def remove_current_tab(self):
        """
        Remove the currently active tab from the notebook.
        """
        current_page = self.nb.currentIndex()
        if current_page >= 0 and current_page < self.nb.count():
            self.nb_tab_names.pop(current_page)
            self.nb.removeTab(current_page)
            self.nb.update()

    def dia_about(self):
        """
        Show the "About" dialog box.
        """
        msg_box = QMessageBox()
        msg_box.setWindowTitle("FPDB3")
        msg_box.setText("".join([
            "Copyright 2008-2023. See contributors.txt for details",
            "You are free to change, and distribute original or changed versions of fpdb within the rules set out by the license",
            "Your config file is: ", self.config.file]))
        msg_box.exec_()

    def dia_advanced_preferences(self, widget, data=None):
        """
        Opens the 'Advanced Preferences' dialog, allowing the user to modify
        various settings for the application.

        Args:
            widget: The widget that triggered the function.
            data: Optional data to pass to the function.

        Returns:
            None
        """

        # Force reload of preferences from XML file - needed because HUD could
        # have changed file contents.
        self.load_profile()

        # If the user makes changes to the preferences, save the updated config
        # and reload the configuration.
        if GuiPrefs.GuiPrefs(self.config, self).exec_():
            self.config.save()
            self.reload_config()

    def dia_maintain_dbs(self, widget, data=None):
        """
        Opens the 'Maintain Databases' dialog, allowing the user to modify
        various settings for the application.

        Args:
            widget: The widget that triggered the function.
            data: Optional data to pass to the function.

        Returns:
            None
        """

        if len(self.tab_names) == 1:
            if self.obtain_global_lock("dia_maintain_dbs"):
                # only main tab has been opened, open dialog
                dia = QDialog(self.window)
                dia.setWindowTitle("Maintain Databases")
                dia.setModal(True)
                dia.setAttribute(Qt.WA_DeleteOnClose)
                dia.setStandardButtons(QMessageBox.Cancel | QMessageBox.Save)
                dia.setDefaultButton(QMessageBox.Save)
                dia.resize(700, 320)

                prefs = GuiDatabase.GuiDatabase(self.config, self.window, dia)
                response = dia.exec_()
                if response == QMessageBox.Save:
                    log.info('saving updated db data')
                    # save updated config
                    self.config.save()
                    self.load_profile()
                    # for name in self.config.supported_databases:
                    #     log.debug('fpdb: name,desc=' + name + ',' + self.config.supported_databases[name].db_desc)

                self.release_global_lock()

                dia.close()
            else:
                self.warning_box("Cannot open Database Maintenance window because other windows have been opened. Re-start fpdb to use this option.")

    def dia_database_stats(self, widget, data=None):
        """
        Display a message box with the database statistics.

        Args:
            widget: The widget to associate with the dialog box.
            data: Optional data to pass to the function.

        Returns:
            None
        """
        # Create a message box with the database statistics
        message_box = QMessageBox()
        message_box.setWindowTitle("Database Statistics")

        # Get the number of hands, tourneys, and tourney types from the database
        num_hands = self.db.getHandCount()
        num_tourneys = self.db.getTourneyCount()
        num_tourney_types = self.db.getTourneyTypeCount()

        # Add the statistics to the message box text
        message_box.setText("Number of Hands: {}\nNumber of Tourneys: {}\nNumber of TourneyTypes: {}".format(
            num_hands, num_tourneys, num_tourney_types))

        # Display the message box
        message_box.exec_()

    def dia_hud_preferences(self, widget, data=None):
        """
        Opens a dialog for modifying HUD preferences.

        Args:
        self: Object instance.
        widget: Widget instance.
        data: Optional data.

        Returns:
        None
        """
        # Create dialog window
        dia = QDialog(self)
        dia.setWindowTitle(("Modifying Huds"))
        dia.resize(1200,600)

        # Add labels to dialog window
        label = QLabel(("Please edit your huds."))
        dia.setLayout(QVBoxLayout())
        dia.layout().addWidget(label)

        label2 = QLabel(("Please select the game category for which you want to configure HUD stats:"))
        dia.layout().addWidget(label2)

        # Add drop-down menu for selecting game category
        self.comboGame = QComboBox()
        games = self.config.get_stat_sets()
        for game in games:
            self.comboGame.addItem(game)
        dia.layout().addWidget(self.comboGame)
        self.comboGame.setCurrentIndex(1)

        # Load selected game category's profile
        result = self.comboGame.currentText()
        self.load_profile()
        hud_stats = self.config.stat_sets[result]
        hud_nb_col = self.config.stat_sets[result].cols
        hud_nb_row = self.config.stat_sets[result].rows
        tab_rows = hud_nb_col*hud_nb_row

        # Create a scrolling frame for displaying HUD stats
        self.table = QGridLayout()
        self.table.setSpacing(0)
        scrolling_frame = QScrollArea(dia)
        dia.layout().addWidget(scrolling_frame)
        scrolling_frame.setLayout(self.table)

        # Add buttons for saving or canceling changes
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dia)
        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)
        dia.layout().addWidget(btns)

        # Update HUD stats when selected game category changes
        self.comboGame.currentIndexChanged.connect(self.index_changed)
        response = dia.exec_()
        if self.comboGame.currentIndexChanged and response:
            for y in range(0, len(self.config.stat_sets[result].stats)):
                self.config.edit_hud(result, self.stat2_dict[y].text(), self.stat3_dict[y].text(), self.stat4_dict[y].text(), self.stat5_dict[y].text(), self.stat6_dict[y].text(), self.stat7_dict[y].text(), self.stat8_dict[y].text(), self.stat9_dict[y].text(), self.stat10_dict[y].text(), self.stat11_dict[y].text(), self.stat12_dict[y].text(), self.stat13_dict[y].text())

            # Save changes and reload config
            self.config.save()
            self.reload_config()


    def index_changed(self, index):
        # TODO: rewrite this function
        self.comboGame.setCurrentIndex(index)
        result = self.comboGame.currentText()
        for i in reversed(range(self.table.count())):
            self.table.itemAt(i).widget().deleteLater()

        self.table.setSpacing(0)

        column_headers = [("coordonate"), ("stats name"), ("click"), ("hudcolor"), ("hudprefix"), ("hudsuffix"),
                          ("popup"), ("stat_hicolor"), ("stat_hith"), ("stat_locolor"), ("stat_loth"),
                          ("tip")]  # todo ("HUD")

        for header_number in range(0, len(column_headers)):
            label = QLabel(column_headers[header_number])
            label.setAlignment(Qt.AlignCenter)
            self.table.addWidget(label, 0, header_number)

        self.stat2_dict, self.stat3_dict, self.stat4_dict, self.stat5_dict, self.stat6_dict, self.stat7_dict, self.stat8_dict, self.stat9_dict, self.stat10_dict, self.stat11_dict, self.stat12_dict, self.stat13_dict = [], [], [], [], [], [], [], [], [], [], [], []

        self.load_profile()
        # print('resultat', result)
        hud_stats = self.config.stat_sets[result]
        hud_nb_col = self.config.stat_sets[result].cols
        hud_nb_row = self.config.stat_sets[result].rows
        tab_rows = hud_nb_col * hud_nb_row
        # print('stats set',hud_stats )



        result2 = list(self.config.stat_sets[result].stats)
        result3 = len(self.config.stat_sets[result].stats)
        # print(self.config.stat_sets[result].stats)
        # print(result2)
        # print(result3)
        y_pos = 1
        for y in range(0, result3):
            # print(result2[y])
            stat = result2[y]
            # print(self.config.stat_sets[result].stats[stat].stat_name)
            stat2 = QLabel()
            stat2.setText(str(stat))
            self.table.addWidget(stat2, y_pos, 0)
            self.stat2_dict.append(stat2)
            if os.name == 'nt' :
                icoPath = os.path.dirname(__file__)
                
                icoPath = icoPath+"\\"
                print(icoPath)
            else:
                icoPath = ""
            stat3 = QComboBox()
            stats_cash = self.config.get_gui_cash_stat_params()
            for x in range(0, len(stats_cash)):
                #print(stats_cash[x][0])
                stat3.addItem(QIcon(icoPath +'Letter-C-icon.png'),stats_cash[x][0])
            stats_tour = self.config.get_gui_tour_stat_params()
            for x in range(0, len(stats_tour)):
                #print(stats_tour[x][0])
                stat3.addItem(QIcon(icoPath +'Letter-T-icon.png'),stats_tour[x][0])
            stat3.setCurrentText(str(self.config.stat_sets[result].stats[stat].stat_name))
            self.table.addWidget(stat3, y_pos, 1)
            self.stat3_dict.append(stat3)

            stat4 = QLineEdit()
            stat4.setText(str(self.config.stat_sets[result].stats[stat].click))
            self.table.addWidget(stat4, y_pos, 2)
            self.stat4_dict.append(stat4)

            stat5 = QLineEdit()
            stat5.setText(str(self.config.stat_sets[result].stats[stat].hudcolor))
            self.table.addWidget(stat5, y_pos, 3)
            self.stat5_dict.append(stat5)

            stat6 = QLineEdit()
            stat6.setText(str(self.config.stat_sets[result].stats[stat].hudprefix))
            self.table.addWidget(stat6, y_pos, 4)
            self.stat6_dict.append(stat6)

            stat7 = QLineEdit()
            stat7.setText(str(self.config.stat_sets[result].stats[stat].hudsuffix))
            self.table.addWidget(stat7, y_pos, 5)
            self.stat7_dict.append(stat7)

            stat8 = QComboBox()
            for popup in self.config.popup_windows.keys():
                stat8.addItem(popup)
            stat8.setCurrentText(str(self.config.stat_sets[result].stats[stat].popup))
            self.table.addWidget(stat8, y_pos, 6)
            self.stat8_dict.append(stat8)

            stat9 = QLineEdit()
            stat9.setText(str(self.config.stat_sets[result].stats[stat].stat_hicolor))
            self.table.addWidget(stat9, y_pos, 7)
            self.stat9_dict.append(stat9)

            stat10 = QLineEdit()
            stat10.setText(str(self.config.stat_sets[result].stats[stat].stat_hith))
            self.table.addWidget(stat10, y_pos, 8)
            self.stat10_dict.append(stat10)

            stat11 = QLineEdit()
            stat11.setText(str(self.config.stat_sets[result].stats[stat].stat_locolor))
            self.table.addWidget(stat11, y_pos, 9)
            self.stat11_dict.append(stat11)

            stat12 = QLineEdit()
            stat12.setText(str(self.config.stat_sets[result].stats[stat].stat_loth))
            self.table.addWidget(stat12, y_pos, 10)
            self.stat12_dict.append(stat12)

            stat13 = QLineEdit()
            stat13.setText(str(self.config.stat_sets[result].stats[stat].tip))
            self.table.addWidget(stat13, y_pos, 11)
            self.stat13_dict.append(stat13)
            # if available_site_names[site_number] in detector.supportedSites:
            # pass

            y_pos += 1

    def dia_import_filters(self, checkState):
        """
        Opens a dialog window to allow the user to select which games to skip when importing.

        Args:
            checkState: The state of the checkbox.

        Returns:
            None
        """
        # Create the dialog window and set its title
        dia = QDialog()
        dia.setWindowTitle("Skip these games when importing")

        # Set the layout of the dialog window to a vertical box layout
        dia.setLayout(QVBoxLayout())

        # Create a dictionary to store the checkboxes for each game
        checkboxes = {}

        # Get the import filters from the config
        filters = self.config.get_import_parameters()['importFilters']

        # Create a checkbox for each game and add it to the dialog window
        for game in Card.games:
            checkboxes[game] = QCheckBox(game)
            dia.layout().addWidget(checkboxes[game])

            # If the game is already in the filters, check the checkbox
            if game in filters:
                checkboxes[game].setChecked(True)

        # Add "Ok" and "Cancel" buttons to the dialog window
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dia.layout().addWidget(btns)

        # When the "Ok" button is clicked, accept the dialog
        btns.accepted.connect(dia.accept)

        # When the "Cancel" button is clicked, reject the dialog
        btns.rejected.connect(dia.reject)

        # If the dialog is accepted, update the import filters in the config
        if dia.exec_():
            filterGames = []
            for game, cb in list(checkboxes.items()):
                if cb.isChecked():
                    filterGames.append(game)
            self.config.editImportFilters(",".join(filterGames))
            self.config.save()


    def dia_dump_db(self, widget, data=None):
        """
        Dump the contents of the database to a file.

        Args:
            widget: The widget that triggered the function.
            data: Any additional data that may be passed.

        Returns:
            None.
        """
        # Set the filename for the dump file.
        filename = "database-dump.sql"

        # Get the contents of the database.
        result = self.db.dumpDatabase()

        # Open the dump file for writing.
        dumpFile = open(filename, 'w')

        # Write the contents of the database to the dump file.
        dumpFile.write(result)

        # Close the dump file.
        dumpFile.close()

    #end def dia_database_stats

    def dia_recreate_tables(self, widget, data=None):
        """
        Dialogue that asks user to confirm that he wants to delete and recreate the tables.
        """
        # Try to obtain the global lock and return true if successful
        if self.obtain_global_lock("fpdb.dia_recreate_tables"):
            # Create a warning message box asking the user to confirm deleting and recreating tables
            dia_confirm = QMessageBox(QMessageBox.Warning, "Wipe DB", ("Confirm deleting and recreating tables"), QMessageBox.Yes | QMessageBox.No, self)
            # Create a string with the message to show in the dialog box
            diastring = ("Please confirm that you want to (re-)create the tables.") \
                        + " " + (("If there already are tables in the database %s on %s they will be deleted and you will have to re-import your histories.") % (self.db.database, self.db.host)) + "\n"\
                        + ("This may take a while.")
            # Set the informative text of the dialog box to the created string
            dia_confirm.setInformativeText(diastring)  # todo: make above string with bold for db, host and deleted
            # Show the dialog box and get the response
            response = dia_confirm.exec_()

            # If the user confirmed, recreate the tables and clear the cache in any guibulkimport/guiautoimport windows
            if response == QMessageBox.Yes:
                self.db.recreate_tables()
                for t in self.threads:
                    if isinstance(t, GuiBulkImport.GuiBulkImport) or isinstance(t, GuiAutoImport.GuiAutoImport):
                        t.importer.database.resetCache()
                # Release the global lock
                self.release_global_lock()
            else:
                # If the user cancelled, release the global lock and print a message
                self.release_global_lock()
                print ('User cancelled recreating tables')
        else:
            # If the global lock could not be obtained, show a warning box
            self.warning_box(("Cannot open Database Maintenance window because other windows have been opened. Re-start fpdb to use this option."))

    def dia_recreate_hudcache(self, widget, data=None):
        """
        Function to recreate the HUD cache.

        Parameters:
            widget (QWidget): The widget to which the dialog box should be attached.
            data (any): Any additional data that should be passed to the function. Defaults to None.

        Returns:
            None
        """
        if self.obtain_global_lock("dia_recreate_hudcache"):
            # Create a dialog box to confirm recreation of the HUD cache
            self.dia_confirm = QDialog()
            self.dia_confirm.setWindowTitle("Confirm recreating HUD cache")
            self.dia_confirm.setLayout(QVBoxLayout())
            # Add a label to the dialog box to ask for confirmation
            self.dia_confirm.layout().addWidget(QLabel(("Please confirm that you want to re-create the HUD cache.")))

            hb1 = QHBoxLayout()
            # Create a QDateEdit widget to select the Hero's cache start date
            self.h_start_date = QDateEdit(QDate.fromString(self.db.get_hero_hudcache_start(), "yyyy-MM-dd"))
            lbl = QLabel((" Hero's cache starts: "))
            btn = QPushButton("Cal")
            # Connect the button to open a calendar dialog when clicked
            btn.clicked.connect(partial(self.__calendar_dialog, entry=self.h_start_date))

            hb1.addWidget(lbl)
            hb1.addStretch()
            hb1.addWidget(self.h_start_date)
            hb1.addWidget(btn)
            self.dia_confirm.layout().addLayout(hb1)

            hb2 = QHBoxLayout()
            # Create a QDateEdit widget to select the Villains' cache start date
            self.start_date = QDateEdit(QDate.fromString(self.db.get_hero_hudcache_start(), "yyyy-MM-dd"))
            lbl = QLabel((" Villains' cache starts: "))
            btn = QPushButton("Cal")
            # Connect the button to open a calendar dialog when clicked
            btn.clicked.connect(partial(self.__calendar_dialog, entry=self.start_date))

            hb2.addWidget(lbl)
            hb2.addStretch()
            hb2.addWidget(self.start_date)
            hb2.addWidget(btn)
            self.dia_confirm.layout().addLayout(hb2)

            # Add Yes and No buttons to the dialog box
            btns = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
            self.dia_confirm.layout().addWidget(btns)
            # Connect the buttons to the appropriate functions
            btns.accepted.connect(self.dia_confirm.accept)
            btns.rejected.connect(self.dia_confirm.reject)

            # Display the dialog box and get the user's response
            response = self.dia_confirm.exec_()

            # If the user confirms, rebuild the HUD Cache
            if response:
                print("Rebuilding HUD Cache...")
                self.db.rebuild_cache(
                    self.h_start_date.date().toString("yyyy-MM-dd"),
                    self.start_date.date().toString("yyyy-MM-dd")
                )
            else:
                # Otherwise, print a message indicating the cache will not be rebuilt
                print('User cancelled rebuilding hud cache')

            # Release the global lock
            self.release_global_lock()
        else:
            # If the global lock cannot be obtained, display a warning box
            self.warning_box(
                ("Cannot open Database Maintenance window because other windows have been opened. "
                "Re-start fpdb to use this option.")
            )

    def dia_rebuild_indexes(self, widget, data=None):
        """
        Rebuilds the database indexes and performs maintenance tasks.

        Args:
            widget: The widget object triggering the function.
            data: Optional data to be passed.

        Returns:
            None.
        """
        if self.obtain_global_lock("dia_rebuild_indexes"):
            # Display a confirmation dialog.
            self.dia_confirm = QMessageBox(QMessageBox.Warning,
                                        "Rebuild DB",
                                        ("Confirm rebuilding database indexes"),
                                        QMessageBox.Yes | QMessageBox.No,
                                        self)
            diastring = ("Please confirm that you want to rebuild the database indexes.")
            self.dia_confirm.setInformativeText(diastring)

            response = self.dia_confirm.exec_()
            if response == QMessageBox.Yes:
                # Rebuild the database indexes.
                print (" Rebuilding Indexes ... ")
                self.db.rebuild_indexes()

                # Clean the database.
                print (" Cleaning Database ... ")
                self.db.vacuumDB()

                # Analyze the database.
                print (" Analyzing Database ... ")
                self.db.analyzeDB()
            else:
                # User cancelled rebuilding db indexes.
                print ('User cancelled rebuilding db indexes')

            self.release_global_lock()
        else:
            # Cannot open Database Maintenance window because other windows have been opened. Re-start fpdb to use this option.
            self.warning_box(("Cannot open Database Maintenance window because other windows have been opened. Re-start fpdb to use this option."))

    def dia_logs(self, widget, data=None):
        """Opens the log viewer window"""

        # remove members from self.threads if close messages received
        self.process_close_messages()

        # Search for existing GuiLogView object
        viewer = None
        for i, t in enumerate(self.threads):
            if str(t.__class__) == 'GuiLogView.GuiLogView':
                viewer = t
                break

        # If GuiLogView object does not exist, create a new one and append it to self.threads
        if viewer is None:
            new_thread = GuiLogView.GuiLogView(self.config, self.window, self.closeq)
            self.threads.append(new_thread)
        # If GuiLogView object exists, show it
        else:
            viewer.get_dialog().present()


    def dia_site_preferences_seat(self, widget, data=None):
        """
        Opens a dialog box that allows the user to select their preferred seat for each supported site.

        Args:
        - widget: the widget that triggered the function (unused)
        - data: optional data to pass to the function (unused)

        Returns: None
        """
        # Initialize dialog box
        dia = QDialog(self)
        dia.setWindowTitle("Seat Preferences")
        dia.resize(1200, 600)
        dia.setLayout(QVBoxLayout())

        # Add label to dialog box
        label = QLabel("Please select your preferred seat.")
        dia.layout().addWidget(label)

        # Load profile and get available sites
        self.load_profile()
        available_sites = self.get_available_sites()

        # Define headers for table
        headers = [
            "Site", "2 players:\nBetween 0 & 2", "3 players:\nBetween 0 & 3",
            "4 players:\nBetween 0 & 4", "5 players:\nBetween 0 & 5",
            "6 players:\nBetween 0 & 6", "7 players:\nBetween 0 & 7",
            "8 players:\nBetween 0 & 8", "9 players:\nBetween 0 & 9",
            "10 players:\nBetween 0 & 10"
        ]

        # Create table layout and add to scrolling frame
        table = QGridLayout()
        table.setSpacing(0)
        scrolling_frame = QScrollArea(dia)
        dia.layout().addWidget(scrolling_frame)
        scrolling_frame.setLayout(table)

        # Add headers to table
        self.add_headers(table, headers)

        # Add check boxes for seat selection to table
        check_buttons = []
        seat_dicts = self.add_seats_to_table(table, available_sites, check_buttons)

        # Add save and cancel buttons to dialog box
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dia)
        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)
        dia.layout().addWidget(btns)

        # Display dialog box and save preferences if save button is clicked
        response = dia.exec_()
        if response:
            for site_dict in seat_dicts:
                for site_name, seat_dict in site_dict.items():
                    site = self.config.supported_sites[site_name]
                    site.fav_seat = list(seat_dict.values())
                    site.enabled = self.is_site_enabled(site_name)
            self.save_profile()


    def add_headers(self, table, headers):
        """
        Adds headers to a table widget.

        Args:
            table (QTableWidget): The table widget to add the headers to.
            headers (list of str): The headers to add to the table widget.

        Returns:
            None
        """
        for i, header in enumerate(headers):
            # Create a label widget for the header and center the text.
            label = QLabel(header)
            label.setAlignment(Qt.AlignCenter)

            # Add the label to the table widget at row 0 and column i.
            table.addWidget(label, 0, i)


    def add_seats_to_table(self, table, available_sites, check_buttons):
        """
        Adds seats to a table widget for each available site

        Args:
            table (QTableWidget): The table widget to add the seats to
            available_sites (list): A list of available site names
            check_buttons (list): A list of check box widgets for each site

        Returns:
            list: A list of seat dictionaries for each site
        """

        # Initialize an empty list to store the seat dictionaries for each site
        seat_dicts = []

        # Initialize the vertical position of the table to 1
        y_pos = 1

        # Loop through each available site
        for site_name in available_sites:

            # Get the site object from the configuration
            site = self.config.supported_sites[site_name]

            # Create a check box widget and add it to the table
            check_button = QCheckBox(site_name)
            check_button.setChecked(site.enabled)
            table.addWidget(check_button, y_pos, 0)

            # Add the check box widget to the list of check box widgets
            check_buttons.append(check_button)

            # Initialize an empty dictionary to store the seat values for the site
            seat_dict = {}

            # Loop through each seat value for the site
            for i in range(2, 11):

                # Create a line edit widget with the seat value and add it to the table
                seat = QLineEdit(str(site.fav_seat[i]))
                seat.textChanged.connect(partial(self.autoenableSite, checkbox=check_button))
                table.addWidget(seat, y_pos, i - 1)

                # Add the seat value to the seat dictionary
                seat_dict[i] = seat.text

            # Add the seat dictionary to the list of seat dictionaries
            seat_dicts.append({site_name: seat_dict})

            # Increment the vertical position of the table
            y_pos += 1

        # Return the list of seat dictionaries for each site
        return seat_dicts


    def get_available_sites(self):
        """
        Returns a list of names of all supported and enabled sites.

        :return: A list of strings representing site names.
        """
        available_site_names = []
        for site_name, site in self.config.supported_sites.items():
            # Check if the site is enabled
            if site.enabled:
                # Add the site name to the list of available site names
                available_site_names.append(site_name)
        return available_site_names


    def is_site_enabled(self, site_name):
        """
        Check if a site is enabled.

        Args:
            site_name (str): The name of the site to check.

        Returns:
            bool: True if the site is enabled, False otherwise.
        """
        # Loop through all check buttons to find the button with the matching text
        for button in self.check_buttons:
            if button.text() == site_name:
                # Return the checked status of the button if the text matches
                return button.isChecked()

        # Return False if no matching button was found
        return False


        
    def dia_site_preferences(self, widget, data=None):
        """
        Open a dialog for site preferences.

        :param widget: The parent widget.
        :param data: Optional data.
        """
        dia = QDialog(self)
        dia.setWindowTitle(("Site Preferences"))
        dia.resize(1200,600)
        label = QLabel(("Please select which sites you play on and enter your usernames."))
        dia.setLayout(QVBoxLayout())
        dia.layout().addWidget(label)
        
        self.load_profile()
        site_names = self.config.site_ids
        available_site_names=[]
        for site_name in site_names:
            try:
                tmp = self.config.supported_sites[site_name].enabled
                available_site_names.append(site_name)
            except KeyError:
                pass
        
        column_headers=[("Site"), ("Detect"), ("Screen Name"), ("Hand History Path"), "", ("Tournament Summary Path"), "", ("Favorite seat")]  # todo ("HUD")
        #HUD column will contain a button that shows favseat and HUD locations. Make it possible to load screenshot to arrange HUD windowlets.

        table = QGridLayout()
        table.setSpacing(0)

        scrolling_frame = QScrollArea(dia)
        dia.layout().addWidget(scrolling_frame)
        scrolling_frame.setLayout(table)
                
        for header_number in range (0, len(column_headers)):
            label = QLabel(column_headers[header_number])
            label.setAlignment(Qt.AlignCenter)
            table.addWidget(label, 0, header_number)
        
        check_buttons=[]
        screen_names=[]
        history_paths=[]
        summary_paths=[]
        detector = DetectInstalledSites.DetectInstalledSites()
              
        y_pos=1
        for site_number in range(0, len(available_site_names)):
            check_button = QCheckBox(available_site_names[site_number])
            check_button.setChecked(self.config.supported_sites[available_site_names[site_number]].enabled)
            table.addWidget(check_button, y_pos, 0)
            check_buttons.append(check_button)
            
            hero = QLineEdit()
            hero.setText(self.config.supported_sites[available_site_names[site_number]].screen_name)
            table.addWidget(hero, y_pos, 2)
            screen_names.append(hero)
            hero.textChanged.connect(partial(self.autoenableSite, checkbox=check_buttons[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[available_site_names[site_number]].HH_path)
            table.addWidget(entry, y_pos, 3)
            history_paths.append(entry)
            
            choose1 = QPushButton("Browse")
            table.addWidget(choose1, y_pos, 4)
            choose1.clicked.connect(partial(self.browseClicked, parent=dia, path=history_paths[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[available_site_names[site_number]].TS_path)
            table.addWidget(entry, y_pos, 5)
            summary_paths.append(entry)

            choose2 = QPushButton("Browse")
            table.addWidget(choose2, y_pos, 6)
            choose2.clicked.connect(partial(self.browseClicked, parent=dia, path=summary_paths[site_number]))

            if available_site_names[site_number] in detector.supportedSites:
                button = QPushButton(("Detect"))
                table.addWidget(button, y_pos, 1)
                button.clicked.connect(partial(self.detect_clicked, data=(detector, available_site_names[site_number], screen_names[site_number], history_paths[site_number], summary_paths[site_number])))
            y_pos+=1

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dia)
        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)
        dia.layout().addWidget(btns)

        response = dia.exec_()
        if response:
            for site_number in range(0, len(available_site_names)):
                #print "site %s enabled=%s name=%s" % (available_site_names[site_number], check_buttons[site_number].get_active(), screen_names[site_number].get_text(), history_paths[site_number].get_text())
                self.config.edit_site(available_site_names[site_number], str(check_buttons[site_number].isChecked()), screen_names[site_number].text(), history_paths[site_number].text(), summary_paths[site_number].text())
            
            self.config.save()
            self.reload_config()
        
    def autoenableSite(self, text, checkbox):
        """
        Auto-activates the site if something is typed in the screename field.

        Args:
            text (str): The text entered into the screename field.
            checkbox (QCheckBox): The checkbox for site activation.

        Returns:
            None
        """
        # Set the checkbox to checked, indicating site activation
        checkbox.setChecked(True)

                
    def browseClicked(self, widget, parent, path):
        """
        Runs when the user clicks one of the browse buttons for the TS folder.

        Args:
            widget: The widget that was clicked.
            parent: The parent widget.
            path: The path to the current folder.

        Returns:
            None
        """

        # Open a file dialog to choose the directory to import.
        newpath = QFileDialog.getExistingDirectory(parent, ("Please choose the path that you want to Auto Import"), path.text())

        # If a new path was chosen, update the path.
        if newpath:
            path.setText(newpath)

    
    def detect_clicked(self, widget, data):
        """
        This function is called when the detect button is clicked.
        It updates the entry fields with information obtained by the detector.

        :param widget: The widget that triggered the event
        :type widget: Gtk.Widget
        :param data: The data associated with the event
        :type data: tuple
        """
        detector = data[0]
        site_name = data[1]
        entry_screen_name = data[2]
        entry_history_path = data[3]
        entry_summary_path = data[4]

        # update the entry fields with information obtained by the detector
        if detector.sitestatusdict[site_name]['detected']:
            entry_screen_name.setText(detector.sitestatusdict[site_name]['heroname'])
            entry_history_path.setText(detector.sitestatusdict[site_name]['hhpath'])
            if detector.sitestatusdict[site_name]['tspath']:
                entry_summary_path.setText(detector.sitestatusdict[site_name]['tspath'])

    def reload_config(self):
        """
        Reloads the configuration settings for Fpdb.
        If only the main tab is open, the profile is reloaded and Fpdb is restarted.
        If other windows are open, a warning message is displayed to re-start Fpdb to load the updated preferences.
        """
        if len(self.nb_tab_names) == 1:
            # only main tab open, reload profile
            self.load_profile()
            self.warning_box(("Configuration settings have been updated, Fpdb needs to be restarted now")+"\n\n"+("Click OK to close Fpdb"))
            sys.exit()
        else:
            # other windows are open, display warning message
            self.warning_box(("Updated preferences have not been loaded because windows are open.")+" "+("Re-start fpdb to load them."))

    def addLogText(self, text):
        """
        Inserts text into the log buffer and scrolls to the bottom of the log view.

        Args:
            text (str): The text to insert into the log buffer.
        """
        # Get the end iterator of the log buffer
        end_iter = self.logbuffer.get_end_iter()

        # Insert the text at the end iterator
        self.logbuffer.insert(end_iter, text)

        # Scroll to the bottom of the log view
        self.logview.scroll_to_mark(self.logbuffer.get_insert(), 0)


    def process_close_messages(self):
        """
        Process close messages from the close queue, and remove any threads that have ended.

        This function loops through the close queue to check for any close messages. If a close message is found, it
        searches through the list of threads to find the thread with the matching class name, and removes it from the
        list. If no close messages are found, the function does nothing.

        Args:
            self: The instance of the class.

        Returns:
            None
        """
        try:
            # Loop through the close queue to check for close messages
            while True:
                name = self.closeq.get(False)
                # Search through the list of threads to find the thread with the matching class name
                for i, t in enumerate(self.threads):
                    if str(t.__class__) == str(name):
                        # Thread has ended, so remove it from the list
                        del self.threads[i]
                        break
        except queue.Empty:
            # No close messages on queue, do nothing
            pass


    def __calendar_dialog(self, widget, entry):
        """
        Creates a calendar dialog window for selecting a date.

        Args:
            widget: The widget that triggered the dialog window.
            entry: The entry field where the selected date will be displayed.

        Returns:
            None
        """
        d = QDialog(self.dia_confirm)  # Create a new QDialog window.
        d.setWindowTitle(('Pick a date'))

        vb = QVBoxLayout()  # Create a new QVBoxLayout object.
        d.setLayout(vb)  # Set the layout for the QDialog window.
        cal = QCalendarWidget()  # Create a new QCalendarWidget object.
        vb.addWidget(cal)  # Add the calendar widget to the QVBoxLayout.

        btn = QPushButton(('Done'))  # Create a new QPushButton object.
        btn.clicked.connect(partial(self.__get_date, calendar=cal, entry=entry, win=d))  # Connect the button to a callback.

        vb.addWidget(btn)  # Add the button to the QVBoxLayout.

        d.exec_()  # Show the QDialog window.
        return


    def createMenuBar(self):
        """
        Creates the menu bar with various menus and actions.
        """
        mb = self.menuBar()
        configMenu = mb.addMenu(('Configure'))
        importMenu = mb.addMenu(('Import'))
        hudMenu = mb.addMenu(('HUD'))
        cashMenu = mb.addMenu(('Cash'))
        tournamentMenu = mb.addMenu(('Tournament'))
        maintenanceMenu = mb.addMenu(('Maintenance'))
        toolsMenu = mb.addMenu(('Tools'))
        helpMenu = mb.addMenu(('Help'))

        # Create actions
        def makeAction(name, callback, shortcut=None, tip=None):
            """
            Create a QAction with given name and settings.

            Args:
                name (str): Name of the action.
                callback (function): Function to be called when the action is triggered.
                shortcut (str): Shortcut key for the action.
                tip (str): Tooltip for the action.

            Returns:
                QAction: The created action.
            """
            action = QAction(name, self)
            if shortcut:
                action.setShortcut(shortcut)
            if tip:
                action.setToolTip(tip)
            action.triggered.connect(callback)
            return action

        # Add actions to each menu
        configMenu.addAction(makeAction(('Site Settings'), self.dia_site_preferences))
        configMenu.addAction(makeAction(('Seat Settings'), self.dia_site_preferences_seat))
        configMenu.addAction(makeAction(('Hud Settings'), self.dia_hud_preferences))
        configMenu.addAction(makeAction(('Adv Preferences'), self.dia_advanced_preferences, tip='Edit your preferences'))
        #configMenu.addAction(makeAction(('HUD Stats Settings'), self.dia_hud_preferences))
        configMenu.addAction(makeAction('Import filters', self.dia_import_filters))
        configMenu.addSeparator()
        configMenu.addAction(makeAction(('Close Fpdb'), self.quit, 'Ctrl+Q', 'Quit the Program'))

        importMenu.addAction(makeAction(('Bulk Import'), self.tab_bulk_import, 'Ctrl+B'))
        #importMenu.addAction(makeAction(('_Import through eMail/IMAP'), self.tab_imap_import))

        hudMenu.addAction(makeAction(('HUD and Auto Import'), self.tab_auto_import, 'Ctrl+A'))

        cashMenu.addAction(makeAction(('Graphs'), self.tabGraphViewer, 'Ctrl+G'))
        cashMenu.addAction(makeAction(('Ring Player Stats'), self.tab_ring_player_stats, 'Ctrl+P'))
        cashMenu.addAction(makeAction(('Hand Viewer'), self.tab_hand_viewer))
        #cashMenu.addAction(makeAction(('Positional Stats (tabulated view)'), self.tab_positional_stats))
        cashMenu.addAction(makeAction(('Session Stats'), self.tab_session_stats, 'Ctrl+S'))
        #cashMenu.addAction(makeAction(('Stove (preview)'), self.tabStove))

        tournamentMenu.addAction(makeAction(('Tourney Graphs'), self.tabTourneyGraphViewer))
        tournamentMenu.addAction(makeAction(('Tourney Stats'), self.tab_tourney_player_stats, 'Ctrl+T'))
        #tournamentMenu.addAction(makeAction(('Tourney Viewer'), self.tab_tourney_viewer_stats))
        tournamentMenu.addAction(makeAction(('Tourney Viewer'), self.tab_tourney_viewer_stats))

        maintenanceMenu.addAction(makeAction(('Statistics'), self.dia_database_stats, 'View Database Statistics'))
        maintenanceMenu.addAction(makeAction(('Create or Recreate Tables'), self.dia_recreate_tables))
        maintenanceMenu.addAction(makeAction(('Rebuild HUD Cache'), self.dia_recreate_hudcache))
        maintenanceMenu.addAction(makeAction(('Rebuild DB Indexes'), self.dia_rebuild_indexes))
        maintenanceMenu.addAction(makeAction(('Dump Database to Textfile (takes ALOT of time)'), self.dia_dump_db))
        #maintenanceMenu.addAction(makeAction(('Database'), self.tab_database

        
        toolsMenu.addAction(makeAction(('Odds Calc'), self.tab_odds_calc))
        toolsMenu.addAction(makeAction(('PokerProTools'), self.launch_ppt))

        helpMenu.addAction(makeAction(('Log Messages'), self.dia_logs, 'Log and Debug Messages'))
        helpMenu.addAction(makeAction(('Help Tab'), self.tab_main_help))
        helpMenu.addSeparator()
        helpMenu.addAction(makeAction(('Infos'), self.dia_about, 'About the program'))

    def load_profile(self, create_db=False):
        """Loads profile from the provided path name."""
        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        if self.config.file_error:
            self.warning_box(("There is an error in your config file %s") % self.config.file
                              + ":\n" + str(self.config.file_error),
                              diatitle=("CONFIG FILE ERROR"))
            sys.exit()

        log = logging.getLogger("fpdb")
        print ((("Logfile is %s") % os.path.join(self.config.dir_log, self.config.log_file)))
        print("load profiles", self.config.example_copy)
        print(self.display_config_created_dialogue)
        print(self.config.wrongConfigVersion)
        if self.config.example_copy or self.display_config_created_dialogue:
            self.info_box(("Config file"),
                          ("Config file has been created at %s.") % self.config.file + " "
                           + ("Enter your screen_name and hand history path in the Site Preferences window (Main menu) before trying to import hands."))
            self.display_config_created_dialogue = False
        elif self.config.wrongConfigVersion:
            diaConfigVersionWarning = QDialog()
            diaConfigVersionWarning.setWindowTitle(("Strong Warning - Local configuration out of date"))
            diaConfigVersionWarning.setLayout(QVBoxLayout())

            label = QLabel("\n"+("Your local configuration file needs to be updated."))
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("This error is not necessarily fatal but it is strongly recommended that you update the configuration.")+"\n")
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("To create a new configuration, see fpdb.sourceforge.net/apps/mediawiki/fpdb/index.php?title=Reset_Configuration"))
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel(("A new configuration will destroy all personal settings (hud layout, site folders, screennames, favourite seats)")+"\n")
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("To keep existing personal settings, you must edit the local file."))
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("See the release note for information about the edits needed"))
            diaConfigVersionWarning.layout().addWidget(label)

            btns = QDialogButtonBox(QDialogButtonBox.Ok)
            btns.accepted.connect(diaConfigVersionWarning.accept)
            diaConfigVersionWarning.layout().addWidget(btns)

            diaConfigVersionWarning.exec_()
            self.config.wrongConfigVersion = False
            
        self.settings = {}
        self.settings['global_lock'] = self.lock
        if (os.sep == "/"):
            self.settings['os'] = "linuxmac"
        else:
            self.settings['os'] = "windows"

        self.settings.update({'cl_options': cl_options})
        self.settings.update(self.config.get_db_parameters())
        self.settings.update(self.config.get_import_parameters())
        self.settings.update(self.config.get_default_paths())

        if self.db is not None and self.db.is_connected():
            self.db.disconnect()

        self.sql = SQL.Sql(db_server=self.settings['db-server'])
        err_msg = None
        try:
            self.db = Database.Database(self.config, sql=self.sql)
            if self.db.get_backend_name() == 'SQLite':
                # tell sqlite users where the db file is
                print ((("Connected to SQLite: %s") % self.db.db_path))
        except Exceptions.FpdbMySQLAccessDenied:
            err_msg = ("MySQL Server reports: Access denied. Are your permissions set correctly?")
        except Exceptions.FpdbMySQLNoDatabase:
            err_msg = ("MySQL client reports: 2002 or 2003 error. Unable to connect - ") \
                      + ("Please check that the MySQL service has been started")
        except Exceptions.FpdbPostgresqlAccessDenied:
            err_msg = ("PostgreSQL Server reports: Access denied. Are your permissions set correctly?")
        except Exceptions.FpdbPostgresqlNoDatabase:
            err_msg = ("PostgreSQL client reports: Unable to connect - ") \
                      + ("Please check that the PostgreSQL service has been started")
        if err_msg is not None:
            self.db = None
            self.warning_box(err_msg)
        if self.db is not None and not self.db.is_connected():
            self.db = None

        if self.db is not None and self.db.wrongDbVersion:
            diaDbVersionWarning = QMessageBox(QMessageBox.Warning, ("Strong Warning - Invalid database version"), ("An invalid DB version or missing tables have been detected."), QMessageBox.Ok, self)
            diaDbVersionWarning.setInformativeText(("This error is not necessarily fatal but it is strongly recommended that you recreate the tables by using the Database menu.")
                                                   + "\n" +  ("Not doing this will likely lead to misbehaviour including fpdb crashes, corrupt data etc."))
            diaDbVersionWarning.exec_()
        if self.db is not None and self.db.is_connected():
            self.statusBar().showMessage(("Status: Connected to %s database named %s on host %s")
                                     % (self.db.get_backend_name(), self.db.database, self.db.host))
            # rollback to make sure any locks are cleared:
            self.db.rollback()

        #If the db-version is out of date, don't validate the config 
        # otherwise the end user gets bombarded with false messages
        # about every site not existing
        if hasattr(self.db, 'wrongDbVersion'):
            if not self.db.wrongDbVersion:
                self.validate_config()


    def obtain_global_lock(self, source: str) -> bool:
        """Attempts to obtain a global lock and returns a boolean indicating success.

        Args:
            source (str): A string identifying the source of the lock request.

        Returns:
            bool: True if the lock was successfully obtained, False otherwise.
        """
        ret = self.lock.acquire(source=source)  # will return false if lock is already held
        if ret:
            print((("Global lock taken by %s") % source))
            self.lockTakenBy = source
        else:
            print((("Failed to get global lock, it is currently held by %s") % source))
        return ret
        # need to release it later:
        # self.lock.release()


    def quit(self, widget, data=None):
        """
        Function to quit the application.

        Args:
            widget: The widget that was activated to trigger the quit.
            data: Optional data that might be associated with the widget.

        Returns:
            None
        """
        # TODO: can we get some / all of the stuff done in this function to execute on any kind of abort?

        # Check if the application is already quitting
        if not self.quitting:
            self.quitting = True  # Set the quitting flag
            print("Quitting normally")

        # TODO: can we get some / all of the stuff done in this function to execute on any kind of abort?
        # The following code could be called on any kind of abort:
        # 1. Handle any unsaved changes
        # 2. Close any open files
        # 3. Save the current user preferences
        # 4. Save the current state of any running processes or threads

        # TODO: check if current settings differ from profile, if so offer to save or abort

        # Handle database disconnection
        if self.db is not None:
            if self.db.backend == self.db.MYSQL_INNODB:
                try:
                    import _mysql_exceptions
                    if self.db is not None and self.db.is_connected():
                        self.db.disconnect()
                except _mysql_exceptions.OperationalError:  # oh, damn, we're already disconnected
                    pass
            else:
                if self.db is not None and self.db.is_connected():
                    self.db.disconnect()
        else:
            pass

        # Quit the application
        QCoreApplication.quit()




    def release_global_lock(self):
        """Release the global lock and reset the owner field."""
        # Release the lock
        self.lock.release()
        # Reset the owner to None
        self.lockTakenBy = None
        # Print a message to indicate that the lock has been released
        print("Global lock released.")


    def tab_auto_import(self, widget, data=None):
        """
        Opens the auto import tab.
        Args:
            widget: The widget that triggered the function.
            data: Additional data passed to the function.
        """
        # Create a new GuiAutoImport thread with the necessary arguments.
        new_aimp_thread = GuiAutoImport.GuiAutoImport(self.settings, self.config, self.sql, self)

        # Add the new thread to the list of threads.
        self.threads.append(new_aimp_thread)

        # Add and display the new thread as a tab with the label "HUD".
        self.add_and_display_tab(new_aimp_thread, ("HUD"))

        # Check if the autoimport option is set and start the thread if it is.
        if options.autoimport:
            new_aimp_thread.startClicked(new_aimp_thread.startButton, "autostart")
            options.autoimport = False


    def tab_bulk_import(self, widget, data=None):
        """
        Opens a tab for bulk importing.

        Args:
            widget: The widget that triggered the function.
            data: Optional data passed to the function.
        """
        # Create a new GuiBulkImport thread with the necessary parameters.
        new_import_thread = GuiBulkImport.GuiBulkImport(self.settings, self.config, self.sql, self)

        # Add the new thread to the list of threads.
        self.threads.append(new_import_thread)

        # Add and display the new tab.
        self.add_and_display_tab(new_import_thread, ("Bulk Import"))


    def tab_database(self, widget, data=None):
        """
        Opens a tab for database.

        Args:
            widget: Widget to open the tab in.
            data: Optional data to pass to the function.
        """
        # Create a new instance of GuiDatabase using the config, sql, and self objects.
        new_import_thread = GuiDatabase.GuiDatabase(self.config, self.sql, self)
        # Append the new_import_thread to the threads list.
        self.threads.append(new_import_thread)
        # Add and display the new_import_thread in the widget as a tab labeled "Database".
        self.add_and_display_tab(new_import_thread, ("Database"))


    def tab_odds_calc(self, widget, data=None):
        """
        Opens a tab for bulk importing.

        Args:
            widget: The widget object.
            data: The data object.

        Returns:
            None.
        """
        # Create a new import thread.
        new_import_thread = GuiOddsCalc.GuiOddsCalc(self)

        # Append the new thread to the list of threads.
        self.threads.append(new_import_thread)

        # Add and display the new thread as a tab.
        self.add_and_display_tab(new_import_thread, ("Odds Calc"))


    def tab_tourney_import(self, widget, data=None):
        """
        Opens a tab for bulk importing tournament summaries.

        Args:
            widget: The widget that triggered the function.
            data: Additional data to be passed to the function (default None).
        """
        # Create a new import thread
        new_import_thread = GuiTourneyImport.GuiTourneyImport(self.settings, self.config, self.sql, self.window)
        # Add the new thread to the threads list
        self.threads.append(new_import_thread)
        # Get the VBox for the new thread
        bulk_tab=new_import_thread.get_vbox()
        # Add and display the bulk tab with the given title
        self.add_and_display_tab(bulk_tab, "Tournament Results Import")


    def tab_ring_player_stats(self, widget, data=None):
        """
        Create a new thread to display ring player statistics and add that thread as a tab to the main GUI.

        :param widget: The widget that triggered the function.
        :param data: Any additional data associated with the widget.
        """
        # Create a new instance of the GuiRingPlayerStats class
        new_ps_thread = GuiRingPlayerStats.GuiRingPlayerStats(self.config, self.sql, self)
        # Add the new thread to the list of threads
        self.threads.append(new_ps_thread)
        # Add the new thread as a tab to the main GUI
        self.add_and_display_tab(new_ps_thread, ("Ring Player Stats"))


    def tab_tourney_player_stats(self, widget, data=None):
        """
        This function creates a new GuiTourneyPlayerStats thread and appends it to the list of threads. 
        It also adds the thread as a tab with the label "Tourney Stats".

        :param widget: The widget that triggered this function.
        :param data: Additional data passed to the function (default None).
        """
        # Create a new GuiTourneyPlayerStats thread
        new_ps_thread = GuiTourneyPlayerStats.GuiTourneyPlayerStats(self.config, self.db, self.sql, self)

        # Append the new thread to the list of threads
        self.threads.append(new_ps_thread)

        # Add the thread as a tab with the label "Tourney Stats"
        self.add_and_display_tab(new_ps_thread, ("Tourney Stats"))


    def tab_tourney_viewer_stats(self, widget, data=None):
        """
        Opens a new tab with a tournament viewer GUI.

        Args:
            widget: The widget that triggered this method.
            data: Optional data to pass to the method.
        """
        # Create a new instance of the GuiTourneyViewer class.
        new_thread = GuiTourneyViewer.GuiTourneyViewer(self.config, self.db, self.sql, self)

        # Add the new thread to the list of threads.
        self.threads.append(new_thread)

        # Add and display the new tab.
        self.add_and_display_tab(new_thread, ("Tourney Viewer"))


    def tab_positional_stats(self, widget, data=None):
        """
        This method creates a new tab containing positional statistics for the GUI.

        Args:
            widget: The widget associated with the new tab.
            data: Optional data to pass to the method.

        Returns:
            None
        """
        # Create a new GuiPositionalStats thread and append it to the threads list.
        new_ps_thread = GuiPositionalStats.GuiPositionalStats(self.config, self.sql)
        self.threads.append(new_ps_thread)

        # Get the vbox associated with the new thread.
        ps_tab = new_ps_thread.get_vbox()

        # Add the new tab to the GUI and display it.
        self.add_and_display_tab(ps_tab, ("Positional Stats"))

    def tab_session_stats(self, widget, data=None):
        """
        Adds a new tab to the GUI session viewer for session statistics.

        Args:
            widget: The widget for the tab.
            data: Optional data for the tab.

        Returns:
            None
        """
        # Create a new instance of the GUI session viewer
        new_ps_thread = GuiSessionViewer.GuiSessionViewer(self.config, self.sql, self, self)
        # Add the new instance to the threads list
        self.threads.append(new_ps_thread)
        # Add the new instance to the GUI and display the tab
        self.add_and_display_tab(new_ps_thread, ("Session Stats"))


    def tab_hand_viewer(self, widget, data=None):
        """
        Add a new tab for hand viewer to the GUI.

        Args:
            widget: The widget to add the tab to.
            data: Optional data to pass to the function.

        Returns:
            None
        """
        # Create a new GuiHandViewer thread
        new_ps_thread = GuiHandViewer.GuiHandViewer(self.config, self.sql, self)

        # Add the thread to the list of threads
        self.threads.append(new_ps_thread)

        # Add and display the tab for the new thread
        self.add_and_display_tab(new_ps_thread, ("Hand Viewer"))


    def tab_main_help(self, widget, data=None):
        """Displays a tab with the main fpdb help screen.

        Args:
            widget: The widget that will contain the help tab.
            data: Optional data to be passed to the function.

        Returns:
            None.
        """
        # Help text to be displayed in the tab
        help_text = """Welcome to Fpdb!

        This program is currently in an alpha-state, so our database format is still sometimes changed.
        You should therefore always keep your hand history files so that you can re-import after an update, if necessary.

        all configuration now happens in HUD_config.xml.

        This program is free/libre open source software licensed partially under the AGPL3, and partially under GPL2 or later.
        The Windows installer package includes code licensed under the MIT license.
        You can find the full license texts in agpl-3.0.txt, gpl-2.0.txt, gpl-3.0.txt and mit.txt in the fpdb installation directory."""

        # Create a QLabel containing the help text
        mh_tab = QLabel(help_text)

        # Add the tab to the widget and display it
        self.add_and_display_tab(mh_tab, "Help")


    def tabGraphViewer(self, widget, data=None):
        """
        Opens a graph viewer tab.

        Args:
            widget: The widget to use for the new tab.
            data: Optional data to pass to the new graph viewer.

        Returns:
            None.
        """
        # Create a new GuiGraphViewer thread with the given SQL, config, and parent.
        new_gv_thread = GuiGraphViewer.GuiGraphViewer(self.sql, self.config, self)

        # Add the new thread to the list of threads.
        self.threads.append(new_gv_thread)

        # Add the new thread's tab to the display.
        self.add_and_display_tab(new_gv_thread, ("Graphs"))


    def tabTourneyGraphViewer(self, widget, data=None):
        """
        Open a graph viewer tab.

        Args:
            widget: The widget to add the tab to.
            data: Optional data to pass to the function.

        Returns:
            None
        """
        # Create a new instance of GuiTourneyGraphViewer
        new_gv_thread = GuiTourneyGraphViewer.GuiTourneyGraphViewer(self.sql, self.config, self)
        # Add the new instance to the threads list
        self.threads.append(new_gv_thread)
        # Add and display the new instance as a tab
        self.add_and_display_tab(new_gv_thread, ("Tourney Graphs"))


    def tabStove(self, widget, data=None):
        """Opens a tab for Poker Stove.

        Args:
            widget: The widget object.
            data: Additional data for the function (default None).

        Returns:
            None
        """
        # Create a new thread for the GUI stove
        thread = GuiStove.GuiStove(self.config, self)
        # Add the thread to the list of threads
        self.threads.append(thread)
        # Add and display the tab
        self.add_and_display_tab(thread, ("Stove"))





    def info_box(self, str1, str2):
        """
        This function creates an information box with a title and message.

        Args:
            self: The object instance.
            str1 (str): The title of the information box.
            str2 (str): The message to display in the information box.

        Returns:
            int: The result of the information box execution.
        """
        # Create a QMessageBox object instance
        diapath = QMessageBox(self)
        # Set the title of the information box
        diapath.setWindowTitle(str1)
        # Set the message to display in the information box
        diapath.setText(str2)
        # Execute the information box and return the result
        return diapath.exec_()


    def warning_box(self, string, diatitle=("FPDB WARNING")):
        """
        Create a QMessageBox instance with a warning icon and given title and text.

        Parameters:
        -----------
        string : str
            The text to display in the message box.
        diatitle : str, optional
            The title of the message box. Default is "FPDB WARNING".

        Returns:
        --------
        int
            The result of calling `QMessageBox.exec_()`.
        """
        # Create a QMessageBox instance with a warning icon, the given title, and text
        msg_box = QMessageBox(QMessageBox.Warning, diatitle, string)
        # Execute the message box and return the result
        return msg_box.exec_()


    def validate_config(self):
        """
        Validates the configuration by checking if sites in the config file are in the database.
        If a site is missing from the database, a warning message is displayed.

        Args:
            self (object): The object instance.

        Returns:
            None.
        """
        # Check if sites in config file are in the database
        for site in self.config.supported_sites:
            try:
                self.config.get_site_id(site)
            except KeyError as exc:
                # Log a warning message if the site is missing from the database
                log.warning("Site %s missing from database" % site)

                # Create a QMessageBox instance with a warning icon, the given title, and text
                msg_box = QMessageBox(QMessageBox.Warning, "Unknown Site", "Warning: Unable to find site '%s'" % site)

                # Execute the message box and destroy it when closed
                msg_box.exec_()






if __name__ == "__main__":
    app = QApplication([])
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))
    me = fpdb()
    app.exec_()
