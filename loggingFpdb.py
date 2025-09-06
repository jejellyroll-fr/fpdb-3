"""FPDB logging configuration and utilities.

This module provides custom logging functionality for FPDB, including colored console output,
JSON file formatting, and advanced log rotation capabilities.
"""

import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from typing import Any

import colorlog
from colorlog import ColoredFormatter
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

# Define default logging and debugging modes


@dataclass
class LoggerInfo:
    """Information about a registered logger."""

    name: str
    logger: logging.Logger
    original_level: int
    current_level: int
    enabled: bool = True


class LoggerRegistry:
    """Central registry for managing all FPDB loggers."""

    def __init__(self) -> None:
        """Initialize the LoggerRegistry instance.

        Sets up the internal logger registry, configuration, and prepares for logger discovery and management.
        """
        self._loggers: dict[str, LoggerInfo] = {}
        self._auto_discovery_enabled = True
        self._config = None
        self._saved_config = {}
        self._saving_in_progress = False  # Prevent recursive discover during save

        # Initialize config when first needed
        self._init_config()

    def _init_config(self) -> None:
        """Initialize the logger configuration if it has not been set.

        Ensures that the logger configuration object is created and loads any existing configuration from file.
        """
        if self._config is None:
            self._config = LogConfig()
            self._load_config()

    def _load_config(self) -> None:
        """Load logger configuration data from persistent storage.

        Retrieves logger configuration from file and updates the saved configuration for later application.
        """
        config_data = self._config.load_config_data()
        if config_data and "loggers" in config_data:
            # Store the config data to apply after discovery
            self._saved_config = config_data["loggers"]
        else:
            self._saved_config = {}

    def register_logger(self, name: str, logger: logging.Logger) -> None:
        """Register a logger with the registry and apply any saved configuration.

        Adds the logger to the registry, restoring its previous level and enabled state if available.

        Args:
            name: The name of the logger to register.
            logger: The logger instance to register.
        """
        # Store original level only if not already registered
        original_level = logger.level if name not in self._loggers else self._loggers[name].original_level

        # Always check if we have saved configuration for this logger
        if name in self._saved_config:
            saved_level = self._saved_config[name]["level"]
            saved_enabled = self._saved_config[name]["enabled"]
            # Apply saved configuration
            logger.setLevel(saved_level)
            current_level = saved_level
            enabled = saved_enabled
        else:
            current_level = logger.level
            enabled = logger.level != logging.NOTSET

        self._loggers[name] = LoggerInfo(
            name=name,
            logger=logger,
            original_level=original_level,
            current_level=current_level,
            enabled=enabled,
        )

    def discover_loggers(self) -> list[str]:
        """Discover and register all active and relevant loggers.

        Finds all loggers currently active in the logging module and pre-creates FPDB-specific loggers for consistent management. Returns a list of all discovered logger names.

        Returns:
            list[str]: A list of logger names that have been discovered and registered.
        """
        discovered = []

        # FPDB logger names actually used in the codebase (extracted from get_logger calls)
        fpdb_loggers = [
            "auto_import_config_observer",
            "aux_base",
            "aux_classic_hud",
            "aux_hud",
            "bovada_parser",
            "bovada_summary_parser",
            "cake_parser",
            "card",
            "config",
            "config_observers",
            "config_reload_widget",
            "configuration",
            "configuration_manager",
            "database",
            "deck",
            "derived_stats",
            "detect_installed_sites",
            "filter",
            "fpdb",
            "ggpoker_parser",
            "gui_auto_import",
            "gui_bulk_import",
            "gui_config_observer",
            "gui_graph_viewer",
            "gui_hand_viewer",
            "gui_log_view",
            "gui_replayer",
            "gui_ring_player_stats",
            "gui_session_viewer",
            "gui_tour_hand_viewer",
            "gui_tourney_graph_viewer",
            "gui_tourney_player_stats",
            "hand",
            "hand_history",
            "hand_history_converter",
            "hud",
            "hud_main",
            "hud_stats_persistence",
            "identify_site",
            "importer",
            "improved_error_handler",
            "interlocks",
            "ipoker_parser",
            "ipoker_summary_parser",
            "kings_club_parser",
            "modern_hud_preferences",
            "modern_popup",
            "modern_seat_preferences",
            "modern_site_preferences",
            "mucked_hud",
            "options",
            "osx_tables",
            "pacific_poker_parser",
            "pacific_poker_summary_parser",
            "partypoker_parser",
            "pokerstars_parser",
            "pokerstars_summary_parser",
            "pokertracker_parser",
            "pokertracker_summary_parser",
            "popup",
            "popup_icons",
            "popup_themes",
            "seals_with_clubs_parser",
            "smart_hud_manager",
            "stats",
            "table_window",
            "tourney_summary_parser",
            "translation",
            "unibet_parser",
            "winamax_parser",
            "winamax_summary_parser",
            "winning_parser",
            "winning_summary_parser",
            "win_tables",
            "x_tables",
        ]

        # Always include root logger
        root_logger = logging.getLogger()
        self.register_logger("root", root_logger)
        discovered.append("root")

        # Get all loggers from logging module that are actually active
        for name in logging.Logger.manager.loggerDict:
            logger = logging.getLogger(name)
            if logger.level != logging.NOTSET or logger.handlers:
                self.register_logger(name, logger)
                discovered.append(name)

        # Pre-create FPDB loggers that are actually used in the codebase
        for logger_name in fpdb_loggers:
            if logger_name not in self._loggers:
                logger = logging.getLogger(logger_name)
                # Set default level to ERROR for production use
                logger.setLevel(logging.ERROR)
                self.register_logger(logger_name, logger)
            discovered.append(logger_name)

        return discovered

    def get_all_loggers(self) -> dict[str, LoggerInfo]:
        """Return a copy of all registered loggers and their information.

        This method retrieves all loggers currently managed by the registry, performing auto-discovery if enabled and not in the process of saving. The returned dictionary maps logger names to their corresponding LoggerInfo objects.

        Returns:
            dict[str, LoggerInfo]: A dictionary of logger names to LoggerInfo instances.
        """
        if self._auto_discovery_enabled and not self._saving_in_progress:
            self.discover_loggers()
        return self._loggers.copy()

    def set_logger_level(self, name: str, level: int) -> bool:
        """Set the logging level for a specific logger.

        Updates the specified logger's level and ensures that the logger and its handlers reflect the new level. If the logger does not exist, it will be discovered and registered before updating.

        Args:
            name: The name of the logger to update.
            level: The new logging level to set.

        Returns:
            bool: True if the logger level was successfully updated, False otherwise.
        """
        # If logger not found, try discovering it first
        if name not in self._loggers:
            self.discover_loggers()

        if name in self._loggers:
            logger_info = self._loggers[name]

            # CRITICAL: Update the actual Python logger instance that the application uses
            # This ensures that existing loggers in the application get the new level
            actual_python_logger = logging.getLogger(name)
            actual_python_logger.setLevel(level)

            # Also update our registry logger (which might be the same instance)
            logger_info.logger.setLevel(level)
            logger_info.current_level = level
            logger_info.enabled = level != logging.NOTSET

            # Also update all handlers of the actual Python logger to match the new level
            # This is needed for loggers like HUD that have their own handlers
            console_handlers_updated = 0
            for handler in actual_python_logger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    # Only update console handlers, keep file handlers as they are
                    if not hasattr(handler, "baseFilename"):  # Not a file handler
                        handler.setLevel(level)
                        console_handlers_updated += 1

            # Ensure logger can output to console when level is lowered
            # Check if root logger has console handlers
            root_logger = logging.getLogger()
            root_has_console_handler = any(
                isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename") for h in root_logger.handlers
            )

            # If logger propagates, ensure root logger and its handlers allow the new level
            if level < logging.ERROR and actual_python_logger.propagate:
                # Update root logger level to allow messages through
                if root_logger.level > level:
                    root_logger.setLevel(level)

                # Update existing root handlers to allow the new level
                handlers_updated = 0
                for handler in root_logger.handlers:
                    if (
                        isinstance(handler, logging.StreamHandler)
                        and not hasattr(
                            handler,
                            "baseFilename",
                        )
                        and handler.level > level
                    ):
                        handler.setLevel(level)
                        handlers_updated += 1

                # If no handlers were found or updated, add a new console handler
                if not root_has_console_handler and handlers_updated == 0:
                    console_handler = logging.StreamHandler()
                    console_handler.setLevel(
                        logging.DEBUG,
                    )  # Let individual loggers control their level

                    # Use the same format as the main system
                    log_colors = {
                        "DEBUG": "green",
                        "INFO": "blue",
                        "WARNING": "yellow",
                        "ERROR": "red",
                    }
                    log_format = "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] [%(levelname)s] %(message)s%(reset)s"
                    date_format = "%Y-%m-%d %H:%M:%S"
                    formatter = ColoredFormatter(
                        fmt=log_format,
                        datefmt=date_format,
                        log_colors=log_colors,
                    )
                    console_handler.setFormatter(formatter)

                    root_logger.addHandler(console_handler)

            # If logger doesn't propagate, add handler directly to it
            elif level < logging.ERROR and not actual_python_logger.propagate:
                has_console_handler = any(
                    isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename")
                    for h in actual_python_logger.handlers
                )

                if not has_console_handler:
                    console_handler = logging.StreamHandler()
                    console_handler.setLevel(level)

                    # Use the same format as the main system
                    log_colors = {
                        "DEBUG": "green",
                        "INFO": "blue",
                        "WARNING": "yellow",
                        "ERROR": "red",
                    }
                    log_format = "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] [%(levelname)s] %(message)s%(reset)s"
                    date_format = "%Y-%m-%d %H:%M:%S"
                    formatter = ColoredFormatter(
                        fmt=log_format,
                        datefmt=date_format,
                        log_colors=log_colors,
                    )
                    console_handler.setFormatter(formatter)

                    actual_python_logger.addHandler(console_handler)

            # Save the configuration to persist the change
            self._init_config()  # Ensure config is initialized
            self._saving_in_progress = True
            try:
                self._config.save_config(self)
            finally:
                self._saving_in_progress = False
            return True
        return False

    def enable_logger(self, name: str, enable: bool = True) -> bool:
        """Enable or disable a specific logger.

        This method sets the enabled state of the specified logger, restoring its original level when enabled or setting it to NOTSET when disabled. Returns True if the logger was found and updated, otherwise False.

        Args:
            name: The name of the logger to enable or disable.
            enable: Whether to enable (True) or disable (False) the logger.

        Returns:
            bool: True if the logger was updated, False if the logger was not found.
        """
        if name in self._loggers:
            logger_info = self._loggers[name]
            if enable:
                # Restore to original level or INFO if was NOTSET
                level = logger_info.original_level if logger_info.original_level != logging.NOTSET else logging.INFO
                logger_info.logger.setLevel(level)
                logger_info.current_level = level
            else:
                logger_info.logger.setLevel(logging.NOTSET)
                logger_info.current_level = logging.NOTSET
            logger_info.enabled = enable
            return True
        return False

    def get_logger_info(self, name: str) -> LoggerInfo | None:
        """Retrieve information about a specific logger.

        Returns the LoggerInfo object for the given logger name, or None if the logger does not exist. If the logger is not found, it will attempt to discover and register it before returning the result.

        Args:
            name: The name of the logger to retrieve.

        Returns:
            LoggerInfo | None: The LoggerInfo object for the logger, or None if not found.
        """
        # If logger not found, try discovering it first
        if name not in self._loggers:
            self.discover_loggers()
        return self._loggers.get(name)

    def filter_loggers(
        self,
        pattern: str = "",
        level_filter: int | None = None,
    ) -> dict[str, LoggerInfo]:
        """Filter registered loggers by name pattern and/or logging level.

        Returns a dictionary of loggers whose names match the given pattern and whose current level matches the specified filter. If no pattern or level filter is provided, all loggers are returned.

        Args:
            pattern: A substring to match logger names (case-insensitive).
            level_filter: The logging level to filter loggers by.

        Returns:
            dict[str, LoggerInfo]: A dictionary of filtered logger names to LoggerInfo instances.
        """
        filtered = {}
        for name, info in self._loggers.items():
            # Filter by pattern
            if pattern and pattern.lower() not in name.lower():
                continue
            # Filter by level
            if level_filter is not None and info.current_level != level_filter:
                continue
            filtered[name] = info
        return filtered


def get_logger_registry() -> LoggerRegistry:
    """Get the global logger registry instance.

    Returns the singleton LoggerRegistry used for managing all FPDB loggers.

    Returns:
        LoggerRegistry: The global logger registry instance.
    """
    return _logger_registry


class LogConfig:
    """Configuration manager for logger settings with JSON persistence."""

    def __init__(self, config_dir: str | None = None) -> None:
        """Initialize the LogConfig instance and set up configuration file paths.

        Sets the directory and file path for logger configuration, creating the directory if it does not exist. If no directory is provided, defaults to a 'fpdb_logs' folder in the user's home directory.

        Args:
            config_dir: Optional path to the directory where the configuration file will be stored.
        """
        if config_dir is None:
            config_dir = os.path.join(os.path.expanduser("~"), "fpdb_logs")
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "logger_config.json")
        os.makedirs(config_dir, exist_ok=True)

    def save_config(self, registry: LoggerRegistry) -> bool:
        """Save the current logger configuration to a JSON file.

        Persists the logger levels and enabled states for all registered loggers to disk. Returns True if the configuration was saved successfully, or False if an error occurred.

        Args:
            registry: The LoggerRegistry instance containing logger configurations to save.

        Returns:
            bool: True if the configuration was saved successfully, False otherwise.
        """
        try:
            config_data = {
                "version": "1.0",
                "timestamp": time.time(),
                "loggers": {},
            }

            for name, info in registry.get_all_loggers().items():
                config_data["loggers"][name] = {
                    "level": info.current_level,
                    "enabled": info.enabled,
                    "original_level": info.original_level,
                }

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            return True

        except Exception as e:
            logging.getLogger(__name__).exception(f"Failed to save logger config: {e}")
            return False

    def load_config_data(self) -> dict:
        """Load logger configuration data from the JSON configuration file.

        Reads the configuration file and returns its contents as a dictionary. If the file does not exist or an error occurs, an empty dictionary is returned.

        Returns:
            dict: The loaded configuration data, or an empty dictionary if loading fails.
        """
        if not os.path.exists(self.config_file):
            return {}

        try:
            with open(self.config_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.getLogger(__name__).exception(f"Failed to load logger config data: {e}")
            return {}

    def load_config(self, registry: LoggerRegistry) -> bool:
        """Load logger configuration from the JSON file and apply it to the registry.

        Reads the configuration file, applies logger levels and enabled states to the provided registry, and returns True if successful. Returns False if the file does not exist, is invalid, or an error occurs.

        Args:
            registry: The LoggerRegistry instance to apply the loaded configuration to.

        Returns:
            bool: True if the configuration was loaded and applied successfully, False otherwise.
        """
        if not os.path.exists(self.config_file):
            return False

        try:
            with open(self.config_file, encoding="utf-8") as f:
                config_data = json.load(f)

            if "loggers" not in config_data:
                return False

            # Apply configurations to registry
            for name, config in config_data["loggers"].items():
                if registry.set_logger_level(name, config.get("level", logging.INFO)):
                    registry.enable_logger(name, config.get("enabled", True))

            return True

        except Exception as e:
            logging.getLogger(__name__).exception(f"Failed to load logger config: {e}")
            return False

    def export_config(self, registry: LoggerRegistry, filename: str) -> bool:
        """Export the current logger configuration to a specified file.

        Writes the logger levels, enabled states, and additional metadata to a JSON file for external use or backup. Returns True if the export was successful, or False if an error occurred.

        Args:
            registry: The LoggerRegistry instance containing logger configurations to export.
            filename: The path to the file where the configuration will be saved.

        Returns:
            bool: True if the configuration was exported successfully, False otherwise.
        """
        try:
            config_data = {
                "version": "1.0",
                "timestamp": time.time(),
                "exported_from": "FPDB Logger Dev Tool",
                "loggers": {},
            }

            for name, info in registry.get_all_loggers().items():
                config_data["loggers"][name] = {
                    "level": info.current_level,
                    "level_name": logging.getLevelName(info.current_level),
                    "enabled": info.enabled,
                    "original_level": info.original_level,
                    "original_level_name": logging.getLevelName(info.original_level),
                }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            return True

        except Exception as e:
            logging.getLogger(__name__).exception(f"Failed to export config: {e}")
            return False

    def import_config(self, registry: LoggerRegistry, filename: str) -> bool:
        """Import logger configuration from a specified file and apply it to the registry.

        Loads logger levels and enabled states from the given JSON file, applies them to the provided registry, and saves the imported configuration as the current config. Returns True if the import and application were successful, or False if an error occurred.

        Args:
            registry: The LoggerRegistry instance to apply the imported configuration to.
            filename: The path to the file from which the configuration will be loaded.

        Returns:
            bool: True if the configuration was imported and applied successfully, False otherwise.
        """
        if not os.path.exists(filename):
            return False

        try:
            with open(filename, encoding="utf-8") as f:
                config_data = json.load(f)

            if "loggers" not in config_data:
                return False

            # Apply configurations to registry
            for name, config in config_data["loggers"].items():
                if registry.set_logger_level(name, config.get("level", logging.INFO)):
                    registry.enable_logger(name, config.get("enabled", True))

            # Save imported config as current config
            self.save_config(registry)
            return True

        except Exception as e:
            logging.getLogger(__name__).exception(f"Failed to import config: {e}")
            return False


# Global config instance
_log_config = LogConfig()


def get_log_config() -> LogConfig:
    """Get the global LogConfig instance.

    Returns the singleton LogConfig used for managing logger configuration persistence.

    Returns:
        LogConfig: The global LogConfig instance.
    """
    return _log_config


class LoggerDevTool:
    """Development tool GUI for managing logger configurations."""

    def __init__(self, parent=None) -> None:
        """Initialize the LoggerDevTool GUI for managing logger configurations.

        Sets up the dialog window, layouts, controls, and logger tree for interactive management of logger levels and configuration. The GUI allows filtering, exporting, importing, saving, and resetting logger settings.

        Args:
            parent: The parent widget for the dialog, if any.
        """
        self.registry = get_logger_registry()
        self.config = get_log_config()

        # Create main dialog
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("FPDB Logger Development Tool")
        self.dialog.setMinimumSize(900, 700)

        # The dialog automatically inherits the parent's theme
        # No additional styling needed - Qt handles this automatically

        # Main layout
        main_layout = QVBoxLayout()
        self.dialog.setLayout(main_layout)

        # Top controls
        controls_layout = QHBoxLayout()

        # Filter controls
        filter_group = QGroupBox("Filters and Controls")
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by logger name...")
        self.search_edit.textChanged.connect(self._filter_loggers)
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Level:"))
        self.level_filter = QComboBox()
        self.level_filter.addItems(
            ["All", "DEBUG", "INFO", "WARNING", "ERROR", "NOTSET"],
        )
        self.level_filter.currentTextChanged.connect(self._filter_loggers)
        filter_layout.addWidget(self.level_filter)

        # Global controls
        self.reset_all_btn = QPushButton("Reset all to default")
        self.reset_all_btn.clicked.connect(self._reset_all_loggers)
        filter_layout.addWidget(self.reset_all_btn)

        filter_group.setLayout(filter_layout)
        controls_layout.addWidget(filter_group)
        main_layout.addLayout(controls_layout)

        # Logger tree (simplified - no enable column)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Logger", "Current Level", "Default Level"])
        self.tree.setAlternatingRowColors(False)  # Disable to use parent theme colors
        self.tree.setSortingEnabled(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)  # Consistent row heights
        self.tree.setStyleSheet("")  # Clear any default styling to inherit parent theme

        # Configure header
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        main_layout.addWidget(self.tree)

        # Bottom buttons
        buttons_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self._refresh_loggers)
        self.refresh_btn.setToolTip("Update the list of loggers")
        buttons_layout.addWidget(self.refresh_btn)

        buttons_layout.addStretch()

        self.export_btn = QPushButton("📤 Export")
        self.export_btn.clicked.connect(self._export_config)
        self.export_btn.setToolTip("Export configuration to file")
        buttons_layout.addWidget(self.export_btn)

        self.import_btn = QPushButton("📥 Import")
        self.import_btn.clicked.connect(self._import_config)
        self.import_btn.setToolTip("Import a configuration from a file")
        buttons_layout.addWidget(self.import_btn)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self._save_config)
        self.save_btn.setToolTip("Save current configuration")
        buttons_layout.addWidget(self.save_btn)

        buttons_layout.addStretch()

        self.close_btn = QPushButton("❌ Close")
        self.close_btn.clicked.connect(self.dialog.accept)
        buttons_layout.addWidget(self.close_btn)

        main_layout.addLayout(buttons_layout)

        # No auto-refresh timer - manual refresh only when needed

        # Initial load
        self._refresh_loggers()

    def show(self):
        """Display the LoggerDevTool dialog and start the event loop.

        Shows the logger development tool window and blocks until the dialog is closed. Returns the result of the dialog execution.

        Returns:
            int: The result code from the dialog execution.
        """
        return self.dialog.exec_()

    def _refresh_loggers(self) -> None:
        """Refresh the logger tree display with current logger information.

        Clears and repopulates the logger tree widget with all registered loggers, updating their displayed levels and controls. This method ensures the GUI reflects the latest logger states and configuration.
        """
        self.tree.clear()

        # Get all loggers (discovery was already done at startup)
        # We don't call discover_loggers() here to avoid resetting configurations
        loggers = self.registry.get_all_loggers()

        for name, info in sorted(loggers.items()):
            item = QTreeWidgetItem(
                [
                    name,
                    "",  # Empty text for column 1 since we'll put a widget there
                    logging.getLevelName(info.original_level),
                ],
            )

            # Store logger name for reference
            item.setData(0, Qt.UserRole, name)

            self.tree.addTopLevelItem(item)

            # Add level selector in column 1
            level_combo = QComboBox()
            level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "NOTSET"])
            level_combo.setCurrentText(logging.getLevelName(info.current_level))
            level_combo.currentTextChanged.connect(
                lambda level, logger_name=name: self._change_logger_level(
                    logger_name,
                    level,
                ),
            )
            # Ensure the combo inherits parent styling and fits properly
            level_combo.setStyleSheet("")  # Clear any default styling to inherit parent
            level_combo.setSizePolicy(
                level_combo.sizePolicy().Expanding,
                level_combo.sizePolicy().Fixed,
            )
            self.tree.setItemWidget(item, 1, level_combo)

    def _filter_loggers(self) -> None:
        """Filter the displayed loggers in the tree based on search text and level.

        Updates the visibility of logger entries in the tree widget according to the current search and level filter controls. Only loggers matching both filters remain visible.
        """
        from PyQt5.QtCore import Qt

        search_text = self.search_edit.text().lower()
        level_filter = self.level_filter.currentText()

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            logger_name = item.data(0, Qt.UserRole)

            # Check search filter
            name_match = search_text in logger_name.lower() if search_text else True

            # Check level filter
            if level_filter == "All":
                level_match = True
            else:
                # Get current level from the combo box widget in column 1
                combo = self.tree.itemWidget(item, 1)
                if combo:
                    current_level = combo.currentText()
                    level_match = current_level == level_filter
                else:
                    level_match = True

            item.setHidden(not (name_match and level_match))

    def _change_logger_level(self, logger_name: str, level_name: str) -> None:
        """Change the logging level for a specific logger in the registry.

        Updates the logger's level based on the selected level name and refreshes the corresponding tree item in the GUI to reflect the change.

        Args:
            logger_name: The name of the logger to update.
            level_name: The new logging level as a string (e.g., "DEBUG", "INFO").
        """
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "NOTSET": logging.NOTSET,
        }

        level = level_map.get(level_name, logging.INFO)
        self.registry.set_logger_level(logger_name, level)

        # Update the tree display to reflect the new level
        self._update_tree_item(logger_name)

    def _update_tree_item(self, logger_name: str) -> None:
        """Update the tree widget item for a specific logger to reflect its current level.

        Finds the tree item corresponding to the given logger and updates its level selector to match the logger's current level. The original level display remains unchanged.
        """
        from PyQt5.QtCore import Qt

        info = self.registry.get_logger_info(logger_name)
        if not info:
            return

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == logger_name:
                # Update the combo box in column 1 (not the text, since we have a widget there)
                combo = self.tree.itemWidget(item, 1)
                if combo:
                    combo.setCurrentText(logging.getLevelName(info.current_level))
                # Column 2 text stays the same (original level doesn't change)
                break

    def _reset_all_loggers(self) -> None:
        """Reset all loggers to their default levels.

        Prompts the user for confirmation and, if confirmed, restores all registered loggers to their original levels. After resetting, the logger tree is refreshed and a success message is displayed.
        """
        from PyQt5.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self.dialog,
            "Confirmation",
            "Do you want to reset all loggers to their default level?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            for name, info in self.registry.get_all_loggers().items():
                default_level = info.original_level if info.original_level != logging.NOTSET else logging.INFO
                self.registry.set_logger_level(name, default_level)
            self._refresh_loggers()
            QMessageBox.information(
                self.dialog,
                "Success",
                "All loggers have been reset to default values.",
            )

    def _save_config(self) -> None:
        """Save the current logger configuration to disk.

        Attempts to persist the current logger settings using the configuration manager. Displays a success or error message based on the outcome.
        """
        # Use the same protection mechanism as set_logger_level
        self.registry._saving_in_progress = True
        try:
            success = self.config.save_config(self.registry)
        finally:
            self.registry._saving_in_progress = False

        if success:
            QMessageBox.information(
                self.dialog,
                "Success",
                "Configuration saved successfully!",
            )
        else:
            QMessageBox.warning(self.dialog, "Error", "Failed to save configuration.")

    def _export_config(self) -> None:
        """Export the current logger configuration to a user-specified file.

        Opens a file dialog for the user to select a destination and saves the current logger configuration. Displays a success or error message based on the outcome.
        """
        filename, _ = QFileDialog.getSaveFileName(
            self.dialog,
            "Export logger configuration",
            "logger_config_export.json",
            "JSON Files (*.json);;All Files (*)",
        )

        if filename:
            # Use the same protection mechanism as set_logger_level
            self.registry._saving_in_progress = True
            try:
                success = self.config.export_config(self.registry, filename)
            finally:
                self.registry._saving_in_progress = False

            if success:
                QMessageBox.information(
                    self.dialog,
                    "Success",
                    f"Configuration exported to:\n{filename}",
                )
            else:
                QMessageBox.warning(
                    self.dialog,
                    "Error",
                    "Failed to export configuration.",
                )

    def _import_config(self) -> None:
        """Import a logger configuration from a user-selected file.

        Opens a file dialog for the user to select a configuration file and applies the imported settings to the logger registry. Displays a success or error message based on the outcome and refreshes the logger tree if successful.
        """
        filename, _ = QFileDialog.getOpenFileName(
            self.dialog,
            "Import logger configuration",
            "",
            "JSON Files (*.json);;All Files (*)",
        )

        if filename:
            if self.config.import_config(self.registry, filename):
                QMessageBox.information(
                    self.dialog,
                    "Success",
                    "Configuration imported successfully!",
                )
                self._refresh_loggers()
            else:
                QMessageBox.warning(
                    self.dialog,
                    "Error",
                    "Failed to import configuration.",
                )


def show_logger_dev_tool(parent=None):
    """Show the LoggerDevTool GUI for managing logger configurations.

    Instantiates and displays the LoggerDevTool dialog, returning its result code. If PyQt5 is not available, logs an error and returns None.

    Args:
        parent: The parent widget for the dialog, if any.

    Returns:
        int | None: The result code from the dialog execution, or None if the tool could not be shown.
    """
    try:
        tool = LoggerDevTool(parent)
        return tool.show()
    except ImportError as e:
        logging.getLogger(__name__).exception(f"Cannot show Logger Dev Tool: {e}")
        return None


def set_default_logging() -> None:
    """Configure the global logging level to display only errors.

    This function sets the root logger's level to ERROR, ensuring that only messages
    with a severity of ERROR and above are displayed in production.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)

    # Also update console handler if it exists
    for handler in root_logger.handlers:
        if (
            isinstance(handler, logging.StreamHandler) and not hasattr(handler, "stream")
        ) or handler.stream.name == "<stderr>":
            handler.setLevel(logging.ERROR)


def enable_debug_logging() -> None:
    """Configure the global logging level to display all log levels, including INFO and DEBUG.

    This function sets the root logger's level to DEBUG, allowing all messages, including
    those with lower severity, to be displayed.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Also update console handler to show debug messages
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and (
            not hasattr(handler, "stream") or handler.stream.name == "<stderr>"
        ):
            handler.setLevel(logging.DEBUG)


def enable_warning_logging() -> None:
    """Configure the global logging level to display warnings and errors.

    This function sets the root logger's level to WARNING, useful for development
    when you need more information than just errors.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # Also update console handler to show warnings
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and (
            not hasattr(handler, "stream") or handler.stream.name == "<stderr>"
        ):
            handler.setLevel(logging.WARNING)


class FpdbLogFormatter(colorlog.ColoredFormatter):
    """Custom formatter for FPDB logs with variable highlighting.

    This formatter extends colorlog.ColoredFormatter to add specific coloring to variables
    within log messages, enhancing readability.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the formatter with color codes for variables.

        Args:
            *args: Positional arguments passed to the parent constructor.
            **kwargs: Keyword arguments passed to the parent constructor.

        """
        super().__init__(*args, **kwargs)
        self.var_color = "\033[36m"  # ANSI code for cyan color, used for variables
        self.reset_color = "\033[0m"  # ANSI code to reset color

    def format(self, record: logging.LogRecord) -> str:
        """Format the log message by highlighting variables.

        Args:
            record (LogRecord): The log record to format.

        Returns:
            str: The formatted log message with variables highlighted.

        """
        if hasattr(record, "msg"):
            # Apply coloring to variables in the message
            record.msg = self._colorize_variables(record.msg)
        return super().format(record)

    def _colorize_variables(self, message: str) -> str:
        """Apply coloring to variables present in the message.

        Variables are identified by single or double quotes.
        For example, in "Variable 'x' is set", 'x' will be colored in cyan.

        Args:
            message (str): The log message potentially containing variables.

        Returns:
            str: The message with variables colored.

        """
        if not isinstance(message, str):
            return message  # If the message is not a string, return it as is

        # Define a regex pattern to capture strings enclosed in single or double quotes
        pattern = r"'([^']*)'|\"([^\"]*)\""

        def repl(match: re.Match[str]) -> str:
            """Replacement function used by re.sub.

            It colors the captured variable in cyan.

            Args:
                match (re.Match): The regex match object.

            Returns:
                str: The captured variable with color codes added.

            """
            var = match.group(1) or match.group(
                2,
            )  # Extract the variable without quotes
            return f"{self.var_color}'{var}'{self.reset_color}"  # Add color codes around the quotes

        # Use re.sub to replace all occurrences of variables with their colored versions
        return re.sub(pattern, repl, message)


class JsonFormatter(logging.Formatter):
    """Formatter that converts log records to JSON format.

    This formatter facilitates automated log analysis by structuring logs in JSON.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON object containing key information.

        The included fields are:
            - asctime : Timestamp of the log event.
            - name : Name of the logger.
            - levelname : Severity level (DEBUG, INFO, etc.).
            - module : Name of the module where the log was generated.
            - funcName : Name of the function where the log was generated.
            - message : The log message itself.

        Args:
            record (LogRecord): The log record to format.

        Returns:
            str: The JSON representation of the log record.

        """
        record_dict = {
            "asctime": self.formatTime(record, self.datefmt),  # Format the timestamp
            "name": record.name,  # Logger name
            "levelname": record.levelname,  # Log level
            "module": record.module,  # Originating module
            "funcName": record.funcName,  # Originating function
            "message": record.getMessage(),  # Log message
        }
        return json.dumps(record_dict)  # Convert the dictionary to a JSON string


class TimedSizedRotatingFileHandler(TimedRotatingFileHandler):
    """Log file handler that performs rotation based on both time and file size.

    This handler rotates the log file at specified time intervals and when the file
    reaches a certain size. Rotated files include the date and a part number in their name.
    """

    def __init__(  # noqa: PLR0913
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 0,
        encoding: str | None = None,
        delay: bool = False,  # noqa: FBT001, FBT002
        utc: bool = False,  # noqa: FBT001, FBT002
        at_time: Any = None,
        max_bytes: int = 0,
    ) -> None:
        """Initialize the handler with parameters for time-based and size-based rotation.

        Args:
            filename (str): Path to the log file.
            when (str): Time interval for rotation ('midnight' by default).
            interval (int): Rotation interval (1 by default).
            backupCount (int): Number of backup files to keep.
            encoding (str): Encoding of the log file.
            delay (bool): If True, file opening is deferred until the first log message.
            utc (bool): If True, use UTC for time-based rotation.
            atTime (datetime.time): Specific time for time-based rotation.
            maxBytes (int): Maximum file size in bytes before rotation.
            at_time (datetime.time): Specific time for time-based rotation.
            backup_count (int): Number of backup files to keep.
            max_bytes (int): Maximum file size in bytes before rotation.

        """
        super().__init__(
            filename,
            when,
            interval,
            backup_count,
            encoding,
            delay,
            utc,
            at_time,
        )
        self.max_bytes = max_bytes  # Maximum size before size-based rotation
        self.part = 1  # Initialize part number for rotated files
        self.currentDate = time.strftime(
            "%Y-%m-%d",
        )  # Current date in YYYY-MM-DD format

    def shouldRollover(self, _record: logging.LogRecord) -> bool:
        """Determine whether the log file should be rotated.

        This method checks both time-based and size-based rotation conditions.

        Args:
            record (LogRecord): The current log record.

        Returns:
            bool: True if rotation should occur, False otherwise.

        """
        t = int(time.time())  # Current time in seconds since epoch
        if t >= self.rolloverAt:
            # If current time exceeds the scheduled rollover time
            self.part = 1  # Reset part number
            self.currentDate = time.strftime("%Y-%m-%d")  # Update current date
            return True  # Indicate that a rollover is needed

        if self.max_bytes > 0:
            # If a size limit is set, check the current file size
            self.stream.seek(0, os.SEEK_END)  # Move to the end of the file
            if self.stream.tell() >= self.max_bytes:
                # If current file size exceeds max_bytes
                return True  # Indicate that a rollover is needed

        return False  # No rollover condition met

    def doRollover(self) -> None:
        """Perform the log file rollover.

        This method renames the current log file, deletes old log files if necessary,
        and sets up the next rollover time.
        """
        self.stream.close()  # Close the current log file stream
        current_time = int(time.time())  # Current time
        time_tuple = time.localtime(current_time)  # Convert time to struct_time
        date_str = time.strftime("%d-%m-%Y", time_tuple)  # Format date as DD-MM-YYYY

        # Construct the rotated file name with date and part number
        dfn = f"{self.baseFilename}-{date_str}-part{self.part}.txt"

        # Increment the part number for the next rollover
        self.part += 1

        # Perform the file rotation
        if os.path.exists(dfn):  # noqa: PTH110
            os.remove(
                dfn,
            )  # Remove the file if it already exists to avoid conflicts
        os.rename(
            self.baseFilename,
            dfn,
        )  # Rename the current log file to the new name

        # Delete old log files if necessary
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)  # Remove files exceeding the backup count  # noqa: PTH107

        # Reopen the log file stream if delay is not enabled
        if not self.delay:
            self.stream = self._open()  # Open a new log file

        # Calculate the next rollover time based on the current time
        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at += self.interval  # Add the interval until rolloverAt is in the future
        self.rolloverAt = new_rollover_at  # Update rolloverAt

    def getFilesToDelete(self) -> list[str]:
        """Determine which log files should be deleted during rollover.

        This method is overridden to match the rotated file naming pattern.
        It searches for all files that start with the base name and end with '.txt',
        then retains only the most recent files based on backupCount.

        Returns:
            list: List of full paths to log files that should be deleted.

        """
        dir_name, base_name = os.path.split(
            self.baseFilename,
        )  # Split directory and base filename
        file_names = os.listdir(dir_name)  # List all files in the directory
        result = [
            os.path.join(dir_name, file_name)  # noqa: PTH118
            for file_name in file_names
            if file_name.startswith(base_name) and file_name.endswith(".txt")
        ]
        result.sort()  # Sort files alphabetically (usually chronological if dates are in the name)

        # If the number of files exceeds backupCount, return the oldest files to delete
        if len(result) <= self.backupCount:
            return []  # No files to delete
        # Return the excess files, i.e., the oldest ones
        return result[: len(result) - self.backupCount]


def auto_load_logger_config() -> None:
    """Automatically load logger configuration at startup.

    Attempts to load the saved logger configuration and apply it to the global registry. Logs an informational message if successful, or a debug message if no configuration is loaded or an error occurs.
    """
    try:
        registry = get_logger_registry()
        config = get_log_config()

        # Try to load existing configuration
        if config.load_config(registry):
            logging.getLogger(__name__).info(
                "Configuration loggers loaded automatically.",
            )

    except Exception as e:
        logging.getLogger(__name__).debug(f"No configuration loaded: {e}")


def ensure_console_handlers_configured() -> None:
    """Ensure console handlers reflect the minimum log level required by all enabled loggers.

    Adjusts the root logger and its console handlers to match the lowest log level needed by any enabled logger in the registry. This ensures that messages at the required levels are visible in the console.

    """
    try:
        registry = get_logger_registry()
        root_logger = logging.getLogger()

        # Find the minimum level needed across all configured loggers
        min_level = logging.ERROR  # Start with ERROR (highest)

        for logger_info in registry.get_all_loggers().values():
            if logger_info.enabled and logger_info.current_level < min_level:
                min_level = logger_info.current_level

        # If any logger needs DEBUG/INFO/WARNING, update root logger and handlers
        if min_level < logging.ERROR:
            # Update root logger level
            if root_logger.level > min_level:
                root_logger.setLevel(min_level)

            # Update existing console handlers
            for handler in root_logger.handlers:
                if (
                    isinstance(handler, logging.StreamHandler)
                    and not hasattr(
                        handler,
                        "baseFilename",
                    )
                    and handler.level > min_level
                ):
                    handler.setLevel(min_level)

    except Exception as e:
        logging.getLogger(__name__).debug(f"Error configuring console handlers: {e}")


def setup_logging(log_dir: str | None = None, *, console_only: bool = False) -> None:
    """Configure the logging system.

    This function sets up console and file handlers with custom formatters,
    applies color coding for console logs, and manages log file rotation.

    Args:
        log_dir (str, optional): Path to the directory where logs will be stored.
            If None, the default directory is '~/fpdb_logs'.
        console_only (bool, optional): If True, only the console handler is configured.
            By default, both console and file handlers are set up.

    Raises:
        Exception: If an error occurs during logging configuration.

    """
    try:
        # Configure the console handler with color coding
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
        formatter = colorlog.ColoredFormatter(
            fmt=log_format,
            datefmt=date_format,
            log_colors=log_colors,
        )

        # Create a stream handler for the console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)  # Apply the colored formatter
        console_handler.setLevel(logging.ERROR)  # Console shows only errors by default

        # Configure the root logger
        logger = logging.getLogger()
        logger.setLevel(logging.ERROR)  # Default level set to ERROR for production

        # Remove existing handlers to prevent duplicate logs
        logger.handlers = []
        logger.addHandler(console_handler)  # Add the console handler

        if not console_only:
            # Set the log directory if not specified
            if log_dir is None:
                log_dir = os.path.join(
                    os.path.expanduser("~"),
                    "fpdb_logs",
                )
            log_dir = os.path.normpath(log_dir)  # Normalize the directory path
            os.makedirs(  # noqa: PTH103
                log_dir,
                exist_ok=True,
            )  # Create the directory if it doesn't exist
            log_file = os.path.join(  # noqa: PTH118
                log_dir,
                "fpdb-log.txt",
            )  # Full path to the log file

            # Use the custom TimedSizedRotatingFileHandler
            max_bytes = 1024 * 1024  # 1 MB
            backup_count = 30  # Keep logs for 30 rotations
            file_formatter = JsonFormatter(
                datefmt=date_format,
            )  # Use JsonFormatter for files
            file_handler = TimedSizedRotatingFileHandler(
                log_file,
                when="midnight",  # Daily rotation at midnight
                interval=1,  # Every day
                backup_count=backup_count,
                encoding="utf-8",
                max_bytes=max_bytes,
            )
            file_handler.setFormatter(file_formatter)  # Apply the JSON formatter
            file_handler.setLevel(logging.DEBUG)  # Minimum log level for the file

            logger.addHandler(file_handler)  # Add the file handler to the root logger

        # Auto-load saved logger configuration
        auto_load_logger_config()

        # Ensure console handlers are properly configured for saved logger levels
        ensure_console_handlers_configured()

    except Exception:  # noqa: TRY203
        raise  # Re-raise the exception after printing the error


def update_log_level(logger_name: str, level: int) -> None:
    """Update the logging level for a specific logger.

    This function allows dynamic modification of a logger's severity level.

    Args:
        logger_name (str): The name of the logger whose level needs to be updated.
        level (int): The new logging level (e.g., logging.DEBUG).

    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)


class FpdbLogger:
    """Custom logger for FPDB.

    This class provides a simplified interface for logging with methods for different
    levels (debug, info, warning, error) and dynamically manages the stack level
    to ensure accurate log information.
    """

    def __init__(self, name: str) -> None:
        """Initialize the FpdbLogger with a specific name.

        Args:
            name (str): The name of the logger (typically __name__ of the calling module).

        """
        self.logger = logging.getLogger(name)  # Obtain a logger with the specified name

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()  # Calculate stack level for accurate information
        self.logger.debug(msg, *args, stacklevel=stacklevel, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an informational message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.info(msg, *args, stacklevel=stacklevel, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.warning(msg, *args, stacklevel=stacklevel, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.error(msg, *args, stacklevel=stacklevel, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an exception message with stack trace.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.exception(msg, *args, stacklevel=stacklevel, **kwargs)

    def setLevel(self, level: int) -> None:
        """Set the logging level for this logger.

        Args:
            level (int): The new logging level (e.g., logging.DEBUG).

        """
        self.logger.setLevel(level)

    def getEffectiveLevel(self) -> int:
        """Get the effective logging level for this logger.

        Returns:
            int: The effective logging level.

        """
        return self.logger.getEffectiveLevel()

    def _get_stacklevel(self) -> int:
        """Calculate the stack level to pass to the underlying logger.

        This method inspects the call stack to determine the appropriate stack level
        so that log records reflect accurate line numbers and function names.

        Returns:
            int: The calculated stack level for the logger.

        """
        frame = inspect.currentframe()  # Get the current frame
        stacklevel = 1  # Initialize stack level
        while frame:
            co_name = frame.f_code.co_name  # Get the function name of the current frame
            if co_name in (
                "debug",
                "info",
                "warning",
                "error",
                "__init__",
                "_get_stacklevel",
            ):
                # If the function name is one of the logging methods or internal methods,
                # continue traversing the stack
                frame = frame.f_back  # Move to the previous frame
                stacklevel += 1  # Increment the stack level
            else:
                break  # Stop if a different function name is encountered
        return stacklevel  # Return the calculated stack level


def get_logger(name: str) -> FpdbLogger:
    """Return a configured FPDB logger.

    This function provides an instance of FpdbLogger configured with the specified name.
    It also registers the logger with the global registry and applies any saved configuration.

    Args:
        name (str): The name of the logger (typically __name__ of the calling module).

    Returns:
        FpdbLogger: An instance of FpdbLogger ready for use.

    """
    fpdb_logger = FpdbLogger(name)

    # Register the logger with the global registry and apply saved configuration
    global _logger_registry
    _logger_registry.register_logger(name, fpdb_logger.logger)

    # Force synchronization with registry current configuration
    # This ensures the Python logger instance matches the Logger Dev Tool settings
    logger_info = _logger_registry.get_logger_info(name)
    if logger_info:
        # Force set the level on the actual Python logger instance
        # This is crucial for loggers that may have been configured elsewhere (like HUD)
        existing_logger = logging.getLogger(name)
        existing_logger.setLevel(logger_info.current_level)
        fpdb_logger.logger.setLevel(logger_info.current_level)

    return fpdb_logger


# Global logger registry instance - initialized after all classes are defined
_logger_registry = LoggerRegistry()
