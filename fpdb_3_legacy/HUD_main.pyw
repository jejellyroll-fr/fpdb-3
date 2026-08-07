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

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from optparse import Values
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import zmq as _zmq

zmq: Any = _zmq

# Add a cache for frequently accessed data
from cachetools import TTLCache
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qt_material import apply_stylesheet

from fpdb_3_legacy import Aux_Base, Configuration, Database, Deck, Hud, Options, db_profile
from fpdb_3_legacy.db_reconnect import is_connection_lost
from fpdb_3_legacy.hud_profiles import HudContext, HudPositionScope
from fpdb_3_legacy.hud_read_service import (
    HudBatchReadRequest,
    HudBatchSnapshot,
    HudReadService,
    HudReplayDatabase,
    HudTableReadContext,
)
from fpdb_3_legacy.HudStatsPersistence import get_hud_stats_persistence
from fpdb_3_legacy.loggingFpdb import get_logger, hud_trace
from fpdb_3_legacy.SmartHudManager import RestartReason, get_smart_hud_manager
from fpdb_3_legacy.table_info import TableInfo

# Logging configuration

log = get_logger("hud_main")

# How long an arriving hand waits for its neighbours. Twelve tables dealing at
# once arrive as twelve separate notifications; holding them briefly turns that
# into one batch, so each HUD is refreshed once rather than once per hand. Long
# enough to catch the burst, short enough to stay ahead of the player acting.
HAND_BATCH_INTERVAL_MS = 200

# How long the recovery worker waits between attempts to re-open a database
# connection that has dropped. Database.recover_connection has its own cooldown;
# this only decides how often we ask.
DB_RECOVERY_INTERVAL_S = 5.0

# A long outage must not grow memory without bound, but dropping every hand
# means a recovered HUD stays invisible until another hand happens to arrive.
# Keep a generous tail and reduce it to the latest hand per table once the
# database is available again and table identities can be queried safely.
MAX_DEFERRED_HANDS = 1000
MAX_PENDING_HANDS = 1000
DB_BATCH_RETRY_MS = 5000
DB_BATCH_RETRY_BACKOFF_MS = 30000
DB_BATCH_RETRY_BACKOFF_AFTER = 5


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
    context: HudContext | None = None
    hand_instance: Any = None
    loading: bool = False


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


class DbRecoveryWorker(QThread):
    """Re-opens a dropped database connection away from the UI thread.

    Reconnecting costs a full connect timeout when the database is unreachable,
    which is exactly the stall the HUD must not take on the thread that repaints
    it. This thread owns the connection for the duration of the outage: it is
    started only once HudMain has stopped querying (the breaker is open) and it
    stops before HudMain resumes, so the connection still has a single user at
    any moment despite being touched from two threads.
    """

    recovered = Signal()

    def __init__(self, db_connection, parent: QObject | None = None) -> None:
        """Initialize the recovery worker."""
        super().__init__(parent)
        self.db_connection = db_connection
        # An Event rather than a sleep plus a flag, so closing the HUD during an
        # outage does not wait out the retry interval before shutting down.
        self._stopping = threading.Event()

    def run(self) -> None:
        """Retry the connection until it comes back or shutdown is requested."""
        log.info("Database recovery worker started")
        while not self._stopping.wait(DB_RECOVERY_INTERVAL_S):
            try:
                if self.db_connection.recover_connection():
                    log.info("Database connection recovered; resuming HUD updates")
                    self.recovered.emit()
                    return
            except Exception:
                log.exception("Database recovery attempt failed unexpectedly")

    def stop(self) -> None:
        """Stop the worker thread."""
        self._stopping.set()
        # Bounded: an attempt already inside connect() has to run out its own
        # connect timeout, but shutdown must not hang on it either.
        if not self.wait(15000):
            log.warning("Database recovery worker did not stop in time")


class HudReadWorker(QThread):
    """Own the HUD database connection and execute read batches off the UI thread."""

    ready = Signal(int)
    snapshot_ready = Signal(object)
    unavailable = Signal(str)
    batch_failed = Signal(object, str)

    def __init__(
        self,
        config: Configuration.Config,
        parent: QObject | None = None,
        db_factory: Callable[..., Any] = Database.Database,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.db_factory = db_factory
        self._requests: Queue[HudBatchReadRequest | None] = Queue()
        self._stopping = threading.Event()

    def submit(self, request: HudBatchReadRequest) -> None:
        """Queue one immutable request from the Qt thread."""
        self._requests.put(request)

    @staticmethod
    def _configure_session(database: Database.Database) -> None:
        """Bound only the worker's PostgreSQL statements, never the importer."""
        if database.backend != Database.Database.PGSQL:
            return
        with contextlib.suppress(Exception):
            database.connection.rollback()
        cursor = database.connection.cursor()
        try:
            cursor.execute("SET statement_timeout = 10000")
            cursor.execute("SET lock_timeout = 2000")
            cursor.execute("SET idle_in_transaction_session_timeout = 30000")
            database.connection.commit()
        finally:
            cursor.close()

    @staticmethod
    def _close_database(database: Database.Database | None) -> None:
        if database is None:
            return
        with contextlib.suppress(Exception):
            database.close_connection()

    def run(self) -> None:
        """Connect, process one request at a time, and reconnect in this thread."""
        database: Database.Database | None = None
        service: HudReadService | None = None
        pending: HudBatchReadRequest | None = None
        unavailable_announced = False
        while not self._stopping.is_set():
            if database is None:
                try:
                    database = self.db_factory(self.config)
                    self._configure_session(database)
                    service = HudReadService(self.config, database)
                except Exception as exc:
                    self._close_database(database)
                    database = None
                    service = None
                    if not unavailable_announced:
                        self.unavailable.emit(str(exc))
                        unavailable_announced = True
                    self._stopping.wait(DB_RECOVERY_INTERVAL_S)
                    continue
                unavailable_announced = False
                self.ready.emit(database.backend)

            if pending is None:
                try:
                    pending = self._requests.get(timeout=0.2)
                except Empty:
                    continue
                if pending is None:
                    break

            assert service is not None
            try:
                snapshot = service.read_batch(pending, progress_callback=self.snapshot_ready.emit)
            except Exception as exc:
                if database is not None and is_connection_lost(database.backend, exc):
                    if not unavailable_announced:
                        self.unavailable.emit(str(exc))
                        unavailable_announced = True
                    self._close_database(database)
                    database = None
                    service = None
                    continue
                self.batch_failed.emit(pending, str(exc))
            else:
                self.snapshot_ready.emit(snapshot)
            pending = None

        self._close_database(database)

    def stop(self) -> None:
        """Wake the queue and wait for the bounded statement timeout."""
        self._stopping.set()
        self._requests.put(None)
        if not self.wait(15000):
            log.warning("HUD read worker did not stop in time")


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
            # HUD dictionary and parameters
            self.hud_dict: dict[str, Hud.Hud] = {}
            # Session-only profile choices made from an individual table menu.
            # Values include game identity so a recycled table key cannot leak a
            # Hold'em/PLO choice into another game.
            self._table_stat_set_overrides: dict[str, tuple[str, str, str]] = {}
            # Fingerprint of HUD_config.xml as last read. Preferences run in the
            # fpdb process, not this one, so a saved profile rule reaches the
            # open tables by way of the file rather than a call.
            self._config_fingerprint = self._read_config_fingerprint()
            # Last hand id processed per table. The ZMQ producer (auto-import
            # re-scanning growing files) can deliver the same Hands.id more than
            # once; this makes read_stdin idempotent so each hand refreshes the
            # HUD exactly once, without re-running create/update on a duplicate.
            self._last_processed_hands: dict[str, str] = {}
            self.blacklist: list[Any] = []
            # The real connection is created and owned by HudReadWorker.  The
            # UI only ever sees an in-memory replay facade for completed reads.
            empty_snapshot = HudBatchSnapshot(0, (), (), {}, {}, {}, {}, {})
            self.db_connection = HudReplayDatabase(empty_snapshot, 0)
            self._db_backend = 0
            self._db_available = False
            self._db_batch_inflight = False
            self._db_batch_sequence = 0
            self._last_applied_sequence = 0
            self._last_applied_revision = -1
            self._db_progress_refreshed: set[str] = set()
            self._db_consecutive_failures = 0
            self._prepared_hands: dict[str, Any] = {}
            self._last_table_info: dict[str, tuple] = {}
            self._db_recovery_worker: DbRecoveryWorker | None = None
            # Statements counted at the end of the previous batch, so each batch
            # can report its own cost rather than the running total.
            self._last_batch_queries = 0
            self.hud_params = self.config.get_hud_ui_parameters()
            self.deck = Deck.Deck(
                self.config,
                deck_type=self.hud_params["deck_type"],
                card_back=self.hud_params["card_back"],
                width=self.hud_params["card_wd"],
                height=self.hud_params["card_ht"],
            )

            from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader

            self.winamax_log_reader = WinamaxLiveLogReader(
                on_seat_update=self._on_winamax_log_seat_update
            )
            self.winamax_log_reader.start()

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
            self._deferred_hands: list[str] = []
            self._hand_batch_timer = QTimer(self)
            self._hand_batch_timer.setSingleShot(True)
            self._hand_batch_timer.setInterval(HAND_BATCH_INTERVAL_MS)
            self._hand_batch_timer.timeout.connect(self._drain_pending_hands)

            self._db_worker: HudReadWorker | None = HudReadWorker(self.config, parent=self)
            self._db_worker.ready.connect(self._on_db_worker_ready)
            self._db_worker.snapshot_ready.connect(self._on_db_snapshot)
            self._db_worker.unavailable.connect(self._on_db_worker_unavailable)
            self._db_worker.batch_failed.connect(self._on_db_batch_failed)
            self._db_worker.start()

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

    def note_db_error(self, exc: BaseException) -> bool:
        """Open the breaker if ``exc`` means the connection is gone.

        Returns:
            True when the database is now considered unavailable, so the caller
            can stop working on a hand it has no way of finishing.

        Database already reconnects and replays a query transparently; an error
        still reaching here means that failed too, and the link is genuinely
        down rather than merely interrupted.
        """
        if not is_connection_lost(self.db_connection.backend, exc):
            return False
        if getattr(self, "_db_worker", None) is not None:
            # Runtime SQL recovery belongs exclusively to HudReadWorker. The
            # Qt side holds only HudReplayDatabase, which cannot and must not
            # be handed to the legacy DbRecoveryWorker.
            log.error("Unexpected connection-style error from HUD replay data: %s", exc)
            return False
        if self._db_available:
            log.error("Database unreachable; HUD updates are paused until it returns (%s)", exc)
            self._db_available = False
            self._start_db_recovery()
        return True

    def _start_db_recovery(self) -> None:
        """Legacy synchronous-test recovery; runtime uses HudReadWorker."""
        if not hasattr(self.db_connection, "recover_connection"):
            log.error("Refusing legacy DB recovery for an in-memory HUD replay facade")
            return
        if self._db_recovery_worker is not None and self._db_recovery_worker.isRunning():
            return
        worker = DbRecoveryWorker(self.db_connection, parent=self)
        worker.recovered.connect(self._on_db_recovered)
        self._db_recovery_worker = worker
        worker.start()

    def _on_db_recovered(self) -> None:
        """Resume querying once the recovery thread has restored the link."""
        # Runs on the UI thread (queued signal), and the worker has already
        # returned from run(), so the connection is unowned at this point.
        self._db_available = True
        log.info("Database available again; HUD updates resumed")
        deferred, self._deferred_hands = self._deferred_hands, []
        if deferred:
            log.info("Replaying %d hand notification(s) deferred during the outage", len(deferred))
            self._pending_hands.extend(deferred)
            if not self._hand_batch_timer.isActive():
                self._hand_batch_timer.start()

    def _on_db_worker_ready(self, backend: int) -> None:
        """Resume submissions after the worker connected or reconnected."""
        recovered = not self._db_available
        self._db_backend = backend
        self._db_available = True
        if recovered:
            log.info("HUD database worker is ready; updates resumed")
        deferred, self._deferred_hands = self._deferred_hands, []
        if deferred:
            self._pending_hands.extend(deferred)
        if self._pending_hands and not self._db_batch_inflight and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _on_db_worker_unavailable(self, message: str) -> None:
        """Open the UI-side breaker without touching the worker's connection."""
        if self._db_available:
            log.error("HUD database unavailable; updates remain responsive (%s)", message)
        else:
            log.debug("HUD database still unavailable: %s", message)
        self._db_available = False

    def _retry_hands(self, hand_ids: tuple[str, ...]) -> None:
        if self._shutdown_started:
            return
        for hand_id in hand_ids:
            with contextlib.suppress(ValueError):
                self._pending_hands.remove(hand_id)
            self._pending_hands.append(hand_id)
        if self._db_available and not self._db_batch_inflight and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _on_db_batch_failed(self, request: HudBatchReadRequest, message: str) -> None:
        """Retry an ordinary timeout later while the Qt loop stays available."""
        self._db_batch_inflight = False
        self._db_consecutive_failures += 1
        retry_ms = (
            DB_BATCH_RETRY_BACKOFF_MS
            if self._db_consecutive_failures > DB_BATCH_RETRY_BACKOFF_AFTER
            else DB_BATCH_RETRY_MS
        )
        log.warning(
            "HUD database batch %d failed (%d consecutive failure(s)); "
            "the loading HUD stays visible and stats will retry in %d seconds: %s",
            request.sequence,
            self._db_consecutive_failures,
            retry_ms // 1000,
            message,
        )
        if self._db_consecutive_failures == DB_BATCH_RETRY_BACKOFF_AFTER + 1:
            log.error(
                "HUD database remains too slow after %d batches; reducing retries to every %d seconds",
                self._db_consecutive_failures,
                retry_ms // 1000,
            )
        QTimer.singleShot(retry_ms, lambda hands=request.hand_ids: self._retry_hands(hands))

    def _table_read_contexts(self) -> tuple[HudTableReadContext, ...]:
        contexts = []
        for temp_key, hud in list(self.hud_dict.items()):
            last_hand_id = self._last_processed_hands.get(temp_key)
            if not last_hand_id:
                continue
            table_info = self._last_table_info.get(temp_key) or self.cache.get(last_hand_id)
            if table_info is None:
                continue
            info = TableInfo.coerce(table_info)
            needs_mucked = any(type(aux).__module__.rsplit(".", 1)[-1] == "Mucked" for aux in hud.aux_windows)
            contexts.append(
                HudTableReadContext(
                    temp_key=temp_key,
                    last_hand_id=last_hand_id,
                    hud_params=dict(hud.hud_params),
                    poker_game=hud.poker_game,
                    game_type=info.game_type,
                    site_id=info.site_id,
                    num_seats=info.num_seats,
                    needs_mucked_data=needs_mucked,
                ),
            )
        return tuple(contexts)

    def _build_batch_request(self, hand_ids: list[str]) -> HudBatchReadRequest:
        self._db_batch_sequence += 1
        return HudBatchReadRequest(
            sequence=self._db_batch_sequence,
            hand_ids=tuple(hand_ids),
            hud_params=dict(self.hud_params),
            tables=self._table_read_contexts(),
        )

    def _show_loading_hud(self, hand_id: str) -> str | None:
        """Create an empty-but-visible HUD as soon as table identity is known."""
        prepared = self._prepared_hands.get(str(hand_id))
        if prepared is None or prepared.table_info is None:
            return None
        table_info = prepared.table_info
        info = TableInfo.coerce(table_info)
        table_name = info.table_name
        if not isinstance(table_name, str) or not table_name.strip():
            return None

        enabled_sites = self.config.get_supported_sites()
        hud_site_name = self._resolve_hud_config_site(info.site_name, enabled_sites)
        aux_disabled_sites = [
            site for site in enabled_sites if not self.config.get_site_parameters(site)["aux_enabled"]
        ]
        if info.fast or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            return None

        temp_key = self._get_temp_key(info.game_type, info.tour_number, info.tab_number, table_name)
        if temp_key in self.hud_dict:
            return temp_key
        if self._handle_tournament_table_changes(info.game_type, temp_key, info.tour_number):
            return None
        self._create_new_hud(
            hand_id,
            temp_key,
            table_info,
            info.site_id,
            info.num_seats,
            hud_site_name,
            loading=True,
        )
        if temp_key in self.hud_dict:
            self._last_table_info[temp_key] = table_info
            return temp_key
        return None

    def _on_db_snapshot(self, snapshot: HudBatchSnapshot) -> None:
        """Apply a database-free snapshot on the Qt thread."""
        if self._shutdown_started:
            return
        if snapshot.sequence < self._last_applied_sequence:
            return
        if snapshot.sequence == self._last_applied_sequence and snapshot.revision <= self._last_applied_revision:
            return
        if snapshot.sequence > self._last_applied_sequence:
            self._last_applied_sequence = snapshot.sequence
            self._last_applied_revision = -1
            self._db_progress_refreshed = set()
        self._last_applied_revision = snapshot.revision
        self.db_connection = HudReplayDatabase(snapshot, self._db_backend)
        self._prepared_hands = snapshot.hands
        if not snapshot.identity_only:
            self.hero = dict(snapshot.hero)
            self.hero_ids = dict(snapshot.hero_ids)

        for prepared in snapshot.hands.values():
            if prepared.table_info is None:
                continue
            self.cache[prepared.hand_id] = prepared.table_info
            self._hand_players[("seats", prepared.hand_id)] = prepared.seat_players
            self._hand_players[("positions", prepared.hand_id)] = prepared.positions

        if snapshot.identity_only:
            for hand_id in snapshot.primary_order:
                self._show_loading_hud(hand_id)
            return

        refreshed = set(self._db_progress_refreshed)
        apply_failed: list[str] = []
        failed = set(snapshot.failed_hand_ids)
        for hand_id in snapshot.primary_order:
            if hand_id in failed:
                continue
            try:
                served = self.read_stdin(hand_id)
            except Exception:
                log.exception("Error applying prepared HUD hand %s", hand_id)
                apply_failed.append(hand_id)
            else:
                if served is not None:
                    refreshed.add(served)
                    self._db_progress_refreshed.add(served)
                    prepared = snapshot.hands.get(str(hand_id))
                    if prepared is not None and prepared.table_info is not None:
                        self._last_table_info[served] = prepared.table_info

        if not snapshot.final:
            return

        self._db_batch_inflight = False
        self._db_consecutive_failures = 0
        # A secondary read that failed must leave that HUD's previous stats on
        # screen. Excluding it from the replay refresh prevents a missing
        # snapshot entry from looking like a legitimate empty result.
        unavailable_secondary = {
            context.temp_key
            for context in self._table_read_contexts()
            if str(context.last_hand_id) not in snapshot.hands
        }
        self._refresh_other_huds(refreshed | unavailable_secondary)
        self._report_batch_round_trips(len(snapshot.requested_hand_ids), len(self.hud_dict))

        retry_hands = tuple(dict.fromkeys((*snapshot.failed_hand_ids, *apply_failed)))
        if retry_hands:
            QTimer.singleShot(5000, lambda hands=retry_hands: self._retry_hands(hands))
        if self._pending_hands and self._db_available and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()
        self._db_progress_refreshed = set()

    def _stop_db_recovery(self) -> None:
        """Stop the recovery thread, if one is running."""
        worker = getattr(self, "_db_recovery_worker", None)
        if worker is None:
            return
        self._db_recovery_worker = None
        with contextlib.suppress(RuntimeError):
            worker.stop()

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

        if not self._db_available:
            # The read worker owns the real connection. Keep the notification
            # bounded here until that worker reports a successful reconnect.
            self._defer_hands([hand_id])
            log.debug("Deferring hand %s: database unavailable", hand_id)
            return

        try:
            self._enqueue_hand(hand_id)
            log.debug("Hand %s queued for the next batch", hand_id)
        except Exception as e:
            log.exception("Error handling message for hand_id %s: %s", hand_id, e)

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
        self._deferred_hands = []

        db_worker = getattr(self, "_db_worker", None)
        if db_worker is not None:
            with contextlib.suppress(RuntimeError):
                db_worker.stop()
            self._db_worker = None

        self._stop_db_recovery()

        zmq_worker = getattr(self, "zmq_worker", None)
        if zmq_worker is not None:
            with contextlib.suppress(RuntimeError):
                zmq_worker.stop()
            self.zmq_worker = None

        log_reader = getattr(self, "winamax_log_reader", None)
        if log_reader is not None:
            with contextlib.suppress(Exception):
                log_reader.stop()
            self.winamax_log_reader = None

        zmq_receiver = getattr(self, "zmq_receiver", None)
        if zmq_receiver is not None:
            with contextlib.suppress(RuntimeError):
                zmq_receiver.close()
            self.zmq_receiver = None

        db_profile.get_profile().log_report("HUD database round-trip profile:")

        log.info("Quitting normally")
        QCoreApplication.quit()

    def _on_winamax_log_seat_update(self, pool_id: str, seat_map: dict[int, str]) -> None:
        """Callback from WinamaxLiveLogReader when real-time seat assignments change."""
        log.info("WinamaxLiveLogReader seat update for pool %s: %s", pool_id, seat_map)
        self.update_fast_fold_seats("Winamax", seat_map, pool_id=pool_id)

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
        # Checked here rather than on a timer of its own: it is one os.stat
        # unless the file really changed, and skipping it during a drag also
        # keeps the HUD's own layout writes from rebuilding what is being
        # dragged.
        self.refresh_profiles_from_config()
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

    def _read_config_fingerprint(self) -> tuple[float, int] | None:
        """Cheap change detector for HUD_config.xml, polled with the tables."""
        try:
            stat = os.stat(self.config.file)
        except OSError:
            return None
        return (stat.st_mtime, stat.st_size)

    def refresh_profiles_from_config(self) -> int:
        """Re-apply the profile rules to open tables after a config change.

        HUD Preferences runs in the fpdb process and this one is a subprocess,
        so nothing can call in when Apply is pressed: the configuration file is
        the signal. Rebuilding a HUD destroys and recreates its windows, which
        the player sees, so only tables whose effective profile actually
        changed are touched -- saving an unrelated preference rebuilds nothing.

        Returns the number of tables rebuilt.
        """
        fingerprint = self._read_config_fingerprint()
        if fingerprint is None or fingerprint == self._config_fingerprint:
            return 0
        self._config_fingerprint = fingerprint
        if self.config.reload() is False:
            log.warning("HUD_config.xml changed but could not be reloaded; keeping the profiles in use")
            return 0

        rebuilt = 0
        for temp_key, hud in list(self.hud_dict.items()):
            if self._reapply_profile(temp_key, hud):
                rebuilt += 1
        if rebuilt:
            log.info("Config change applied: %d table(s) rebuilt with a new HUD profile", rebuilt)
        return rebuilt

    def _reapply_profile(self, temp_key: str, hud: Hud.Hud) -> bool:
        """Rebuild one table if the rules now select a different profile."""
        context = getattr(hud, "hud_context", None)
        if context is None:
            return False
        table_key = getattr(getattr(hud, "table", None), "key", None)
        if table_key is not None and self.get_table_stat_set_override(table_key, hud.poker_game, hud.game_type):
            # The table menu is an explicit, session-only choice by the player.
            return False

        params = self.config.get_supported_games_parameters(hud.poker_game, hud.game_type, context)
        new_stat_set = params.get("game_stat_set") if isinstance(params, dict) else None
        if new_stat_set is None:
            return False
        current = (hud.supported_games_parameters or {}).get("game_stat_set")
        if getattr(new_stat_set, "name", None) == getattr(current, "name", None):
            return False

        try:
            self._rebuild_hud_with_stat_set(hud, new_stat_set)
        except Exception:  # intentional broad catch: a failed rebuild must leave no orphan windows
            log.exception("Rebuilding %s for profile %s failed; restarting it", temp_key, new_stat_set.name)
            self.kill_hud(None, temp_key)
        return True

    @staticmethod
    def _rebuild_hud_with_stat_set(hud: Hud.Hud, stat_set: Any) -> None:
        """Swap a HUD onto another profile, the way the table menu does.

        The scope is recomputed with the profile because saved positions are
        filed under it: a table that changes profile has to read the positions
        belonging to the new one, not keep pointing at the old one's.
        """
        hud.supported_games_parameters = dict(hud.supported_games_parameters)
        hud.supported_games_parameters["game_stat_set"] = stat_set
        hud.position_scope = HudPositionScope.from_hud(hud)
        for aux in list(getattr(hud, "aux_windows", [])):
            if not hasattr(aux, "refresh_stats_layout"):
                continue  # Mucked and friends carry no stat-set layout
            aux.game_params = stat_set
            aux.destroy()
            aux.refresh_stats_layout()
            aux.create()
            if getattr(hud, "stat_dict", None):
                aux.update_gui(None)
        log.info("Table %s rebuilt with HUD profile %s", getattr(hud, "table_name", "?"), stat_set.name)

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
            args.context,
        )
        self.hud_dict[args.temp_key].table_name = args.temp_key
        self.hud_dict[args.temp_key].stat_dict = args.stat_dict
        self.hud_dict[args.temp_key].cards = args.cards
        self.hud_dict[args.temp_key].max = args.max_seats

        args.table.hud = self.hud_dict[args.temp_key]

        self.hud_dict[args.temp_key].hud_params["new_max_seats"] = None  # trigger for seat layout change

        if not args.loading:
            for aw in self.hud_dict[args.temp_key].aux_windows:
                aw.update_data(args.new_hand_id, self.db_connection)

        self.idle_create(args)
        log.debug("HUD for table %s created successfully.", args.temp_key)

    def update_HUD(
        self,
        new_hand_id: str,
        table_name: str,
        config: Configuration.Config,
        *,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
        """Update an existing HUD."""
        log.debug("Updating HUD for table %s and hand %s", table_name, new_hand_id)
        if cards is None and hand_instance is None:
            self.idle_update(new_hand_id, table_name, config)
        else:
            self.idle_update(
                new_hand_id,
                table_name,
            )

    def update_fast_fold_seats(
        self,
        table_name: str,
        seat_player_map: dict[int, str],
        game_type: str = "ring",
        pool_id: str = "",
    ) -> bool:
        """Update live HUD overlays for a Fast-Fold / Escape table with new seat assignments immediately."""
        import re

        from fpdb_3_legacy.fast_fold_engine import FastFoldEngine, is_fast_fold_table

        log.info("HUD_main.update_fast_fold_seats: table=%s, pool=%s, seats=%s", table_name, pool_id, seat_player_map)
        target_huds = []
        for key, hud in self.hud_dict.items():
            hud_title = getattr(hud, "title", "") or getattr(hud, "table_name", "") or key
            if table_name in key or table_name in hud_title or is_fast_fold_table(hud_title):
                target_huds.append(hud)

        if not target_huds:
            return False

        target_hud = target_huds[0]
        if pool_id and len(target_huds) > 1:
            m = re.search(r"t(\d+)$|(\d+)\.\d+$|\.(\d+)$", pool_id)
            if m:
                idx = int(m.group(1) or m.group(2) or m.group(3)) % len(target_huds)
                target_hud = target_huds[idx]

        target_hud.fast_fold_seats = seat_player_map
        engine = FastFoldEngine(config=self.config, db_connection=self.db_connection)
        success = engine.update_hud_seats(target_hud, seat_player_map, game_type=game_type)

        for aw in getattr(target_hud, "aux_windows", []):
            with contextlib.suppress(Exception):
                aw.update_data(None, self.db_connection)
                if hasattr(aw, "update_gui"):
                    aw.update_gui(None)

        return success

    def _initialize_hero_data(self) -> None:
        """Initialize hero data from the configuration."""
        self.hero = {}
        self.hero_ids = {}
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
        except Exception as exc:
            if self.note_db_error(exc):
                # Swallowing this one would make every hand of the outage look
                # like a hand that is merely not committed yet, which is how the
                # HUD used to die silently and stay dead.
                return None
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

    @db_profile.scoped("update_hud")
    def _update_existing_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
    ) -> bool:
        """Update an existing HUD with new hand data."""
        log.debug("update hud for hand %s", new_hand_id)
        hud = self.hud_dict[temp_key]
        was_loading = bool(getattr(hud, "is_loading", False))
        self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
        stat_dict = self.db_connection.get_stats_from_hand(
            new_hand_id,
            game_type,
            hud.hud_params,
            self.hero_ids[site_id],
            num_seats,
            poker_game=hud.poker_game,
        )
        log.debug("got stats for hand %s", new_hand_id)

        if was_loading and not any(
            values.get("screen_name") == self.hero.get(site_id)
            for values in stat_dict.values()
        ):
            from fpdb_3_legacy.fast_fold_engine import is_fast_fold_table

            if not is_fast_fold_table(getattr(hud, "title", "")):
                log.warning(
                    "Removing loading HUD for hand %s table=%s: hero %r is not seated",
                    new_hand_id,
                    temp_key,
                    self.hero.get(site_id),
                )
                self.kill_hud(None, temp_key)
                return False

        if was_loading:
            cached_stats = self.stats_persistence.load_hud_stats(temp_key)
            if cached_stats:
                merged = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
                stat_dict = merged.get("stat_dict", stat_dict)

        if is_fast_fold_table(getattr(hud, "title", "")) and getattr(hud, "fast_fold_seats", None):
            from fpdb_3_legacy.fast_fold_engine import FastFoldEngine

            engine = FastFoldEngine(config=self.config, db_connection=self.db_connection)
            stat_dict = engine.get_player_stats_for_seat_map(
                hud.fast_fold_seats,
                game_type=game_type,
                db_conn=self.db_connection,
            )

        self._merge_positions(stat_dict, new_hand_id)
        try:
            hud.stat_dict = stat_dict
        except KeyError:
            log.exception("hud_dict[%s] was not found", temp_key)
            return False

        if is_fast_fold_table(getattr(hud, "title", "")) and getattr(hud, "fast_fold_seat_players", None):
            hud.seat_players = hud.fast_fold_seat_players
        else:
            hud.seat_players = self._seat_players(new_hand_id)
        self._set_table_stats(hud, new_hand_id)
        hud.cards = self.get_cards(new_hand_id, hud.poker_game)
        for aw in hud.aux_windows:
            aw.update_data(new_hand_id, self.db_connection)
            if hasattr(aw, "update_gui"):
                with contextlib.suppress(Exception):
                    aw.update_gui(None)
        prepared = self._prepared_hands.get(str(new_hand_id))
        self.update_HUD(
            new_hand_id,
            temp_key,
            self.config,
            cards=hud.cards,
            hand_instance=prepared.hand_instance if prepared is not None else None,
        )
        hud.is_loading = False
        log.debug("hud updated for table %s and hand %s", temp_key, new_hand_id)
        return True

    def _enqueue_hand(self, hand_id: str) -> None:
        """Hold a hand briefly so the tables dealing alongside it join the batch."""
        with contextlib.suppress(ValueError):
            self._pending_hands.remove(hand_id)
        self._pending_hands.append(hand_id)
        overflow = len(self._pending_hands) - MAX_PENDING_HANDS
        if overflow > 0:
            del self._pending_hands[:overflow]
            log.warning("HUD pending-hand queue reached %d; oldest notification(s) were dropped", MAX_PENDING_HANDS)
        if not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _defer_hands(self, hand_ids: list[str]) -> None:
        """Keep recent hand notifications until the recovery worker succeeds."""
        for hand_id in hand_ids:
            if not hand_id:
                continue
            # A duplicate notification should move to the end rather than use
            # two slots in the bounded outage queue.
            with contextlib.suppress(ValueError):
                self._deferred_hands.remove(hand_id)
            self._deferred_hands.append(hand_id)
        overflow = len(self._deferred_hands) - MAX_DEFERRED_HANDS
        if overflow > 0:
            del self._deferred_hands[:overflow]

    def _finish_read_batch(self) -> None:
        """Release the successful HUD read transaction and any pooled server slot."""
        if not self._db_available:
            # Recovery owns the connection as soon as the breaker opens.
            return
        try:
            self.db_connection.connection.rollback()
        except Exception as exc:
            if not self.note_db_error(exc):
                log.exception("Could not finish the HUD read transaction")

    def _latest_hand_per_table(self, hand_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        """Reduce a batch to the last hand of each table.

        Processing an earlier hand of a table only to overwrite it with the
        next one is work nobody sees, and the HUD shows the latest hand either
        way. Hands whose table cannot be resolved are handed back untouched so
        they take the normal path and log what they normally log.
        """
        latest: dict[str, str] = {}
        unresolved: list[str] = []
        for index, hand_id in enumerate(hand_ids):
            table_info = self._get_table_info(hand_id)
            if table_info is None:
                unresolved.append(hand_id)
                if not self._db_available:
                    unresolved.extend(hand_ids[index + 1 :])
                    break
                continue
            info = TableInfo.coerce(table_info)
            latest[self._get_temp_key(info.game_type, info.tour_number, info.tab_number, info.table_name)] = hand_id
        return latest, unresolved

    def _drain_pending_hands(self) -> None:
        """Submit one batch without running a database call on the Qt thread."""
        worker = getattr(self, "_db_worker", None)
        if worker is None:
            # Narrow compatibility seam for focused legacy unit tests. Runtime
            # construction always installs HudReadWorker.
            self._drain_pending_hands_sync()
            return
        if self._db_batch_inflight:
            return
        pending, self._pending_hands = self._pending_hands, []
        if not pending:
            return
        if not self._db_available:
            self._defer_hands(pending)
            return
        request = self._build_batch_request(pending)
        self._db_batch_inflight = True
        worker.submit(request)

    def _drain_pending_hands_sync(self) -> None:
        """Process one batch of hands, then refresh every other HUD once.

        The refresh is what this exists for: it used to run per hand, so a
        round of twelve tables cost twelve refreshes of twelve HUDs. One batch
        means one refresh each.
        """
        pending, self._pending_hands = self._pending_hands, []
        if not pending:
            return
        if not self._db_available:
            self._defer_hands(pending)
            log.debug("Deferring %d pending hand(s): database unavailable", len(pending))
            return

        try:
            with db_profile.scope("batch"):
                latest, unresolved = self._latest_hand_per_table(pending)
                if not self._db_available:
                    self._defer_hands(pending)
                    log.warning("Deferring this batch: database went away during table lookup")
                    return
                log.debug("Draining %d hand(s) into %d table(s)", len(pending), len(latest))

                refreshed: set[str] = set()
                for hand_id in [*latest.values(), *unresolved]:
                    try:
                        with db_profile.scope("hand"):
                            served = self.read_stdin(hand_id)
                    except Exception as exc:
                        if self.note_db_error(exc):
                            self._defer_hands(pending)
                            log.warning("Deferring this batch: database went away while processing hand %s", hand_id)
                            return
                        log.exception("Error processing hand %s", hand_id)
                        with contextlib.suppress(Exception):
                            self.db_connection.connection.rollback()
                    else:
                        if served is not None:
                            refreshed.add(served)

                # Only the tables actually brought up to date are left out of the
                # statistics refresh; one that failed still needs it.
                self._refresh_other_huds(refreshed)
                if not self._db_available:
                    self._defer_hands(pending)
                    log.warning("Deferring this batch: database went away during the HUD refresh")
                    return
        finally:
            self._finish_read_batch()

        self._report_batch_round_trips(len(pending), len(self.hud_dict))

    def _report_batch_round_trips(self, hands: int, tables: int) -> None:
        """Log what this batch cost in statements, when profiling is on.

        Per batch rather than per process: what decides how the HUD feels is the
        cost of one round of hands with the tables the player actually has open,
        and that is the number a cumulative total hides.
        """
        if not db_profile.is_enabled():
            return
        profile = db_profile.get_profile()
        batch = profile.by_scope.get("batch")
        hand_scope = profile.by_scope.get("hand")
        if batch is None:
            return
        log.info(
            "Round trips: batch of %d hand(s) over %d table(s) -- %d statements in this run "
            "(running average %.1f per batch, %.1f per hand)",
            hands,
            tables,
            batch.queries - getattr(self, "_last_batch_queries", 0),
            batch.queries_per_entry,
            hand_scope.queries_per_entry if hand_scope else 0.0,
        )
        self._last_batch_queries = batch.queries

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

    @db_profile.scoped("secondary_refresh")
    def _refresh_secondary_hud(
        self,
        hand_id: str,
        temp_key: str,
        game_type: str,
        site_id: int,
        num_seats: int,
        stat_dict: dict | None = None,
    ) -> None:
        """Update a HUD whose own table has not dealt a new hand.

        ``stat_dict`` is the statistics this table's caller already fetched, in
        one query covering every table being refreshed; passing None makes this
        fetch its own, which is the fallback when the tables cannot share a
        query (see _refresh_other_huds).

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
        if stat_dict is None:
            self.db_connection.init_hud_stat_vars(hud.hud_params["hud_days"], hud.hud_params["h_hud_days"])
            stat_dict = self.db_connection.get_stats_from_hand(
                hand_id,
                game_type,
                hud.hud_params,
                self.hero_ids[site_id],
                num_seats,
                poker_game=hud.poker_game,
            )
        self._merge_positions(stat_dict, hand_id)
        hud.stat_dict = stat_dict
        for aux in hud.aux_windows:
            try:
                aux.refresh_stats(hand_id)
            except Exception:
                log.exception("Error redrawing aux window of table %s", temp_key)
        log.debug("secondary hud redrawn for table %s using hand %s", temp_key, hand_id)

    def _tables_to_refresh(self, updated_tables: set[str]) -> list[tuple]:
        """The tables owed a statistics refresh, with what each one needs."""
        pending = []
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

            info = TableInfo.coerce(table_info)
            pending.append((table_name, last_hand_id, info.game_type, info.site_id, info.num_seats))
        return pending

    def _batch_secondary_stats(self, pending: list[tuple]) -> dict:
        """Fetch every refreshing table's statistics in as few queries as possible.

        Tables can share a query only when every parameter of that query
        matches, so they are grouped by the whole set: the stat-window
        configuration, the hero, the seat count and the game. Multi-tabling one
        site at one stake -- which is what makes this path expensive in the
        first place -- collapses to a single group, and so to a single round
        trip in place of one per table.

        Best-effort by design: a group that fails leaves its tables without a
        precomputed answer, and each falls back to fetching its own.
        """
        # The hero is only known once a hand has been processed. Before that
        # there is nothing to group by, and each table falls back to fetching
        # its own -- which is what this path did before it batched at all.
        hero_ids = getattr(self, "hero_ids", None)
        if not hero_ids:
            return {}

        groups: dict[str, tuple] = {}
        for table_name, last_hand_id, game_type, site_id, num_seats in pending:
            hud = self.hud_dict.get(table_name)
            if hud is None:
                continue
            hero_id = hero_ids.get(site_id)
            if hero_id is None:
                continue
            # repr rather than a tuple of the items: hud_params comes from
            # user-edited configuration, and one unhashable value in it would
            # otherwise take down the refresh round rather than merely stop it
            # batching.
            key = repr((sorted(hud.hud_params.items(), key=str), hero_id, num_seats, hud.poker_game, game_type))
            if key not in groups:
                groups[key] = (hud.hud_params, hero_id, num_seats, hud.poker_game, game_type, [])
            groups[key][5].append(last_hand_id)

        stats_by_hand: dict = {}
        for hud_params, hero_id, num_seats, poker_game, game_type, hand_ids in groups.values():
            try:
                self.db_connection.init_hud_stat_vars(hud_params["hud_days"], hud_params["h_hud_days"])
                stats_by_hand.update(
                    self.db_connection.get_stats_from_hands(
                        hand_ids,
                        game_type,
                        hud_params,
                        hero_id,
                        num_seats,
                        poker_game=poker_game,
                    ),
                )
            except Exception as exc:
                if self.note_db_error(exc):
                    return stats_by_hand
                # PostgreSQL leaves the transaction aborted after a statement
                # error. Clear it before the caller falls back to per-table
                # queries, otherwise the first fallback necessarily fails with
                # InFailedSqlTransaction and that table remains stale.
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()
                log.exception("Batched statistics failed for %d table(s); each will ask for its own", len(hand_ids))
        return stats_by_hand

    def _refresh_other_huds(self, updated_tables: set[str]) -> None:
        """Refresh every active HUD except the tables this batch already updated.

        HUD statistics are aggregated globally, but each HUD must keep using
        its own latest hand for seats, cards, positions, and game context.
        Reusing that table's last processed hand makes all open HUDs observe
        the latest HudCache state without mixing table-local data.

        A secondary HUD is best-effort: one stale or failing table must not
        prevent the remaining tables from refreshing.
        """
        pending = self._tables_to_refresh(updated_tables)
        if not pending:
            return
        stats_by_hand = self._batch_secondary_stats(pending)

        for table_name, last_hand_id, game_type, site_id, num_seats in pending:
            if not self._db_available:
                # Opened by an earlier table in this same loop.
                log.debug("Stopping the HUD refresh round: database unavailable")
                return
            try:
                self._refresh_secondary_hud(
                    last_hand_id,
                    table_name,
                    game_type,
                    site_id,
                    num_seats,
                    stat_dict=stats_by_hand.get(last_hand_id),
                )
            except Exception as exc:
                if self.note_db_error(exc):
                    return
                log.exception(
                    "Global HUD refresh failed for table %s using hand %s",
                    table_name,
                    last_hand_id,
                )
                # PostgreSQL rejects every later query after one statement
                # fails until the transaction is explicitly rolled back.
                with contextlib.suppress(Exception):
                    self.db_connection.connection.rollback()

    @db_profile.scoped("create_hud")
    def _create_new_hud(
        self,
        new_hand_id: str,
        temp_key: str,
        table_info: tuple,
        site_id: int,
        num_seats: int,
        hud_site_name: str | None = None,
        *,
        loading: bool = False,
    ) -> None:
        """Create a new HUD for a table."""
        info = TableInfo.coerce(table_info)
        table_name = info.table_name
        max_seats = info.max_seats
        poker_game = info.poker_game
        game_type = info.game_type
        tour_number = info.tour_number
        tab_number = info.tab_number
        tourney_name = info.tourney_name
        hud_site_name = hud_site_name or info.site_name
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
        if loading:
            stat_dict = {}
        else:
            self.db_connection.init_hud_stat_vars(self.hud_params["hud_days"], self.hud_params["h_hud_days"])
            stat_dict = self.db_connection.get_stats_from_hand(
                new_hand_id,
                game_type,
                self.hud_params,
                self.hero_ids[site_id],
                num_seats,
                poker_game=hud_poker_game,
            )
            log.debug("got stats for hand %s", new_hand_id)

        # Try to load cached stats to preserve data across restarts
        cached_stats = None if loading else self.stats_persistence.load_hud_stats(temp_key)
        if cached_stats:
            log.info(f"Found cached HUD stats for table {temp_key}, merging with current data")
            merged_data = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
            stat_dict = merged_data.get("stat_dict", stat_dict)
            log.debug("Merged cached stats with fresh database stats")

        if not loading:
            self._merge_positions(stat_dict, new_hand_id)
        if not loading and not any(stat_dict[key]["screen_name"] == self.hero[site_id] for key in stat_dict):
            log.warning(
                "HUD not created for hand %s table=%s: hero %r (site_id=%s) not among players %s",
                new_hand_id,
                table_name,
                self.hero.get(site_id),
                site_id,
                sorted(stat_dict[key]["screen_name"] for key in stat_dict),
            )
            return

        prepared = self._prepared_hands.get(str(new_hand_id))
        cards = prepared.cards if prepared is not None else self.get_cards(new_hand_id, poker_game)
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
                info.site_name,
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
                context=HudContext(
                    site=hud_site_name,
                    game=hud_poker_game,
                    game_type=game_type,
                    limit_type=info.limit_type,
                    max_seats=max_seats,
                    players=info.num_seats,
                    speed="fast" if info.fast else "normal",
                ),
                hand_instance=prepared.hand_instance if prepared is not None else None,
                loading=loading,
            )
            self.create_HUD(args)
            if args.temp_key in self.hud_dict:
                self.hud_dict[args.temp_key].is_loading = loading
                if not loading:
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

        info = TableInfo.coerce(table_info)
        table_name = info.table_name
        poker_game = info.poker_game
        game_type = info.game_type
        site_id = info.site_id
        site_name = info.site_name
        num_seats = info.num_seats
        tour_number = info.tour_number
        tab_number = info.tab_number

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
        if info.fast or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            log.warning(
                "HUD creation skipped for hand %s table=%s db_site=%s hud_site=%s: fast=%s, aux_disabled=%s, site_enabled=%s",
                new_hand_id,
                table_name,
                site_name,
                hud_site_name,
                info.fast,
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

        if self._handle_tournament_table_changes(game_type, temp_key, tour_number):
            return None  # Stale table was handled

        poker_game, new_max_seats = self._handle_hud_reconfiguration(temp_key, poker_game)
        if new_max_seats:
            # Re-create the HUD with the new max seats
            self.kill_hud(None, temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, num_seats, hud_site_name)
            if temp_key in self.hud_dict:
                self._last_processed_hands[temp_key] = new_hand_id
                return temp_key
            return None

        if temp_key in self.hud_dict:
            hud = self.hud_dict[temp_key]
            if getattr(hud, "is_loading", False) is True:
                # The identity-only snapshot deliberately creates the HUD before
                # player seats and statistics are available.  Aux windows derive
                # their visual-to-physical seat map in create(), so updating that
                # empty HUD in place leaves every slot mapped to None and every
                # player block hidden.  Recreate it once with the complete
                # snapshot so seat rotation, player lookup, and visibility are
                # all initialized from the same hand data.
                log.info(
                    "Replacing loading HUD with complete HUD for table %s and hand %s",
                    temp_key,
                    new_hand_id,
                )
                self.kill_hud(None, temp_key)
                self._create_new_hud(
                    new_hand_id,
                    temp_key,
                    table_info,
                    site_id,
                    num_seats,
                    hud_site_name,
                )
                if temp_key not in self.hud_dict:
                    return None
            else:
                log.debug("Updating existing HUD for temp_key: %s", temp_key)
                if not self._update_existing_hud(new_hand_id, temp_key, game_type, site_id, num_seats):
                    return None
        else:
            log.debug("Creating new HUD for temp_key: %s", temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, num_seats, hud_site_name)
        if temp_key not in self.hud_dict:
            return None
        self._last_processed_hands[temp_key] = new_hand_id
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
            self._position_loading_indicator(hud)
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
            self._position_loading_indicator(hud)
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
                if not getattr(hud, "is_loading", False):
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
            self.hud_dict[args.temp_key].create(
                args.new_hand_id,
                self.config,
                args.stat_dict,
                prepared=str(args.new_hand_id) in self._prepared_hands,
                cards=args.cards,
                hand_instance=args.hand_instance,
            )
            if args.loading:
                self._create_loading_indicator(self.hud_dict[args.temp_key])
                hud_trace("idle_create loading: table=%s hand=%s", args.temp_key, args.new_hand_id)
                return
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

    @staticmethod
    def _create_loading_indicator(hud: Hud.Hud) -> None:
        """Show one cheap table overlay while the complete snapshot is loading."""
        label: QLabel | None = None
        try:
            flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            label = QLabel("Loading HUD…", None, flags)
            label.setObjectName("hud-loading-indicator")
            label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            label.setStyleSheet(
                "QLabel { color: white; background: rgba(20, 20, 20, 210); "
                "border: 1px solid #777; border-radius: 4px; padding: 6px 10px; }",
            )
            label.adjustSize()
            hud.loading_window = label
            HudMain._position_loading_indicator(hud)
            label.create()
            hud.table.topify(label)
            label.show()
        except Exception:
            if label is not None:
                label.close()
                label.deleteLater()
            hud.loading_window = None
            log.exception("Could not create loading indicator for table %s", hud.table_name)

    @staticmethod
    def _position_loading_indicator(hud: Hud.Hud) -> None:
        """Keep the provisional indicator centered on the current table geometry."""
        label = hud.loading_window
        if label is None:
            return
        table_x = hud.table.x if hud.table.x is not None else 0
        table_y = hud.table.y if hud.table.y is not None else 0
        table_width = hud.table.width if hud.table.width is not None else label.width()
        table_height = hud.table.height if hud.table.height is not None else label.height()
        x = table_x + max(0, (table_width - label.width()) // 2)
        y = table_y + max(0, (table_height - label.height()) // 2)
        x, y = Aux_Base.clamp_to_screen(x, y)
        label.move(x, y)

    def idle_update(
        self,
        new_hand_id: str,
        table_name: str,
        config: Configuration.Config,
        *,
        cards: dict[str, Any] | None = None,
        hand_instance: Any = None,
    ) -> None:
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
            if str(new_hand_id) in self._prepared_hands:
                hud.update(
                    new_hand_id,
                    config,
                    prepared=True,
                    cards=cards,
                    hand_instance=hand_instance,
                )
            else:
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
