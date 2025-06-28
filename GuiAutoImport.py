#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os

# import L10n
# _ = L10n.get_translation()
import subprocess
import sys
import traceback
from optparse import OptionParser

from PyQt5.QtCore import QTimer, QDateTime
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

import Configuration
import Importer
import interlocks
from loggingFpdb import get_logger

# Import pour le rechargement dynamique de configuration
try:
    from AutoImportConfigObserver import AutoImportConfigObserver
    from ConfigurationManager import ConfigurationManager

    DYNAMIC_CONFIG_AVAILABLE = True
except ImportError:
    DYNAMIC_CONFIG_AVAILABLE = False
    log = get_logger("importer")
    log.warning("ConfigurationManager not available, dynamic config reload disabled")

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("importer")

if os.name == "nt":
    import win32console


def to_raw(string):
    return rf"{string}"


class GuiAutoImport(QWidget):
    def __init__(self, settings, config, sql=None, parent=None, cli=False):
        if not cli:
            QWidget.__init__(self, parent)
        self.importtimer = None
        self.settings = settings
        self.config = config
        self.sql = sql
        self.parent = parent

        self.pipe_to_hud = None
        self.doAutoImportBool = False

        self.importer = Importer.Importer(self, self.settings, self.config, self.sql)

        self.importer.setCallHud(True)
        self.importer.setQuiet(False)
        self.importer.setHandCount(0)
        self.importer.setMode("auto")

        self.server = settings["db-host"]
        self.user = settings["db-user"]
        self.password = settings["db-password"]
        self.database = settings["db-databaseName"]

        if cli is False:
            self.setupGui()
            self._setup_config_observer()
        else:
            # TODO: Separate the code that grabs the directories from config
            #       Separate the calls to the Importer API
            #       Create a timer interface that doesn't rely on GTK
            raise NotImplementedError

    def setupGui(self):
        self.setWindowTitle("FPDB Auto Import")
        self.setGeometry(100, 100, 800, 600)
        
        # Let qt_material handle the styling
        # Only set minimal custom styles for specific needs
        self.setStyleSheet("""
            QTextEdit#logView {
                font-family: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
                font-size: 13px;
            }
        """)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # --- Settings Group ---
        settingsGroup = QGroupBox("Settings")
        settingsLayout = QFormLayout()
        settingsGroup.setLayout(settingsLayout)
        mainLayout.addWidget(settingsGroup)

        self.intervalEntry = QSpinBox()
        self.intervalEntry.setValue(
            int(self.config.get_import_parameters().get("interval"))
        )
        settingsLayout.addRow(QLabel("Time between imports (seconds):"), self.intervalEntry)

        # --- Log Group ---
        logGroup = QGroupBox("Log")
        logLayout = QVBoxLayout()
        logGroup.setLayout(logLayout)
        mainLayout.addWidget(logGroup)

        self.textview = QTextEdit()
        self.textview.setObjectName("logView")  # For custom styling
        self.textview.setReadOnly(True)
        logLayout.addWidget(self.textview)

        # --- Controls ---
        controlsLayout = QHBoxLayout()
        
        self.startButton = QCheckBox("Start Auto Import")
        self.startButton.stateChanged.connect(self.startClicked)
        controlsLayout.addWidget(self.startButton)
        
        # Add a progress indicator
        self.progressBar = QProgressBar()
        self.progressBar.setTextVisible(False)
        self.progressBar.setMaximum(0)  # Indeterminate progress
        self.progressBar.setVisible(False)
        self.progressBar.setMaximumHeight(4)
        # Let qt_material handle the progress bar styling
        controlsLayout.addWidget(self.progressBar, 1)
        
        controlsLayout.addStretch()
        
        mainLayout.addLayout(controlsLayout)
        
        # Status label
        self.statusLabel = QLabel("Ready")
        # Use qt_material property for styling
        self.statusLabel.setProperty("class", "caption")
        mainLayout.addWidget(self.statusLabel)

        self.addText("Auto Import Ready.\n", "info")

    def addText(self, text, level="info"):
        """Add formatted text to the log with timestamp and color coding"""
        cursor = self.textview.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Add timestamp
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        timestamp_format = QTextCharFormat()
        # Use theme's disabled text color for timestamp
        palette = self.palette()
        timestamp_format.setForeground(palette.color(QPalette.Disabled, QPalette.Text))
        cursor.insertText(f"[{timestamp}] ", timestamp_format)
        
        # Set color based on level using theme-aware colors
        text_format = QTextCharFormat()
        if level == "error":
            # Red color for errors
            text_format.setForeground(QColor("#f44336"))
        elif level == "warning":
            # Orange color for warnings
            text_format.setForeground(QColor("#ff9800"))
        elif level == "success":
            # Green color for success
            text_format.setForeground(QColor("#4caf50"))
        elif level == "info":
            # Use theme's link color for info
            text_format.setForeground(palette.color(QPalette.Link))
        else:
            # Use theme's normal text color
            text_format.setForeground(palette.color(QPalette.Text))
        
        cursor.insertText(text, text_format)
        
        # Ensure the new text is visible
        self.textview.setTextCursor(cursor)
        self.textview.ensureCursorVisible()

    #   end of GuiAutoImport.__init__

    
    def do_import(self):
        """Callback for timer to do an import iteration."""
        if self.doAutoImportBool:
            self.importer.autoSummaryGrab()
            self.importer.runUpdated()
            # The detailed logging is now handled in Importer.runUpdated()
            return True
        return False

    def reset_startbutton(self):
        if self.pipe_to_hud is not None:
            self.startButton.set_label(("Stop Auto Import"))
        else:
            self.startButton.set_label(("Start Auto Import"))

        return False

    def detect_hh_dirs(self, widget, data):
        """Attempt to find user hand history directories for enabled sites"""
        the_sites = self.config.get_supported_sites()
        for site in the_sites:
            params = self.config.get_site_parameters(site)
            if params["enabled"] is True:
                log.debug(f"Detecting hand history directory for site: '{site}'")
                if os.name == "posix":
                    if self.posix_detect_hh_dirs(site):
                        # data[1].set_text(dia_chooser.get_filename())
                        pass
                elif os.name == "nt":
                    # Sorry
                    pass

    def posix_detect_hh_dirs(self, site):
        defaults = {
            "PokerStars": "~/.wine/drive_c/Program Files/PokerStars/HandHistory",
        }
        if site == "PokerStars":
            directory = os.path.expanduser(defaults[site])
            for file in [
                file for file in os.listdir(directory) if file not in [".", ".."]
            ]:
                log.debug(file)
        return False

    def startClicked(self):
        """runs when user clicks start on auto import tab"""

        # Check to see if we have an open file handle to the HUD and open one if we do not.
        # bufsize = 1 means unbuffered
        # We need to close this file handle sometime.

        # TODO:  Allow for importing from multiple dirs - REB 29AUG2008
        # As presently written this function does nothing if there is already a pipe open.
        # That is not correct.  It should open another dir for importing while piping the
        # results to the same pipe.  This means that self.path should be a a list of dirs
        # to watch.

        if self.startButton.isChecked():
            # - Does the lock acquisition need to be more sophisticated for multiple dirs?
            # (see comment above about what to do if pipe already open)
            # - Ideally we want to release the lock if the auto-import is killed by some
            # kind of exception - is this possible?
            if self.settings["global_lock"].acquire(wait=False, source="AutoImport"):
                self.addText("\nGlobal lock taken ... Auto Import Started.\n", "success")
                self.doAutoImportBool = True
                self.intervalEntry.setEnabled(False)
                self.progressBar.setVisible(True)
                self.statusLabel.setText("Auto Import Running...")
                if self.pipe_to_hud is None:
                    log.debug("start hud- pipe_to_hud is none:")
                    try:
                        if self.config.install_method == "exe":
                            command = "HUD_main.exe"
                            bs = 0
                        elif self.config.install_method == "app":
                            base_path = (
                                sys._MEIPASS
                                if getattr(sys, "frozen", False)
                                else sys.path[0]
                            )
                            command = os.path.join(base_path, "HUD_main")
                            if not os.path.isfile(command):
                                raise FileNotFoundError(
                                    f"HUD_main not found at {command}"
                                )
                            bs = 1
                        elif os.name == "nt":
                            path = to_raw(sys.path[0])
                            log.debug(f"start hud - path: {path}")
                            path2 = os.getcwd()
                            log.debug(f"start hud - path2: {path2}")
                            if win32console.GetConsoleWindow() == 0:
                                command = (
                                    'pythonw "'
                                    + path
                                    + '\HUD_main.pyw" '
                                    + self.settings["cl_options"]
                                )
                                log.debug(f"start hud - command: {command}")
                            else:
                                command = (
                                    'python "'
                                    + path
                                    + '\HUD_main.pyw" '
                                    + self.settings["cl_options"]
                                )
                                log.debug(f"start hud - command: {command}")
                            bs = 0
                        else:
                            base_path = (
                                sys._MEIPASS
                                if getattr(sys, "frozen", False)
                                else sys.path[0] or os.getcwd()
                            )
                            command = os.path.join(base_path, "HUD_main.pyw")
                            if not os.path.isfile(command):
                                self.addText(
                                    "\n" + ("*** %s was not found") % (command)
                                )
                            command = [
                                command,
                            ] + str.split(self.settings["cl_options"], ".")
                            bs = 1

                        log.info(("opening pipe to HUD"))
                        log.debug(f"Running {command.__repr__()}")
                        if self.config.install_method == "exe" or (
                            os.name == "nt" and win32console.GetConsoleWindow() == 0
                        ):
                            self.pipe_to_hud = subprocess.Popen(
                                command,
                                bufsize=bs,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                            )
                        else:
                            self.pipe_to_hud = subprocess.Popen(
                                command,
                                bufsize=bs,
                                stdin=subprocess.PIPE,
                                universal_newlines=True,
                            )

                    except Exception:
                        error_msg = f"GuiAutoImport Error opening pipe: {traceback.format_exc()}"
                        log.warning(error_msg)
                        self.addText(f"\n*** {error_msg}", "error")
                    else:
                        # Get import directories from configuration
                        the_sites = self.config.get_supported_sites()
                        for site in the_sites:
                            params = self.config.get_site_parameters(site)
                            if params["enabled"]:
                                paths = self.config.get_default_paths(site)
                                
                                # Add hand history directory
                                if "hud-defaultPath" in paths and paths["hud-defaultPath"]:
                                    self.importer.addImportDirectory(
                                        paths["hud-defaultPath"],
                                        monitor=True,
                                        site=(site, "hh"),
                                    )
                                    self.addText(
                                        f"\n * Add {site} hand history directory: {paths['hud-defaultPath']}",
                                        "info"
                                    )
                                
                                # Add tournament summary directory if exists
                                if "hud-defaultTSPath" in paths and paths["hud-defaultTSPath"]:
                                    self.importer.addImportDirectory(
                                        paths["hud-defaultTSPath"],
                                        monitor=True,
                                        site=(site, "ts"),
                                    )
                                    self.addText(
                                        f"\n * Add {site} tournament summary directory: {paths['hud-defaultTSPath']}",
                                        "info"
                                    )
                        
                        self.do_import()
                        interval = self.intervalEntry.value()
                        self.importtimer = QTimer()
                        self.importtimer.timeout.connect(self.do_import)
                        self.importtimer.start(interval * 1000)

            else:
                self.addText("\nAuto Import aborted. Global lock not available.", "error")
        else:  # toggled off
            self.doAutoImportBool = False
            if self.importtimer:
                self.importtimer.stop()
                self.importtimer = None
            self.importer.autoSummaryGrab(True)
            self.settings["global_lock"].release()
            self.addText("\nStopping Auto Import. Global lock released.", "warning")
            self.progressBar.setVisible(False)
            self.statusLabel.setText("Ready")
            if self.pipe_to_hud and self.pipe_to_hud.poll() is not None:
                self.addText("\n * Stop Auto Import: HUD already terminated.", "info")
            else:
                if self.pipe_to_hud:
                    self.pipe_to_hud.terminate()
                    log.debug(f"pipe_to_hud stdin: {self.pipe_to_hud.stdin}")
                self.pipe_to_hud = None
            self.intervalEntry.setEnabled(True)

    # end def GuiAutoImport.startClicked

    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.mainVBox

    # end def get_vbox

    
    def _setup_config_observer(self):
        """Configure l'observateur de configuration pour l'auto-import"""
        if DYNAMIC_CONFIG_AVAILABLE:
            try:
                config_manager = ConfigurationManager()

                # S'assurer que le ConfigurationManager est initialisé
                if not config_manager.initialized:
                    config_manager.initialize(self.config.file)

                # Créer et enregistrer l'observateur
                self.config_observer = AutoImportConfigObserver(self)
                config_manager.register_observer(self.config_observer)

                log.info("Observateur de configuration enregistré pour l'auto-import")

            except Exception as e:
                log.error(f"Erreur lors de la configuration de l'observateur: {e}")

    def updatePaths(self):
        """Met à jour l'affichage des chemins d'import (appelé par l'observateur)"""
        # Cette méthode peut être appelée pour rafraîchir l'interface
        # après un changement de configuration dynamique
        log.debug("Mise à jour des chemins d'import dans l'interface")


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option(
        "-q",
        "--quiet",
        action="store_false",
        dest="gui",
        default=True,
        help="don't start gui",
    )
    (options, argv) = parser.parse_args()

    config = Configuration.Config()

    settings = {}
    if os.name == "nt":
        settings["os"] = "windows"
    else:
        settings["os"] = "linuxmac"

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    settings["global_lock"] = interlocks.InterProcessLock(name="fpdb_global_lock")
    settings["cl_options"] = ".".join(sys.argv[1:])

    if options.gui is True:
        from PyQt5.QtWidgets import QApplication, QMainWindow

        app = QApplication([])
        i = GuiAutoImport(settings, config, None, None)
        main_window = QMainWindow()
        main_window.setCentralWidget(i)
        main_window.show()
        app.exec_()
    else:
        i = GuiAutoImport(settings, config, cli=True)
