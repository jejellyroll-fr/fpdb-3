#!/usr/bin/env python
from __future__ import annotations

import os

# OPTION A : on veut XWayland si la variable est posée
if os.getenv("FPDB_FORCE_X11") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import subprocess
import sys
import time
import traceback
from optparse import OptionParser
from typing import Any

import interlocks
from PySide6.QtCore import QDateTime, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration, Importer
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

# Import for dynamic reloading configuration
try:
    from AutoImportConfigObserver import AutoImportConfigObserver

    from fpdb_3_legacy.ConfigurationManager import ConfigurationManager

    DYNAMIC_CONFIG_AVAILABLE = True
except ImportError:
    DYNAMIC_CONFIG_AVAILABLE = False
    log = get_logger("gui_auto_import")
    log.warning("ConfigurationManager not available, dynamic config reload disabled")

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("gui_auto_import")

if os.name == "nt":
    try:
        import win32console
    except ImportError:
        # pywin32 is optional (e.g. not installed in CI); console detection for
        # the HUD launch degrades gracefully when it is unavailable.
        win32console = None


def to_raw(string) -> str:
    return rf"{string}"


class AutoImportThread(QThread):
    """Worker thread to run auto-import cycle off the main GUI thread."""
    finished = Signal()
    error = Signal(str)

    def __init__(self, importer) -> None:
        super().__init__()
        self.importer = importer

    def run(self) -> None:
        try:
            self.importer.autoSummaryGrab()
            self.importer.runUpdated()
            self.finished.emit()
        except Exception as e:  # intentional broad catch: Qt worker thread surfaces any failure via the error signal
            self.error.emit(str(e))


class GuiAutoImport(QWidget):
    log_message = Signal(str, str)

    def __init__(self, settings, config, sql=None, parent=None, cli=False) -> None:
        if not cli:
            QWidget.__init__(self, parent)
            self.log_message.connect(self._addText_slot)
        self.importtimer: QTimer | None = None
        self.import_thread: AutoImportThread | None = None
        self.settings = settings
        self.config = config
        self.sql = sql
        self.parent = parent

        self.pipe_to_hud: subprocess.Popen[Any] | None = None
        self.doAutoImportBool = False

        self.cli = cli

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
        # In headless (cli) mode there is no GUI to build and no config observer
        # to attach; the caller drives the import loop via run_headless().

    def setupGui(self) -> None:
        self.setWindowTitle(_("FPDB Auto Import"))
        self.setGeometry(100, 100, 800, 600)

        # Set minimal custom styles for specific needs
        self.setStyleSheet("""
            QTextEdit#logView {
                font-family: Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
                font-size: 13px;
                line-height: 1.4;
                border-radius: 8px;
            }

            QGroupBox {
                font-weight: bold;
                margin-top: 10px;
            }

            QProgressBar {
                border-radius: 2px;
                text-align: center;
            }
        """)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # --- Settings Group ---
        settingsGroup = QGroupBox(_("Settings"))
        settingsLayout = QFormLayout()
        settingsGroup.setLayout(settingsLayout)
        mainLayout.addWidget(settingsGroup)

        self.intervalEntry = QSpinBox()
        self.intervalEntry.setValue(
            int(self.config.get_import_parameters().get("interval")),
        )
        settingsLayout.addRow(QLabel(_("Time between imports (seconds):")), self.intervalEntry)

        # --- Log Group ---
        logGroup = QGroupBox(_("Log"))
        logLayout = QVBoxLayout()
        logGroup.setLayout(logLayout)
        mainLayout.addWidget(logGroup)

        self.textview = QTextEdit()
        self.textview.setObjectName("logView")  # For custom styling
        self.textview.setReadOnly(True)
        logLayout.addWidget(self.textview)

        # --- Controls ---
        controlsLayout = QHBoxLayout()

        self.startButton = QCheckBox(_("Start Auto Import"))
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
        self.statusLabel = QLabel(_("Ready"))
        # Use qt_material property for styling
        self.statusLabel.setProperty("class", "caption")
        mainLayout.addWidget(self.statusLabel)

        self.addText(_("Auto Import Ready.\n"), "info")

    def apply_theme(self, theme_name="dark_purple.xml") -> None:
        """Apply a qt_material theme to the widget."""
        from fpdb_3_legacy.ThemeManager import ThemeManager

        if ThemeManager().set_qt_material_theme(theme_name):
            self.addText(f"Theme changed to {theme_name.replace('.xml', '')}\n", "info")
        else:
            self.addText(f"Unable to apply theme {theme_name}\n", "warning")

    def addText(self, text, level="info") -> None:
        if getattr(self, "cli", False):
            # Headless mode: no GUI log view — route to the logger instead.
            message = text.strip()
            if message:
                {"error": log.error, "warning": log.warning}.get(level, log.info)(message)
            return
        try:
            self.log_message.emit(text, level)
        except RuntimeError:
            # The widget's C++ object was deleted (e.g. the auto-import tab was
            # closed) while a config-observer callback was still running. Drop
            # the UI log line instead of crashing on a dead signal source.
            log.debug("addText: GuiAutoImport widget already deleted, skipping UI log")

    def _addText_slot(self, text, level="info") -> None:
        """Add formatted text to the log with timestamp, icon and color coding."""
        cursor = self.textview.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Clean text: remove leading newlines to ensure timestamp stays at line start
        clean_text = text.lstrip("\n")
        leading_newlines = len(text) - len(clean_text)

        # Add any leading newlines first (but not before timestamp)
        if leading_newlines > 0:
            cursor.insertText("\n" * leading_newlines)

        # Add timestamp at the start of the actual message line
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        timestamp_format = QTextCharFormat()

        palette = self.palette()
        timestamp_format.setForeground(palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))

        cursor.insertText(f"[{timestamp}] ", timestamp_format)

        # Add icon and set color based on level
        icon_format = QTextCharFormat()
        text_format = QTextCharFormat()

        if level == "error":
            # Material Red 500
            color = QColor("#F44336")
            icon = "❌ "  # Cross mark
        elif level == "warning":
            # Material Orange 500
            color = QColor("#FF9800")
            icon = "⚠️  "  # Warning sign
        elif level == "success":
            # Material Green 500
            color = QColor("#4CAF50")
            icon = "✅ "  # Check mark
        elif level == "info":
            # Material Blue 500
            color = QColor("#2196F3")
            icon = "ℹ️  "  # Information
        elif level == "import":
            # Material Purple 500
            color = QColor("#9C27B0")
            icon = "📥 "  # Inbox tray (import)
        elif level == "export":
            # Material Indigo 500
            color = QColor("#3F51B5")
            icon = "📤 "  # Outbox tray (export)
        elif level == "process":
            # Material Deep Orange 500
            color = QColor("#FF5722")
            icon = "⚙️  "  # Gear (processing)
        elif level == "hud":
            # Material Teal 500
            color = QColor("#009688")
            icon = "🎮 "  # Video game controller (HUD)
        elif level == "file":
            # Material Brown 500
            color = QColor("#795548")
            icon = "📄 "  # Document
        elif level == "folder":
            # Material Blue Grey 500
            color = QColor("#607D8B")
            icon = "📁 "  # Folder
        elif level == "network":
            # Material Light Green 500
            color = QColor("#8BC34A")
            icon = "🌐 "  # Globe
        elif level == "database":
            # Material Cyan 500
            color = QColor("#00BCD4")
            icon = "🗄️  "  # File cabinet
        elif level == "poker":
            # Material Red 700
            color = QColor("#D32F2F")
            icon = "♠️  "  # Spade suit
        elif level == "lock":
            # Material Amber 700
            color = QColor("#FFA000")
            icon = "🔒 "  # Lock
        elif level == "unlock":
            # Material Light Green 700
            color = QColor("#689F38")
            icon = "🔓 "  # Unlock
        else:
            # Use theme's normal text color
            color = palette.color(QPalette.ColorRole.Text)
            icon = "📝 "  # Memo (default)

        # Set format for both icon and text
        icon_format.setForeground(color)
        text_format.setForeground(color)

        # Insert icon and text
        cursor.insertText(icon, icon_format)
        cursor.insertText(clean_text, text_format)

        # Ensure the new text is visible
        self.textview.setTextCursor(cursor)
        self.textview.ensureCursorVisible()

    #   end of GuiAutoImport.__init__

    def do_import(self) -> bool:
        """Callback for timer to do an import iteration asynchronously."""
        if self.doAutoImportBool:
            if self.import_thread is not None and self.import_thread.isRunning():
                log.debug("AutoImport: previous import thread is still running, deferring this iteration.")
                return True

            self.progressBar.setVisible(True)
            self.progressBar.setMaximum(0)  # Indeterminate progress

            self.import_thread = AutoImportThread(self.importer)
            self.import_thread.finished.connect(self.import_finished)
            self.import_thread.error.connect(self.import_error)
            self.import_thread.start()
            return True
        return False

    def import_finished(self) -> None:
        """Called when auto import cycle finishes in the background."""
        self.progressBar.setVisible(False)
        log.debug("AutoImport: background import cycle finished successfully")

    def import_error(self, error_msg: str) -> None:
        """Called when auto import cycle fails in the background."""
        self.progressBar.setVisible(False)
        log.error(f"AutoImport: background import cycle failed: {error_msg}")
        self.addText(f"Auto Import Error: {error_msg}\n", "error")

    def run_headless(self, interval: int | None = None, launch_hud: bool = True) -> int:
        """Run the auto-import loop without a GUI (used by the ``-q``/``--quiet`` mode).

        Watches the hand-history and tournament-summary directories configured for
        the enabled sites and imports new/updated files on a fixed interval — the
        same engine the GUI auto-import tab drives, but stepped by a plain
        ``time.sleep`` loop instead of a Qt timer. Runs until interrupted
        (Ctrl+C / SIGTERM).

        Like the GUI "Start Auto Import" button, this launches the HUD subprocess
        (``launch_hud=True``) and feeds it the imported hands over ZMQ. Note the
        HUD is itself a GUI overlay, so a display must be available.

        Args:
            interval: Seconds between import cycles. Defaults to the ``interval``
                import parameter from the configuration.
            launch_hud: Whether to spawn the HUD_main subprocess. Set False to run
                a pure background importer with no HUD.

        Returns:
            int: Process exit code (0 on clean shutdown, 1 if the global lock is
            unavailable).
        """
        if interval is None:
            try:
                interval = int(self.config.get_import_parameters().get("interval"))
            except (TypeError, ValueError):
                interval = 10
        interval = max(1, interval)

        lock = self.settings.get("global_lock")
        if lock is not None and not lock.acquire(wait=False, source="AutoImport"):
            log.error("Auto Import aborted: global lock not available (another fpdb import running?).")
            return 1

        log.info("Headless auto-import started (interval: %ss). Press Ctrl+C to stop.", interval)
        self.doAutoImportBool = True

        if launch_hud and self.pipe_to_hud is None:
            # HUD_main uses fpdb's shared option parser and rejects the
            # auto-import's own -q flag, so hand it HUD-appropriate options (the
            # config path) instead of whatever this process was invoked with.
            config_file = getattr(self.config, "file", None)
            self.settings["cl_options"] = f"-c {config_file}" if config_file else ""
            try:
                self._launch_hud()
                log.info("HUD launched.")
            except (OSError, ValueError):
                # A missing HUD must not stop imports; log and carry on headless.
                log.warning("Could not launch HUD; continuing without it: %s", traceback.format_exc())

        try:
            self.updatePaths()
            while True:
                try:
                    self.importer.autoSummaryGrab()
                    self.importer.runUpdated()
                except Exception:
                    # One bad cycle must not kill the daemon; log and keep watching.
                    log.exception("Auto-import cycle failed; continuing.")
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Stopping headless auto-import (interrupt received).")
        finally:
            self.doAutoImportBool = False
            try:
                self.importer.autoSummaryGrab(force=True)
            except Exception:
                log.exception("Final tournament-summary grab failed.")
            if self.pipe_to_hud is not None:
                try:
                    self.pipe_to_hud.terminate()
                except OSError:
                    log.debug("HUD subprocess already gone.")
                self.pipe_to_hud = None
                log.info("HUD subprocess stopped.")
            if lock is not None:
                lock.release()
                log.info("Global lock released.")
        return 0

    def reset_startbutton(self) -> bool:
        if self.pipe_to_hud is not None:
            self.startButton.set_label(_("Stop Auto Import"))
        else:
            self.startButton.set_label(_("Start Auto Import"))

        return False

    def detect_hh_dirs(self, widget, data) -> None:
        """Attempt to find user hand history directories for enabled sites."""
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

    def posix_detect_hh_dirs(self, site) -> bool:
        defaults = {
            "PokerStars": "~/.wine/drive_c/Program Files/PokerStars/HandHistory",
        }
        if site == "PokerStars":
            directory = os.path.expanduser(defaults[site])
            for file in [file for file in os.listdir(directory) if file not in [".", ".."]]:
                log.debug(file)
        return False

    @staticmethod
    def _hud_base_path() -> str:
        """Return the directory that contains HUD_main(.pyw), resolved robustly.

        Frozen builds unpack their resources next to ``sys._MEIPASS``. Otherwise
        HUD_main lives next to this module (both in ``fpdb_3_legacy``), so resolve
        it relative to ``__file__`` rather than ``sys.path[0]``/CWD, which depend
        on how the process was launched (e.g. ``python -m ...`` vs the installed
        entry point).
        """
        if getattr(sys, "frozen", False):
            return str(getattr(sys, "_MEIPASS"))
        return os.path.dirname(os.path.abspath(__file__))

    def _launch_hud(self) -> None:
        """Build the HUD_main command for the current install method and spawn it.

        Sets ``self.pipe_to_hud`` to the launched subprocess. Raises OSError or
        ValueError on failure (callers decide how to surface it). Shared by the
        GUI auto-import (startClicked) and the headless mode (run_headless).
        """
        # ------------------------------------------------------------------
        # 1) build command line
        # ------------------------------------------------------------------
        command: str | list[str]
        if getattr(sys, "frozen", False) == "pyoxidizer":
            command = [sys.executable, "--hud", *self.settings["cl_options"].split()]
            bs = 1

        elif self.config.install_method == "exe":
            command = "HUD_main.exe"
            bs = 0

        elif self.config.install_method == "app":
            base_path = self._hud_base_path()
            command = os.path.join(base_path, "HUD_main")
            if not os.path.isfile(command):
                msg = f"HUD_main not found at {command}"
                raise FileNotFoundError(msg)
            bs = 1

        elif os.name == "nt":  # Windows installation source
            path = to_raw(self._hud_base_path())
            use_pythonw = win32console is not None and win32console.GetConsoleWindow() == 0
            # Use the current interpreter (e.g. the uv/venv python) so the
            # HUD subprocess shares the same environment and installed
            # packages (zmq, PyQt, ...). Falling back to a bare
            # "python"/"pythonw" from PATH would pick a different
            # interpreter that may lack our dependencies.
            interpreter = sys.executable
            if use_pythonw:
                pythonw = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
                if os.path.isfile(pythonw):
                    interpreter = pythonw
            command = f'"{interpreter}" "{path}\\HUD_main.pyw" {self.settings["cl_options"]}'
            bs = 0

        else:  # Linux & macOS installation source
            base_path = self._hud_base_path()
            command = os.path.join(base_path, "HUD_main.pyw")
            if not os.path.isfile(command):
                self.addText(f"\n*** {command} was not found", "error")
            command = [command, *self.settings["cl_options"].split()]
            bs = 1

        # ------------------------------------------------------------------
        # 2) prepare env for sub process
        # ------------------------------------------------------------------
        env = None  # default

        if sys.platform.startswith("linux") and os.getenv("FPDB_FORCE_X11") == "1":
            env = os.environ.copy()
            env.setdefault("QT_QPA_PLATFORM", "xcb")
            env.setdefault("FPDB_FORCE_X11", "1")

        log.info("opening pipe to HUD")
        log.debug(f"Running {command!r} with bs={bs}")

        # ------------------------------------------------------------------
        # 3) launch HUD
        # ------------------------------------------------------------------
        popen_kwargs: dict[str, Any] = {
            "bufsize": bs,
            "stdin": subprocess.PIPE,
            "universal_newlines": True,
        }
        # Capture stdout/err for windows « exe »
        if self.config.install_method == "exe" or (
            os.name == "nt" and win32console is not None and win32console.GetConsoleWindow() == 0
        ):
            popen_kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if env is not None:
            popen_kwargs["env"] = env

        self.pipe_to_hud = subprocess.Popen(command, **popen_kwargs)

    def startClicked(self) -> None:
        """Runs when user clicks start on auto import tab."""
        # Check to see if we have an open file handle to the HUD and open one if we do not.
        # bufsize = 1 means unbuffered
        # We need to close this file handle sometime.

        if self.startButton.isChecked():
            # - Ideally we want to release the lock if the auto-import is killed by some
            # kind of exception - is this possible?
            if self.settings["global_lock"].acquire(wait=False, source="AutoImport"):
                self.addText("\nGlobal lock taken ... Auto Import Started.\n", "lock")
                self.doAutoImportBool = True
                self.intervalEntry.setEnabled(False)
                self.progressBar.setVisible(True)
                self.statusLabel.setText(_("Auto Import Running..."))

                if self.pipe_to_hud is None:
                    log.debug("start hud - pipe_to_hud is none:")
                    try:
                        self._launch_hud()
                    except (OSError, ValueError):
                        error_msg = f"GuiAutoImport Error opening pipe: {traceback.format_exc()}"
                        log.warning(error_msg)
                        self.addText(f"\n*** {error_msg}", "error")
                    else:
                        # ------------------------------------------------------------------
                        # path config, timer, etc.
                        # ------------------------------------------------------------------
                        self.updatePaths()

                        self.do_import()
                        interval = self.intervalEntry.value()
                        self.importtimer = QTimer()
                        self.importtimer.timeout.connect(self.do_import)
                        self.importtimer.start(interval * 1000)

            else:
                self.addText("\nAuto Import aborted. Global lock not available.", "error")

        else:  # bouton « Start » décoché → arrêt
            self.doAutoImportBool = False
            if self.importtimer:
                self.importtimer.stop()
                self.importtimer = None
            if self.import_thread is not None and self.import_thread.isRunning():
                self.import_thread.wait()
            self.importer.autoSummaryGrab(True)
            self.settings["global_lock"].release()
            self.addText("\nStopping Auto Import. Global lock released.", "unlock")
            self.progressBar.setVisible(False)
            self.statusLabel.setText(_("Ready"))
            if self.pipe_to_hud and self.pipe_to_hud.poll() is not None:
                self.addText("\n * Stop Auto Import: HUD already terminated.", "hud")
            else:
                if self.pipe_to_hud:
                    self.pipe_to_hud.terminate()
                    log.debug(f"pipe_to_hud stdin: {self.pipe_to_hud.stdin}")
                self.pipe_to_hud = None
            self.intervalEntry.setEnabled(True)

    # end def GuiAutoImport.startClicked

    def get_vbox(self):
        """Returns the vbox of this thread."""
        return self.mainVBox

    # end def get_vbox

    def _setup_config_observer(self) -> None:
        """Configure the configuration observer for auto-import."""
        if DYNAMIC_CONFIG_AVAILABLE:
            try:
                config_manager = ConfigurationManager()

                # Ensure ConfigurationManager is initialized
                if not config_manager.initialized:
                    config_manager.initialize(self.config.file)

                # Create and register observer
                self.config_observer = AutoImportConfigObserver(self)
                config_manager.register_observer(self.config_observer)

                log.info("Configuration observer registered for auto-import")

            except Exception as e:  # intentional broad catch: config observer registration best-effort, log only
                log.exception(f"Error during observer configuration: {e}")

    def _teardown_config_observer(self) -> None:
        """Unregister the config observer so it can't call into a deleted widget.

        Without this the ConfigurationManager (a singleton) keeps a reference to
        this widget after it is closed; the next config change then calls
        updatePaths() -> addText() and emits a signal on a dead Qt object.
        """
        observer = getattr(self, "config_observer", None)
        if observer is None or not DYNAMIC_CONFIG_AVAILABLE:
            return
        try:
            ConfigurationManager().unregister_observer(observer)
        except Exception:  # intentional broad catch: teardown best-effort, log only
            log.debug("Failed to unregister auto-import config observer", exc_info=True)
        self.config_observer = None

    def closeEvent(self, event) -> None:
        self._teardown_config_observer()
        super().closeEvent(event)

    def _configured_import_directories(self) -> dict[tuple[str, str], str]:
        """Return existing import directories from the current enabled sites."""
        directories: dict[tuple[str, str], str] = {}
        for site in self.config.get_supported_sites():
            # A site can be enabled under <supported_sites> without a matching
            # <hhc> converter entry (e.g. "BetOnline" vs "BetOnline Poker").
            # Skip such a site instead of letting one KeyError abort auto-import
            # for every site — which leaves the HUD with nothing to import.
            try:
                params = self.config.get_site_parameters(site)
            except KeyError as e:
                log.warning("Skipping auto-import for misconfigured site %s (missing config: %s)", site, e)
                continue
            if not params["enabled"]:
                continue

            try:
                paths = self.config.get_default_paths(site)
            except KeyError as e:
                log.warning("Skipping auto-import paths for misconfigured site %s (missing config: %s)", site, e)
                continue
            hh_path = paths.get("hud-defaultPath")
            if hh_path and os.path.isdir(hh_path):
                directories[(site, "hh")] = hh_path
            elif hh_path:
                log.warning("Ignoring invalid hand-history path for %s: %s", site, hh_path)

            ts_path = paths.get("hud-defaultTSPath")
            if ts_path and os.path.isdir(ts_path):
                directories[(site, "ts")] = ts_path
            elif ts_path:
                log.warning("Ignoring invalid tournament-summary path for %s: %s", site, ts_path)

        return directories

    def updatePaths(self) -> None:
        """Reload config paths and resynchronise the importer's watched dirs."""
        log.debug("Updating auto-import paths from configuration")

        if hasattr(self.config, "reload"):
            self.config.reload()

        desired = self._configured_import_directories()
        current = dict(getattr(self.importer, "dirlist", {}))

        for key, (old_path, _old_filter) in current.items():
            new_path = desired.get(key)
            if new_path != old_path:
                self.importer.removeImportDirectory(old_path, site=key)
                self.addText(f"\n * Remove {key[0]} {key[1]} directory: {old_path}", "folder")

        for key, path in desired.items():
            current_path = self.importer.dirlist.get(key, [None])[0]
            if current_path == path:
                continue
            self.importer.addImportDirectory(path, monitor=True, site=key)
            label = "hand history" if key[1] == "hh" else "tournament summary"
            self.addText(f"\n * Add {key[0]} {label} directory: {path}", "folder")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Parse command line options
    parser = OptionParser()
    parser.add_option(
        "-q",
        "--quiet",
        action="store_false",
        dest="gui",
        default=True,
        help="don't start gui",
    )
    (options, remaining_argv) = parser.parse_args(argv)

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
    settings["cl_options"] = ".".join(argv)

    if options.gui is True:
        from PySide6.QtWidgets import QApplication, QMainWindow

        app = QApplication([])
        i = GuiAutoImport(settings, config, None, None)
        main_window = QMainWindow()
        main_window.setCentralWidget(i)
        main_window.show()
        app.exec()
    else:
        i = GuiAutoImport(settings, config, cli=True)
        return i.run_headless()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
