#!/usr/bin/env python
"""Hud_main.py.

Main for FreePokerTools HUD.
"""

import contextlib
import os
import sys

if sys.platform.startswith("linux") and os.getenv("FPDB_FORCE_X11") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import zmq

# Add a cache for frequently accessed data
from cachetools import TTLCache
from PyQt5.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qt_material import apply_stylesheet

import Configuration
import Database
import Deck
import Hud
import Options
from HudStatsPersistence import get_hud_stats_persistence
from loggingFpdb import get_logger
from SmartHudManager import RestartReason, get_smart_hud_manager

# Logging configuration

log = get_logger("hud_main")


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

    error_occurred = pyqtSignal(str)

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

    message_received = pyqtSignal(str)

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
        try:
            socks = dict(self.poller.poll(1000))  # Timeout 1 seconde
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
            else:
                log.exception("ZMQ error")

    def close(self) -> None:
        """Close the ZMQ socket and context."""
        self.socket.close()
        self.context.term()
        log.info("ZMQ receiver closed")


class HudMain(QObject):
    """A main() object to own both the socket thread and the gui."""

    def __init__(self, options: "Options.Values", db_name: str = "fpdb") -> None:
        """Initialize the main HUD application."""
        self.options = options
        QObject.__init__(self)
        self.db_name = db_name

        # Ensure HUD logging is properly initialized
        import logging
        from pathlib import Path

        from loggingFpdb import JsonFormatter, TimedSizedRotatingFileHandler

        try:
            # Import LoggerRegistry to get the current logger configuration
            from loggingFpdb import LoggerRegistry

            # Create HUD-specific log directory and file
            hud_log_dir = Path.home() / ".fpdb" / "log"
            hud_log_dir.mkdir(parents=True, exist_ok=True)
            hud_log_file = hud_log_dir / "HUD-log.txt"

            # Get the HUD logger and check if it's already configured by Logger Dev Tool
            hud_logger = logging.getLogger("hud_main")
            registry = LoggerRegistry()

            # Get the current level from Logger Dev Tool configuration or use ERROR as default
            logger_info = registry.get_logger_info("hud_main")
            if logger_info:
                configured_level = logger_info.current_level
                log.info(f"Using Logger Dev Tool configuration: level={logging.getLevelName(configured_level)}")
            else:
                configured_level = logging.ERROR
                log.info("Using default ERROR level for HUD logger")

            hud_logger.setLevel(configured_level)

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
            # File handler should respect the logger level
            file_handler.setLevel(configured_level)

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
                "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] " "[%(levelname)s] %(message)s%(reset)s"
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

            # Stats persistence initialization
            self.stats_persistence = get_hud_stats_persistence()

            # Smart HUD manager initialization
            self.smart_hud_manager = get_smart_hud_manager()

            # Initialization ZMQ avec QThread
            log.info("Initializing ZMQ communication...")
            self.zmq_receiver = ZMQReceiver(parent=self)
            log.info("ZMQ receiver created successfully")
            self.zmq_receiver.message_received.connect(self.handle_message)
            self.zmq_worker = ZMQWorker(self.zmq_receiver)
            self.zmq_worker.error_occurred.connect(self.handle_worker_error)
            log.info("Starting ZMQ worker...")
            self.zmq_worker.start()

            # Main window
            self.init_main_window()

            log.debug("Main window initialized and shown.")
        except Exception:
            log.exception("Error during HudMain initialization")
            raise

    def handle_worker_error(self, error_message: str) -> None:
        """Handle errors from the ZMQ worker."""
        log.error("ZMQWorker encountered an error: %s", error_message)

    def init_main_window(self) -> None:
        """Initialize the main application window."""
        self.main_window = QWidget(None, Qt.Dialog | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        if self.options.xloc is not None or self.options.yloc is not None:
            x = int(self.options.xloc) if self.options.xloc is not None else self.main_window.x()
            y = int(self.options.yloc) if self.options.yloc is not None else self.main_window.y()
            self.main_window.move(x, y)
        self.main_window.destroyed.connect(self.destroy)
        self.vb = QVBoxLayout()
        self.vb.setContentsMargins(2, 0, 2, 0)
        self.main_window.setLayout(self.vb)
        self.label = QLabel("Closing this window will exit from the HUD.")
        self.main_window.closeEvent = self.close_event_handler
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

    def close_event_handler(self, event: QEvent) -> None:
        """Handle the close event of the main window."""
        self.destroy()
        event.accept()

    def handle_message(self, hand_id: str) -> None:
        """Handle an incoming message from the ZMQ receiver."""
        # This method will be called in the main thread
        log.info("HUD RECEIVED MESSAGE - hand_id: %s", hand_id)
        self.read_stdin(hand_id)
        log.debug("Message processing completed for hand_id: %s", hand_id)

    def destroy(self) -> None:
        """Destroy the application and clean up resources."""
        if hasattr(self, "zmq_receiver"):
            self.zmq_receiver.close()
        if hasattr(self, "zmq_worker"):
            self.zmq_worker.stop()
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
        self.kill_hud(None, hud.table.key)

    def kill_hud(self, _event: QEvent | None, table: str) -> None:
        """Kill the HUD for a specific table."""
        log.debug("kill_hud event")
        self.idle_kill(table)

    def blacklist_hud(self, _event: QEvent | None, table: str) -> None:
        """Blacklist a HUD and kill it."""
        log.debug("blacklist_hud event")
        self.blacklist.append(self.hud_dict[table].tablenumber)
        self.idle_kill(table)

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

    def _get_table_info(self, hand_id: str) -> tuple | None:
        """Get table information from cache or database."""
        if hand_id in self.cache:
            log.debug("Using cached data for hand %s", hand_id)
            return self.cache[hand_id]

        log.debug("Data not found in cache for hand_id: %s", hand_id)
        try:
            table_info = self.db_connection.get_table_info(hand_id)
            self.cache[hand_id] = table_info
        except Exception:
            log.exception("Database error while processing hand %s", hand_id)
            return None
        else:
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
                if k.startswith(tour_number):
                    log.debug("check if the tournament number is in the hud_dict under a different table")
                    self.table_is_stale(self.hud_dict[k])
                    # continue checking other tables
        return False

    def _handle_hud_reconfiguration(self, temp_key: str, poker_game: str) -> tuple[str, str] | None:
        """Handle HUD reconfiguration for max seats and game type changes."""
        if temp_key not in self.hud_dict:
            return poker_game, None

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
                    self.kill_hud("activate", temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
                    hud.hud_params["new_max_seats"] = None
                    return poker_game, newmax
                log.info(f"Skipping restart for max seats change: {reason}")

        # Check for game type change
        if hud.poker_game != poker_game:
            new_state = current_state.copy()
            new_state["poker_game"] = poker_game

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
                    self.kill_hud("activate", temp_key)
                    while temp_key in self.hud_dict:
                        time.sleep(0.5)
            else:
                log.info(f"Skipping restart for game type change: {reason}")

        return poker_game, None

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

        try:
            hud.stat_dict = stat_dict
        except KeyError:
            log.exception("hud_dict[%s] was not found", temp_key)
            return

        hud.cards = self.get_cards(new_hand_id, hud.poker_game)
        for aw in hud.aux_windows:
            aw.update_data(new_hand_id, self.db_connection)
        self.update_HUD(new_hand_id, temp_key, self.config)
        log.debug("hud updated for table %s and hand %s", temp_key, new_hand_id)

    def _create_new_hud(self, new_hand_id: str, temp_key: str, table_info: tuple, site_id: int, num_seats: int) -> None:
        """Create a new HUD for a table."""
        (table_name, max_seats, poker_game, game_type, _, _, site_name, _, tour_number, tab_number) = table_info

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

        if not any(stat_dict[key]["screen_name"] == self.hero[site_id] for key in stat_dict):
            log.info("HUD not created yet, because hero is not seated for this hand")
            return

        cards = self.get_cards(new_hand_id, poker_game)
        table_kwargs = {"table_name": table_name, "tournament": tour_number, "table_number": tab_number}
        tablewindow = self.Tables.Table(self.config, site_name, **table_kwargs)

        if tablewindow.number is None:
            if game_type == "tour":
                table_name = f"{tour_number} {tab_number}"
            log.error("HUD create: table name %s not found, skipping.", table_name)
            return
        if tablewindow.number in self.blacklist:
            return

        tablewindow.key = temp_key
        tablewindow.max = max_seats
        tablewindow.site = site_name

        # Register table state with smart HUD manager
        self.smart_hud_manager.update_table_state(
            temp_key,
            poker_game,
            game_type,
            max_seats,
            site_name,
            table_name,
        )

        if hasattr(tablewindow, "number"):
            args = HUDCreationArgs(
                new_hand_id=new_hand_id,
                table=tablewindow,
                temp_key=temp_key,
                max_seats=max_seats,
                poker_game=poker_game,
                game_type=game_type,
                stat_dict=stat_dict,
                cards=cards,
            )
            self.create_HUD(args)
        else:
            log.error('Table "%s" no longer exists', table_name)

    def read_stdin(self, new_hand_id: str) -> None:
        """Read and process a new hand ID from stdin."""
        log.debug("Processing new hand id: %s", new_hand_id)
        self._initialize_hero_data()

        if not new_hand_id:
            return

        table_info = self._get_table_info(new_hand_id)
        if not table_info:
            return

        (table_name, max_seats, poker_game, game_type, fast, site_id, site_name, num_seats, tour_number, tab_number) = (
            table_info
        )

        enabled_sites = self.config.get_supported_sites()
        aux_disabled_sites = [
            site for site in enabled_sites if not self.config.get_site_parameters(site)["aux_enabled"]
        ]
        if fast or site_name in aux_disabled_sites or site_name not in enabled_sites:
            log.debug(
                "HUD creation skipped: fast=%s, site_disabled=%s, site_enabled=%s",
                fast,
                site_name in aux_disabled_sites,
                site_name in enabled_sites,
            )
            return

        temp_key = self._get_temp_key(game_type, tour_number, tab_number, table_name)
        log.debug("Generated temp_key: %s for table: %s", temp_key, table_name)

        if self._handle_tournament_table_changes(game_type, temp_key, tour_number):
            return  # Stale table was handled

        poker_game, new_max_seats = self._handle_hud_reconfiguration(temp_key, poker_game)
        if new_max_seats:
            # Re-create the HUD with the new max seats
            self.kill_hud(None, temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, new_max_seats)
            return

        if temp_key in self.hud_dict:
            log.debug("Updating existing HUD for temp_key: %s", temp_key)
            self._update_existing_hud(new_hand_id, temp_key, game_type, site_id, num_seats)
        else:
            log.debug("Creating new HUD for temp_key: %s", temp_key)
            self._create_new_hud(new_hand_id, temp_key, table_info, site_id, num_seats)

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
            hud.move_table_position()
            for aw in hud.aux_windows:
                aw.move_windows()
        except Exception:
            log.exception("Error moving HUD for table: %s.", hud.table.title)

    def idle_resize(self, hud: Hud.Hud) -> None:
        """Handle the idle resize event."""
        try:
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

                # Original kill logic
                self.vb.removeWidget(self.hud_dict[table].tablehudlabel)
                self.hud_dict[table].tablehudlabel.setParent(None)
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
            for m in self.hud_dict[args.temp_key].aux_windows:
                m.create()
                log.debug("idle_create new_hand_id %s", args.new_hand_id)
                m.update_gui(args.new_hand_id)

        except Exception:
            log.exception("Error creating HUD for hand %s.", args.new_hand_id)

    def idle_update(self, new_hand_id: str, table_name: str, config: Configuration.Config) -> None:
        """Handle the idle update event."""
        try:
            log.debug("idle_update entered for %s %s", table_name, new_hand_id)
            self.hud_dict[table_name].update(new_hand_id, config)
            log.debug("idle_update update_gui %s", new_hand_id)
            for aw in self.hud_dict[table_name].aux_windows:
                aw.update_gui(new_hand_id)
        except Exception:
            log.exception("Error updating HUD for hand %s.", new_hand_id)


if __name__ == "__main__":
    (options, argv) = Options.fpdb_options()

    app = QApplication([])
    apply_stylesheet(app, theme="dark_purple.xml")

    hm = HudMain(options, db_name=options.dbname)

    app.exec_()
