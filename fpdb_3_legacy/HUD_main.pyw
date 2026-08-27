#!/usr/bin/env python
"""Hud_main.py.

Main for FreePokerTools HUD.
"""

import contextlib
import os
import re
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
from types import ModuleType
from typing import Any

import zmq as _zmq

zmq: Any = _zmq

# Add a cache for frequently accessed data
from cachetools import TTLCache
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from qt_material import apply_stylesheet

from fpdb_3_legacy import Aux_Base, Configuration, Database, Deck, Hud, Options, db_profile
from fpdb_3_legacy.db_reconnect import is_connection_lost
from fpdb_3_legacy.fast_fold_engine import (
    FastFoldEngine,
    FastFoldStatsRequest,
    FastFoldStatsResult,
    build_seat_map,
    is_fast_fold_table,
)
from fpdb_3_legacy.hud_diagnostics import ROLE_HUD, format_identity, log_process_identity, session_id
from fpdb_3_legacy.hud_profiles import HudContext, HudPositionScope
from fpdb_3_legacy.hud_read_service import (
    HudBatchReadRequest,
    HudBatchSnapshot,
    HudPreparedHand,
    HudReadService,
    HudReplayDatabase,
    HudTableReadContext,
)
from fpdb_3_legacy.hud_window_registry import ClaimOutcome, HudWindowRegistry
from fpdb_3_legacy.HudStatsPersistence import get_hud_stats_persistence
from fpdb_3_legacy.interlocks import (
    HUD_ALREADY_RUNNING_EXIT_CODE,
    HUD_INSTANCE_LOCK_NAME,
    HUD_LOCK_UNDETERMINED_EXIT_CODE,
    LockUndeterminedError,
    SingleInstanceError,
    acquire_hud_instance_lock,
    read_lock_owner,
)
from fpdb_3_legacy.loggingFpdb import get_logger, hud_trace
from fpdb_3_legacy.SmartHudManager import RestartReason, get_smart_hud_manager
from fpdb_3_legacy.table_info import TableInfo

# Logging configuration

log = get_logger("hud_main")

FAST_FOLD_POOL_PREFIX = "gf."
"""What the Winamax log calls a Fast-Fold pool, covering Escape and HOLD-UP."""

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


@dataclass(frozen=True)
class FastFoldQualification:
    """What an imported hand says about the window it was played on.

    ``table_no`` is the client's own window index, taken from the log map. It
    is carried out of qualification rather than recomputed because it is also
    how an imported hand finds the HUD the live log already built for that
    window, instead of building a second one.
    """

    info: TableInfo
    table_no: str | None
    site_hand_no: Any


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
    fast_fold_stats_ready = Signal(object)

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

    @staticmethod
    def _read_fast_fold_stats(
        database: Database.Database,
        request: FastFoldStatsRequest,
    ) -> FastFoldStatsResult:
        """Read stats for the players a Fast-Fold table currently seats.

        Ends the read transaction the way HudReadService.read_batch does. On
        PostgreSQL a SELECT opens one, and leaving it open parks the connection
        "idle in transaction" holding its snapshot -- which stalls the importer
        writing alongside it, and eventually trips the worker's own
        idle_in_transaction_session_timeout.
        """
        try:
            gametype_id = None
            if request.hand_id is not None:
                info = database.get_gameinfo_from_hid(request.hand_id)
                gametype_id = info["gametypeId"] if info else None
            if gametype_id is None and request.site_name and request.pool_name:
                # A table the client log named before any of its hands was
                # imported. Without this the statistics query below is skipped
                # and the table's first update draws every block empty. Only
                # this pool's own hands are consulted, and only when the pool
                # is known: borrowing another table's stakes would be worse
                # than showing nothing.
                with contextlib.suppress(Exception):
                    gametype_id = database.get_last_gametype_id_for_table(
                        request.site_name,
                        request.pool_name,
                    )

            stat_dict = FastFoldEngine(db_connection=database).get_player_stats_for_seat_map(
                request.seat_map,
                db_conn=database,
                gametype_id=gametype_id,
                num_seats=request.num_seats,
            )
        finally:
            with contextlib.suppress(Exception):
                database.connection.rollback()

        return FastFoldStatsResult(
            temp_key=request.temp_key,
            seat_map=dict(request.seat_map),
            stat_dict=stat_dict,
            request_id=request.request_id,
        )

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
            fast_fold = isinstance(pending, FastFoldStatsRequest)
            try:
                if fast_fold:
                    result = self._read_fast_fold_stats(database, pending)
                else:
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
                if fast_fold:
                    # Seats are refreshed on the next log line anyway, so a failed
                    # read is not worth the batch-retry machinery.
                    log.warning("Fast-Fold stats read failed for table %s: %s", pending.temp_key, exc)
                else:
                    self.batch_failed.emit(pending, str(exc))
            else:
                if fast_fold:
                    self.fast_fold_stats_ready.emit(result)
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


class MacOSPermissionsDialog(QDialog):
    """Explicit, non-modal onboarding for the HUD's macOS permissions.

    Constructing or refreshing this dialog only runs side-effect-free
    preflights. Native prompts and System Settings are reached exclusively from
    the corresponding user-operated buttons.
    """

    status_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the permission status and action rows."""
        super().__init__(parent)
        self.setWindowTitle("FPDB macOS Permissions")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "FPDB checks these permissions without requesting them. "
            "Use the buttons below only when you want macOS to prompt or open System Settings.",
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        screen_note = QLabel(
            "macOS groups this under Screen & System Audio Recording. "
            "FPDB reads window metadata only and does not request microphone access.",
        )
        screen_note.setWordWrap(True)
        layout.addWidget(screen_note)

        grid = QGridLayout()
        grid.addWidget(QLabel("Permission"), 0, 0)
        grid.addWidget(QLabel("Status"), 0, 1)
        grid.addWidget(QLabel("Actions"), 0, 2, 1, 2)

        self.screen_status_label = QLabel()
        self.screen_request_button = QPushButton("Request Screen Recording")
        self.screen_settings_button = QPushButton("Open Screen Recording Settings")
        grid.addWidget(QLabel("Screen Recording"), 1, 0)
        grid.addWidget(self.screen_status_label, 1, 1)
        grid.addWidget(self.screen_request_button, 1, 2)
        grid.addWidget(self.screen_settings_button, 1, 3)

        self.accessibility_status_label = QLabel()
        self.accessibility_request_button = QPushButton("Request Accessibility")
        self.accessibility_settings_button = QPushButton("Open Accessibility Settings")
        grid.addWidget(QLabel("Accessibility"), 2, 0)
        grid.addWidget(self.accessibility_status_label, 2, 1)
        grid.addWidget(self.accessibility_request_button, 2, 2)
        grid.addWidget(self.accessibility_settings_button, 2, 3)

        self.app_data_status_label = QLabel()
        self.app_data_info_label = QLabel(
            "Informational only: macOS prompts on the first protected Winamax file access, "
            "using the bundle's NSAppDataUsageDescription.",
        )
        self.app_data_info_label.setWordWrap(True)
        grid.addWidget(QLabel("App Data"), 3, 0)
        grid.addWidget(self.app_data_status_label, 3, 1)
        grid.addWidget(self.app_data_info_label, 3, 2, 1, 2)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        restart_note = QLabel(
            "After changing Screen Recording, quit and reopen FPDB yourself if table titles remain unavailable. "
            "FPDB never restarts automatically.",
        )
        restart_note.setWordWrap(True)
        layout.addWidget(restart_note)

        button_row = QHBoxLayout()
        self.recheck_button = QPushButton("Recheck")
        self.close_button = QPushButton("Close")
        button_row.addWidget(self.recheck_button)
        button_row.addStretch(1)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self.screen_request_button.clicked.connect(self._request_screen_recording)
        self.screen_settings_button.clicked.connect(self._open_screen_recording_settings)
        self.accessibility_request_button.clicked.connect(self._request_accessibility)
        self.accessibility_settings_button.clicked.connect(self._open_accessibility_settings)
        self.recheck_button.clicked.connect(self.refresh_status)
        self.close_button.clicked.connect(self.hide)

    @staticmethod
    def _binary_status(granted: bool) -> str:
        return "Granted" if granted else "Missing"

    def set_status(self, status: Any) -> None:
        """Render an already-computed permission snapshot without side effects."""
        self.screen_status_label.setText(self._binary_status(status.screen_recording))
        self.accessibility_status_label.setText(self._binary_status(status.accessibility))
        if status.app_data is None:
            self.app_data_status_label.setText("Not preflightable")
        else:
            self.app_data_status_label.setText(self._binary_status(status.app_data))
        self.screen_request_button.setEnabled(not status.screen_recording)
        self.accessibility_request_button.setEnabled(not status.accessibility)

    def refresh_status(self) -> Any:
        """Run diagnostic-only preflights and update the three status rows."""
        from fpdb.infrastructure.platform import permissions

        status = permissions.get_status()
        self.set_status(status)
        self.status_changed.emit(status)
        return status

    def _request_screen_recording(self) -> None:
        """Request Screen Recording after an explicit button click."""
        from fpdb.infrastructure.platform import permissions

        permissions.request_screen_recording_permission()
        self.refresh_status()

    def _request_accessibility(self) -> None:
        """Request Accessibility after an explicit button click."""
        from fpdb.infrastructure.platform import permissions

        permissions.request_accessibility_permission(prompt=True)
        self.refresh_status()

    @staticmethod
    def _open_screen_recording_settings() -> None:
        from fpdb.infrastructure.platform import permissions

        permissions.open_screen_recording_settings()

    @staticmethod
    def _open_accessibility_settings() -> None:
        from fpdb.infrastructure.platform import permissions

        permissions.open_accessibility_settings()


class HudMain(QObject):
    """A main() object to own both the socket thread and the gui."""

    # WinamaxLiveLogReader tails the log on its own thread; this carries its
    # updates onto the GUI thread, which is the only one allowed to touch the
    # HUD widgets or the database connection.
    winamax_table_update = Signal(object)

    AX_READS_PER_HAND = 6
    """How many times a table's window may be re-read within one hand.

    A read costs ~20ms through the macOS accessibility API and 100-300ms
    through Windows UIAutomation (measured on a Chromium window), and the seats
    settle within the first few log lines, so this bounds the cost while still
    letting a table that was read before it was drawn fill in. Reads stop as
    soon as the table looks full, so a full table costs one or two of them.
    """

    HERO_SLOT = 0
    """The bottom chair, which is where the client always draws the hero."""

    FF_IDLE_RECHECK_SECONDS = 20.0
    """Silence on a Fast-Fold table before its window is asked about directly.

    Long enough that a hand being tanked over is never mistaken for an empty
    table -- the log emits a line for every action, so a hand in progress
    refreshes this constantly -- and short enough that blocks do not sit over
    an abandoned felt for the minutes measured before the sweep existed.
    """

    FF_UNMAPPED_LOG_MEMORY = 500
    """Hands remembered as already reported missing from the log window map.

    Only large enough that the two snapshots of one hand fall inside it; the
    set is cleared wholesale past this, since an old hand can no longer be
    warned about twice.
    """

    MIN_PLAYERS_TO_SHOW = 2
    """Players a window must be drawing before its blocks are worth showing.

    The hero alone means the table is between hands or waiting for players, and
    stat blocks over an empty felt describe nobody.
    """

    FAST_FOLD_MAX_SEATS = 6
    """Seats on a Winamax Escape / Go Fast table.

    The window says what is played and for how much, but not how many chairs it
    draws; the pools are 6-max. An imported hand corrects it if that changes.
    """

    AX_RECHECK_DELAYS_MS = (250, 700, 1500)
    """When to look at the window again after a hand starts.

    Every log line of a new hand -- the hand id, both blinds, the hole cards --
    is written in the same millisecond, before the client has drawn the table,
    so re-reading on log lines alone would just repeat the same empty answer.
    """

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

        # Selecting the right module for the OS. Imported through the package
        # rather than as bare top-level modules: a bare "import OSXTables" only
        # resolves because the repository root happens to be on sys.path, which
        # is true of a source checkout and of HUD_main's own frozen archive, but
        # not of every way this file can be run. Each import stays inside its
        # branch -- the other two backends need bindings this platform lacks --
        # and the module is bound once, so mypy sees a single definition.
        tables: ModuleType
        if self.config.os_family == "Linux":
            # Simplified: XWayland support or X11 fallback
            if os.getenv("QT_QPA_PLATFORM") == "xcb" or not os.environ.get("WAYLAND_DISPLAY"):
                log.info("XWayland forced under wayland → backend XTables")
            else:
                log.info("Session X11 detected → backend XTables")
            from fpdb_3_legacy import XTables

            tables = XTables
        elif self.config.os_family == "Mac":
            from fpdb_3_legacy import OSXTables

            tables = OSXTables
        elif self.config.os_family in ("XP", "Win7"):
            from fpdb_3_legacy import WinTables

            tables = WinTables
        log.info("HudMain starting: Using db name = %s", db_name)
        self.Tables = tables

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
            # Canonical window_id -> temp_key -> generation mapping. hud_dict is
            # keyed by a table's text name, which a Fast-Fold pool shares across
            # several windows; this is what makes "one renderer per window"
            # enforceable rather than hoped for.
            self._window_registry = HudWindowRegistry()
            self._hud_generation = 0
            self._macos_permissions_dialog: MacOSPermissionsDialog | None = None
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
            # Winamax log pool -> hud_dict key, learned once a hand from that
            # table has been imported and reused while the table stays open.
            self._winamax_pool_huds: dict[str, str] = {}
            # Imported hands use the human table key while a live FastFold HUD
            # may also carry a window discriminator. Keep that alias explicit
            # instead of making every caller guess with string prefixes.
            self._fast_fold_aliases: dict[str, str] = {}
            # hud_dict keys known to be Fast-Fold tables.
            self._fast_fold_tables: set[str] = set()
            # hud_dict key -> the seat map last sent to the worker, so an
            # unchanged table does not queue a read on every log line.
            self._fast_fold_pending: dict[str, dict[int, str]] = {}
            # Pools reported once as having no HUD of their own, so the warning
            # is not repeated on every log line.
            self._unpaired_pools: set[str] = set()
            # window title -> (hand id, slot -> login read off that window). Kept
            # per window so two tables do not evict each other, and per hand
            # because each read walks another process's accessibility tree.
            self._ax_rings: dict[str, tuple[str, dict[int, str], int]] = {}
            # Timeline bookkeeping: when each hand's first log line arrived, and
            # which hand/table request is currently allowed to update the HUD.
            self._ff_started: dict[str, float] = {}
            self._ff_pending_hand: dict[str, str] = {}
            self._ff_pending_request: dict[str, int] = {}
            # HUD generation each in-flight read was started for, so a reply
            # that outlives its HUD is dropped instead of painting the rebuild.
            self._ff_pending_generation: dict[str, int | None] = {}
            self._ff_request_sequence = 0
            # Hands already reported as absent from the log window map. Both
            # snapshots of one hand pass through qualification, and warning
            # twice made one delayed hand look like two.
            self._ff_unmapped_logged: set[str] = set()
            self._import_request_sequence = 0
            # When each Fast-Fold table was last spoken about by the client
            # log. A table nobody has mentioned for a while is asked directly
            # whether it still seats anyone; see _sweep_stale_fast_fold_tables.
            self._ff_last_activity: dict[str, float] = {}
            # Learned from the first imported Winamax hand. A log-created HUD
            # does not need it (it reads nothing from the database), but keeping
            # it lets the table carry the same identity as an imported one.
            self._winamax_site_id: Any = None
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

            self._initialize_winamax_live_sources()

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

            self._cleanup_timer = QTimer(self)
            self._cleanup_timer.setInterval(2000)
            self._cleanup_timer.timeout.connect(self._cleanup_closed_windows)
            self._cleanup_timer.timeout.connect(self._sweep_stale_fast_fold_tables)
            self._cleanup_timer.start()

            self._db_worker: HudReadWorker | None = HudReadWorker(self.config, parent=self)
            self._db_worker.ready.connect(self._on_db_worker_ready)
            self._db_worker.snapshot_ready.connect(self._on_db_snapshot)
            self._db_worker.unavailable.connect(self._on_db_worker_unavailable)
            self._db_worker.batch_failed.connect(self._on_db_batch_failed)
            self._db_worker.fast_fold_stats_ready.connect(self._on_fast_fold_stats)
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
        """Diagnose macOS privacy permissions without prompting or opening Settings.

        This startup path is deliberately identical for source and frozen
        builds. Permission requests belong only to the explicit onboarding
        buttons in :class:`MacOSPermissionsDialog`.
        """
        try:
            from fpdb.infrastructure.platform import permissions
        except Exception:
            log.debug("macOS permissions preflight unavailable", exc_info=True)
            self._macos_permission_status = None
            return

        status = permissions.get_status()
        self._macos_permission_status = status
        if status.all_granted:
            log.info("macOS permissions OK (Screen Recording + Accessibility granted)")
        for message in permissions.describe_missing(status):
            log.warning(message)
        if status.app_data is None:
            log.info("macOS App Data permission is managed by macOS and cannot be preflighted safely")

    @staticmethod
    def _site_enabled_in_config(config: Any, site_name: str) -> bool:
        """Read an enabled-site flag from the loaded config without resolving paths."""
        try:
            enabled_sites = config.get_supported_sites()
            wanted = site_name.casefold()
            return any(str(site).casefold() == wanted for site in enabled_sites)
        except Exception:
            log.warning("Could not read enabled sites while initializing %s live sources", site_name, exc_info=True)
            return False

    def _initialize_winamax_live_sources(self) -> None:
        """Start Winamax-only helpers when Winamax is enabled in the loaded config."""
        self.winamax_ax_seats = None
        self.winamax_pool_games = None
        self.winamax_log_reader = None
        if not self._site_enabled_in_config(self.config, "Winamax"):
            log.info("Winamax is disabled; live log and Accessibility helpers will not be initialized")
            return

        from fpdb_3_legacy.winamax_ax_seats import WinamaxAXSeatReader, is_supported
        from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader
        from fpdb_3_legacy.winamax_pool_games import WinamaxPoolGames

        # Reads seats off the table window itself. The log can only say who has
        # acted, and never where they sit; this knows both, immediately.
        self.winamax_ax_seats = WinamaxAXSeatReader() if is_supported() else None
        if self.winamax_ax_seats is not None:
            # Whatever the reader has to build, it builds now: the first hand of
            # the session must not pay for it on the GUI thread.
            with contextlib.suppress(Exception):
                self.winamax_ax_seats.prewarm()

        # The window says which game it deals only to a process holding macOS
        # Accessibility. Imported hands say it unconditionally, so keep what
        # they prove for later live hands.
        self.winamax_pool_games = WinamaxPoolGames(
            Path(Configuration.CONFIG_PATH) / "winamax_pool_games.json" if Configuration.CONFIG_PATH else None,
        )

        # Queued by Qt because the reader emits from its tailing thread.
        self.winamax_table_update.connect(self._on_winamax_table_update)
        self.winamax_log_reader = WinamaxLiveLogReader(
            on_table_update=self.winamax_table_update.emit,
        )
        self.winamax_log_reader.start()

    def show_macos_permissions(self) -> None:
        """Show the explicit macOS permission onboarding window."""
        dialog = getattr(self, "_macos_permissions_dialog", None)
        if dialog is None:
            dialog = MacOSPermissionsDialog(self.main_window)
            dialog.status_changed.connect(self._remember_macos_permission_status)
            self._macos_permissions_dialog = dialog
        dialog.refresh_status()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _remember_macos_permission_status(self, status: Any) -> None:
        """Keep the latest UI preflight snapshot for diagnostics."""
        self._macos_permission_status = status

    def _on_application_state_changed(self, state: Any) -> None:
        """Recheck an open onboarding window after returning from Settings."""
        if state != Qt.ApplicationState.ApplicationActive:
            return
        dialog = getattr(self, "_macos_permissions_dialog", None)
        if dialog is not None and dialog.isVisible():
            dialog.refresh_status()

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
        fast_unsupported = info.fast and not self._has_live_seat_source(info.site_name)
        if fast_unsupported or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            return None

        qualified = self._qualify_fast_fold_table(info, hand_id)
        if qualified is None:
            return None
        info = qualified.info
        table_name = info.table_name
        table_info = info

        temp_key = self._get_temp_key(info.game_type, info.tour_number, info.tab_number, table_name)
        if info.fast:
            self._fast_fold_tables.add(temp_key)
        resolved_key = self._resolve_fast_fold_key(temp_key, table_no=qualified.table_no)
        if resolved_key != temp_key:
            return resolved_key
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

    def _resolve_fast_fold_key(self, temp_key: str, table_no: str | None = None) -> str:
        """Resolve an imported human key to its active window HUD key.

        An imported hand carries the pool's name; the live log built that
        table's HUD under a key qualified by its native window id. Failing to
        connect the two is what makes an import rebuild a HUD that is already
        on screen, so three routes are tried before giving up and returning the
        bare key: the alias learned when the live HUD was created, a single
        window-qualified key under this name, and -- when the client's window
        index is known -- the window itself, which is the only identity that
        cannot be confused between two tables of one pool.
        """
        aliases = getattr(self, "_fast_fold_aliases", {})
        aliased = aliases.get(temp_key)
        hud_dict = getattr(self, "hud_dict", {})
        if isinstance(aliased, str) and aliased in hud_dict:
            return aliased
        candidates = [key for key in hud_dict if key.startswith(f"{temp_key} #")]
        if len(candidates) == 1:
            return candidates[0]

        window_key = self._live_hud_key_for_table_no(table_no)
        if window_key is not None:
            # Remember it so the next hand on this pool takes the cheap route.
            if isinstance(aliases, dict):
                aliases[temp_key] = window_key
            return window_key
        return temp_key

    def _live_hud_key_for_table_no(self, table_no: str | None) -> str | None:
        """Return the HUD key already rendering the client window ``table_no``.

        Asks the resolver which native window carries that client index, then
        the registry which HUD holds it. Silent when the resolver is absent or
        the window has closed: the caller then goes on to create a HUD, which
        is the right outcome when no renderer holds the window.
        """
        if not table_no:
            return None
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            return None
        try:
            window = reader.find_table_window(table_no)
        except Exception:
            log.exception("Could not resolve Winamax window for client index %s", table_no)
            return None
        if window is None or getattr(window, "window_id", None) is None:
            return None
        registry = getattr(self, "_window_registry", None)
        registered = registry.key_for(window.window_id) if registry is not None else None
        if registered is not None and registered in getattr(self, "hud_dict", {}):
            return registered
        existing = self._find_hud_by_window_id(window.window_id)
        return None if existing is None else existing[0]

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
        if self.config.os_family == "Mac":
            self._macos_permissions_dialog = None
            self.macos_permissions_button = QPushButton("macOS Permissions…")
            self.macos_permissions_button.clicked.connect(self.show_macos_permissions)
            self.vb.addWidget(self.macos_permissions_button)
            app = QApplication.instance()
            if app is not None:
                app.applicationStateChanged.connect(self._on_application_state_changed)
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

        # Stop every timer owned by the HUD before the event loop can dispatch
        # another callback against tables that are already being torn down.
        for timer_name in ("_cleanup_timer", "check_tables_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                with contextlib.suppress(RuntimeError):
                    timer.stop()

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

    def _clear_fast_fold_table(self, temp_key: str, hud: Hud.Hud, hand_id: str, reason: str) -> None:
        """Take a Fast-Fold table's blocks down and say why.

        The seat windows hide themselves when their seat holds nobody, so
        emptying the seats is what removes them from an idle felt.
        """
        pending = self._fast_fold_pending.pop(temp_key, None)
        pending_requests = getattr(self, "_ff_pending_request", None)
        if pending_requests is not None:
            pending_requests.pop(temp_key, None)
        pending_hands = getattr(self, "_ff_pending_hand", None)
        if pending_hands is not None:
            pending_hands.pop(temp_key, None)
        pending_generations = getattr(self, "_ff_pending_generation", None)
        if pending_generations is not None:
            pending_generations.pop(temp_key, None)
        if pending is None and not getattr(hud, "stat_dict", None) and not getattr(hud, "seat_players", None):
            return  # already down
        FastFoldEngine.clear_seats(hud)
        self._ff_trace(hand_id, "cleared", f"table={temp_key} ({reason})")

    def _sweep_stale_fast_fold_tables(self) -> None:
        """Take down blocks left over a table the log has gone quiet on.

        Clearing a Fast-Fold table is otherwise driven entirely by the client
        log: the hand-over line, or the next hand's start. Neither arrives when
        the hero has been moved away and the felt is waiting for players, and
        neither arrives for a hand that was already finished when the reader
        started tailing -- which is why starting the HUD mid-hand left one
        table showing the remains of a hand nobody was playing. Measured on a
        real session, blocks stayed up over an empty table for 50, 80 and 124
        seconds at a stretch.

        So a table nobody has said anything about for a while is asked
        directly. Only a window that answers with the hero drawn and nobody
        else is cleared: the client always draws the hero when it draws the
        table at all, so a read without the hero is a failed or half-finished
        read rather than an empty table, and acting on it would blank a live
        table every time the accessibility API was slow.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            return
        now = time.monotonic()
        for temp_key, hud in list(self.hud_dict.items()):
            if not getattr(hud, "is_fast_fold", False):
                continue
            if not (getattr(hud, "stat_dict", None) or getattr(hud, "seat_players", None)):
                continue  # nothing on screen to take down
            idle = now - self._ff_last_activity.get(temp_key, now)
            if idle < self.FF_IDLE_RECHECK_SECONDS:
                continue

            slots = self._read_window_slots(hud)
            # Whatever the answer, do not ask again for another idle period:
            # each read walks another process's accessibility tree.
            self._ff_last_activity[temp_key] = now
            if slots is None or self.HERO_SLOT not in slots:
                continue  # could not read it; leave what is on screen alone
            if len(slots) >= self.MIN_PLAYERS_TO_SHOW:
                continue  # really still being played

            self._clear_fast_fold_table(
                temp_key,
                hud,
                "idle-sweep",
                f"the window seats {len(slots)} player(s) after {idle:.0f}s without a log line",
            )

    def _read_window_slots(self, hud: Hud.Hud) -> dict[int, str] | None:
        """Read a table window's seats now, bypassing the per-hand cache.

        None when there is nothing to read from -- no resolver, or a HUD whose
        table has no title -- which the caller must not confuse with an empty
        table.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        table = getattr(hud, "table", None)
        title = getattr(table, "title", "") or ""
        if reader is None or not title:
            return None
        try:
            return reader.read_window(
                title,
                getattr(hud, "max", 6) or 6,
                window_id=getattr(table, "number", None),
            ) or {}
        except Exception:
            log.exception("Could not re-read the Fast-Fold window %r while sweeping idle tables", title)
            return None

    def _cleanup_closed_windows(self) -> None:
        """Close HUD overlays for Winamax table windows that have closed at session end."""
        import platform
        if platform.system() != "Windows":
            return
        import ctypes
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
        is_window = windll.user32.IsWindow
        to_remove = []
        for temp_key, hud in list(self.hud_dict.items()):
            if not getattr(hud, "is_fast_fold", False):
                continue
            m = re.search(r"#(\d+)$", temp_key)
            if m:
                hwnd = int(m.group(1))
                if not is_window(hwnd):
                    to_remove.append((temp_key, hud))
        for temp_key, hud in to_remove:
            log.info("Closing Fast-Fold HUD for closed window: %s", temp_key)
            self._clear_fast_fold_table(temp_key, hud, "session-end", "window closed")
            close_hud = getattr(hud, "close", getattr(hud, "kill", None))
            if callable(close_hud):
                with contextlib.suppress(Exception):
                    close_hud()
            self.hud_dict.pop(temp_key, None)
            # This path bypasses idle_kill, so the window it held has to be
            # given back explicitly or the next HUD on it reads as a duplicate.
            self._window_registry.release(temp_key)
            aliases = getattr(self, "_fast_fold_aliases", None)
            if aliases is not None:
                for alias, live_key in list(aliases.items()):
                    if live_key == temp_key:
                        aliases.pop(alias, None)

    def _recheck_window(self, pool: str) -> None:
        """Re-run a table's live update once the client has had time to draw it."""
        reader = getattr(self, "winamax_log_reader", None)
        table = reader.get_table(pool) if reader is not None else None
        if table is not None:
            self._on_winamax_table_update(table)

    def _ff_trace(self, hand_id: str, event: str, detail: str = "") -> None:
        """One timeline line per step of a live Fast-Fold update.

        At WARNING because that is the level this HUD's diagnostics are pinned
        to (see DIAGNOSTIC_LEVEL_CAP): a report of "the seats are wrong" cannot
        be acted on without knowing what was read, when, and from where. ``+Nms``
        is measured from the hand-start line, so a slow step is visible as a
        gap rather than having to be inferred.
        """
        started = self._ff_started.get(hand_id)
        elapsed = "" if started is None else f" +{(time.monotonic() - started) * 1000:.0f}ms"
        log.warning("FF[%s]%s %s %s", hand_id, elapsed, event, detail)

    def _next_fast_fold_request_id(self) -> int:
        """Return a process-local id for the next asynchronous seat read."""
        request_id = int(getattr(self, "_ff_request_sequence", 0)) + 1
        self._ff_request_sequence = request_id
        return request_id

    def _on_winamax_table_update(self, update: Any) -> None:
        """Apply a live Winamax log update. Runs on the GUI thread."""
        if not update.pool.startswith(FAST_FOLD_POOL_PREFIX):
            # An ordinary cash or tournament table. It has a HUD of its own,
            # driven by imports; tracing it and scheduling window rechecks for
            # it would be work with nothing at the end of it.
            return

        if update.hand_id not in self._ff_started:
            # The hand-start line: the clock for everything that follows.
            if len(self._ff_started) > 200:
                self._ff_started.clear()
            self._ff_started[update.hand_id] = time.monotonic()
            lag = ""
            if update.logged_at_ms:
                lag = f" (read {time.time() * 1000 - update.logged_at_ms:.0f}ms after the client wrote it)"
            self._ff_trace(
                update.hand_id,
                "hand-start",
                f"pool={update.pool} [table] {update.table_no}{lag}",
            )
            # The client writes the hand-start line before it has drawn the new
            # table, and the blinds and hole cards follow in the same
            # millisecond -- so every log line of this hand arrives too early to
            # see the players. Come back once the window has caught up.
            for delay_ms in self.AX_RECHECK_DELAYS_MS:
                QTimer.singleShot(delay_ms, lambda pool=update.pool: self._recheck_window(pool))

        found = self._find_fast_fold_hud(update)
        if found is None:
            return
        temp_key, hud = found
        # What the idle sweep measures staleness against.
        self._ff_last_activity[temp_key] = time.monotonic()

        if update.finished:
            # The hand is over, or the hero folded and was moved on. Either way
            # nobody is at this table now, and leaving the blocks up over an
            # empty felt is the one thing worse than showing nothing.
            reason = "hero folded, moving on" if update.hero_left else "hand over"
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, reason)
            return

        last_hand = getattr(hud, "ff_last_hand_id", None)
        if last_hand != update.hand_id:
            setattr(hud, "ff_last_hand_id", update.hand_id)
            if getattr(hud, "stat_dict", None) or getattr(hud, "seat_players", None):
                self._clear_fast_fold_table(temp_key, hud, update.hand_id, "new hand start")

        max_seats = getattr(hud, "max", 6) or 6
        engine = FastFoldEngine(config=self.config)
        hero_seat = engine.pin_hero_seat(hud)

        # The window itself is the better source: it names every player at the
        # chair they are drawn in, so the table is right from the moment it is
        # dealt, empty chairs included. The log ring stays as the fallback for
        # platforms with no accessibility reader.
        slots = self._ax_slots(hud, update.hand_id, max_seats)
        # The client draws the hero in the bottom chair whenever the table is
        # drawn at all, sitting out included. A read without it caught the
        # window mid-redraw, and acting on it seats the wrong people for a
        # fraction of a second before the next read corrects them.
        drawn = self.HERO_SLOT in slots
        if drawn and len(slots) >= self.MIN_PLAYERS_TO_SHOW:
            # Slot 0 is the bottom-center chair where the client draws the hero.
            # Map slot 0 to the layout anchor seat (seat 3 for 6-max Winamax layouts).
            anchor_seat = engine._anchor_slot(hud) or 3
            seat_map = {((slot + anchor_seat - 1) % max_seats) + 1: login for slot, login in slots.items()}
            source = "window"
        elif slots and not self._ax_reads_spent(hud, update.hand_id):
            # Either the window holds nobody but the hero -- between hands, or
            # waiting for players -- or it was caught half-drawn. Either way
            # there is no table to describe yet; the rechecks will come back.
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, "table not dealt yet")
            return
        elif update.ring and update.hero:
            hand_start_time = self._ff_started.get(update.hand_id, 0)
            elapsed = time.monotonic() - hand_start_time if hand_start_time else 1.0
            if len(update.ring) < max_seats and elapsed < 0.5:
                # Wait for the full ring to accumulate in log buffer so all 6 player HUDs appear simultaneously
                return
            seat_map = build_seat_map(update.ring, update.hero, max_seats=max_seats, hero_seat=hero_seat)
            source = "log-ring"
        else:
            # Nothing to show yet: a new hand has started and neither the window
            # nor the log has said who is at the new table.
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, "no players known yet")
            return

        if not seat_map or seat_map == self._fast_fold_pending.get(temp_key):
            return
        self._fast_fold_pending[temp_key] = seat_map

        self._ff_trace(
            update.hand_id,
            "seats",
            f"table={temp_key} source={source} hero_seat={hero_seat} "
            f"seats={ {s: seat_map[s] for s in sorted(seat_map)} }",
        )
        self._request_fast_fold_stats(temp_key, hud, seat_map, update.hand_id)

    def _request_fast_fold_stats(
        self,
        temp_key: str,
        hud: Hud.Hud,
        seat_map: dict[int, str],
        hand_id: Any,
    ) -> None:
        """Ask the worker for the seated players' statistics.

        Reading them needs the real connection, which lives on the worker
        thread; the answer comes back through ``fast_fold_stats_ready``. The
        request carries the site and pool as well as a reference hand, because
        a table the client log named before any of its hands was imported has
        no hand of its own and would otherwise get no statistics at all.
        """
        worker = getattr(self, "_db_worker", None)
        if worker is None:
            self._ff_trace(hand_id, "stats-skipped", "no database worker")
            return
        request_id = self._next_fast_fold_request_id()
        self._ff_pending_hand[temp_key] = hand_id
        self._ff_pending_request[temp_key] = request_id
        # The generation this read belongs to. A HUD destroyed and rebuilt
        # while the worker is busy gets a new one, and the answer to the old
        # request must not be painted onto the replacement's windows.
        self._ff_pending_generation[temp_key] = getattr(hud, "_fpdb_generation", None)
        reference_hand = self._stats_reference_hand(temp_key)
        self._ff_trace(
            hand_id,
            "stats-requested",
            f"table={temp_key} window_id={getattr(getattr(hud, 'table', None), 'number', None)} "
            f"generation={self._ff_pending_generation[temp_key]} request={request_id} "
            f"reference_hand={reference_hand}",
        )
        worker.submit(
            FastFoldStatsRequest(
                temp_key=temp_key,
                seat_map=seat_map,
                hand_id=reference_hand,
                site_name=getattr(getattr(hud, "table", None), "site", "") or "Winamax",
                pool_name=self._pool_name(temp_key),
                num_seats=getattr(hud, "max", 6) or 6,
                request_id=request_id,
            ),
        )

    @staticmethod
    def _pool_name(temp_key: str) -> str:
        """The table name a hand history records, taken back out of a HUD key.

        A Fast-Fold HUD key is the pool plus the client's window index plus the
        native window id ("Casablanca 5 #61825"); the hands themselves are
        written under the bare pool name. Stripping both suffixes is what lets
        the worker find a hand of this pool when the table has none of its own.
        """
        return re.sub(r"\s+\d+$", "", re.sub(r"\s*#\d+$", "", temp_key)).strip()

    def _stats_reference_hand(self, temp_key: str) -> Any:
        """A hand to take the gametypeId from when reading live player stats.

        This table's own last hand, when it has one. A window that has not had a
        hand imported yet may use another window from the same pool, which is
        still narrower than guessing from the newest global Gametypes row.

        None when nothing has been imported yet -- the first table of a
        session. The worker then resolves the gametypeId from the pool's own
        last hand instead; see ``get_last_gametype_id_for_table``.
        """
        hand_id = self._last_processed_hands.get(temp_key)
        if hand_id is not None:
            return hand_id

        aliases = getattr(self, "_fast_fold_aliases", {})
        for imported_key, live_key in aliases.items():
            if live_key == temp_key:
                hand_id = self._last_processed_hands.get(imported_key)
                if hand_id is not None:
                    return hand_id

        clean_key = re.sub(r"\s*#\d+$", "", temp_key)
        base = re.sub(r"\s+\d+$", "", clean_key)
        for other_key, other_hand in self._last_processed_hands.items():
            clean_other = re.sub(r"\s*#\d+$", "", other_key)
            if re.sub(r"\s+\d+$", "", clean_other) == base:
                return other_hand
        return None

    def _ax_slots(self, hud: Hud.Hud, hand_id: str, max_seats: int) -> dict[int, str]:
        """Players drawn on this table's window, keyed by layout slot from the bottom.

        Read once per hand and remembered: the seats cannot change within one,
        while the log emits a line for every action, and each read is a
        synchronous walk of another process's accessibility tree (~20ms).

        Empty when the platform has no reader, or the window could not be read;
        the caller then falls back to the log-derived ring.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        table = getattr(hud, "table", None)
        title = getattr(table, "title", "") or ""
        if reader is None or not title:
            return {}

        table_key = getattr(table, "key", None) or title
        cached_hand, cached_slots, reads = self._ax_rings.get(table_key, (None, {}, 0))
        if cached_hand != hand_id:
            cached_slots, reads = {}, 0

        # The hand-start line beats the client to the draw: read then and only
        # the hero is on the table yet. So keep re-reading on later lines of the
        # same hand, taking the fullest answer, until the table is full or the
        # budget runs out -- caching that first partial read is what left the
        # overlay showing one player for a whole hand.
        if (self.HERO_SLOT in cached_slots and len(cached_slots) >= max_seats - 1) or len(cached_slots) >= max_seats or reads >= self.AX_READS_PER_HAND:
            return cached_slots

        table_pos = None
        if table is not None and getattr(table, "x", None) is not None and getattr(table, "y", None) is not None:
            table_pos = (float(table.x), float(table.y))

        started = time.monotonic()
        # The window id is the table's identity: every window of a Fast-Fold
        # pool carries the same name, and resolving one by title again -- on
        # every read of every hand -- means enumerating the whole desktop.
        slots = reader.read_window(
            title,
            max_seats,
            table_pos=table_pos,
            window_id=getattr(table, "number", None),
        )
        took = (time.monotonic() - started) * 1000
        # A read holding the hero's chair beats one without it even when the
        # one without it names more players: the second caught the window
        # half-drawn, and its extra names are the previous table's.
        best = max(
            (cached_slots, slots),
            key=lambda answer: (self.HERO_SLOT in answer, len(answer)),
        )
        self._ax_rings[table_key] = (hand_id, best, reads + 1)

        if slots != cached_slots:
            empty = sorted(set(range(max_seats)) - set(best))
            self._ff_trace(
                hand_id,
                "window-read",
                f"{title!r} (key={table_key}) {took:.0f}ms read#{reads + 1} players={len(best)} "
                f"slots={ {s: best[s] for s in sorted(best)} } empty={empty}",
            )
        return best

    def _ax_reads_spent(self, hud: Hud.Hud, hand_id: str) -> bool:
        """Whether this hand's budget of window reads is used up for this table.

        Once it is, re-reading cannot improve the answer within this hand, so a
        window read that never showed a dealt table has said all it is going to
        say -- and the log-derived ring, slow as it is, describes the table
        better than nothing. Without this, a client that answers the
        accessibility API only partially (or not at all, while still yielding a
        label or two) would leave the overlay permanently blank, which is worse
        than the ring it replaced.
        """
        table = getattr(hud, "table", None)
        table_key = getattr(table, "key", None) or getattr(table, "title", "") or ""
        cached_hand, _cached_slots, reads = self._ax_rings.get(table_key, (None, {}, 0))
        return cached_hand == hand_id and reads >= self.AX_READS_PER_HAND

    def _on_fast_fold_stats(self, result: FastFoldStatsResult) -> None:
        """Apply stats the worker read for a Fast-Fold table. Runs on the GUI thread."""
        hand_id = self._ff_pending_hand.get(result.temp_key, "?")
        expected_request = getattr(self, "_ff_pending_request", {}).get(result.temp_key)
        if expected_request is None or result.request_id != expected_request:
            self._ff_trace(
                hand_id,
                "stats-dropped",
                f"table={result.temp_key} stale_request={result.request_id} expected={expected_request}",
            )
            return
        hud = self.hud_dict.get(result.temp_key)
        if hud is None:
            self._ff_trace(hand_id, "stats-dropped", f"table={result.temp_key} has no HUD any more")
            return

        requested_generation = getattr(self, "_ff_pending_generation", {}).get(result.temp_key)
        current_generation = getattr(hud, "_fpdb_generation", None)
        if requested_generation is not None and requested_generation != current_generation:
            # The HUD was torn down and rebuilt while this read was in flight.
            self._ff_trace(
                hand_id,
                "stats-dropped",
                f"table={result.temp_key} stale_generation={requested_generation} now={current_generation}",
            )
            return

        applied = FastFoldEngine.apply_seats(hud, result.seat_map, result.stat_dict)
        with_stats = sum(1 for row in result.stat_dict.values() if row.get("n"))
        self._ff_trace(
            hand_id,
            "stats-applied" if applied else "stats-empty",
            f"table={result.temp_key} players={len(result.stat_dict)} with_history={with_stats}",
        )

    def _has_live_seat_source(self, site_name: str) -> bool:
        """Whether a real-time seat source is running for this site.

        Only Winamax has one: its client writes a log this HUD tails. Without it
        a Fast-Fold HUD can only ever show the players of an already-finished
        hand, which is why such tables are still skipped elsewhere.
        """
        if str(site_name).lower() != "winamax":
            return False
        reader = getattr(self, "winamax_log_reader", None)
        return bool(reader is not None and reader.is_tailing)

    def _next_import_request_id(self) -> int:
        """Return a process-local id for the next imported-hand application.

        Paired with the hand id and the window id in the "FF import applied"
        line, this is what distinguishes one hand applied once from the same
        hand applied twice: two applications carry two request ids.
        """
        request_id = int(getattr(self, "_import_request_sequence", 0)) + 1
        self._import_request_sequence = request_id
        return request_id

    def _qualify_fast_fold_table(self, info: TableInfo, hand_id: Any) -> FastFoldQualification | None:
        """Qualify a Fast-Fold table name with the client window it was played on.

        Every Escape window on a pool writes its hands under the pool's name
        ("Casablanca"), so all of them key one HUD and overwrite each other's
        seats. The client log records which ``[table] N`` dealt each hand, and
        that index is also the suffix in the window title, so appending it both
        separates the HUDs and narrows the existing title search to the single
        matching window ("Winamax Casablanca 5").

        Returns ``None`` when the window cannot be determined -- typically a hand
        already in flight when the log tailing started. Creating a HUD from the
        bare pool name would let it claim whichever window matched first and
        report the wrong table number; the next hand carries the mapping.

        The hand's site id comes from the snapshot rather than a query: by the
        time this runs, ``db_connection`` is the database-free replay facade.

        This decides and says nothing. It runs once for the identity-only
        snapshot and again for the final one, and it used to announce "FF
        import: hand X -> window N" both times -- before the idempotence check
        that stops the second one from being applied. Two lines for one
        applied hand is what made the logs read like a double update. The
        announcement now lives at the point the hand is really applied; see
        :meth:`_log_fast_fold_import_applied`.
        """
        if not info.fast or not self._has_live_seat_source(info.site_name):
            return FastFoldQualification(info=info, table_no=None, site_hand_no=None)

        prepared = self._prepared_hands.get(str(hand_id))
        # The identity-only snapshot carries site_hand_no and nothing else, so
        # prefer it: it arrives a hand earlier than the Hand object does.
        site_hand_no = getattr(prepared, "site_hand_no", None) or getattr(
            getattr(prepared, "hand_instance", None), "handid", None
        )
        log_reader = getattr(self, "winamax_log_reader", None)
        table_no = log_reader.table_no_for_hand(site_hand_no) if log_reader is not None and site_hand_no else None
        if not table_no:
            # WARNING because this is what delays a table's HUD by a hand or two
            # at startup, and the delay is otherwise invisible. Said once per
            # hand: the identity-only and final snapshots both come through here.
            if str(hand_id) not in self._ff_unmapped_logged:
                self._ff_unmapped_logged.add(str(hand_id))
                if len(self._ff_unmapped_logged) > self.FF_UNMAPPED_LOG_MEMORY:
                    self._ff_unmapped_logged.clear()
                log.warning(
                    "FF import: hand %s (site id %s) is not in the log window map, so which window "
                    "it was played on is unknown; skipping it rather than keying a HUD on the bare "
                    "pool name %r. The next hand on that window carries the mapping.",
                    hand_id,
                    site_hand_no,
                    info.table_name,
                )
            return None

        # This hand settles what the pool deals, which is the one thing the log
        # cannot say. Kept so later hands on this pool -- and later sessions --
        # can build their HUD from the log alone.
        pool_games = getattr(self, "winamax_pool_games", None)
        if pool_games is not None:
            pool_games.remember(info.table_name, info.poker_game)
        return FastFoldQualification(
            info=info._replace(table_name=f"{info.table_name} {table_no}"),
            table_no=table_no,
            site_hand_no=site_hand_no,
        )

    def _log_fast_fold_import_applied(self, hand_id: Any, temp_key: str) -> None:
        """Announce an imported Fast-Fold hand at the moment it is applied.

        Carries ``(hand_id, window_id, request_id)`` so two lines for one hand
        can be told apart from one line for each of two hands -- the question
        the previous logging could not answer.
        """
        hud = self.hud_dict.get(temp_key)
        log.warning(
            "FF import applied: hand=%s table=%r window_id=%s request=%s generation=%s",
            hand_id,
            temp_key,
            getattr(getattr(hud, "table", None), "number", None),
            self._next_import_request_id(),
            getattr(hud, "_fpdb_generation", None),
        )

    def _hud_is_fast_fold(self, hud: Hud.Hud, temp_key: str = "") -> bool:
        """Whether this table plays the Fast-Fold format.

        Checked in order of reliability: active fast fold tables, base table
        names with matching table indices, imported hand game types, then window titles.
        """
        if getattr(hud, "is_fast_fold", False) is True:
            return True
        if temp_key and temp_key in self._fast_fold_tables:
            hud.is_fast_fold = True
            return True

        resolved_key = self._resolve_fast_fold_key(temp_key) if temp_key else temp_key
        if resolved_key and resolved_key != temp_key and resolved_key in self.hud_dict:
            hud.is_fast_fold = True
            return True

        clean_key = re.sub(r"\s*#\d+$", "", temp_key or "")
        hud_table_name = getattr(hud, "table_name", None) or ""
        clean_hud_name = re.sub(r"\s*#\d+$", "", hud_table_name if isinstance(hud_table_name, str) else "")

        for ff_table in list(self._fast_fold_tables):
            clean_ff = re.sub(r"\s*#\d+$", "", ff_table)
            for check in (clean_key, clean_hud_name):
                if not check:
                    continue
                if check == clean_ff:
                    hud.is_fast_fold = True
                    return True
                m1 = re.search(r"(\d+)\s*$", check)
                m2 = re.search(r"(\d+)\s*$", clean_ff)
                if m1 and m2 and m1.group(1) == m2.group(1):
                    b1 = re.sub(r"\s*\d+$", "", check)
                    b2 = re.sub(r"\s*\d+$", "", clean_ff)
                    if b1 in b2 or b2 in b1:
                        hud.is_fast_fold = True
                        return True

        table_name = getattr(hud, "table_name", None)
        game_type = getattr(hud, "game_type", None)
        is_ff = is_fast_fold_table(
            table_name if isinstance(table_name, str) and table_name else temp_key,
            game_type=game_type if isinstance(game_type, str) else "",
        )
        if is_ff:
            hud.is_fast_fold = True
        return is_ff

    def _ensure_fast_fold_hud(self, update: Any) -> tuple[str, Hud.Hud] | None:
        """Create the HUD for a Fast-Fold window the log has just reported.

        Display is driven by the log, which names the window the instant a hand
        starts. Hand histories cannot do this job: they arrive seconds to
        minutes later, every window on a pool writes under the same table name,
        and at startup a backlog of already-finished hands would each claim a
        window at random. They are left to do what only they can -- bring the
        statistics.

        The window describes itself ("ESCAPE - 0,01-0,02 EUR - Pot Limit
        Omaha"), which is where the game comes from; everything else is the
        pool's own shape.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            self._ff_trace(
                update.hand_id,
                "create-deferred",
                "Winamax table resolver unavailable; waiting for an imported hand",
            )
            return None

        window = reader.find_table_window(update.table_no)
        if window is None:
            self._ff_trace(
                update.hand_id,
                "create-deferred",
                f"no open Winamax window is titled with the client index {update.table_no}; "
                f"waiting for an imported hand",
            )
            return None
        if window.window_id is not None:
            temp_key = f"{window.table_name} #{window.window_id}"
        else:
            temp_key = window.table_name
        aliases = getattr(self, "_fast_fold_aliases", None)
        if aliases is not None:
            aliases[window.table_name] = temp_key
        if temp_key in self.hud_dict and not self._discard_loading_hud(temp_key, update.hand_id):
            return temp_key, self.hud_dict[temp_key]

        # The table title is not unique in Fast-Fold.  The native window id is
        # the stable identity, so reuse a HUD already attached to that window
        # even if an earlier resolver pass produced a different text key.
        existing = self._find_hud_by_window_id(window.window_id)
        if existing is not None:
            existing_key, existing_hud = existing
            if not self._discard_loading_hud(existing_key, update.hand_id):
                if aliases is not None:
                    aliases[window.table_name] = existing_key
                existing_hud.is_fast_fold = True
                self._ff_trace(
                    update.hand_id,
                    "hud-reused",
                    f"table={existing_key} window={window.title!r} window_id={window.window_id}",
                )
                return existing_key, existing_hud

        # The window states the game only when the accessibility API answered.
        # Otherwise fall back on what an imported hand from this pool proved.
        pool_games = getattr(self, "winamax_pool_games", None)
        poker_game = window.poker_game or (pool_games.get(temp_key) or pool_games.get(window.table_name) if pool_games is not None else None)
        if not poker_game:
            self._ff_trace(
                update.hand_id,
                "create-skipped",
                f"{window.title!r} does not say what is being played ({window.description!r}) and "
                f"no hand from this pool has been imported yet; the next one settles it",
            )
            return None

        info = TableInfo(
            table_name=temp_key,
            max_seats=self.FAST_FOLD_MAX_SEATS,
            poker_game=poker_game,
            game_type="ring",
            fast=True,
            site_id=self._winamax_site_id,
            site_name="Winamax",
            num_seats=self.FAST_FOLD_MAX_SEATS,
        )
        # A loading HUD reads nothing from the database, but it does take the
        # hole cards from the prepared hand; there is no hand here, so stand one
        # in rather than sending it to look for one.
        synthetic_hand = f"live:{update.hand_id}"
        self._prepared_hands[synthetic_hand] = HudPreparedHand(hand_id=synthetic_hand)

        self._fast_fold_tables.add(temp_key)
        # A full HUD, not the loading placeholder: that one has no aux windows,
        # so it can only ever show "Loading HUD..." until an import replaces it.
        # The seats arrive from the window moments later.
        create_kwargs: dict[str, Any] = {"stats": {}}
        if window.window_id is not None:
            create_kwargs["resolved_window"] = window
        self._create_new_hud(
            synthetic_hand,
            temp_key,
            info,
            self._winamax_site_id,
            self.FAST_FOLD_MAX_SEATS,
            "Winamax",
            **create_kwargs,
        )
        hud = self.hud_dict.get(temp_key)
        if hud is None:
            self._ff_trace(update.hand_id, "create-failed", f"table={temp_key} window={window.title!r}")
            return None

        hud.is_fast_fold = True
        self._ff_trace(
            update.hand_id,
            "hud-created",
            f"table={temp_key} window={window.title!r} game={poker_game} (from the log, no import needed)",
        )
        return temp_key, hud

    def _discard_loading_hud(self, temp_key: str, hand_id: Any) -> bool:
        """Tear down a loading placeholder so a real HUD can take its window.

        The placeholder an imported hand puts up has ``loading=True``, and
        ``idle_create`` returns from that before building a single aux window
        -- it exists to show "Loading HUD..." and nothing else. Adopting it
        because it holds the right native window, which is what the
        duplicate-renderer guard would otherwise do, leaves the live log
        writing seats into a HUD that has no windows to draw them in: the
        table stays on "Loading HUD..." for as long as it is open.

        Returns whether a placeholder was discarded, in which case the caller
        must go on and create the real HUD.
        """
        hud = self.hud_dict.get(temp_key)
        if hud is None or not getattr(hud, "is_loading", False):
            return False
        self._ff_trace(
            hand_id,
            "loading-replaced",
            f"table={temp_key} had no overlay windows; building the real HUD from the log",
        )
        self.idle_kill(temp_key)
        return temp_key not in self.hud_dict

    def _find_hud_by_window_id(self, window_id: Any) -> tuple[str, Hud.Hud] | None:
        """Return the HUD attached to ``window_id``, if one is already alive."""
        if window_id is None:
            return None
        for key, hud in self.hud_dict.items():
            table = getattr(hud, "table", None)
            if getattr(table, "number", None) == window_id:
                return key, hud
        return None

    def _find_fast_fold_hud(self, update: Any) -> tuple[str, Hud.Hud] | None:
        """Match a log pool to an open Winamax HUD.

        The log is what identifies a table as Fast-Fold: pools are named ``gf.``
        ("go fast"), which covers Escape and HOLD-UP too. The window title cannot
        be used for this -- an Escape table is titled "Winamax Casablanca 3",
        carrying only the display name and the client's table index, with no hint
        of the format.

        That trailing index is what ties a window to a ``[table] N`` line, so it
        is also what pairs a pool with a HUD when several tables are open.
        """
        if not update.pool.startswith(FAST_FOLD_POOL_PREFIX):
            return None

        candidates: list[tuple[str, Hud.Hud]] = [
            (temp_key, hud)
            for temp_key, hud in self.hud_dict.items()
            if str(getattr(hud, "site", "")).lower() == "winamax"
        ]
        if not candidates:
            return self._ensure_fast_fold_hud(update)

        chosen: tuple[str, Hud.Hud] | None = None
        indexed = False
        for temp_key, hud in candidates:
            title = getattr(getattr(hud, "table", None), "title", "") or ""
            m = re.search(r"(\d+)\s*$", title)
            if not m:
                continue
            indexed = True
            if m.group(1) == str(update.table_no):
                chosen = (temp_key, hud)
                break

        # Falling back to "the only table open" is right only when no window
        # title carried an index to match on. Once they do, a pool that matches
        # none of them belongs to a window whose HUD does not exist yet -- taking
        # somebody else's is how the wrong table's players end up on screen.
        if chosen is None and not indexed and len(candidates) == 1:
            chosen = candidates[0]

        if chosen is None:
            remembered = self._winamax_pool_huds.get(update.pool)
            chosen = next(((k, h) for k, h in candidates if k == remembered), None)

        if chosen is None:
            # No HUD for this window yet: build one from the window itself
            # rather than waiting for one of its hands to be imported.
            return self._ensure_fast_fold_hud(update)

        temp_key, hud = chosen

        # Every Escape window on a pool is named after the pool ("Casablanca"), so
        # hands from all of them import under one table name and share a single
        # HUD -- fpdb has no window-level identity to tell them apart. Feeding
        # that one HUD from several pools just makes it flip between tables, so
        # bind it to the first pool and leave the rest alone: one correct table
        # beats two wrong ones.
        bound = self._winamax_pool_huds.get(update.pool)
        if bound is None and temp_key in self._winamax_pool_huds.values():
            if update.pool not in self._unpaired_pools:
                self._unpaired_pools.add(update.pool)
                log.warning(
                    "Winamax pool %s (table %s) shares table name %r with a pool already "
                    "driving that HUD; its seats will not be shown. Multiple Escape tables "
                    "on one pool need per-window HUDs.",
                    update.pool,
                    update.table_no,
                    temp_key,
                )
            return None

        self._winamax_pool_huds[update.pool] = temp_key
        self._fast_fold_tables.add(temp_key)
        # The pool name is the authority, so record it on the HUD: the background
        # import path needs to know this table is Fast-Fold, and the hand history
        # it works from arrives far too late to decide it.
        hud.is_fast_fold = True
        return temp_key, hud

    def _handle_table_status(self, hud: Hud.Hud) -> None:
        """Handle status changes for a single table."""
        table = getattr(hud, "table", None)
        if table is None:
            # Preview and lightweight test HUDs can intentionally omit the
            # live table object. They must not break the shared status timer.
            return
        status = table.check_table()
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
        """Create a new HUD for a table.

        Refuses outright to put a second renderer on a window that already has
        one, and destroys the previous generation when a window's HUD key
        changes. Both cases are what a player sees as doubled overlays, and
        both are decided here rather than at each of the callers that can
        reach this method.
        """
        log.debug("Creating HUD for table %s and hand %s", args.temp_key, args.new_hand_id)
        window_id = getattr(args.table, "number", None)
        claim = self._window_registry.claim(window_id, args.temp_key)
        if claim.outcome is ClaimOutcome.DUPLICATE:
            log.warning(
                "HUD create refused: window %s already renders table %r at generation %s "
                "(session=%s pid=%s hand=%s)",
                window_id,
                args.temp_key,
                claim.generation,
                session_id(),
                os.getpid(),
                args.new_hand_id,
            )
            return
        if claim.outcome is ClaimOutcome.SUPERSEDED and claim.superseded is not None:
            log.warning(
                "HUD create supersedes table %r on window %s (generation %s -> %s); "
                "destroying the previous renderer first",
                claim.superseded.temp_key,
                window_id,
                claim.superseded.generation,
                claim.generation,
            )
            self._destroy_superseded_hud(claim.superseded.temp_key)

        self._hud_generation = claim.generation
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
        self.hud_dict[args.temp_key]._fpdb_generation = self._hud_generation
        # Before idle_create, because the aux windows read this in adj_seats()
        # when they are built. Setting it afterwards -- which is where every
        # caller used to set it -- left the seat rotation applied twice.
        if self._creation_is_fast_fold(args):
            self.hud_dict[args.temp_key].is_fast_fold = True

        args.table.hud = self.hud_dict[args.temp_key]

        self.hud_dict[args.temp_key].hud_params["new_max_seats"] = None  # trigger for seat layout change

        if not args.loading:
            for aw in self.hud_dict[args.temp_key].aux_windows:
                aw.update_data(args.new_hand_id, self.db_connection)

        self.idle_create(args)
        created = self.hud_dict[args.temp_key]
        log.warning(
            "HUD created: session=%s pid=%s generation=%s table=%r window_id=%s hand=%s "
            "profile=%r aux=%s overlays=%s",
            session_id(),
            os.getpid(),
            self._hud_generation,
            args.temp_key,
            window_id,
            args.new_hand_id,
            getattr(getattr(created, "stat_set", None), "name", None),
            self._describe_aux_windows(created),
            self._describe_overlay_win_ids(created),
        )
        log.debug("HUD for table %s created successfully.", args.temp_key)

    def _creation_is_fast_fold(self, args: HUDCreationArgs) -> bool:
        """Whether the HUD being created is for a Fast-Fold table.

        Decided from what the caller already knows rather than from the HUD
        object, because this has to be answered before the HUD's aux windows
        exist. ``context.speed`` is set by ``_create_new_hud`` for every path;
        the table set is the fallback for a direct ``create_HUD`` call.
        """
        if getattr(args.context, "speed", None) == "fast":
            return True
        return args.temp_key in getattr(self, "_fast_fold_tables", set())

    def _destroy_superseded_hud(self, temp_key: str) -> None:
        """Tear down a HUD whose window has been claimed by another key.

        Goes through the ordinary kill path so the label, the aux windows and
        the pending Fast-Fold state all go with it; leaving any of them behind
        is exactly the residual overlay this guard exists to prevent.
        """
        if temp_key not in self.hud_dict:
            self._window_registry.release(temp_key)
            return
        self.clear_table_stat_set_override(temp_key)
        self.idle_kill(temp_key)

    @staticmethod
    def _describe_aux_windows(hud: Hud.Hud) -> str:
        """Name the aux window classes attached to a HUD, with their count."""
        aux_windows = list(getattr(hud, "aux_windows", []) or [])
        names = ",".join(sorted({type(aux).__name__ for aux in aux_windows})) or "none"
        return f"{len(aux_windows)}[{names}]"

    @staticmethod
    def _describe_overlay_win_ids(hud: Hud.Hud) -> str:
        """List the native window ids of a HUD's own overlay windows.

        This is what tells a second renderer from a redrawn one: two sets of
        blocks over one table carry two disjoint sets of native ids, while one
        set painted twice keeps the ids it already had. ``m_windows`` holds the
        per-seat blocks, ``container`` the single-window aux types.
        """
        ids: list[str] = []
        for aux in list(getattr(hud, "aux_windows", []) or []):
            name = type(aux).__name__
            widgets = list((getattr(aux, "m_windows", None) or {}).values())
            container = getattr(aux, "container", None)
            if container is not None:
                widgets.append(container)
            for widget in widgets:
                win_id = getattr(widget, "winId", None)
                if not callable(win_id):
                    continue
                with contextlib.suppress(Exception):
                    ids.append(f"{name}:{int(win_id())}")
        return ",".join(ids) or "none"

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
                config,
                cards=cards,
                hand_instance=hand_instance,
            )

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
            values.get("screen_name") == self.hero.get(site_id) for values in stat_dict.values()
        ):
            if not self._hud_is_fast_fold(hud, temp_key):
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

        # On a Fast-Fold table the hand being imported finished seconds ago and
        # the hero has already been moved on. Its players are history, so the
        # live path owns this overlay outright -- including when it holds
        # nobody. Falling back to the imported hand when the live map is empty
        # is what put a finished table's players back on screen seconds after
        # the overlay had been cleared, and left them there once the hero sat
        # out and no further hand came to clear them again.
        if self._hud_is_fast_fold(hud, temp_key):
            stat_dict = getattr(hud, "stat_dict", None) or {}
            seat_players = getattr(hud, "fast_fold_seat_players", None) or {}
        else:
            self._merge_positions(stat_dict, new_hand_id)
            seat_players = self._seat_players(new_hand_id)

        try:
            hud.stat_dict = stat_dict
        except KeyError:
            log.exception("hud_dict[%s] was not found", temp_key)
            return False

        hud.seat_players = seat_players
        self._set_table_stats(hud, new_hand_id)
        hud.cards = self.get_cards(new_hand_id, hud.poker_game)
        for aw in hud.aux_windows:
            aw.update_data(new_hand_id, self.db_connection)
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

            if self._hud_is_fast_fold(self.hud_dict[table_name], table_name):
                # This refresh replaces stat_dict with the players of the last
                # hand imported for the table. On a Fast-Fold table those left
                # long ago, and the seats still point at the live players -- so
                # every block would look up a player id the statistics no longer
                # hold, and show a nameless column of NA. Its statistics come
                # from the live path instead.
                log.debug("Skipping global HUD refresh for Fast-Fold table %s", table_name)
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
        stats: dict | None = None,
        resolved_window: Any | None = None,
    ) -> None:
        """Create a new HUD for a table.

        ``loading`` builds the placeholder shown while a table's first hand is
        still being read: it has no aux windows, so it cannot display anything
        until a later hand replaces it.

        ``stats`` supplies the statistics directly instead of reading them from
        the database, which is what lets a table be created from the client log
        with no hand behind it -- a full HUD, aux windows and all, on a thread
        that has no database connection.

        ``resolved_window`` is a macOS Fast-Fold window already found at hand
        start. Passing it through prevents OSXTables from performing a second
        window scan that can disagree with the first one while TCC is changing.
        """
        if not resolved_window and self._resolve_fast_fold_key(temp_key) != temp_key:
            log.info("Skipping legacy HUD creation for %r: live FastFold HUD is already active", temp_key)
            return

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
        # Everything below that reads the database is skipped both for the
        # placeholder and when the caller brought its own statistics.
        from_database = stats is None and not loading
        if stats is not None:
            stat_dict = stats
        elif loading:
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
        cached_stats = self.stats_persistence.load_hud_stats(temp_key) if from_database else None
        if cached_stats:
            log.info(f"Found cached HUD stats for table {temp_key}, merging with current data")
            merged_data = self.stats_persistence.merge_stats(cached_stats, {"stat_dict": stat_dict})
            stat_dict = merged_data.get("stat_dict", stat_dict)
            log.debug("Merged cached stats with fresh database stats")

        if from_database:
            self._merge_positions(stat_dict, new_hand_id)
        if from_database and not any(stat_dict[key]["screen_name"] == self.hero[site_id] for key in stat_dict):
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
        if resolved_window is not None:
            table_kwargs["resolved_window"] = resolved_window
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
        # Fast-Fold tables were skipped outright because a hand history names
        # opponents the hero has already left behind by the time it is imported.
        # Winamax is now covered by the live log reader, which reports the real
        # composition within milliseconds, so a HUD there is worth creating.
        # Sites with no such source would still only show stale opponents.
        fast_unsupported = info.fast and not self._has_live_seat_source(site_name)
        if fast_unsupported or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            log.warning(
                "HUD creation skipped for hand %s table=%s db_site=%s hud_site=%s: "
                "fast=%s (live seat source=%s), aux_disabled=%s, site_enabled=%s",
                new_hand_id,
                table_name,
                site_name,
                hud_site_name,
                info.fast,
                self._has_live_seat_source(site_name),
                hud_site_name in aux_disabled_sites,
                hud_site_name in enabled_sites,
            )
            return None

        if str(site_name).lower() == "winamax" and info.site_id is not None:
            self._winamax_site_id = info.site_id

        qualified = self._qualify_fast_fold_table(info, new_hand_id)
        if qualified is None:
            return None
        info = qualified.info
        table_name = info.table_name
        table_info = info

        temp_key = self._get_temp_key(game_type, tour_number, tab_number, table_name)
        if info.fast:
            # Remembered so the background import path keeps the live composition
            # from the very first hand, before any log update has been matched.
            self._fast_fold_tables.add(temp_key)
            temp_key = self._resolve_fast_fold_key(temp_key, table_no=qualified.table_no)
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
        if info.fast:
            # Past the idempotence check and past creation: this hand really
            # reached the screen, which is the only case worth announcing.
            self._log_fast_fold_import_applied(new_hand_id, temp_key)
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
                overlays = self._describe_overlay_win_ids(hud)
                self.hud_dict[table].kill()
                del self.hud_dict[table]
                released = self._window_registry.release(table)
                log.warning(
                    "HUD destroyed: session=%s pid=%s generation=%s table=%r window_id=%s overlays=%s",
                    session_id(),
                    os.getpid(),
                    None if released is None else released.generation,
                    table,
                    None if released is None else released.window_id,
                    overlays,
                )
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
            # The session id and pid are what let one trace file holding
            # several relaunches be split back into them.
            handler.setFormatter(
                logging.Formatter(f"%(asctime)s [{session_id()}/%(process)d] - %(message)s"),
            )
            trace_log.addHandler(handler)
            trace_log.propagate = False
            trace_log.info("HUD Trace Log Initialized")

            # NB: diagnostics go through this "hud_trace" logger, never through
            # "hud_main". get_logger() re-applies the level saved in
            # ~/fpdb_logs/logger_config.json on every call, and "hud_main" is saved
            # at ERROR -- which is why the HUD's INFO/WARNING traces never reached
            # HUD-log.txt. "hud_trace" is unregistered, so this handler survives.
            trace_log.info("HUD trace channel active (bypasses fpdb logger registry)")

    identity = log_process_identity(log, ROLE_HUD)

    try:
        hud_instance_lock = acquire_hud_instance_lock(format_identity(identity))
    except LockUndeterminedError as exc:
        # Not a refusal: the lock mechanism never answered. Saying "another HUD
        # owns the lock" here would be a guess, and the one time it was wrong
        # the user had no HUD to quit and no way to tell (#259).
        log.error(
            "HUD startup aborted: the single-HUD lock %s could not be tested (%s). This process "
            "(pid=%s session=%s) is exiting. Whether another HUD is running is unknown.",
            HUD_INSTANCE_LOCK_NAME,
            exc,
            identity["pid"],
            identity["session"],
        )
        raise SystemExit(HUD_LOCK_UNDETERMINED_EXIT_CODE) from None
    except SingleInstanceError:
        # Naming the owner matters: two HUDs draw two sets of stat blocks over
        # every table, and without this the second one dies silently and the
        # player is left looking at a duplicate nobody can account for.
        log.error(
            "HUD startup refused: another FPDB HUD already owns %s. This process (pid=%s session=%s) "
            "is exiting. Owner: %s",
            HUD_INSTANCE_LOCK_NAME,
            identity["pid"],
            identity["session"],
            read_lock_owner() or "not recorded (an older build, or a lock with no file)",
        )
        raise SystemExit(HUD_ALREADY_RUNNING_EXIT_CODE) from None

    try:
        (options, argv) = Options.fpdb_options()

        app = QApplication([])
        apply_stylesheet(app, theme="dark_purple.xml")

        hm = HudMain(options, db_name=options.dbname)

        app.exec()
    finally:
        hud_instance_lock.release()
