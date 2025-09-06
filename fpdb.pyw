#!/usr/bin/env python

# Copyright 2008-2013 Steffen Schaumburg
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

import codecs
import contextlib
import cProfile
import io
import os
import pstats
import queue
import sqlite3
import sys
from functools import partial

import numpy as np
from PyQt5.QtCore import QCoreApplication, QDate, QPoint, Qt
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import Card
import Configuration
import Database
import Exceptions
import GuiAutoImport
import GuiBulkImport
import GuiGraphViewer
import GuiHandViewer
import GuiLogView
import GuiPrefs
import GuiRingPlayerStats
import GuiSessionViewer
import GuiTourHandViewer
import GuiTourneyGraphViewer
import GuiTourneyPlayerStats
import interlocks
import ModernHudPreferences
import Options
import SQL
from ConfigInitializer import ensure_config_initialized
from ConfigurationManager import ConfigurationManager
from Exceptions import FpdbError
from GuiConfigObserver import GuiConfigObserver
from L10n import set_locale_translation
from loggingFpdb import get_logger, setup_logging

# Early configuration initialization (fix issue #22)
ensure_config_initialized()

# import GuiTourneyImport


# import GuiOddsCalc
# import GuiStove


cl_options = ".".join(sys.argv[1:])
(options, argv) = Options.fpdb_options()


numpy_version = np.__version__


sqlite3_version = sqlite3.version
sqlite_version = sqlite3.sqlite_version


PROFILE_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "fpdb_profiles")
os.makedirs(PROFILE_OUTPUT_DIR, exist_ok=True)

profiler = cProfile.Profile()
profiler.enable()


# Set up initial console logging to capture early logs
setup_logging(console_only=True)

# Obtain the logger
log = get_logger("fpdb")
# Note: Logger level is now controlled by Logger Dev Tool configuration
# The get_logger() function automatically applies the correct level from saved configuration

try:
    assert not hasattr(sys, "frozen")  # We're surely not in a git repo if this fails
    import subprocess

    VERSION = subprocess.Popen(["git", "describe", "--tags", "--dirty"], stdout=subprocess.PIPE).communicate()[0]
    VERSION = VERSION[:-1]
except Exception:
    VERSION = "3.0.0alpha"


class fpdb(QMainWindow):
    # def launch_ppt(self):
    #     path = os.getcwd()
    #     if os.name == "nt":
    #         pathcomp = f"{path}\pyfpdb\ppt\p2.jar"
    #     else:
    #         pathcomp = f"{path}/ppt/p2.jar"
    #     subprocess.call(["java", "-jar", pathcomp])

    def add_and_display_tab(self, new_page, new_tab_name) -> None:
        """Adds a tab, namely creates the button and displays it and appends all the relevant arrays."""
        for name in self.nb_tab_names:  # TODO: check this is valid
            if name == new_tab_name:
                self.display_tab(new_tab_name)
                return  # if tab already exists, just go to it

        used_before = False
        for i, name in enumerate(self.nb_tab_names):
            if name == new_tab_name:
                used_before = True
                page = self.pages[i]
                break

        if not used_before:
            page = new_page
            self.pages.append(new_page)
            self.nb_tab_names.append(new_tab_name)

        index = self.nb.addTab(page, new_tab_name)
        self.nb.setCurrentIndex(index)

    def display_tab(self, new_tab_name) -> None:
        """Displays the indicated tab."""
        tab_no = -1
        for i, name in enumerate(self.nb_tab_names):
            if new_tab_name == name:
                tab_no = i
                break

        if tab_no < 0 or tab_no >= self.nb.count():
            msg = f"invalid tab_no {tab_no!s}"
            raise FpdbError(msg)
        self.nb.setCurrentIndex(tab_no)

    def dia_about(self, widget, data=None) -> None:
        QMessageBox.about(
            self,
            f"FPDB{VERSION!s}",
            "Copyright 2008-2023. See contributors.txt for details"
            "You are free to change, and distribute original or changed versions "
            "of fpdb within the rules set out by the license"
            "https://github.com/jejellyroll-fr/fpdb-3"
            "\n"
            "Your config file is: " + self.config.file,
        )

    def dia_advanced_preferences(self, widget, data=None) -> None:
        # force reload of prefs from xml file - needed because HUD could
        # have changed file contents
        self.load_profile()
        if GuiPrefs.GuiPrefs(self.config, self).exec_():
            # save updated config
            # Detect changes before saving
            config_manager = ConfigurationManager()
            if config_manager.initialized:
                pending_changes = config_manager.check_pending_changes(self.config)
                config_manager._pending_changes = pending_changes

            self.config.save()
            self.reload_config()

    def dia_database_stats(self, widget, data=None) -> None:
        self.warning_box(
            string=f"Number of Hands: {self.db.getHandCount()}\nNumber of Tourneys: {self.db.getTourneyCount()}\nNumber of TourneyTypes: {self.db.getTourneyTypeCount()}",
            diatitle="Database Statistics",
        )

    # end def dia_database_stats

    @staticmethod
    def get_text(widget: QWidget):
        """Return text of widget, depending on widget type."""
        return widget.currentText() if isinstance(widget, QComboBox) else widget.text()

    def dia_hud_preferences(self, widget, data=None) -> None:
        """Open modern HUD preferences dialog."""
        # force reload of prefs from xml file - needed because HUD could
        # have changed file contents
        self.load_profile()

        dia = ModernHudPreferences.ModernHudPreferences(self.config, self)
        if dia.exec_():
            # Detect changes before saving
            config_manager = ConfigurationManager()
            if config_manager.initialized:
                pending_changes = config_manager.check_pending_changes(self.config)
                config_manager._pending_changes = pending_changes

            self.config.save()
            self.reload_config()

    def dia_manage_hud_sites(self, widget, data=None) -> None:
        """Dialog to manage HUD sites - enable/disable sites."""
        dia = QDialog(self)
        dia.setWindowTitle("Manage HUD Sites")
        dia.resize(800, 600)
        dia.setLayout(QVBoxLayout())

        # Header
        header_label = QLabel("Enable or disable sites for HUD display")
        header_label.setProperty("class", "h2")
        dia.layout().addWidget(header_label)

        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.site_search = QLineEdit()
        self.site_search.setPlaceholderText("Type to filter sites...")
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.site_search)
        dia.layout().addLayout(search_layout)

        # Create scrollable area for sites
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        dia.layout().addWidget(scroll_area)

        # Load current configuration
        self.load_profile()

        # Get all sites from site_ids
        site_checkboxes = {}
        site_widgets = []

        for site_name, site_id in self.config.site_ids.items():
            # Create a widget for each site
            site_widget = QWidget()
            site_layout = QHBoxLayout(site_widget)
            site_layout.setContentsMargins(5, 5, 5, 5)

            # Checkbox
            checkbox = QCheckBox()
            # Check if site is enabled in supported_sites
            try:
                checkbox.setChecked(self.config.supported_sites[site_name].enabled)
            except KeyError:
                checkbox.setChecked(False)

            site_layout.addWidget(checkbox)

            # Site name
            name_label = QLabel(site_name)
            name_label.setMinimumWidth(300)
            site_layout.addWidget(name_label)

            # Site ID
            id_label = QLabel(f"ID: {site_id}")
            id_label.setProperty("class", "badge")
            site_layout.addWidget(id_label)

            site_layout.addStretch()

            scroll_layout.addWidget(site_widget)
            site_checkboxes[site_name] = checkbox
            site_widgets.append((site_widget, site_name))

        # Connect search functionality
        def filter_sites() -> None:
            search_text = self.site_search.text().lower()
            for widget, name in site_widgets:
                widget.setVisible(search_text in name.lower())

        self.site_search.textChanged.connect(filter_sites)

        # Statistics label
        self.stats_label = QLabel()
        self.update_site_stats(site_checkboxes)
        dia.layout().addWidget(self.stats_label)

        # Connect checkboxes to update stats
        for checkbox in site_checkboxes.values():
            checkbox.stateChanged.connect(lambda: self.update_site_stats(site_checkboxes))

        # Buttons
        button_layout = QHBoxLayout()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self.set_all_sites(site_checkboxes, True))
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(lambda: self.set_all_sites(site_checkboxes, False))
        button_layout.addWidget(deselect_all_btn)

        button_layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_layout.addWidget(btns)

        dia.layout().addLayout(button_layout)

        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)

        # Show dialog and save if accepted
        if dia.exec_():
            # Save the enabled/disabled state for each site
            for site_name, checkbox in site_checkboxes.items():
                enabled = checkbox.isChecked()
                enabled_str = "True" if enabled else "False"

                # Check if site exists in supported_sites
                if site_name in self.config.supported_sites:
                    # Use the edit_site method to properly update the XML
                    current_site = self.config.supported_sites[site_name]
                    self.config.edit_site(
                        site_name,
                        enabled_str,
                        current_site.screen_name,
                        current_site.HH_path,
                        current_site.TS_path,
                    )
                else:
                    # Create a new site entry if it doesn't exist
                    # First, check if there's a site node in the XML
                    site_node = self.config.get_site_node(site_name)
                    if site_node is None:
                        # Create a new site node
                        sites_nodes = self.config.doc.getElementsByTagName("supported_sites")
                        if sites_nodes:
                            sites_node = sites_nodes[0]
                        else:
                            # Create supported_sites node if it doesn't exist
                            root = self.config.doc.getElementsByTagName("FreePokerToolsConfig")[0]
                            sites_node = self.config.doc.createElement("supported_sites")
                            root.appendChild(sites_node)

                        new_site = self.config.doc.createElement("site")
                        new_site.setAttribute("site_name", site_name)
                        new_site.setAttribute("enabled", enabled_str)
                        new_site.setAttribute("screen_name", "YOUR SCREEN NAME HERE")
                        new_site.setAttribute("HH_path", "")
                        new_site.setAttribute("TS_path", "")
                        new_site.setAttribute("aux_enabled", "True")
                        sites_node.appendChild(new_site)
                    else:
                        # Site node exists but not in supported_sites dict, just update enabled
                        site_node.setAttribute("enabled", enabled_str)

            # Save configuration
            # Detect changes before saving
            config_manager = ConfigurationManager()
            if config_manager.initialized:
                pending_changes = config_manager.check_pending_changes(self.config)
                config_manager._pending_changes = pending_changes

            self.config.save()
            self.reload_config()

    def update_site_stats(self, checkboxes) -> None:
        """Update the statistics label."""
        total = len(checkboxes)
        enabled = sum(1 for cb in checkboxes.values() if cb.isChecked())
        self.stats_label.setText(f"Enabled sites: {enabled} / {total}")
        # Use a class for styling instead of hard-coded CSS
        self.stats_label.setProperty("class", "info-box")

    def set_all_sites(self, checkboxes, state) -> None:
        """Set all site checkboxes to the given state."""
        for checkbox in checkboxes.values():
            checkbox.setChecked(state)

    def dia_import_filters(self, checkState) -> None:
        dia = QDialog()
        dia.setWindowTitle("Skip these games when importing")
        dia.setLayout(QVBoxLayout())
        checkboxes = {}
        filters = self.config.get_import_parameters()["importFilters"]
        for game in Card.games:
            checkboxes[game] = QCheckBox(game)
            dia.layout().addWidget(checkboxes[game])
            if game in filters:
                checkboxes[game].setChecked(True)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dia.layout().addWidget(btns)
        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)
        if dia.exec_():
            filterGames = []
            for game, cb in list(checkboxes.items()):
                if cb.isChecked():
                    filterGames.append(game)
            self.config.editImportFilters(",".join(filterGames))
            self.config.save()

    def dia_dump_db(self, widget, data=None) -> None:
        filename = "database-dump.sql"
        result = self.db.dumpDatabase()

        with open(filename, "w") as dumpFile:
            dumpFile.write(result)

    # end def dia_database_stats

    def dia_recreate_tables(self, widget, data=None) -> None:
        """Dialogue that asks user to confirm that he wants to delete and recreate the tables."""
        if self.obtain_global_lock("fpdb.dia_recreate_tables"):  # returns true if successful
            dia_confirm = QMessageBox(
                QMessageBox.Warning,
                "Wipe DB",
                "Confirm deleting and recreating tables",
                QMessageBox.Yes | QMessageBox.No,
                self,
            )
            diastring = (
                f"Please confirm that you want to (re-)create the tables. If there already are tables in"
                f" the database {self.db.database} on {self.db.host}"
                f" they will be deleted and you will have to re-import your histories.\nThis may take a while."
            )

            dia_confirm.setInformativeText(diastring)  # TODO: make above string with bold for db, host and deleted
            response = dia_confirm.exec_()

            if response == QMessageBox.Yes:
                self.db.recreate_tables()
                # find any guibulkimport/guiautoimport windows and clear cache:
                for t in self.threads:
                    if isinstance(t, GuiBulkImport.GuiBulkImport | GuiAutoImport.GuiAutoImport):
                        t.importer.database.resetCache()
                self.release_global_lock()
            else:
                self.release_global_lock()
                log.info("User cancelled recreating tables")
        else:
            self.warning_box(
                "Cannot open Database Maintenance window because other"
                " windows have been opened. Re-start fpdb to use this option.",
            )

    def dia_recreate_hudcache(self, widget, data=None) -> None:
        if self.obtain_global_lock("dia_recreate_hudcache"):
            self.dia_confirm = QDialog()
            self.dia_confirm.setWindowTitle("Confirm recreating HUD cache")
            self.dia_confirm.setLayout(QVBoxLayout())
            self.dia_confirm.layout().addWidget(QLabel("Please confirm that you want to re-create the HUD cache."))

            hb1 = QHBoxLayout()
            self.h_start_date = QDateEdit(QDate.fromString(self.db.get_hero_hudcache_start(), "yyyy-MM-dd"))
            lbl = QLabel(" Hero's cache starts: ")
            btn = QPushButton("Cal")
            btn.clicked.connect(partial(self.__calendar_dialog, entry=self.h_start_date))

            hb1.addWidget(lbl)
            hb1.addStretch()
            hb1.addWidget(self.h_start_date)
            hb1.addWidget(btn)
            self.dia_confirm.layout().addLayout(hb1)

            hb2 = QHBoxLayout()
            self.start_date = QDateEdit(QDate.fromString(self.db.get_hero_hudcache_start(), "yyyy-MM-dd"))
            lbl = QLabel(" Villains' cache starts: ")
            btn = QPushButton("Cal")
            btn.clicked.connect(partial(self.__calendar_dialog, entry=self.start_date))

            hb2.addWidget(lbl)
            hb2.addStretch()
            hb2.addWidget(self.start_date)
            hb2.addWidget(btn)
            self.dia_confirm.layout().addLayout(hb2)

            btns = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
            self.dia_confirm.layout().addWidget(btns)
            btns.accepted.connect(self.dia_confirm.accept)
            btns.rejected.connect(self.dia_confirm.reject)

            response = self.dia_confirm.exec_()
            if response:
                log.info("Rebuilding HUD Cache ...")

                self.db.rebuild_cache(
                    self.h_start_date.date().toString("yyyy-MM-dd"),
                    self.start_date.date().toString("yyyy-MM-dd"),
                )
            else:
                log.info("User cancelled rebuilding hud cache")

            self.release_global_lock()
        else:
            self.warning_box(
                "Cannot open Database Maintenance window because other windows have been opened. "
                "Re-start fpdb to use this option.",
            )

    def dia_rebuild_indexes(self, widget, data=None) -> None:
        if self.obtain_global_lock("dia_rebuild_indexes"):
            self.dia_confirm = QMessageBox(
                QMessageBox.Warning,
                "Rebuild DB",
                "Confirm rebuilding database indexes",
                QMessageBox.Yes | QMessageBox.No,
                self,
            )
            diastring = "Please confirm that you want to rebuild the database indexes."
            self.dia_confirm.setInformativeText(diastring)

            response = self.dia_confirm.exec_()
            if response == QMessageBox.Yes:
                log.info(" Rebuilding Indexes ... ")
                self.db.rebuild_indexes()

                log.info(" Cleaning Database ... ")
                self.db.vacuumDB()

                log.info(" Analyzing Database ... ")
                self.db.analyzeDB()
            else:
                log.info("User cancelled rebuilding db indexes")

            self.release_global_lock()
        else:
            self.warning_box(
                "Cannot open Database Maintenance window because"
                " other windows have been opened. Re-start fpdb to use this option.",
            )

    def dia_logs(self, widget, data=None) -> None:
        """Opens the log viewer window."""
        # remove members from self.threads if close messages received
        self.process_close_messages()

        viewer = None
        for _i, t in enumerate(self.threads):
            if str(t.__class__) == "GuiLogView.GuiLogView":
                viewer = t
                break

        if viewer is None:
            # print "creating new log viewer"
            new_thread = GuiLogView.GuiLogView(self.config, self.window, self.closeq)
            self.threads.append(new_thread)
        else:
            # print "showing existing log viewer"
            viewer.get_dialog().present()

        # if lock_set:
        #    self.release_global_lock()

    def dia_site_preferences_seat(self, widget, data=None) -> None:
        """Open modern seat preferences dialog."""
        from ModernSeatPreferences import ModernSeatPreferencesDialog

        # Create and display modern dialog
        dia = ModernSeatPreferencesDialog(self.config, self)

        # Dialog handles saving and reloading itself
        dia.exec_()

    def dia_site_preferences(self, widget, data=None) -> None:
        """Open modern site preferences dialog."""
        from ModernSitePreferences import ModernSitePreferencesDialog

        # No need to reload profile, use existing config
        # self.load_profile()  # Commented to avoid re-reading XML

        # Create and display modern dialog
        dia = ModernSitePreferencesDialog(self.config, self)

        if dia.exec_():
            # Get changes
            changes = dia.get_changes()

            # Apply changes
            for site_name, values in changes.items():
                if site_name in self.config.supported_sites:
                    self.config.edit_site(
                        site_name,
                        str(values["enabled"]),
                        values["screen_name"],
                        values["hh_path"],
                        values["ts_path"],
                    )

            # Detect changes before saving
            config_manager = ConfigurationManager()
            if config_manager.initialized:
                pending_changes = config_manager.check_pending_changes(self.config)
                config_manager._pending_changes = pending_changes

            self.config.save()
            self.reload_config()

    # The following methods are now managed by ModernSitePreferences
    # but are kept for compatibility with other part of code

    def autoenableSite(self, text, checkbox) -> None:
        # autoactivate site if something gets typed in the screename field
        checkbox.setChecked(True)

    def reload_hud_displays(self) -> None:
        """Reloads all active HUD displays."""
        log.info("Reloading all active HUD displays...")
        reloaded_huds = 0
        for thread in self.threads:
            if isinstance(thread, GuiAutoImport.GuiAutoImport):
                try:
                    thread.reload_hud_config()
                    reloaded_huds += 1
                except Exception as e:
                    log.error(f"Error reloading HUD in thread {thread}: {e}", exc_info=True)

        if reloaded_huds > 0:
            log.info(f"Successfully reloaded {reloaded_huds} HUD displays.")
            self.statusBar().showMessage(f"{reloaded_huds} HUD displays reloaded", 3000)
        else:
            log.info("No active HUD displays found to reload.")

    def reload_config(self) -> None:
        """Reloads the configuration with dynamic reload support."""
        if len(self.nb_tab_names) == 1:
            # Try dynamic reloading via ConfigurationManager
            config_manager = ConfigurationManager()

            # Initialize ConfigurationManager if not already done
            if not config_manager.initialized:
                config_manager.initialize(self.config.file)

            success, message, restart_changes = config_manager.reload_config()

            if success and not restart_changes:
                # Dynamic reload successful without changes requiring restart
                # IMPORTANT: Update self.config to point to the config of ConfigurationManager
                self.config = config_manager.get_config()

                # Also update references in existing tabs
                for thread in self.threads:
                    if hasattr(thread, "config"):
                        thread.config = self.config

                if "No changes detected" in message:
                    self.info_box("Configuration", message)
                else:
                    self.info_box("Configuration updated", message)
                log.info(f"Configuration reloaded: {message}")
            elif success and restart_changes:
                # Some changes require restart
                changes_text = "\n".join([f"- {c.path}: {c.old_value} → {c.new_value}" for c in restart_changes[:5]])
                if len(restart_changes) > 5:
                    changes_text += f"\n... and {len(restart_changes) - 5} other changes"

                self.warning_box(
                    f"{message}\n\n"
                    "The following changes require a restart:\n"
                    f"{changes_text}\n\n"
                    "Fpdb must be restarted now.\n\nClick OK to close Fpdb.",
                )
                sys.exit()
            else:
                # Reload failed
                self.warning_box(
                    f"Error while reloading configuration:\n{message}\n\n"
                    "Fpdb must be restarted now.\n\nClick OK to close Fpdb.",
                )
                sys.exit()
        else:
            self.warning_box(
                "The updated preferences have not been loaded because windows are open. " "Restart fpdb to load them.",
            )

    def process_close_messages(self) -> None:
        # check for close messages
        try:
            while True:
                name = self.closeq.get(False)
                for i, t in enumerate(self.threads):
                    if str(t.__class__) == str(name):
                        # thread has ended so remove from list:
                        del self.threads[i]
                        break
        except queue.Empty:
            # no close messages on queue, do nothing
            pass

    def __calendar_dialog(self, widget, entry) -> None:
        d = QDialog(self.dia_confirm)
        d.setWindowTitle("Pick a date")

        vb = QVBoxLayout()
        d.setLayout(vb)
        cal = QCalendarWidget()
        vb.addWidget(cal)

        btn = QPushButton("Done")
        btn.clicked.connect(partial(self.__get_date, calendar=cal, entry=entry, win=d))

        vb.addWidget(btn)

        d.exec_()

    def createMenuBar(self) -> None:
        mb = self.menuBar()
        configMenu = mb.addMenu("Configure")
        importMenu = mb.addMenu("Import")
        hudMenu = mb.addMenu("HUD")
        cashMenu = mb.addMenu("Cash")
        tournamentMenu = mb.addMenu("Tournament")
        maintenanceMenu = mb.addMenu("Maintenance")
        # toolsMenu = mb.addMenu('Tools')
        helpMenu = mb.addMenu("Help")
        themeMenu = mb.addMenu("Themes")

        configMenu.addAction(self.makeAction("Site Settings", self.dia_site_preferences))
        configMenu.addAction(self.makeAction("Seat Settings", self.dia_site_preferences_seat))
        configMenu.addAction(self.makeAction("HUD Preferences", self.dia_hud_preferences))
        configMenu.addAction(self.makeAction("Manage HUD Sites", self.dia_manage_hud_sites))
        configMenu.addAction(
            self.makeAction("Adv Preferences", self.dia_advanced_preferences, tip="Edit your preferences"),
        )
        configMenu.addAction(self.makeAction("Import filters", self.dia_import_filters))
        # Add the Logger Dev Tool action
        self.logger_dev_tool_action = self.makeAction(
            "Logger Dev Tool", self.show_logger_dev_tool, tip="Advanced logger manager"
        )
        configMenu.addAction(self.logger_dev_tool_action)
        configMenu.addSeparator()
        configMenu.addAction(self.makeAction("Close Fpdb", self.quit, "Ctrl+Q", "Quit the Program"))

        importMenu.addAction(self.makeAction("Bulk Import", self.tab_bulk_import, "Ctrl+B"))
        hudMenu.addAction(self.makeAction("HUD and Auto Import", self.tab_auto_import, "Ctrl+A"))
        cashMenu.addAction(self.makeAction("Graphs", self.tabGraphViewer, "Ctrl+G"))
        cashMenu.addAction(self.makeAction("Ring Player Stats", self.tab_ring_player_stats, "Ctrl+P"))
        cashMenu.addAction(self.makeAction("Hand Viewer", self.tab_hand_viewer))
        cashMenu.addAction(self.makeAction("Session Stats", self.tab_session_stats, "Ctrl+S"))
        tournamentMenu.addAction(self.makeAction("Tourney Graphs", self.tabTourneyGraphViewer))
        tournamentMenu.addAction(self.makeAction("Tourney Stats", self.tab_tourney_player_stats, "Ctrl+T"))
        tournamentMenu.addAction(self.makeAction("Tourney Hand Viewer", self.tab_tourney_viewer_stats))
        maintenanceMenu.addAction(self.makeAction("Statistics", self.dia_database_stats, "View Database Statistics"))
        maintenanceMenu.addAction(self.makeAction("Create or Recreate Tables", self.dia_recreate_tables))
        maintenanceMenu.addAction(self.makeAction("Rebuild HUD Cache", self.dia_recreate_hudcache))
        maintenanceMenu.addAction(self.makeAction("Rebuild DB Indexes", self.dia_rebuild_indexes))
        maintenanceMenu.addAction(self.makeAction("Dump Database to Textfile (takes ALOT of time)", self.dia_dump_db))

        # toolsMenu.addAction(makeAction('PokerProTools', self.launch_ppt))
        helpMenu.addAction(self.makeAction("Log Messages", self.dia_logs, "Log and Debug Messages"))
        helpMenu.addAction(self.makeAction("Help Tab", self.tab_main_help))
        helpMenu.addSeparator()
        helpMenu.addAction(self.makeAction("Infos", self.dia_about, "About the program"))

        # Get available themes from ThemeManager
        try:
            from ThemeManager import ThemeManager

            theme_manager = ThemeManager()
            themes = theme_manager.get_available_qt_themes()
        except ImportError:
            # Fallback theme list if ThemeManager not available
            themes = [
                "dark_purple.xml",
                "dark_teal.xml",
                "dark_blue.xml",
                "dark_cyan.xml",
                "dark_pink.xml",
                "dark_red.xml",
                "light_purple.xml",
                "light_teal.xml",
                "light_blue.xml",
                "light_cyan.xml",
                "light_pink.xml",
                "light_red.xml",
            ]

        for theme in themes:
            themeMenu.addAction(QAction(theme, self, triggered=partial(self.change_theme, theme)))

        # Add separator and theme creation option
        themeMenu.addSeparator()
        themeMenu.addAction(
            self.makeAction("Create Custom Theme...", self.show_theme_creator, tip="Create a new custom theme")
        )

    def makeAction(self, name, callback, shortcut=None, tip=None, checkable=False):
        action = QAction(name, self)
        if shortcut:
            action.setShortcut(shortcut)
        if tip:
            action.setToolTip(tip)
        if checkable:
            action.setCheckable(True)
            action.toggled.connect(callback)
        else:
            action.triggered.connect(callback)
        return action

    def show_logger_dev_tool(self) -> None:
        """Open the advanced logger development tool."""
        try:
            from loggingFpdb import show_logger_dev_tool

            show_logger_dev_tool(self)
            self.statusBar().showMessage("Logger Dev Tool open")
        except Exception as e:
            log.exception(f"Error opening Logger Dev Tool: {e}")
            self.statusBar().showMessage(f"Error: {e}")

    def show_theme_creator(self) -> None:
        """Open the custom theme creator dialog."""
        try:
            from ThemeCreatorDialog import show_theme_creator

            result = show_theme_creator(self)
            if result:  # Dialog was accepted (theme created)
                # Refresh the themes menu to include the new theme
                self.refresh_themes_menu()
                self.statusBar().showMessage("Custom theme created successfully")
            else:
                self.statusBar().showMessage("Theme creation cancelled")
        except Exception as e:
            log.exception(f"Error opening Theme Creator: {e}")
            self.statusBar().showMessage(f"Error: {e}")

    def refresh_themes_menu(self) -> None:
        """Refresh the themes menu to include new custom themes."""
        try:
            # Find and clear the themes menu
            menu_bar = self.menuBar()
            themes_menu = None
            for action in menu_bar.actions():
                if action.text() == "Themes":
                    themes_menu = action.menu()
                    break

            if themes_menu:
                themes_menu.clear()

                # Get updated theme list from ThemeManager
                from ThemeManager import ThemeManager

                theme_manager = ThemeManager()
                themes = theme_manager.get_available_qt_themes()

                # Re-add all themes
                for theme in themes:
                    themes_menu.addAction(QAction(theme, self, triggered=partial(self.change_theme, theme)))

                # Re-add separator and theme creator
                themes_menu.addSeparator()
                themes_menu.addAction(
                    self.makeAction("Create Custom Theme...", self.show_theme_creator, tip="Create a new custom theme")
                )

                log.info(f"Themes menu refreshed with {len(themes)} themes")
        except Exception as e:
            log.exception(f"Error refreshing themes menu: {e}")

    def load_profile(self, create_db=False) -> None:
        """Loads profile from the provided path name.
        Sets:
        - self.settings
        - self.config
        - self.db.
        """
        # Load the configuration
        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        if self.config.file_error:
            self.warning_box(
                f"There is an error in your config file {self.config.file}:\n{self.config.file_error!s}",
                diatitle="CONFIG FILE ERROR",
            )
            sys.exit()

        # Now reconfigure logging with the log directory from the configuration
        setup_logging(log_dir=self.config.dir_log)

        log.info(f"Logfile is {os.path.join(self.config.dir_log, 'fpdb-log.txt')}")
        log.info(f"load profiles {self.config.example_copy}")
        log.info(f"{self.display_config_created_dialogue}")
        log.info(f"{self.config.wrongConfigVersion}")

        if self.config.example_copy or self.display_config_created_dialogue:
            self.info_box(
                "Config file",
                [
                    "Config file has been created at " + self.config.file + ".",
                    "Enter your screen_name and hand history path in the Site Preferences window"
                    " (Main menu) before trying to import hands.",
                ],
            )
            self.display_config_created_dialogue = False
        elif self.config.wrongConfigVersion:
            diaConfigVersionWarning = QDialog()
            diaConfigVersionWarning.setWindowTitle("Strong Warning - Local configuration out of date")
            diaConfigVersionWarning.setLayout(QVBoxLayout())
            label = QLabel("\nYour local configuration file needs to be updated.")
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel(
                "\nYour local configuration file needs to be updated."
                " This error is not necessarily fatal but it is strongly recommended that you update the configuration.",
            )
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel(
                "To create a new configuration, see:"
                " fpdb.sourceforge.net/apps/mediawiki/fpdb/index.php?title=Reset_Configuration",
            )
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel(
                "A new configuration will destroy all personal settings"
                " (hud layout, site folders, screennames, favourite seats).\n",
            )
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel("To keep existing personal settings, you must edit the local file.")
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel("See the release note for information about the edits needed")
            diaConfigVersionWarning.layout().addWidget(label)
            btns = QDialogButtonBox(QDialogButtonBox.Ok)
            btns.accepted.connect(diaConfigVersionWarning.accept)
            diaConfigVersionWarning.layout().addWidget(btns)
            diaConfigVersionWarning.exec_()
            self.config.wrongConfigVersion = False

        # Set up application settings
        self.settings = {}
        self.settings["global_lock"] = self.lock
        if os.sep == "/":
            self.settings["os"] = "linuxmac"
        else:
            self.settings["os"] = "windows"

        self.settings.update({"cl_options": cl_options})
        self.settings.update(self.config.get_db_parameters())
        self.settings.update(self.config.get_import_parameters())
        self.settings.update(self.config.get_default_paths())

        # Disconnect from the database if already connected
        if self.db is not None and self.db.is_connected():
            self.db.disconnect()

        # Set up SQL and connect to the database
        self.sql = SQL.Sql(db_server=self.settings["db-server"])
        err_msg = None
        try:
            self.db = Database.Database(self.config, sql=self.sql)
            if self.db.get_backend_name() == "SQLite":
                # Inform SQLite users where the database file is located
                log.info(f"Connected to SQLite: {self.db.db_path}")
        except Exceptions.FpdbMySQLAccessDenied:
            err_msg = "MySQL Server reports: Access denied. Are your permissions set correctly?"
        except Exceptions.FpdbMySQLNoDatabase:
            err_msg = (
                "MySQL client reports: 2002 or 2003 error."
                " Unable to connect - Please check that the MySQL service has been started."
            )
        except Exceptions.FpdbPostgresqlAccessDenied:
            err_msg = "PostgreSQL Server reports: Access denied. Are your permissions set correctly?"
        except Exceptions.FpdbPostgresqlNoDatabase:
            err_msg = (
                "PostgreSQL client reports: Unable to connect - "
                "Please check that the PostgreSQL service has been started."
            )
        if err_msg is not None:
            self.db = None
            self.warning_box(err_msg)
        if self.db is not None and not self.db.is_connected():
            self.db = None

        # Check for database version issues
        if self.db is not None and self.db.wrongDbVersion:
            diaDbVersionWarning = QMessageBox(
                QMessageBox.Warning,
                "Strong Warning - Invalid database version",
                "An invalid DB version or missing tables have been detected.",
                QMessageBox.Ok,
                self,
            )
            diaDbVersionWarning.setInformativeText(
                "This error is not necessarily fatal but it is strongly"
                " recommended that you recreate the tables by using the Database menu."
                " Not doing this will likely lead to misbehavior including fpdb crashes, corrupt data, etc.",
            )
            diaDbVersionWarning.exec_()

        # Update the status bar with the database connection status
        if self.db is not None and self.db.is_connected():
            self.statusBar().showMessage(
                f"Status: Connected to {self.db.get_backend_name()}"
                f" database named {self.db.database} on host {self.db.host}",
            )
            # Rollback to make sure any locks are cleared
            self.db.rollback()

        # Validate the configuration if the database version is up-to-date
        if hasattr(self.db, "wrongDbVersion") and not self.db.wrongDbVersion:
            self.validate_config()

    def obtain_global_lock(self, source):
        ret = self.lock.acquire(source=source)  # will return false if lock is already held
        if ret:
            log.info(f"Global lock taken by {source}")
            self.lockTakenBy = source
        else:
            log.info(f"Failed to get global lock, it is currently held by {source}")
        return ret
        # need to release it later:
        # self.lock.release()

    def quit(self, widget, data=None) -> None:
        # TODO: can we get some / all of the stuff done in this function to execute on any kind of abort?
        # FIXME  get two "quitting normally" messages, following the addition of the self.window.destroy() call
        #       ... because self.window.destroy() leads to self.destroy() which calls this!
        if not self.quitting:
            log.info("Quitting normally")
            self.quitting = True
        # TODO: check if current settings differ from profile, if so offer to save or abort

        if self.db is not None:
            if self.db.backend == self.db.MYSQL_INNODB:
                try:
                    import _mysql_exceptions

                    if self.db is not None and self.db.is_connected():
                        self.db.disconnect()
                except _mysql_exceptions.OperationalError:  # oh, damn, we're already disconnected
                    pass
            elif self.db is not None and self.db.is_connected():
                self.db.disconnect()
        else:
            pass
        # self.statusIcon.set_visible(False)
        QCoreApplication.quit()

    def release_global_lock(self) -> None:
        self.lock.release()
        self.lockTakenBy = None
        log.info("Global lock released.")

    def tab_auto_import(self, widget, data=None) -> None:
        """Opens the auto import tab."""
        new_aimp_thread = GuiAutoImport.GuiAutoImport(self.settings, self.config, self.sql, self)
        self.threads.append(new_aimp_thread)
        self.add_and_display_tab(new_aimp_thread, "HUD")
        if options.autoimport:
            new_aimp_thread.startClicked(new_aimp_thread.startButton, "autostart")
            options.autoimport = False

    def tab_bulk_import(self, widget, data=None) -> None:
        """Opens a tab for bulk importing."""
        new_import_thread = GuiBulkImport.GuiBulkImport(self.settings, self.config, self.sql, self)
        self.threads.append(new_import_thread)
        self.add_and_display_tab(new_import_thread, "Bulk Import")

    # def tab_tourney_import(self, widget, data=None):
    #     """opens a tab for bulk importing tournament summaries"""
    #     new_import_thread = GuiTourneyImport.GuiTourneyImport(self.settings, self.config, self.sql, self.window)
    #     self.threads.append(new_import_thread)
    #     bulk_tab = new_import_thread.get_vbox()
    #     self.add_and_display_tab(bulk_tab, "Tournament Results Import")

    # end def tab_import_imap_summaries

    def tab_ring_player_stats(self, widget, data=None) -> None:
        new_ps_thread = GuiRingPlayerStats.GuiRingPlayerStats(self.config, self.sql, self)
        self.threads.append(new_ps_thread)
        self.add_and_display_tab(new_ps_thread, "Ring Player Stats")

    def tab_tourney_player_stats(self, widget, data=None) -> None:
        new_ps_thread = GuiTourneyPlayerStats.GuiTourneyPlayerStats(self.config, self.db, self.sql, self)
        self.threads.append(new_ps_thread)
        self.add_and_display_tab(new_ps_thread, "Tourney Stats")

    def tab_tourney_viewer_stats(self, widget, data=None) -> None:
        new_thread = GuiTourHandViewer.TourHandViewer(self.config, self.sql, self)
        self.threads.append(new_thread)
        self.add_and_display_tab(new_thread, "Tourney Viewer")

    # def tab_positional_stats(self, widget, data=None):
    #     new_ps_thread = GuiPositionalStats.GuiPositionalStats(self.config, self.sql)
    #     self.threads.append(new_ps_thread)
    #     ps_tab = new_ps_thread.get_vbox()
    #     self.add_and_display_tab(ps_tab, "Positional Stats")

    def tab_session_stats(self, widget, data=None) -> None:
        colors = self.get_theme_colors()
        new_ps_thread = GuiSessionViewer.GuiSessionViewer(self.config, self.sql, self, self, colors=colors)
        self.threads.append(new_ps_thread)
        self.add_and_display_tab(new_ps_thread, "Session Stats")

    def tab_hand_viewer(self, widget, data=None) -> None:
        new_ps_thread = GuiHandViewer.GuiHandViewer(self.config, self.sql, self)
        self.threads.append(new_ps_thread)
        self.add_and_display_tab(new_ps_thread, "Hand Viewer")

    def tab_main_help(self, widget, data=None) -> None:
        """Displays a tab with the main fpdb help screen."""
        mh_tab = QLabel(
            (
                """
                        Welcome to Fpdb!

                        This program is currently in an alpha-state, so our database format is still sometimes changed.
                        You should therefore always keep your hand history files so that you can re-import
                        after an update, if necessary.

                        all configuration now happens in HUD_config.xml.

                        This program is free/libre open source software licensed partially under the AGPL3,
                        and partially under GPL2 or later.
                        The Windows installer package includes code licensed under the MIT license.
                        You can find the full license texts in agpl-3.0.txt, gpl-2.0.txt, gpl-3.0.txt
                        and mit.txt in the fpdb installation directory."""
            ),
        )
        self.add_and_display_tab(mh_tab, "Help")

    def get_theme_colors(self):
        """Returns a dictionary containing the theme colors used in the application.

        The dictionary contains the following keys:
        - "background": the name of the color used for the background.
        - "foreground": the name of the color used for the foreground.
        - "grid": the name of the color used for the grid.
        - "line_showdown": the name of the color used for the showdown line.
        - "line_nonshowdown": the name of the color used for the non-showdown line.
        - "line_ev": the name of the color used for the event line.
        - "line_hands": the name of the color used for the hands line.

        Returns:
            dict: A dictionary containing the theme colors.

        """
        return {
            "background": self.palette().color(QPalette.Window).name(),
            "foreground": self.palette().color(QPalette.WindowText).name(),
            "grid": "#444444",  # to customize
            "line_up": "g",
            "line_down": "r",
            "line_showdown": "b",
            "line_nonshowdown": "m",
            "line_ev": "orange",
            "line_hands": "c",
        }

    def tabGraphViewer(self, widget, data=None) -> None:
        """Opens a graph viewer tab."""
        colors = self.get_theme_colors()
        new_gv_thread = GuiGraphViewer.GuiGraphViewer(self.sql, self.config, self, colors=colors)
        self.threads.append(new_gv_thread)
        self.add_and_display_tab(new_gv_thread, "Graphs")

    def tabTourneyGraphViewer(self, widget, data=None) -> None:
        """Opens a graph viewer tab."""
        colors = self.get_theme_colors()
        new_gv_thread = GuiTourneyGraphViewer.GuiTourneyGraphViewer(self.sql, self.config, self, colors=colors)
        self.threads.append(new_gv_thread)
        self.add_and_display_tab(new_gv_thread, "Tourney Graphs")

    # def tabStove(self, widget, data=None):
    #     """opens a tab for poker stove"""
    #     thread = GuiStove.GuiStove(self.config, self)
    #     self.threads.append(thread)
    #     # tab = thread.get_vbox()
    #     self.add_and_display_tab(thread, "Stove")

    def validate_config(self) -> None:
        # check if sites in config file are in DB
        for site in self.config.supported_sites:  # get site names from config file
            try:
                self.config.get_site_id(site)  # and check against list from db
            except KeyError:
                log.warning(f"site {site} missing from db")
                dia = QMessageBox()
                dia.setIcon(QMessageBox.Warning)
                dia.setWindowTitle("Unknown Site")
                dia.setText(f"Warning: Unable to find site '{site}' in database")
                dia.setInformativeText(
                    "This site is configured but not found in the database. You may need to recreate the database tables.",
                )
                dia.setStandardButtons(QMessageBox.Ok)
                dia.exec_()

    def info_box(self, str1, str2):
        diapath = QMessageBox(self)
        diapath.setWindowTitle(str1)
        diapath.setText(str2)
        return diapath.exec_()

    def warning_box(self, string, diatitle="FPDB WARNING"):
        return QMessageBox(QMessageBox.Warning, diatitle, string).exec_()

    def change_theme(self, theme) -> None:
        try:
            from ThemeManager import ThemeManager

            # Use ThemeManager to handle theme change and persistence
            theme_manager = ThemeManager()
            if theme_manager.initialized:
                # Use ThemeManager for persistent theme changes (apply_to_ui=False to avoid recursion)
                success = theme_manager.set_qt_material_theme(theme, save=True, apply_to_ui=False)
                if success:
                    # Let ThemeManager handle the application of the theme (built-in or custom)
                    theme_manager._apply_theme_to_application(theme)
                else:
                    log.warning(f"ThemeManager failed to set theme {theme}")
            else:
                # Fallback to direct application if ThemeManager not initialized
                log.warning("ThemeManager not initialized, applying theme directly without persistence")
                from qt_material import apply_stylesheet

                apply_stylesheet(QApplication.instance(), theme=theme)

            self.update_title_bar_theme()
        except ImportError:
            log.warning("qt_material not available, cannot change theme")
        except Exception as e:
            log.exception(f"Error changing theme: {e}")

    def update_title_bar_theme(self) -> None:
        # Apply the stylesheet to the custom title bar
        self.custom_title_bar.update_theme()

    def close_tab(self, index) -> None:
        item = self.nb.widget(index)
        self.nb.removeTab(index)
        self.nb_tab_names.pop(index)

        with contextlib.suppress(ValueError):
            self.threads.remove(item)

        item.deleteLater()

    def __init__(self) -> None:
        super().__init__()
        if sys.platform == "darwin":
            pass
        else:
            self.setWindowFlags(Qt.FramelessWindowHint)
        cards = os.path.join(Configuration.GRAPHICS_PATH, "tribal.jpg")
        if os.path.exists(cards):
            self.setWindowIcon(QIcon(cards))
        set_locale_translation()
        self.lock = interlocks.InterProcessLock(name="fpdb_global_lock")
        self.db = None
        self.status_bar = None
        self.quitting = False
        self.visible = False
        self.threads = []
        self.closeq = queue.Queue(20)

        self.oldPos = self.pos()

        # Initialize the debug_logging_action to None; it will be set in createMenuBar
        self.debug_logging_action = None

        # Logger level is now controlled by Logger Dev Tool configuration
        # No need to override the level here as get_logger() handles this automatically

        if options.initialRun:
            self.display_config_created_dialogue = True
            self.display_site_preferences = True
        else:
            self.display_config_created_dialogue = False
            self.display_site_preferences = False

        if options.xloc is not None or options.yloc is not None:
            if options.xloc is None:
                options.xloc = 0
            if options.yloc is None:
                options.yloc = 0
            self.move(options.xloc, options.yloc)

        self.setWindowTitle("Free Poker DB 3")
        defx, defy = 1920, 1080
        sg = QApplication.primaryScreen().availableGeometry()
        defx = min(sg.width(), defx)
        defy = min(sg.height(), defy)
        self.resize(defx, defy)

        if sys.platform == "darwin":
            pass
        else:
            # Create custom title bar
            self.custom_title_bar = CustomTitleBar(self)
        # Create central widget and layout
        self.central_widget = QWidget(self)
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        if sys.platform == "darwin":
            # Add title bar and menu bar to layout
            self.custom_title_bar = CustomTitleBar(self)
            self.central_layout.addWidget(self.custom_title_bar)
            self.setMenuBar(self.menuBar())
        else:
            # Add title bar and menu bar to layout
            self.central_layout.addWidget(self.custom_title_bar)
            self.menu_bar = self.menuBar()
            self.central_layout.setMenuBar(self.menu_bar)

        self.nb = QTabWidget()
        self.nb.setTabsClosable(True)
        self.nb.tabCloseRequested.connect(self.close_tab)
        self.central_layout.addWidget(self.nb)
        self.setCentralWidget(self.central_widget)

        self.createMenuBar()

        self.pages = []
        self.nb_tab_names = []

        self.tab_main_help(None, None)

        if options.minimized:
            self.showMinimized()
        if options.hidden:
            self.hide()

        if not options.hidden:
            self.show()
            self.visible = True

        self.load_profile(create_db=True)

        # Register GUI observer (ConfigurationManager already initialized dans load_profile)
        self._register_gui_observer()

        if self.config.install_method == "app":
            for site in list(self.config.supported_sites.values()):
                if site.screen_name != "YOUR SCREEN NAME HERE":
                    break
            else:
                options.initialRun = True
                self.display_config_created_dialogue = True
                self.display_site_preferences = True

        if options.initialRun and self.display_site_preferences:
            self.dia_site_preferences(None, None)
            self.display_site_preferences = False

        if not options.errorsToConsole:
            fileName = os.path.join(self.config.dir_log, "fpdb-errors.txt")
            log.info(
                f"Note: error output is being diverted to {self.config.dir_log}. Any major error will be reported there _only_.",
            )
            errorFile = codecs.open(fileName, "w", "utf-8")
            sys.stderr = errorFile

        sys.stderr.write("fpdb starting ...")

        if options.autoimport:
            self.tab_auto_import(None)

    def _register_gui_observer(self) -> None:
        """Registers the GUI observer with the ConfigurationManager."""
        try:
            config_manager = ConfigurationManager()

            # Initialize ConfigurationManager if not already done
            if not config_manager.initialized:
                config_manager.initialize(self.config.file)
                # IMPORTANT: Synchronise config objects
                config_manager._config = self.config
                config_manager._capture_current_state()

            # Register GUI observer
            gui_observer = GuiConfigObserver(self)
            config_manager.register_observer(gui_observer)
            log.info("GUI observer registered with ConfigurationManager")

        except Exception as e:
            log.exception(f"Error while registering the GUI observer: {e}")


class CustomTitleBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.main_window = parent

        self.title = QLabel("Free Poker DB 3")
        self.title.setAlignment(Qt.AlignCenter)

        self.btn_minimize = QPushButton("-")
        self.btn_maximize = QPushButton("+")
        self.btn_close = QPushButton("x")

        button_size = 20
        self.btn_minimize.setFixedSize(button_size, button_size)
        self.btn_maximize.setFixedSize(button_size, button_size)
        self.btn_close.setFixedSize(button_size, button_size)

        self.btn_minimize.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_maximize.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_close.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.btn_minimize.clicked.connect(parent.showMinimized)
        self.btn_maximize.clicked.connect(self.toggle_maximize_restore)
        self.btn_close.clicked.connect(parent.close)

        layout = QHBoxLayout()
        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.btn_minimize)
        layout.addWidget(self.btn_maximize)
        layout.addWidget(self.btn_close)
        self.setLayout(layout)

        self.is_maximized = False
        if sys.platform == "darwin":
            pass
        else:
            self.moving = False
            self.offset = None

    def toggle_maximize_restore(self) -> None:
        if self.is_maximized:
            self.main_window.showNormal()
        else:
            self.main_window.showMaximized()
        self.is_maximized = not self.is_maximized

    def update_theme(self) -> None:
        self.setStyleSheet(self.main_window.styleSheet())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.main_window.oldPos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton:
            delta = QPoint(event.globalPos() - self.main_window.oldPos)
            self.main_window.move(self.main_window.x() + delta.x(), self.main_window.y() + delta.y())
            self.main_window.oldPos = event.globalPos()


if __name__ == "__main__":
    import time

    # qt_material import moved to ThemeManager

    # IMPORTANT: Initialize configuration BEFORE creating the application
    # This ensures all required files (HUD_config.xml, directories) exist
    # before any component tries to use them - fixes issue #22
    try:
        from ConfigInitializer import ConfigInitializer

        config = ConfigInitializer.initialize()
        if config:
            log.info("Configuration initialized successfully")
    except Exception as e:
        log.exception(f"Failed to initialize configuration: {e}")
        sys.exit(1)

    try:
        app = QApplication([])

        # Initialize ThemeManager and apply saved theme
        from ThemeManager import ThemeManager

        theme_manager = ThemeManager()
        theme_manager.initialize(config=config)
        saved_theme = theme_manager.get_qt_material_theme()

        # Apply theme using ThemeManager to handle both built-in and custom themes
        theme_manager._apply_theme_to_application(saved_theme)
        me = fpdb()

        # Register main window with theme manager for future theme changes
        theme_manager._main_window = me

        app.exec_()
    finally:
        profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
        ps.print_stats()

        # Use timestamp or process ID for unique filenames
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        results_file = os.path.join(PROFILE_OUTPUT_DIR, f"fpdb_profile_results_{timestamp}.txt")
        profile_file = os.path.join(PROFILE_OUTPUT_DIR, f"fpdb_profile_{timestamp}.prof")

        with open(results_file, "w") as f:
            f.write(s.getvalue())

        profiler.dump_stats(profile_file)
