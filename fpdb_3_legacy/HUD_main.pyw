#!/usr/bin/env python
"""Hud_main.py.

Main for FreePokerTools HUD.
"""

import contextlib
import os
import sys

# When launched as a bare script (``python HUD_main.pyw``), sys.path[0] is this
# file's own directory (fpdb_3_legacy/), which contains ``fpdb.pyw``. Because
# Python treats ``.pyw`` as importable source, ``import fpdb`` would resolve to
# that GUI entry script and shadow the real top-level ``fpdb`` package (breaking
# ``from fpdb.infrastructure... import ...`` in WinTables and friends). Put the
# repository root first so the package always wins.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

if sys.platform.startswith("linux") and os.getenv("FPDB_FORCE_X11") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import time
from collections.abc import Callable
from dataclasses import dataclass
from optparse import Values
from pathlib import Path
from typing import Any

import zmq as _zmq

zmq: Any = _zmq

# Add a cache for frequently accessed data
from cachetools import TTLCache
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qt_material import apply_stylesheet

from fpdb_3_legacy import Aux_Base, Configuration, Database, Deck, Hud, Options
from fpdb_3_legacy.HudStatsPersistence import get_hud_stats_persistence
from fpdb_3_legacy.loggingFpdb import get_logger, hud_trace
from fpdb_3_legacy.SmartHudManager import RestartReason, get_smart_hud_manager

# Logging configuration

log = get_logger("hud_main")

# How long an arriving hand waits for its neighbours. Twelve tables dealing at
# once arrive as twelve separate notifications; holding them briefly turns that
# into one batch, so each HUD is refreshed once rather than once per hand. Long
# enough to catch the burst, short enough to stay ahead of the player acting.
HAND_BATCH_INTERVAL_MS = 200


@dataclass
class HUDCreationArgs:
    """Arguments for creating a HUD."""

    new_hand_id: str
    table: Any
    temp_key: str
    max_seats: int
    poker_game: str
    game_type: str
    stat_dict: dict[str, Any]
    cards: dict[str, Any]


class ZMQWorker(QThread):
    """A QThread to run the ZMQ message processing loop."""

    error_occurred = Signal(str)

    def __init__(self, zmq_receiver: "ZMQReceiver") -> None:
        """Initialize the ZMQ worker."""
        super().__init__()
        self.zmq_receiver = zmq_receiver
        self.is_running = True

    def run(self) -> None:
        """Run the ZMQ message processing loop."""
        log.info("ZMQWorker started and listening for messages")
        while self.is_running:
            try:
                self.zmq_receiver.process_message()
            except Exception:
                log.exception("Error in ZMQWorker")
                self.error_occurred.emit("Error in ZMQWorker")
            time.sleep(0.01)  # Short delay to avoid excessive CPU usage

    def stop(self) -> None:
        """Stop the worker thread."""
        self.is_running = False
        self.wait()


class ZMQReceiver(QObject):
    """A QObject to receive ZMQ messages."""

    message_received = Signal(str)

    def __init__(self, port: str = "5555", parent: QObject | None = None) -> None:
        """Initialize the ZMQ receiver."""
        super().__init__(parent)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")
        log.info("ZMQ receiver bound to port %s", port)
        # Set socket options for better debugging
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout

        # Heartbeat configuration
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def process_message(self) -> None:
        """Process a ZMQ message."""
        if self.socket.closed:
            return
        try:
            socks = dict(self.poller.poll(1000))  # Timeout 1 seconde
            if self.socket.closed:
                return
            if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                hand_id = self.socket.recv_string(zmq.NOBLOCK)
                log.info("ZMQ received hand ID: %s", hand_id)
                self.message_received.emit(hand_id)
            else:
                # Heartbeat
                log.debug("Heartbeat: No message received")
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                pass  # No message available
            elif hasattr(zmq, "ENOTSOCK") and e.errno == zmq.ENOTSOCK:
                log.info("ZMQ socket closed during poll")
            elif "non-socket" in str(e):
                log.info("ZMQ socket closed during poll")
            else:
                log.exception("ZMQ error")

    def close(self) -> None:
        """Close the ZMQ socket and context."""
        if not self.socket.closed:
            self.socket.close()
        self.context.term()
        log.info("ZMQ receiver closed")


class HudMainWindow(QWidget):
    """Top-level HUD window with a typed close callback."""

    def __init__(self, on_close: Callable[[QCloseEvent], None]) -> None:
        """Initialize the window and retain its close callback."""
        super().__init__(
            None,
            Qt.WindowType.Dialog | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint,
        )
        self._on_close = on_close

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Forward the native close event to the HUD owner."""
        self._on_close(event)


class HudMain(QObject):
    """A main() object to own both the socket thread and the gui."""

    def __init__(self, options: Values, db_name: str = "fpdb") -> None:
        """Initialize the main HUD application."""
        self.options = options
        QObject.__init__(self)
        self.db_name = db_name
        self._shutdown_started = False

        # Ensure HUD logging is properly initialized
        import logging
        from pathlib import Path

        from fpdb_3_legacy.loggingFpdb import JsonFormatter, TimedSizedRotatingFileHandler

        try:
            # Import LoggerRegistry to get the current logger configuration
            from fpdb_3_legacy.loggingFpdb import DIAGNOSTIC_LEVEL_CAP, LoggerRegistry

            # Create HUD-specific log directory and file. Use the fpdb config
            # directory (%APPDATA%/fpdb on Windows, ~/.fpdb elsewhere) so
            # HUD-log.txt sits next to fpdb-log.txt and HUD-errors.txt instead
            # of a second, easily-missed ~/.fpdb tree.
            if Configuration.CONFIG_PATH:
                hud_log_dir = Path(Configuration.CONFIG_PATH) / "log"
            else:
                hud_log_dir = Path.home() / ".fpdb" / "log"
            hud_log_dir.mkdir(parents=True, exist_ok=True)
            hud_log_file = hud_log_dir / "HUD-log.txt"

            # Get the HUD logger and check if it's already configured by Logger Dev Tool
            hud_logger = logging.getLogger("hud_main")
            registry = LoggerRegistry()
            logger_info = registry.get_logger_info("hud_main")

            # Get the current level from command line, Logger Dev Tool configuration, or use ERROR as default
            if options.log_level != "EMPTY":
                configured_level = getattr(logging, options.log_level)
                logging.getLogger().setLevel(configured_level)
                log.info(f"Using command line logging configuration: level={options.log_level}")
            elif logger_info:
                configured_level = logger_info.current_level
                log.info(f"Using Logger Dev Tool configuration: level={logging.getLevelName(configured_level)}")
            else:
                configured_level = logging.ERROR
                log.info("Using default ERROR level for HUD logger")

            # The file log is the diagnostic record: it must never sit above
            # WARNING, or the skip reasons and table-detection traces needed to
            # debug "HUD did not appear" reports are lost. The console keeps
            # the configured (usually ERROR) level below.
            file_level = min(configured_level, DIAGNOSTIC_LEVEL_CAP)
            hud_logger.setLevel(file_level)

            # Remove existing handlers to avoid duplicates
            for handler in hud_logger.handlers[:]:
                hud_logger.removeHandler(handler)

            # Create HUD-specific file handler using our custom rotating handler
            file_handler = TimedSizedRotatingFileHandler(
                filename=str(hud_log_file),
                when="midnight",
                interval=1,
                backup_count=7,
                max_bytes=10 * 1024 * 1024,  # 10 MB
                encoding="utf-8",
            )
            file_handler.setLevel(file_level)

            # Use our JSON formatter
            json_formatter = JsonFormatter()
            file_handler.setFormatter(json_formatter)

            # Add handler to HUD logger
            hud_logger.addHandler(file_handler)

            # Add console handler using FPDB's colored formatter
            import colorlog

            log_colors = {
                "DEBUG": "green",
                "INFO": "blue",
                "WARNING": "yellow",
                "ERROR": "red",
            }
            log_format = (
                "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] [%(levelname)s] %(message)s%(reset)s"
            )
            date_format = "%Y-%m-%d %H:%M:%S"
            console_formatter = colorlog.ColoredFormatter(
                fmt=log_format,
                datefmt=date_format,
                log_colors=log_colors,
            )

            console_handler = logging.StreamHandler()
            # Console handler should also respect the configured level
            console_handler.setLevel(configured_level)
            console_handler.setFormatter(console_formatter)
            hud_logger.addHandler(console_handler)

            hud_logger.propagate = False  # Use our own handlers instead of propagating

            # The HUD process is more than the "hud_main" logger: table
            # detection logs through "win_tables"/"table_window", positioning
            # through "hud"/aux loggers. Those all propagate to the root
            # logger, which had no file handler here, so their WARNINGs (e.g.
            # "Currently open windows: [...]" after a failed table search)
            # vanished. Share the file handler with the root logger so every
            # module's WARNING+ lands in HUD-log.txt. hud_main does not
            # propagate, so its records are not duplicated.
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)
            if root_logger.level > file_level:
                root_logger.setLevel(file_level)
            # Keep ERROR+ from those propagated loggers on stderr too: before
            # the root logger had a handler, Python's lastResort handler sent
            # them to *current* sys.stderr, which the HUD-errors.txt
            # redirection below captures. A plain StreamHandler would bind the
            # original stderr now, before the redirection, so resolve
            # sys.stderr at emit time exactly like lastResort does.
            root_console_handler = logging._StderrHandler(logging.ERROR)  # type: ignore[attr-defined]  # noqa: SLF001
            root_console_handler.setFormatter(console_formatter)
            root_logger.addHandler(root_console_handler)

            log.info(f"HUD logging configured to: {hud_log_file}")
            log.info("HUD_main starting up - logging initialized successfully")

        except Exception as e:
            log.exception(f"Failed to setup HUD logging: {e}")
            import traceback

            traceback.print_exc()

        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        log.info("HUD_main initialized - Config loaded, OS family: %s", self.config.os_family)

        # Selecting the right module for the OS
        if self.config.os_family == "Linux":
            # Simplified: XWayland support or X11 fallback
            if os.getenv("QT_QPA_PLATFORM") == "xcb" or not os.environ.get("WAYLAND_DISPLAY"):
                log.info("XWayland forced under wayland → backend XTables")
                import XTables as Tables
            else:
                log.info("Session X11 detected → backend XTables")
                import XTables as Tables
        elif self.config.os_family == "Mac":
            import OSXTables as Tables
        elif self.config.os_family in ("XP", "Win7"):
            import WinTables as Tables
        log.info("HudMain starting: Using db name = %s", db_name)
        self.Tables = Tables  # Assign Tables to self.Tables

        # Surface missing macOS privacy permissions at startup so table-detection
        # failures ("table name ... not found") are explained before the first hand.
        if self.config.os_family == "Mac":
            self._check_macos_permissions()

        # Logging configuration
        if not options.errorsToConsole:
            log_dir = Path(self.config.dir_log)
            log_dir.mkdir(exist_ok=True)
            file_name = log_dir / "HUD-errors.txt"
            log.info("Note: error output is being diverted to %s.", file_name)
            log.info("Any major error will be reported there *only*.")
            error_file = file_name.open("w", encoding="utf-8")
            sys.stderr = error_file
            log.info("HudMain starting")

        log.info("HudMain.__init__ starting")
        log.info(
            "HUD DEBUG - Options: errorsToConsole=%s, logging_level=%s",
            options.errorsToConsole,
            getattr(options, "logging_level", "Not set"),
        )
        try:
            # Connecting to the database
            log.info("Connecting to database...")
            self.db_connection = Database.Database(self.config)
            log.info("Database connection successful")

            # HUD dictionary and parameters
            self.hud_dict: dict[str, Hud.Hud] = {}
            # Session-only profile choices made from an individual table menu.
            # Values include game identity so a recycled table key cannot leak a
            # Hold'em/PLO choice into another game.
            self._table_stat_set_overrides: dict[str, tuple[str, str, str]] = {}
            # Last hand id processed per table. The ZMQ producer (auto-import
            # re-scanning growing files) can deliver the same Hands.id more than
            # once; this makes read_stdin idempotent so each hand refreshes the
            # HUD exactly once, without re-running create/update on a duplicate.
            self._last_processed_hands: dict[str, str] = {}
            self.blacklist: list[Any] = []
            self.hud_params = self.config.get_hud_ui_parameters()
            self.deck = Deck.Deck(
                self.config,
                deck_type=self.hud_params["deck_type"],
                card_back=self.hud_params["card_back"],
                width=self.hud_params["card_wd"],
                height=self.hud_params["card_ht"],
            )

            # Cache initialization
            self.cache: TTLCache = TTLCache(maxsize=1000, ttl=300)  # Cache of 1000 elements with a TTL of 5 minutes
            # Per-hand reads of HandsPlayers. That table is written in the same
            # transaction as the Hands row and never rewritten afterwards, and
            # read_stdin only gets past _get_table_info for a hand whose own
            # query already joined HandsPlayers -- so once a hand reaches here
            # its seats and positions are settled and worth reading once.
            self._hand_players: TTLCache = TTLCache(maxsize=200, ttl=300)

            # Hands wait here for HAND_BATCH_INTERVAL_MS so a burst becomes one
            # batch. The window starts at the first hand rather than restarting
            # on each, so continuous traffic cannot postpone it indefinitely.
            self._pending_hands: list[str] = []
            self._hand_batch_timer = QTimer(self)
            self._hand_batch_timer.setSingleShot(True)
            self._hand_batch_timer.setInterval(HAND_BATCH_INTERVAL_MS)
            self._hand_batch_timer.timeout.connect(self._drain_pending_hands)

            # Stats persistence initialization
            self.stats_persistence = get_hud_stats_persistence()

            # Smart HUD manager initialization
            self.smart_hud_manager = get_smart_hud_manager()

            # Initialization ZMQ avec QThread
            log.info("Initializing ZMQ communication...")
            self.zmq_receiver: ZMQReceiver | None = ZMQReceiver(parent=self)
            log.info("ZMQ receiver created successfully")
            self.zmq_receiver.message_received.connect(self.handle_message)
            self.zmq_worker: ZMQWorker | None = ZMQWorker(self.zmq_receiver)
            self.zmq_worker.error_occurred.connect(self.handle_worker_error)
            log.info("Starting ZMQ worker...")
            self.zmq_worker.start()

            # Main window
            self.init_main_window()

            log.debug("Main window initialized and shown.")
        except Exception:
            log.exception("Error during HudMain initialization")
            raise

    def _check_macos_permissions(self) -> None:
        """Diagnose macOS privacy permissions required for table detection.

        Screen Recording is needed for Quartz to expose window titles;
        Accessibility/Automation is needed for the AppleScript fallback used by
        Electron clients (e.g. Winamax). Logs a clear, actionable message for any
        missing permission. Set ``FPDB_REQUEST_MACOS_PERMISSIONS=1`` to also
        trigger the native prompts and open the relevant System Settings panes.
        """
        try:
            from fpdb.infrastructure.platform import permissions
        except Exception:
            log.debug("macOS permissions preflight unavailable", exc_info=True)
            return

        status = permissions.get_status()
        if status.all_granted:
            log.info("macOS permissions OK (Screen Recording + Accessibility granted)")
            return

        for message in permissions.describe_missing(status):
            log.warning(message)

        if os.getenv("FPDB_REQUEST_MACOS_PERMISSIONS") == "1":
            if not status.screen_recording:
                log.info("Requesting Screen Recording permission (native prompt)...")
                permissions.request_screen_recording_permission()
                permissions.open_screen_recording_settings()
            if not status.accessibility:
                log.info("Requesting Accessibility permission (native prompt)...")
                permissions.request_accessibility_permission(prompt=True)
                permissions.open_accessibility_settings()
            log.warning("After granting permissions, restart FPDB for them to take effect.")

    def handle_worker_error(self, error_message: str) -> None:
        """Handle errors from the ZMQ worker."""
        log.error("ZMQWorker encountered an error: %s", error_message)

    def init_main_window(self) -> None:
        """Initialize the main application window."""
        self.main_window = HudMainWindow(self.close_event_handler)
        if self.options.xloc is not None or self.options.yloc is not None:
            x = int(self.options.xloc) if self.options.xloc is not None else self.main_window.x()
            y = int(self.options.yloc) if self.options.yloc is not None else self.main_window.y()
            self.main_window.move(x, y)
        self.main_window.destroyed.connect(lambda: self.destroy())
        self.vb = QVBoxLayout()
        self.vb.setContentsMargins(2, 0, 2, 0)
        self.main_window.setLayout(self.vb)
        self.label = QLabel("Closing this window will exit from the HUD.")
        self.vb.addWidget(self.label)
        self.main_window.setWindowTitle("HUD Main Window")
        cards_path = Path(self.config.graphics_path) / "tribal.jpg"
        if cards_path.exists():
            self.main_window.setWindowIcon(QIcon(str(cards_path)))

        # Timer for periodically checking tables
        self.check_tables_timer = QTimer(self)
        self.check_tables_timer.timeout.connect(self.check_tables)
        self.check_tables_timer.start(800)
        self.main_window.show()

    def close_event_handler(self, event: QCloseEvent) -> None:
        """Handle the close event of the main window."""
        self.destroy()
        event.accept()

    def handle_message(self, hand_id: str) -> None:
        """Handle an incoming message from the ZMQ receiver."""
        # This method will be called in the main thread
        log.info("HUD RECEIVED MESSAGE - hand_id: %s", hand_id)

        # Defensive rollback: ensure the PostgreSQL connection is not stuck in
        # an aborted transaction state from a previous error.  Under PostgreSQL,
        # any single failed query permanently blocks every subsequent query on
        # the same connection until an explicit ROLLBACK is issued.  Issuing a
        # rollback on a clean connection is a harmless no-op.
        try:
            if getattr(self, "db_connection", None):
                self.db_connection.connection.rollback()
        except Exception:
            log.debug("Pre-message rollback failed (connection may be closed)")

        try:
            self._enqueue_hand(hand_id)
            log.debug("Hand %s queued for the next batch", hand_id)
        except Exception as e:
            log.exception("Error handling message for hand_id %s: %s", hand_id, e)
            try:
                if getattr(self, "db_connection", None):
                    self.db_connection.connection.rollback()
                    log.info("Successfully rolled back database transaction after error")
            except Exception as roll_err:
                log.exception("Failed to rollback transaction after error: %s", roll_err)

    def destroy(self) -> None:
        """Destroy the application and clean up resources."""
        if self._shutdown_started:
            return
        self._shutdown_started = True

        # A batch still waiting would fire against a torn-down connection.
        batch_timer = getattr(self, "_hand_batch_timer", None)
        if batch_timer is not None:
            with contextlib.suppress(RuntimeError):
                batch_timer.stop()
        self._pending_hands = []

        zmq_worker = getattr(self, "zmq_worker", None)
        if zmq_worker is not None:
            with contextlib.suppress(RuntimeError):
                zmq_worker.stop()
            self.zmq_worker = None

        zmq_receiver = getattr(self, "zmq_receiver", None)
        if zmq_receiver is not None:
            with contextlib.suppress(RuntimeError):
                zmq_receiver.close()
            self.zmq_receiver = None

        log.info("Quitting normally")
        QCoreApplication.quit()

    def _handle_table_status(self, hud: Hud.Hud) -> None:
        """Handle status changes for a single table."""
        status = hud.table.check_table()
        if status == "client_destroyed":
            self.client_destroyed(None, hud)
        elif status == "client_moved":
            self.client_moved(None, hud)
        elif status == "client_resized":
            self.client_resized(None, hud)

    def _topify_mac_windows(self) -> None:
        """Bring all HUD windows to the top on macOS."""
        if self.config.os_family == "Mac":
            for hud in self.hud_dict.values():
                for aw in hud.aux_windows:
                    if not hasattr(aw, "m_windows"):
                        continue
                    for w in aw.m_windows.values():
                        if w.isVisible():
                            hud.table.topify(w)

    def check_tables(self) -> None:
        """Periodically check the status of poker tables."""
        # Skip while a HUD window is being dragged: the geometry poll (an
        # expensive AppleScript scan on macOS) and the window re-raise (topify)
        # both run on the UI thread and re-order the dragged window, which makes
        # the drag stutter. Table geometry changes are picked up on the next tick.
        if Aux_Base.is_drag_active():
            return
        if not self.hud_dict:
            # log.info("Waiting for hands ...")
            pass
        for hud in list(self.hud_dict.values()):
            self._handle_table_status(hud)
        self._topify_mac_windows()

    def client_moved(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client moved event."""
        log.debug("Client moved event")
        self.idle_move(hud)

    def client_resized(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client resized event."""
        log.debug("Client resized event")
        self.idle_resize(hud)

    def client_destroyed(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client destroyed event."""
        log.debug("Client destroyed event")
        self.clear_table_stat_set_override(hud.table.key)
        self.kill_hud(None, hud.table.key)

    def table_title_changed(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the table title changed event."""
        table_key = hud.table.key
        new_title = getattr(hud.table, "title", "")

        # Use smart manager to determine if title change is significant
        if self.smart_hud_manager.has_table_title_changed(table_key, new_title):
            should_restart, reason = self.smart_hud_manager.should_restart_hud(
                table_key,
                RestartReason.TABLE_CLOSED,
            )

            if should_restart:
                log.info(f"Table title changed significantly, restarting HUD: {reason}")
                self.smart_hud_manager.record_restart(table_key, f"Title change: {reason}")
                self.kill_hud(None, table_key)
            else:
                log.debug(f"Table title changed but restart not needed: {reason}")
        else:
            log.debug("Table title change detected but not significant enough for restart")

    def table_is_stale(self, hud: Hud.Hud) -> None:
        """Handle a stale table by killing the HUD."""
        log.debug("Moved to a new table, killing current HUD")
        self.clear_table_stat_set_override(hud.table.key)
        self.kill_hud(None, hud.table.key)

    def kill_hud(self, _event: QEvent | None, table: str) -> None:
        """Kill the HUD for a specific table."""
        log.debug("kill_hud event")
        self.idle_kill(table)

    def blacklist_hud(self, _event: QEvent | None, table: str) -> None:
        """Blacklist a HUD and kill it."""
        log.debug("blacklist_hud event")
        self.blacklist.append(self.hud_dict[table].tablenumber)
        self.clear_table_stat_set_override(table)
        self.idle_kill(table)

    def set_table_stat_set_override(
        self,
        table: str,
        poker_game: str,
        game_type: str,
        stat_set: str,
    ) -> None:
        """Remember a table-local HUD profile for this capture session."""
        if stat_set not in self.config.stat_sets:
            raise KeyError(f"unknown stat set: {stat_set}")
        self._table_stat_set_overrides[table] = (poker_game, game_type, stat_set)
        log.info("Table-local HUD profile: table=%s profile=%s", table, stat_set)

    def get_table_stat_set_override(self, table: str, poker_game: str, game_type: str) -> str | None:
        """Return a compatible table-local profile override, if one exists."""
        override = self._table_stat_set_overrides.get(table)
        if override is None:
            return None
        override_game, override_type, stat_set = override
        if (override_game, override_type) != (poker_game, game_type):
            return None
        return stat_set

    def clear_table_stat_set_override(self, table: str) -> None:
        """Forget the local profile when the underlying table is gone."""
        self._table_stat_set_overrides.pop(table, None)

    def create_HUD(self, args: HUDCreationArgs) -> None:
        """Create a new HUD for a table."""
        log.debug("Creating HUD for table %s and hand %s", args.temp_key, args.new_hand_id)
        self.hud_dict[args.temp_key] = Hud.Hud(
            self,
            args.table,
            args.max_seats,
            args.poker_game,
            args.game_type,
            self.config,
        )
        self.hud_dict[args.temp_key].table_name = args.temp_key
        self.hud_dict[args.temp_key].stat_dict = args.stat_dict
        self.hud_dict[args.temp_key].cards = args.cards
        self.hud_dict[args.temp_key].max = args.max_seats

        args.table.hud = self.hud_dict[args.temp_key]

        self.hud_dict[args.temp_key].hud_params["new_max_seats"] = None  # trigger for seat layout change

        for aw in self.hud_dict[args.temp_key].aux_windows:
            aw.update_data(args.new_hand_id, self.db_connection)

        self.idle_create(args)
        log.debug("HUD for table %s created successfully.", args.temp_key)

    def update_HUD(self, new_hand_id: str, table_name: str, config: Configuration.Config) -> None:
        """Update an existing HUD."""
        log.debug("Updating HUD for table %s and hand %s", table_name, new_hand_id)
        self.idle_update(new_hand_id, table_name, config)

    def _initialize_hero_data(self) -> None:
        """Initialize hero data from the configuration."""
        self.hero: dict[int, str] = {}
        self.hero_ids: dict[int, int] = {}
        enabled_sites = self.config.get_supported_sites()
        if not enabled_sites:
            log.error("No enabled sites found")
            self.db_connection.connection.rollback()
            self.destroy()
            return

        for site in enabled_sites:
            if result := self.db_connection.get_site_id(site):
                site_id = result[0][0]
                self.hero[site_id] = self.config.supported_sites[site].screen_name
                self.hero_ids[site_id] = self.db_connection.get_player_id(self.config, site, self.hero[site_id])
                if self.hero_ids[site_id] is None:
                    self.hero_ids[site_id] = -1

            for db_site in self._get_db_site_aliases(site):
                if db_site == site:
                    continue
                if result := self.db_connection.get_site_id(db_site):
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    self.hero_ids[site_id] = self.db_connection.get_player_id(self.config, db_site, self.hero[site_id])
                    if self.hero_ids[site_id] is None:
                        self.hero_ids[site_id] = -1

    def _get_db_site_aliases(self, config_site: str) -> tuple[str, ...]:
        """Return database site names covered by one HUD config site."""
        if config_site == "PokerStars":
            return (
                "PokerStars",
                "PokerStars.COM",
                "PokerStars.FR",
                "PokerStars.IT",
                "PokerStars.ES",
                "PokerStars.PT",
                "PokerStars.EU",
                "PokerStars.DE",
            )
        return (config_site,)

    def _resolve_hud_config_site(self, db_site_name: str, enabled_sites: list[str]) -> str:
        """Map regional DB site names to the HUD config site used for layout/detection."""
        if db_site_name in enabled_sites:
            return db_site_name
        if db_site_name.startswith("PokerStars.") and "PokerStars" in enabled_sites:
            return "PokerStars"
        return db_site_name

    def _resolve_hud_poker_game(self, poker_game: str) -> str:
        """Map parser game categories to a HUD-supported game profile."""
        aliases = {
            "fusion": "holdem",
        }
        return aliases.get(poker_game, poker_game)

    def _get_table_info(self, hand_id: str) -> tuple | None:
        """Get table information from cache or database."""
        if hand_id in self.cache:
            log.debug("Using cached data for hand %s", hand_id)
            return self.cache[hand_id]

        log.debug("Data not found in cache for hand_id: %s", hand_id)
        try:
            table_info = self.db_connection.get_table_info(hand_id)
        except Exception:
            log.exception("Database error while processing hand %s", hand_id)
            try:
                self.db_connection.connection.rollback()
            except Exception:
                log.debug("Rollback failed after table-info lookup error", exc_info=True)
            return None
        else:
            # Don't cache a missing result: the hand may simply not be committed
            # to the DB yet, and caching None would skip it forever on retries.
            if table_info is not None:
                self.cache[hand_id] = table_info
            return table_info

    def _get_temp_key(self, game_type: str, tour_number: str, tab_number: str, table_name: str) -> str:
        """Generate a temporary key for the table."""
        if game_type != "tour":
            return table_name
        try:
            log.debug("creating temp_key for tour")
            tab_number_suffix = tab_number.rsplit(" ", 1)[-1]
        except ValueError:
            log.exception("Both tab_number and table_name not working")
            return table_name
        else:
            return f"{tour_number} Table {tab_number_suffix}"

    def _handle_tournament_table_changes(self, game_type: str, temp_key: str, tour_number: str) -> bool:
        """Handle table changes in tournaments. Returns True if stale."""
        if game_type != "tour":
            return False

        if temp_key in self.hud_dict:
            if self.hud_dict[temp_key].table.has_table_title_changed(self.hud_dict[temp_key]):
                log.debug("table has been renamed")
                self.table_is_stale(self.hud_dict[temp_key])
                return True
        else:
            for k in list(self.hud_dict.keys()):
                # The key of a tournament HUD is "<tournament> Table <n>", so
                # the tournament is compared whole. A prefix match made
                # tournament 116 the same as 1160391.
                if k.split(" Table ", 1)[0] == tour_number:
                    log.debug("check if the tournament number is in the hud_dict under a different table")
                    self.table_is_stale(self.hud_dict[k])
                    # continue checking other tables
        return False

    def _handle_hud_reconfiguration(self, temp_key: str, poker_game: str) -> tuple[str, int | None]:
        """Handle HUD reconfiguration for max seats and game type changes."""
        if temp_key not in self.hud_dict:
            return poker_game, None

        hud_poker_game = self._resolve_hud_poker_game(poker_game)
        hud = self.hud_dict[temp_key]
        current_state = {
            "poker_game": getattr(hud, "poker_game", ""),
            "max_seats": getattr(hud, "max", 0),
        }

        # Check for max seats change
        with contextlib.suppress(Exception):
            newmax = hud.hud_params.get("new_max_seats")
            if newmax and hud.max != newmax:
                new_state = current_state.copy()
                new_state["max_seats"] = newmax

                should_restart, reason = self.smart_hud_manager.should_restart_hud(
                    temp_key,
                    RestartReason.MAX_SEATS_CHANGE,
                    current_state,
                    new_state,
                )

                if should_restart:
                    log.info(f"Smart restart for max seats change: {reason}")
                    self.smart_hud_manager.record_restart(temp_key, f"Max seats: {reason}")
                    self.kill_hud(None, temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
                    hud.hud_params["new_max_seats"] = None
                    return poker_game, int(newmax)
                log.info(f"Skipping restart for max seats change: {reason}")

        # Check for game type change
        if hud.poker_game != hud_poker_game:
            new_state = current_state.copy()
            new_state["poker_game"] = hud_poker_game

            should_restart, reason = self.smart_hud_manager.should_restart_hud(
                temp_key,
                RestartReason.GAME_TYPE_CHANGE,
                current_state,
                new_state,
            )

            if should_restart:
                log.info(f"Smart restart for game type change: {reason}")
                self.smart_hud_manager.record_restart(temp_key, f"Game type: {reason}")
                with contextlib.suppress(Exception):
                    self.kill_hud(None, temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
            else:
                log.info(f"Skipping restart for game type change: {reason}")

        return hud_poker_game, None

    def _update_existing_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
    ) -> None:
        """Update an existing HUD with new hand data."""
        log.debug("update hud for hand %s", new_hand_id)
        hud = self.hud_dict[temp_key]
        self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
        stat_dict = self.db_connection.get_stats_from_hand(
            new_hand_id,
            game_type,
            hud.hud_params,
            self.hero_ids[site_id],
            num_seats,
        )
        log.debug("got stats for hand %s", new_hand_id)

        self._merge_positions(stat_dict, new_hand_id)
        try:
            hud.stat_dict = stat_dict
        except KeyError:
            log.exception("hud_dict[%s] was not found", temp_key)
            return

        hud.seat_players = self._seat_players(new_hand_id)
        self._set_table_stats(hud, new_hand_id)
        hud.cards = self.get_cards(new_hand_id, hud.poker_game)
        for aw in hud.aux_windows:
            aw.update_data(new_hand_id, self.db_connection)
        self.update_HUD(new_hand_id, temp_key, self.config)
        log.debug("hud updated for table %s and hand %s", temp_key, new_hand_id)

    def _enqueue_hand(self, hand_id: str) -> None:
        """Hold a hand briefly so the tables dealing alongside it join the batch."""
        self._pending_hands.append(hand_id)
        if not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _latest_hand_per_table(self, hand_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        """Reduce a batch to the last hand of each table.

        Processing an earlier hand of a table only to overwrite it with the
        next one is work nobody sees, and the HUD shows the latest hand either
        way. Hands whose table cannot be resolved are handed back untouched so
        they take the normal path and log what they normally log.
        """
        latest: dict[str, str] = {}
        unresolved: list[str] = []
        for hand_id in hand_ids:
            table_info = self._get_table_info(hand_id)
            if table_info is None:
                unresolved.append(hand_id)
                continue
            table_name, game_type = table_info[0], table_info[3]
            tour_number, tab_number = table_info[8], table_info[9]
            latest[self._get_temp_key(game_type, tour_number, tab_number, table_name)] = hand_id
        return latest, unresolved

    def _drain_pending_hands(self) -> None:
        """Process one batch of hands, then refresh every other HUD once.

        The refresh is what this exists for: it used to run per hand, so a
        round of twelve tables cost twelve refreshes of twelve HUDs. One batch
        means one refresh each.
        """
        pending, self._pending_hands = self._pending_hands, []
        if not pending:
            return

        latest, unresolved = self._latest_hand_per_table(pending)
        log.debug("Draining %d hand(s) into %d table(s)", len(pending), len(latest))

        refreshed: set[str] = set()
        for hand_id in [*latest.values(), *unresolved]:
            try:
                served = self.read_stdin(hand_id)
            except Exception:
                log.exception("Error processing hand %s", hand_id)
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()
            else:
                if served is not None:
                    refreshed.add(served)

        # Only the tables actually brought up to date are left out of the
        # statistics refresh; one that failed still needs it.
        self._refresh_other_huds(refreshed)

    def _seat_players(self, hand_id: str) -> dict:
        """Seat players for a hand, read from the database once."""
        key = ("seats", hand_id)
        cached = self._hand_players.get(key)
        if cached is None:
            cached = self.db_connection.get_seat_players(hand_id)
            self._hand_players[key] = cached
        return cached

    def _hand_positions(self, hand_id: str) -> dict:
        """Each player's position in a hand, read from the database once."""
        key = ("positions", hand_id)
        cached = self._hand_players.get(key)
        if cached is None:
            cached = self.db_connection.get_hand_positions(hand_id)
            self._hand_players[key] = cached
        return cached

    def _refresh_secondary_hud(
        self,
        hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
    ) -> None:
        """Update a HUD whose own table has not dealt a new hand.

        Only the aggregated statistics can have moved: the seats, the cards and
        the table stats all describe this table's own last hand, which is the
        hand being reused here, so re-reading them would return what the HUD
        already holds. Skipping them matters because this runs once per open
        table per hand dealt at any table -- the cost of the full update would
        grow with the square of the number of tables, on the path that has to
        finish before the player acts.

        The positions are re-read because the statistics dictionary is built
        afresh and they live inside it.

        The repaint deliberately does not go through update_HUD. That path
        calls Hud.update, which rebuilds the hand from the database through
        hand_factory, re-reads the cards, and refreshes the aux windows a
        second time -- all of it describing the same unchanged hand. The aux
        windows read hud.stat_dict when they redraw, so handing them the new
        one and asking them to redraw is the whole job.
        """
        hud = self.hud_dict[temp_key]
        self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
        stat_dict = self.db_connection.get_stats_from_hand(
            hand_id,
            game_type,
            hud.hud_params,
            self.hero_ids[site_id],
            num_seats,
        )
        self._merge_positions(stat_dict, hand_id)
        hud.stat_dict = stat_dict
        for aux in hud.aux_windows:
            try:
                aux.refresh_stats(hand_id)
            except Exception:
                log.exception("Error redrawing aux window of table %s", temp_key)
        log.debug("secondary hud redrawn for table %s using hand %s", temp_key, hand_id)

    def _refresh_other_huds(self, updated_tables: set[str]) -> None:
        """Refresh every active HUD except the tables this batch already updated.

        HUD statistics are aggregated globally, but each HUD must keep using
        its own latest hand for seats, cards, positions, and game context.
        Reusing that table's last processed hand makes all open HUDs observe
        the latest HudCache state without mixing table-local data.

        A secondary HUD is best-effort: one stale or failing table must not
        prevent the remaining tables from refreshing.
        """
        for table_name in list(self.hud_dict):
            if table_name in updated_tables:
                continue

            last_hand_id = self._last_processed_hands.get(table_name)
            if last_hand_id is None:
                log.debug("Skipping global HUD refresh for %s: no last hand", table_name)
                continue

            table_info = self._get_table_info(last_hand_id)
            if table_info is None:
                log.warning(
                    "Skipping global HUD refresh for table %s: no table info for hand %s",
                    table_name,
                    last_hand_id,
                )
                continue

            game_type = table_info[3]
            site_id = table_info[5]
            num_seats = table_info[7]
            try:
                self._refresh_secondary_hud(
                    last_hand_id,
                    table_name,
                    game_type,
                    site_id,
                    num_seats,
                )
            except Exception:
                log.exception(
                    "Global HUD refresh failed for table %s using hand %s",
                    table_name,
                    last_hand_id,
                )
                # PostgreSQL rejects every later query after one statement
                # fails until the transaction is explicitly rolled back.
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()

    def _create_new_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        table_info: tuple,
        site_id: int,
        num_seats: int,
        hud_site_name: str | None = None,
    ) -> None:
        """Create a new HUD for a table."""
        (table_name, max_seats, poker_game, game_type, _, _, site_name, _, tour_number, tab_number, tourney_name) = (
            table_info
        )
        hud_site_name = hud_site_name or site_name
        hud_poker_game = self._resolve_hud_poker_game(poker_game)
        if self.config.get_supported_games_parameters(hud_poker_game, game_type) is None:
            log.error(
                "HUD creation skipped for hand %s table=%s: no HUD profile for poker_game=%s (mapped from %s) game_type=%s",
                new_hand_id,
                table_name,
                hud_poker_game,
                poker_game,
                game_type,
            )
            return

        log.debug("create new hud for hand %s", new_hand_id)
        self.db_connection.init_hud_stat_vars(self.hud_params["hud_days"], self.hud_params["h_hud_days"])
        stat_dict = self.db_connection.get_stats_from_hand(
            new_hand_id,
            game_type,
            self.hud_params,
            self.hero_ids[site_id],
            num_seats,
        )
        log.debug("got stats for hand %s", new_hand_id)

        # Try to load cached stats to preserve data across restarts
        cached_stats = self.stats_persistence.load_hud_stats(temp_key)
        if cached_stats:
            log.info(f"Found cached HUD stats for table {temp_key}, merging with current data")
            merged_data = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
            stat_dict = merged_data.get("stat_dict", stat_dict)
            log.debug("Merged cached stats with fresh database stats")

        self._merge_positions(stat_dict, new_hand_id)
        if not any(stat_dict[key]["screen_name"] == self.hero[site_id] for key in stat_dict):
            log.warning(
                "HUD not created for hand %s table=%s: hero %r (site_id=%s) not among players %s",
                new_hand_id,
                table_name,
                self.hero.get(site_id),
                site_id,
                sorted(stat_dict[key]["screen_name"] for key in stat_dict),
            )
            return

        cards = self.get_cards(new_hand_id, poker_game)
        table_kwargs = {
            "table_name": table_name,
            "tournament": tour_number,
            "table_number": tab_number,
            "tourney_name": tourney_name,
        }
        tablewindow = self.Tables.Table(self.config, hud_site_name, **table_kwargs)

        if tablewindow.number is None:
            if game_type == "tour":
                table_name = f"{tour_number} {tab_number}"
            log.error(
                "HUD create: table name %s not found for db_site=%s hud_site=%s, skipping.",
                table_name,
                site_name,
                hud_site_name,
            )
            return
        if tablewindow.number in self.blacklist:
            log.warning(
                "HUD skipped for hand %s table=%s: window %s is blacklisted",
                new_hand_id,
                table_name,
                tablewindow.number,
            )
            return

        # One WARNING per HUD creation so the log always records WHICH window
        # was matched: user reports of "table not detected" are impossible to
        # diagnose without the matched hwnd/title (or their absence).
        log.warning(
            "HUD attach: table=%r site=%s hwnd=%s title=%r geometry=(%s,%s %sx%s)",
            temp_key,
            hud_site_name,
            tablewindow.number,
            getattr(tablewindow, "title", ""),
            tablewindow.x,
            tablewindow.y,
            tablewindow.width,
            tablewindow.height,
        )

        tablewindow.key = temp_key
        tablewindow.max = max_seats
        tablewindow.site = hud_site_name

        # Register table state with smart HUD manager
        self.smart_hud_manager.update_table_state(
            temp_key,
            hud_poker_game,
            game_type,
            max_seats,
            hud_site_name,
            table_name,
        )

        if hasattr(tablewindow, "number"):
            args = HUDCreationArgs(
                new_hand_id=new_hand_id,
                table=tablewindow,
                temp_key=temp_key,
                max_seats=max_seats,
                poker_game=hud_poker_game,
                game_type=game_type,
                stat_dict=stat_dict,
                cards=cards,
            )
            self.create_HUD(args)
            if args.temp_key in self.hud_dict:
                self.hud_dict[args.temp_key].seat_players = self._seat_players(new_hand_id)
                self._set_table_stats(self.hud_dict[args.temp_key], new_hand_id)
        else:
            log.error('Table "%s" no longer exists', table_name)

    def read_stdin(self, new_hand_id: str) -> str | None:
        """Process one hand and return the table whose HUD now shows it.

        The answer is what tells the batch which tables still need the
        statistics-only refresh: a table that was skipped, or whose HUD was
        killed as stale, has not been brought up to date and must not be
        treated as though it had.
        """
        log.debug("Processing new hand id: %s", new_hand_id)
        self._initialize_hero_data()

        if not new_hand_id:
            return None

        table_info = self._get_table_info(new_hand_id)
        if not table_info:
            log.warning(
                "HUD skipped for hand %s: table info not found in DB (hand not committed yet?)",
                new_hand_id,
            )
            return None

        (
            table_name,
            max_seats,
            poker_game,
            game_type,
            fast,
            site_id,
            site_name,
            num_seats,
            tour_number,
            tab_number,
            tourney_name,
        ) = table_info

        # A cash-table HUD is keyed directly by table_name.  Legacy/corrupt
        # rows may have an empty name; accepting one creates a ghost HUD shown
        # as "<site> -" and can also make unrelated blank rows share a HUD.
        if not isinstance(table_name, str) or not table_name.strip():
            log.warning(
                "HUD creation skipped for hand %s: missing table name (site=%s)",
                new_hand_id,
                site_name,
            )
            return None

        enabled_sites = self.config.get_supported_sites()
        hud_site_name = self._resolve_hud_config_site(site_name, enabled_sites)
        aux_disabled_sites = [
            site for site in enabled_sites if not self.config.get_site_parameters(site)["aux_enabled"]
        ]
        if fast or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            log.warning(
                "HUD creation skipped for hand %s table=%s db_site=%s hud_site=%s: fast=%s, aux_disabled=%s, site_enabled=%s",
                new_hand_id,
                table_name,
                site_name,
                hud_site_name,
                fast,
                hud_site_name in aux_disabled_sites,
                hud_site_name in enabled_sites,
            )
            return None

        temp_key = self._get_temp_key(game_type, tour_number, tab_number, table_name)
        log.debug("Generated temp_key: %s for table: %s", temp_key, table_name)

        # Idempotency: skip a hand already processed for this table (duplicate
        # ZMQ delivery), so create/update runs exactly once per hand.
        if self._last_processed_hands.get(temp_key) == new_hand_id:
            log.debug("Skipping already processed hand ID %s for table %s", new_hand_id, temp_key)
            return None
        self._last_processed_hands[temp_key] = new_hand_id

        if self._handle_tournament_table_changes(game_type, temp_key, tour_number):
            return None  # Stale table was handled

        poker_game, new_max_seats = self._handle_hud_reconfiguration(temp_key, poker_game)
        if new_max_seats:
            # Re-create the HUD with the new max seats
            self.kill_hud(None, temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, num_seats, hud_site_name)
            return temp_key

        if temp_key in self.hud_dict:
            log.debug("Updating existing HUD for temp_key: %s", temp_key)
            self._update_existing_hud(new_hand_id, temp_key, game_type, site_id, num_seats)
        else:
            log.debug("Creating new HUD for temp_key: %s", temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, num_seats, hud_site_name)
        return temp_key

    def _set_table_stats(self, hud: Hud.Hud, hand_id: str) -> None:
        """Compute table-scope stats once per hand and cache them on the hud.

        Keeps the per-label HUD update off the database: the table stat widgets
        read hud.table_stats instead of querying on the UI thread.
        """
        try:
            hud.table_stats = {
                "live_min_stack_bb": self.db_connection.get_table_min_stack_bb(hand_id),
            }
        except Exception:
            log.exception("could not compute table stats for hand %s", hand_id)
            hud.table_stats = {}

    def _merge_positions(self, stat_dict: dict, hand_id: str) -> None:
        """Attach each player's current-hand position to stat_dict.

        Enables position-conditional HUD panels (e.g. show the SB panel only for
        the player in the small blind this hand). Best-effort: failures are
        logged and leave stat_dict unchanged.
        """
        try:
            positions = self._hand_positions(hand_id)
        except Exception:
            log.exception("could not load positions for hand %s", hand_id)
            return
        for pid, pos in positions.items():
            if pid in stat_dict:
                stat_dict[pid]["position"] = pos
        self._advance_live_positions(stat_dict, hand_id)

    def _advance_live_positions(self, stat_dict: dict, hand_id: str) -> None:
        """Estimate each player's CURRENT-hand position for positional panels.

        An import-driven HUD only knows the *last imported* hand's position, but
        the table has already moved to the next hand, so a positional panel would
        be one hand stale (a BB villain still showing the SB panel). Advance the
        button one seat from the last hand and store the result as live_position;
        block_visible prefers it over the imported position.

        Best-effort: it assumes the same seated players next hand (true between
        Spin&Go hands until someone busts), and leaves live_position unset when
        the button can't be found so the caller falls back to the imported one.
        """
        try:
            seat_players = self._seat_players(hand_id)
        except Exception:
            return
        if len(seat_players) < 2:
            return
        seats = sorted(seat_players)
        n = len(seats)
        btn_codes = {"0", "BTN", "BU", "D", "BUTTON"}
        btn_seat = None
        for seat in seats:
            pid = seat_players[seat].get("player_id")
            pos = stat_dict.get(pid, {}).get("position")
            if pos is not None and str(pos).strip().upper() in btn_codes:
                btn_seat = seat
                break
        if btn_seat is None:
            return
        # Button moves one occupied seat clockwise; SB/BB follow, then seats
        # after the BB. Codes use DerivedStats' convention (0=BTN, S, B, 1..).
        new_btn = (seats.index(btn_seat) + 1) % n
        codes = ["0", "S", "B"] + [str(i) for i in range(1, n)]
        for k in range(n):
            seat = seats[(new_btn + k) % n]
            pid = seat_players[seat].get("player_id")
            if pid in stat_dict:
                stat_dict[pid]["live_position"] = codes[k]

    def get_cards(self, new_hand_id: str, poker_game: str) -> dict[str, Any]:
        """Get card data for a given hand."""
        cards = self.db_connection.get_cards(new_hand_id)
        if poker_game in ["holdem", "omahahi", "omahahilo"]:
            comm_cards = self.db_connection.get_common_cards(new_hand_id)
            cards["common"] = comm_cards["common"]
        return cards

    def idle_move(self, hud: Hud.Hud) -> None:
        """Handle the idle move event."""
        try:
            # Real geometry change: bump the generation so block windows re-place.
            hud.geometry_generation += 1
            hud.move_table_position()
            for aw in hud.aux_windows:
                aw.move_windows()
        except Exception:
            log.exception("Error moving HUD for table: %s.", hud.table.title)

    def idle_resize(self, hud: Hud.Hud) -> None:
        """Handle the idle resize event."""
        try:
            # Real geometry change: bump the generation so block windows re-place.
            hud.geometry_generation += 1
            hud.resize_windows()
            for aw in hud.aux_windows:
                aw.resize_windows()
        except Exception:
            log.exception("Error resizing HUD for table: %s.", hud.table.title)

    def idle_kill(self, table: str) -> None:
        """Handle the idle kill event."""
        try:
            if table in self.hud_dict:
                # Save HUD stats before killing to prevent data loss
                hud = self.hud_dict[table]
                hud_data = {
                    "stat_dict": getattr(hud, "stat_dict", {}),
                    "cards": getattr(hud, "cards", {}),
                    "poker_game": getattr(hud, "poker_game", ""),
                    "game_type": getattr(hud, "game_type", ""),
                    "max_seats": getattr(hud, "max", 0),
                    "hud_params": getattr(hud, "hud_params", {}),
                    "last_hand_id": getattr(hud, "last_hand_id", ""),
                }

                if self.stats_persistence.save_hud_stats(table, hud_data):
                    log.info(f"HUD stats saved before restart for table: {table}")
                else:
                    log.warning(f"Failed to save HUD stats for table: {table}")

                # Take the label out of the main window and destroy it. setParent(None)
                # only detached it, which turns a QLabel into a top-level widget --
                # its own window, captioned with its text ("SealsWithClubs - <tourney>
                # Table 3"). Killing a HUD must leave nothing of it behind: in a
                # tournament the hero is moved from table to table, and each move left
                # one more of these behind.
                label = self.hud_dict[table].tablehudlabel
                self.vb.removeWidget(label)
                label.hide()
                label.deleteLater()
                self.hud_dict[table].tablehudlabel = None
                self.hud_dict[table].kill()
                del self.hud_dict[table]
            self.main_window.resize(1, 1)
        except Exception:
            log.exception("Error killing HUD for table: %s.", table)

    def idle_create(self, args: HUDCreationArgs) -> None:
        """Handle the idle create event."""
        try:
            newlabel = QLabel(f"{args.table.site} - {args.temp_key}")
            log.debug("adding label %s", newlabel.text())
            self.vb.addWidget(newlabel)

            self.hud_dict[args.temp_key].tablehudlabel = newlabel
            self.hud_dict[args.temp_key].tablenumber = args.table.number
            self.hud_dict[args.temp_key].create(args.new_hand_id, self.config, args.stat_dict)
            for aux_index, m in enumerate(self.hud_dict[args.temp_key].aux_windows):
                try:
                    m.create()
                    log.debug("idle_create new_hand_id %s", args.new_hand_id)
                    m.update_gui(args.new_hand_id)
                except Exception:
                    # Isolate a failing aux window so the others still get built.
                    log.exception(
                        "HUD create: aux_window index=%d class=%s failed (table=%s, hand=%s); skipping it",
                        aux_index,
                        type(m).__name__,
                        args.temp_key,
                        args.new_hand_id,
                    )
            hud_trace("idle_create OK: table=%s hand=%s", args.temp_key, args.new_hand_id)

        except Exception:
            log.exception("Error creating HUD for hand %s.", args.new_hand_id)

    def idle_update(self, new_hand_id: str, table_name: str, config: Configuration.Config) -> None:
        """Show a new hand on one table.

        Hud.update owns the new-hand cycle: it rebuilds the hand, re-reads the
        cards, and refreshes every aux window, keeping one failing window from
        stopping the rest. This used to refresh them a second time afterwards,
        which drew each of them twice -- and for the mucked-cards windows that
        is not merely wasted work, since theirs appends a row to the list and
        re-shows the cards, so every hand was replayed to the player.
        """
        try:
            log.debug("idle_update entered for %s %s", table_name, new_hand_id)
            hud = self.hud_dict[table_name]
            hud.update(new_hand_id, config)
            hud_trace(
                "idle_update OK: table=%s hand=%s aux_windows=%d",
                table_name,
                new_hand_id,
                len(hud.aux_windows),
            )
        except Exception:
            log.exception("Error updating HUD for hand %s (table=%s).", new_hand_id, table_name)


if __name__ == "__main__":
    if os.getenv("FPDB_HUD_TRACE") == "1":
        import logging

        trace_log = logging.getLogger("hud_trace")
        trace_log.setLevel(logging.DEBUG)
        if not trace_log.handlers:
            log_dir = os.path.join(os.path.expanduser("~"), ".fpdb")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "HUD_trace.log")
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            trace_log.addHandler(handler)
            trace_log.propagate = False
            trace_log.info("HUD Trace Log Initialized")

            # NB: diagnostics go through this "hud_trace" logger, never through
            # "hud_main". get_logger() re-applies the level saved in
            # ~/fpdb_logs/logger_config.json on every call, and "hud_main" is saved
            # at ERROR -- which is why the HUD's INFO/WARNING traces never reached
            # HUD-log.txt. "hud_trace" is unregistered, so this handler survives.
            trace_log.info("HUD trace channel active (bypasses fpdb logger registry)")

    (options, argv) = Options.fpdb_options()

    app = QApplication([])
    apply_stylesheet(app, theme="dark_purple.xml")

    hm = HudMain(options, db_name=options.dbname)

    app.exec()
