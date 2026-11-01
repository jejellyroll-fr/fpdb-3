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

from optparse import Values
from pathlib import Path
from types import ModuleType
from typing import Any

import zmq as _zmq

zmq: Any = _zmq

# Add a cache for frequently accessed data
from cachetools import TTLCache
from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout
from qt_material import apply_stylesheet

from fpdb_3_legacy import Configuration, Deck, Hud, Options, db_profile
from fpdb_3_legacy.hud_diagnostics import ROLE_HUD, format_identity, log_process_identity, session_id
from fpdb_3_legacy.hud_main_db import HudMainDbMixin
from fpdb_3_legacy.hud_main_fast_fold import HudMainFastFoldMixin
from fpdb_3_legacy.hud_main_huds import HudMainHudsMixin
from fpdb_3_legacy.hud_main_refresh import HudMainRefreshMixin
from fpdb_3_legacy.hud_main_tables import HudMainTablesMixin
from fpdb_3_legacy.hud_main_winamax import HudMainWinamaxMixin
from fpdb_3_legacy.hud_read_service import (
    HudBatchSnapshot,
    HudReplayDatabase,
)
from fpdb_3_legacy.hud_window_registry import HudWindowRegistry
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
from fpdb_3_legacy.loggingFpdb import hud_trace
from fpdb_3_legacy.SmartHudManager import get_smart_hud_manager
from fpdb_3_legacy.table_info import TableInfo

# How long an arriving hand waits for its neighbours. Twelve tables dealing at
# once arrive as twelve separate notifications; holding them briefly turns that
# into one batch, so each HUD is refreshed once rather than once per hand. Long
# enough to catch the burst, short enough to stay ahead of the player acting.
HAND_BATCH_INTERVAL_MS = 200

# What HUD_main defined or imported before it was split by concern (#452) now
# lives in the modules below; every name stays importable from HUD_main.
import json as json
import re as re
import threading as threading
import time as time
from collections.abc import Callable as Callable
from collections.abc import Mapping as Mapping
from dataclasses import dataclass as dataclass
from dataclasses import field as field
from queue import Empty as Empty
from queue import Queue as Queue

from PySide6.QtCore import QEvent as QEvent
from PySide6.QtCore import QThread as QThread
from PySide6.QtWidgets import QDialog as QDialog
from PySide6.QtWidgets import QGridLayout as QGridLayout
from PySide6.QtWidgets import QHBoxLayout as QHBoxLayout
from PySide6.QtWidgets import QWidget as QWidget

from fpdb_3_legacy import Aux_Base as Aux_Base
from fpdb_3_legacy import Database as Database
from fpdb_3_legacy.db_reconnect import is_connection_lost as is_connection_lost
from fpdb_3_legacy.fast_fold_engine import FastFoldEngine as FastFoldEngine
from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest as FastFoldStatsRequest
from fpdb_3_legacy.fast_fold_engine import FastFoldStatsResult as FastFoldStatsResult
from fpdb_3_legacy.fast_fold_engine import build_seat_map as build_seat_map
from fpdb_3_legacy.fast_fold_engine import is_fast_fold_table as is_fast_fold_table
from fpdb_3_legacy.hud_ipc import ZMQReceiver as ZMQReceiver
from fpdb_3_legacy.hud_ipc import ZMQWorker as ZMQWorker
from fpdb_3_legacy.hud_ipc import parse_live_message as parse_live_message
from fpdb_3_legacy.hud_ipc import route_live_action as route_live_action
from fpdb_3_legacy.hud_main_base import FAST_FOLD_POOL_PREFIX as FAST_FOLD_POOL_PREFIX
from fpdb_3_legacy.hud_main_base import HUDCreationArgs as HUDCreationArgs
from fpdb_3_legacy.hud_main_base import TableReadState as TableReadState
from fpdb_3_legacy.hud_main_base import log as log
from fpdb_3_legacy.hud_main_db import DB_BATCH_RETRY_BACKOFF_AFTER as DB_BATCH_RETRY_BACKOFF_AFTER
from fpdb_3_legacy.hud_main_db import DB_BATCH_RETRY_BACKOFF_MS as DB_BATCH_RETRY_BACKOFF_MS
from fpdb_3_legacy.hud_main_db import DB_BATCH_RETRY_MS as DB_BATCH_RETRY_MS
from fpdb_3_legacy.hud_main_db import MAX_DEFERRED_HANDS as MAX_DEFERRED_HANDS
from fpdb_3_legacy.hud_main_db import MAX_PENDING_HANDS as MAX_PENDING_HANDS
from fpdb_3_legacy.hud_main_fast_fold import FastFoldQualification as FastFoldQualification
from fpdb_3_legacy.hud_main_window import HudMainWindow as HudMainWindow
from fpdb_3_legacy.hud_main_window import MacOSPermissionsDialog as MacOSPermissionsDialog
from fpdb_3_legacy.hud_profiles import HudContext as HudContext
from fpdb_3_legacy.hud_profiles import HudPositionScope as HudPositionScope
from fpdb_3_legacy.hud_read_service import HudBatchReadRequest as HudBatchReadRequest
from fpdb_3_legacy.hud_read_service import HudPreparedHand as HudPreparedHand
from fpdb_3_legacy.hud_read_service import HudReadService as HudReadService
from fpdb_3_legacy.hud_read_service import HudTableReadContext as HudTableReadContext
from fpdb_3_legacy.hud_window_registry import ClaimOutcome as ClaimOutcome
from fpdb_3_legacy.hud_workers import DB_RECOVERY_INTERVAL_S as DB_RECOVERY_INTERVAL_S
from fpdb_3_legacy.hud_workers import DbRecoveryWorker as DbRecoveryWorker
from fpdb_3_legacy.hud_workers import HudReadWorker as HudReadWorker
from fpdb_3_legacy.Importer import LIVE_ACTION_PREFIX as LIVE_ACTION_PREFIX
from fpdb_3_legacy.loggingFpdb import get_logger as get_logger
from fpdb_3_legacy.SmartHudManager import RestartReason as RestartReason


class HudMain(
    HudMainDbMixin,
    HudMainWinamaxMixin,
    HudMainFastFoldMixin,
    HudMainTablesMixin,
    HudMainHudsMixin,
    HudMainRefreshMixin,
    QObject,
):
    """A main() object to own both the socket thread and the gui."""

    # WinamaxLiveLogReader tails the log on its own thread; this carries its
    # updates onto the GUI thread, which is the only one allowed to touch the
    # HUD widgets or the database connection.
    winamax_table_update = Signal(object)


    def __init__(self, options: Values, db_name: str = "fpdb") -> None:
        """Initialize the main HUD application."""
        self.options = options
        self._winamax_regular_seen: dict[Any, tuple[Any, str]] = {}
        self._winamax_regular_unmatched: set[tuple[Any, str]] = set()
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
            # Tables that have shown a hand, by the id a live capture names them
            # by (#336). Filled as hands are imported; a live action for a table
            # that has not imported one yet has no HUD to go to.
            self._live_tables: dict[str, str] = {}
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
            # Tables whose window this session found at least once, and tables
            # already reported as not found. Together they keep "table not found"
            # an error the first time and a routine note once the table is known
            # to have existed and closed (see _log_table_not_found).
            self._tables_attached: set[str] = set()
            self._tables_not_found: set[str] = set()
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
            # Coalescing of stats requests: when the last one went out per
            # table, the newest seat map waiting behind it, and the timer that
            # will send that one. See FF_STATS_COALESCE_MS.
            self._ff_last_request_at: dict[str, float] = {}
            self._ff_coalesced: dict[str, tuple[Any, dict[int, str], Any]] = {}
            self._ff_coalesce_timers: dict[str, QTimer] = {}
            # Pools reported once as having no HUD of their own, so the warning
            # is not repeated on every log line.
            self._unpaired_pools: set[str] = set()
            # window title -> (hand id, slot -> login read off that window). Kept
            # per window so two tables do not evict each other, and per hand
            # because each read walks another process's accessibility tree.
            # Window reads in a row that found nobody, and whether that has gone
            # on long enough to stop trying -- both per table. A single counter
            # for the whole session reached its threshold in half the hands with
            # two tables open, and a quarter with four, so multitabling gave up
            # on the reader before it had the evidence a single table needed.
            # See AX_FRUITLESS_READS_BEFORE_GIVING_UP.
            # How long to let the client log finish naming a table's players
            # before showing the ones it has. Read once: it is a preference, not
            # something that changes within a session.
            try:
                self._fast_fold_seat_wait_ms = int(self.config.get_hud_ui_parameters().get("fast_fold_seat_wait_ms", 500))
            except Exception:
                log.debug("Could not read fast_fold_seat_wait_ms; using the default", exc_info=True)
                self._fast_fold_seat_wait_ms = 500
            self._ff_seat_wait_scheduled: set[tuple[str, str]] = set()
            # What has been learned about reading each table's window: the
            # per-hand ring, how many reads in a row could not seat anyone, and
            # whether the reader has been given up on for it. One object with one
            # lifetime -- see TableReadState.
            self._table_reads: dict[str, TableReadState] = {}
            # "off" skips the window reader outright. On a client that never
            # publishes its felt, the reads are pure stutter -- and the player
            # who has established that should not have to re-establish it every
            # session, two hands at a time.
            try:
                self._ax_reader_enabled = (
                    str(self.config.get_hud_ui_parameters().get("fast_fold_window_seats", "auto")) != "off"
                )
            except Exception:
                log.debug("Could not read fast_fold_window_seats; leaving the reader on", exc_info=True)
                self._ax_reader_enabled = True
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
            self.zmq_receiver.live_action_received.connect(self.handle_live_action)
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

    def _remember_live_table(self, temp_key: str, table_name: Any) -> None:
        """Learn which HUD serves a table id, so live actions can be routed.

        A capture names a table by the id read off its hand numbers; the table
        name the database spells carries that same id as its last token -- the
        whole name for a cash game, the trailing number for a tournament. The
        first imported hand of a table is what teaches this, which is why a
        table's very first hand is played without live panels.
        """
        token = str(table_name or "").strip().split()[-1] if str(table_name or "").strip() else ""
        if token:
            self._live_tables[token] = temp_key

    def handle_live_action(self, payload: dict[str, Any]) -> None:
        """Route one live action to the HUD whose table it belongs to (#336).

        The capture sends actions as they are played, so the dynamic panels can
        move at the decision instead of one hand behind. Everything here is
        best-effort: a payload no table claims is dropped with a debug line,
        and a HUD that rejects the action keeps the context it had.
        """
        try:
            hud = route_live_action(payload, self._live_tables, self.hud_dict)
            if hud is None:
                log.debug(
                    "Live action for table %s has no HUD yet (hand %s)",
                    payload.get("table"),
                    payload.get("hand_id"),
                )
                return
            action = self._live_action_from_payload(payload)
            if action is not None:
                hud.accept_live_action(action, hand_id=str(payload.get("hand_id") or ""))
        except Exception:  # noqa: BLE001 - a live feed must never break the HUD loop
            log.exception("Could not route a live action to its HUD")

    def _live_action_from_payload(self, payload: dict[str, Any]) -> Any:
        """The room's action record as the live-context module reads it."""
        from fpdb_3_legacy import hud_live_context

        record = payload.get("record")
        if not isinstance(record, dict):
            return None
        return hud_live_context.coinpoker_action(
            record,
            hand_id=str(payload.get("hand_id") or ""),
            sequence=int(payload.get("sequence") or 0),
        )

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
                self._remember_live_table(temp_key, table_name)
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
        self._remember_live_table(temp_key, table_name)
        if info.fast:
            # Past the idempotence check and past creation: this hand really
            # reached the screen, which is the only case worth announcing.
            self._log_fast_fold_import_applied(new_hand_id, temp_key)
        return temp_key


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
