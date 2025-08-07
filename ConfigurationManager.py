#!/usr/bin/env python

"""ConfigurationManager.py.

Singleton manager for fpdb configuration with dynamic reload support.
This module minimizes the need for restarts when configuration changes.
"""

import copy
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar

import Configuration
from loggingFpdb import get_logger

log = get_logger("configuration_manager")


class ChangeType(Enum):
    """Types of configuration changes."""

    SITE_SETTINGS = "site_settings"
    HUD_SETTINGS = "hud_settings"
    DATABASE_SETTINGS = "database_settings"
    IMPORT_SETTINGS = "import_settings"
    GUI_SETTINGS = "gui_settings"
    THEME_SETTINGS = "theme_settings"
    SEAT_PREFERENCES = "seat_preferences"
    STAT_SETTINGS = "stat_settings"


class ConfigChange:
    """Represents a configuration change."""

    def __init__(self, change_type: ChangeType, path: str, old_value: Any, new_value: Any) -> None:
        self.type = change_type
        self.path = path
        self.old_value = old_value
        self.new_value = new_value
        self.requires_restart = False

    def __repr__(self) -> str:
        return f"ConfigChange({self.type.value}, {self.path}, {self.old_value} -> {self.new_value})"


class ConfigObserver(ABC):
    """Interface for configuration change observers."""

    @abstractmethod
    def on_config_change(self, change: ConfigChange) -> bool:
        """Called when a configuration change occurs.

        Args:
            change: The configuration change

        Returns:
            bool: True if the change was successfully applied, False otherwise

        """

    @abstractmethod
    def get_observed_paths(self) -> list[str]:
        """Returns the list of configuration paths observed by this component.

        Returns:
            List[str]: List of paths (e.g., ["import.interval", "import.path"])

        """


class ConfigurationManager:
    """Singleton manager for fpdb configuration.

    Handles loading, saving, and dynamic reloading of configuration,
    as well as notifying observer components of changes.
    """

    _instance = None
    _lock = threading.RLock()

    # Changes requiring a full restart
    RESTART_REQUIRED_PATHS: ClassVar[list[str]] = [
        "database",  # Any database change
        "supported_sites.*.enabled",  # Site enable/disable
        "import.interval",  # Import interval (thread timing)
        "import.callFpdbHud",  # HUD enable/disable
    ]

    # Changes that can be applied dynamically
    DYNAMIC_CHANGE_PATHS: ClassVar[list[str]] = [
        "supported_sites.*.fav_seat",  # Favorite seats
        "supported_sites.*.screen_name",  # Screen name
        "supported_sites.*.HH_path",  # Hand history path
        "supported_sites.*.TS_path",  # Tournament summary path
        "hud_ui.*",  # HUD UI settings
    ]

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.initialized = False
            self._config = None
            self._observers: list[ConfigObserver] = []
            self._change_history: list[ConfigChange] = []
            self._pending_changes: list[ConfigChange] = []
            self._config_file_path = None
            self._last_saved_state = {}  # Last saved state

    def initialize(self, config_file=None) -> None:
        """Initializes the configuration manager.

        Args:
            config_file: Path to the configuration file (optional)

        """
        with self._lock:
            if self.initialized:
                log.warning("ConfigurationManager already initialized")
                return

            try:
                # Use existing Configuration for compatibility
                self._config = Configuration.Config(file=config_file)
                self._config_file_path = self._config.file
                self.initialized = True
                # Capture initial state
                self._capture_current_state()
                log.info(f"ConfigurationManager initialized with {self._config_file_path}")
            except Exception as e:
                log.exception(f"Error during initialization: {e}")
                raise

    def get_config(self) -> Configuration.Config:
        """Returns the current configuration instance."""
        if not self.initialized:
            msg = "ConfigurationManager not initialized"
            raise RuntimeError(msg)
        return self._config

    def register_observer(self, observer: ConfigObserver) -> None:
        """Registers an observer for configuration changes.

        Args:
            observer: The observer to register

        """
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)
                log.debug(f"Observer {observer.__class__.__name__} registered")

    def unregister_observer(self, observer: ConfigObserver) -> None:
        """Unregisters an observer.

        Args:
            observer: The observer to unregister

        """
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)
                log.debug(f"Observer {observer.__class__.__name__} unregistered")

    def check_pending_changes(self, current_config) -> list[ConfigChange]:
        """Checks for pending configuration changes compared to the last saved state.

        This method compares the current configuration with the last captured state and returns a list of detected changes.

        Args:
            current_config: The current configuration instance to compare.

        Returns:
            List[ConfigChange]: List of configuration changes detected.

        """
        with self._lock:
            if not self.initialized:
                return []

            try:
                # Use the new method that compares with the saved state
                changes = self.detect_changes_from_saved_state(current_config)

                log.debug(f"Pending changes detected: {len(changes)}")
                for change in changes:
                    log.debug(f"  - {change}")

                return changes

            except Exception as e:
                log.exception(f"Error while checking changes: {e}")
                import traceback

                traceback.print_exc()
                return []

    def reload_config(self) -> tuple[bool, str, list[ConfigChange]]:
        """Reloads the configuration from file.

        Returns:
            Tuple[bool, str, List[ConfigChange]]:
                - Success (True/False)
                - Status message
                - List of changes requiring a restart

        """
        with self._lock:
            if not self.initialized:
                return False, "ConfigurationManager not initialized", []

            try:
                # Save important values from the old configuration
                old_config = self._config

                # Reload from file
                new_config = Configuration.Config(file=self._config_file_path)

                # Identify changes
                changes = self._identify_changes(old_config, new_config)

                log.debug(f"Detected changes: {len(changes)}")
                for change in changes:
                    log.debug(f"  - {change}")

                if not changes:
                    # Check if there were pending changes
                    if hasattr(self, "_pending_changes") and self._pending_changes:
                        changes = self._pending_changes
                        self._pending_changes = []
                        log.debug(f"Using pending changes: {len(changes)}")
                    else:
                        return True, "No changes detected", []

                # Separate changes requiring restart
                restart_changes = []
                dynamic_changes = []

                for change in changes:
                    if self._requires_restart(change):
                        change.requires_restart = True
                        restart_changes.append(change)
                    else:
                        dynamic_changes.append(change)

                # Apply dynamic changes
                if dynamic_changes:
                    success = self._apply_dynamic_changes(dynamic_changes, new_config)
                    if not success:
                        return (
                            False,
                            "Failed to apply dynamic changes",
                            restart_changes,
                        )

                # Use reload() method of existing Config object
                # This avoids creating a new object and allows components
                # with a reference to the old object to see the changes
                if hasattr(self._config, "reload"):
                    log.info("Using Config.reload() method")
                    self._config.reload()
                else:
                    # Fallback: copy important attributes
                    log.warning("Config.reload() not available, copying attributes")
                    if hasattr(new_config, "ui"):
                        self._config.ui = new_config.ui
                    if hasattr(new_config, "doc"):
                        self._config.doc = new_config.doc
                    if hasattr(new_config, "supported_sites"):
                        self._config.supported_sites = new_config.supported_sites
                    if hasattr(new_config, "supported_games"):
                        self._config.supported_games = new_config.supported_games
                    if hasattr(new_config, "supported_databases"):
                        self._config.supported_databases = new_config.supported_databases
                    if hasattr(new_config, "stat_sets"):
                        self._config.stat_sets = new_config.stat_sets

                # Capture new state
                self._capture_current_state()

                # Add to history (limit size)
                self._change_history.extend(changes)
                if len(self._change_history) > 1000:
                    self._change_history = self._change_history[-500:]

                if restart_changes:
                    return (
                        True,
                        f"{len(dynamic_changes)} changes applied, {len(restart_changes)} require restart",
                        restart_changes,
                    )
                return (
                    True,
                    f"{len(dynamic_changes)} changes applied successfully",
                    [],
                )

            except Exception as e:
                log.exception(f"Error during reload: {e}")
                import traceback

                traceback.print_exc()
                return False, f"Error: {e!s}", []

    def _identify_changes(
        self,
        old_config: Configuration.Config,
        new_config: Configuration.Config,
    ) -> list[ConfigChange]:
        """Identifies the differences between two configurations.

        Args:
            old_config: Old configuration
            new_config: New configuration

        Returns:
            List[ConfigChange]: List of identified changes

        """
        changes = []

        try:
            # Compare supported sites
            if hasattr(new_config, "supported_sites") and hasattr(old_config, "supported_sites"):
                for site_name in new_config.supported_sites:
                    old_site = old_config.supported_sites.get(site_name)
                    new_site = new_config.supported_sites[site_name]

                    if not old_site:
                        # New site added
                        changes.append(
                            ConfigChange(
                                ChangeType.SITE_SETTINGS,
                                f"supported_sites.{site_name}",
                                None,
                                f"New site: {site_name}",
                            ),
                        )
                    else:
                        # Compare site attributes
                        if hasattr(old_site, "enabled") and hasattr(new_site, "enabled"):
                            if old_site.enabled != new_site.enabled:
                                changes.append(
                                    ConfigChange(
                                        ChangeType.SITE_SETTINGS,
                                        f"supported_sites.{site_name}.enabled",
                                        old_site.enabled,
                                        new_site.enabled,
                                    ),
                                )
                        if hasattr(old_site, "screen_name") and hasattr(new_site, "screen_name"):
                            if old_site.screen_name != new_site.screen_name:
                                changes.append(
                                    ConfigChange(
                                        ChangeType.SITE_SETTINGS,
                                        f"supported_sites.{site_name}.screen_name",
                                        old_site.screen_name,
                                        new_site.screen_name,
                                    ),
                                )
                        if hasattr(old_site, "HH_path") and hasattr(new_site, "HH_path"):
                            if old_site.HH_path != new_site.HH_path:
                                changes.append(
                                    ConfigChange(
                                        ChangeType.SITE_SETTINGS,
                                        f"supported_sites.{site_name}.HH_path",
                                        old_site.HH_path,
                                        new_site.HH_path,
                                    ),
                                )
                        if hasattr(old_site, "TS_path") and hasattr(new_site, "TS_path"):
                            if old_site.TS_path != new_site.TS_path:
                                changes.append(
                                    ConfigChange(
                                        ChangeType.SITE_SETTINGS,
                                        f"supported_sites.{site_name}.TS_path",
                                        old_site.TS_path,
                                        new_site.TS_path,
                                    ),
                                )

                        # Compare favorite seats
                        if hasattr(old_site, "fav_seat") and hasattr(new_site, "fav_seat"):
                            if old_site.fav_seat != new_site.fav_seat:
                                changes.append(
                                    ConfigChange(
                                        ChangeType.SEAT_PREFERENCES,
                                        f"supported_sites.{site_name}.fav_seat",
                                        old_site.fav_seat,
                                        new_site.fav_seat,
                                    ),
                                )

            # Compare import settings
            if hasattr(old_config, "imp") and hasattr(new_config, "imp"):
                old_imp = old_config.imp
                new_imp = new_config.imp

                if hasattr(old_imp, "interval") and hasattr(new_imp, "interval"):
                    if old_imp.interval != new_imp.interval:
                        changes.append(
                            ConfigChange(
                                ChangeType.IMPORT_SETTINGS,
                                "import.interval",
                                old_imp.interval,
                                new_imp.interval,
                            ),
                        )

                if hasattr(old_imp, "callFpdbHud") and hasattr(new_imp, "callFpdbHud"):
                    if old_imp.callFpdbHud != new_imp.callFpdbHud:
                        changes.append(
                            ConfigChange(
                                ChangeType.IMPORT_SETTINGS,
                                "import.callFpdbHud",
                                old_imp.callFpdbHud,
                                new_imp.callFpdbHud,
                            ),
                        )

            # Compare import filters
            try:
                old_filters = old_config.get_import_parameters().get("importFilters", [])
                new_filters = new_config.get_import_parameters().get("importFilters", [])
                if old_filters != new_filters:
                    changes.append(
                        ConfigChange(
                            ChangeType.IMPORT_SETTINGS,
                            "import.ImportFilters",
                            old_filters,
                            new_filters,
                        ),
                    )
            except Exception as e:
                log.debug(f"Error comparing filters: {e}")

            # Compare database parameters
            try:
                old_db = old_config.get_db_parameters()
                new_db = new_config.get_db_parameters()

                for key in new_db:
                    if old_db.get(key) != new_db[key]:
                        changes.append(
                            ConfigChange(
                                ChangeType.DATABASE_SETTINGS,
                                f"database.{key}",
                                old_db.get(key),
                                new_db[key],
                            ),
                        )
            except Exception as e:
                log.debug(f"Error comparing DB parameters: {e}")

            # Compare HUD UI parameters
            try:
                if hasattr(old_config, "get_hud_ui_parameters") and hasattr(new_config, "get_hud_ui_parameters"):
                    old_hud_ui = old_config.get_hud_ui_parameters()
                    new_hud_ui = new_config.get_hud_ui_parameters()

                    for key in new_hud_ui:
                        if old_hud_ui.get(key) != new_hud_ui[key]:
                            changes.append(
                                ConfigChange(
                                    ChangeType.HUD_SETTINGS,
                                    f"hud_ui.{key}",
                                    old_hud_ui.get(key),
                                    new_hud_ui[key],
                                ),
                            )
            except Exception as e:
                log.debug(f"Error comparing HUD UI parameters: {e}")

        except Exception as e:
            log.exception(f"Error identifying changes: {e}")
            import traceback

            traceback.print_exc()

        return changes

    def _requires_restart(self, change: ConfigChange) -> bool:
        """Determines if a change requires a restart.

        Args:
            change: The change to evaluate

        Returns:
            bool: True if a restart is required

        """
        # Check critical paths
        for critical_path in self.RESTART_REQUIRED_PATHS:
            if critical_path.endswith("*"):
                # Wildcard matching
                base_path = critical_path[:-2]
                if change.path.startswith(base_path):
                    return True
            elif change.path.startswith(critical_path):
                return True

        # Some change types always require a restart
        if change.type == ChangeType.DATABASE_SETTINGS:
            return True

        # Favorite seat changes do not require a restart
        if change.type == ChangeType.SEAT_PREFERENCES:
            return False

        return False

    def _apply_dynamic_changes(self, changes: list[ConfigChange], new_config: Configuration.Config) -> bool:
        """Applies changes that can be made dynamically.

        Args:
            changes: List of changes to apply
            new_config: New configuration

        Returns:
            bool: True if all changes were successfully applied

        """
        all_success = True

        # Group changes by relevant observer
        observer_changes: dict[ConfigObserver, list[ConfigChange]] = {}

        for change in changes:
            for observer in self._observers:
                observed_paths = observer.get_observed_paths()
                for path in observed_paths:
                    if change.path.startswith(path):
                        if observer not in observer_changes:
                            observer_changes[observer] = []
                        observer_changes[observer].append(change)
                        break

        # Notify each observer
        for observer, changes_list in observer_changes.items():
            try:
                for change in changes_list:
                    success = observer.on_config_change(change)
                    if not success:
                        log.error(f"Failed to apply change {change} by {observer.__class__.__name__}")
                        all_success = False
            except Exception as e:
                log.exception(f"Error notifying {observer.__class__.__name__}: {e}")
                all_success = False

        return all_success

    def get_pending_restart_changes(self) -> list[ConfigChange]:
        """Returns the list of pending changes that require a restart.

        Returns:
            List[ConfigChange]: List of changes requiring a restart

        """
        return [c for c in self._pending_changes if c.requires_restart]

    def clear_pending_changes(self) -> None:
        """Clears the list of pending changes."""
        self._pending_changes.clear()

    def get_change_history(self, limit: int = 100) -> list[ConfigChange]:
        """Returns the change history.

        Args:
            limit: Maximum number of changes to return

        Returns:
            List[ConfigChange]: Change history

        """
        return self._change_history[-limit:]

    def _capture_current_state(self) -> None:
        """Captures the current configuration state for future comparison."""
        self._last_saved_state = {"sites": {}, "import": {}, "database": {}, "hud_ui": {}}

        # Capture site state
        if hasattr(self._config, "supported_sites"):
            for site_name, site in self._config.supported_sites.items():
                self._last_saved_state["sites"][site_name] = {
                    "enabled": getattr(site, "enabled", None),
                    "screen_name": getattr(site, "screen_name", ""),
                    "HH_path": getattr(site, "HH_path", ""),
                    "TS_path": getattr(site, "TS_path", ""),
                    "fav_seat": copy.deepcopy(getattr(site, "fav_seat", {})),
                }
                log.debug(f"Captured state for {site_name}: {self._last_saved_state['sites'][site_name]}")

        # Capture import state
        if hasattr(self._config, "imp"):
            imp = self._config.imp
            self._last_saved_state["import"] = {
                "interval": getattr(imp, "interval", None),
                "callFpdbHud": getattr(imp, "callFpdbHud", None),
            }

        # Capture import filters
        try:
            self._last_saved_state["import"]["filters"] = self._config.get_import_parameters().get("importFilters", [])
        except Exception as e:
            log.warning("Error loading import filters: %s", e)

        # Capture HUD UI state
        try:
            if hasattr(self._config, "get_hud_ui_parameters"):
                self._last_saved_state["hud_ui"] = copy.deepcopy(self._config.get_hud_ui_parameters())
                log.debug(f"Captured HUD UI state: {len(self._last_saved_state['hud_ui'])} parameters")
        except Exception as e:
            log.warning("Error capturing HUD UI parameters: %s", e)

    def detect_changes_from_saved_state(self, current_config) -> list[ConfigChange]:
        """Detects configuration changes by comparing the current state to the last saved state.

        This method returns a list of configuration changes that have occurred since the last state capture.

        Args:
            current_config: The current configuration instance to compare.

        Returns:
            List[ConfigChange]: List of detected configuration changes.

        """
        changes = []

        log.debug(f"Saved site state: {self._last_saved_state.get('sites', {})}")

        # Compare sites
        if hasattr(current_config, "supported_sites"):
            for site_name, site in current_config.supported_sites.items():
                saved_site = self._last_saved_state.get("sites", {}).get(site_name, {})
                log.debug(f"Comparison for {site_name}:")
                log.debug(f"  Saved: {saved_site}")
                log.debug(
                    f"  Current: screen_name={getattr(site, 'screen_name', '')}, HH_path={getattr(site, 'HH_path', '')}, TS_path={getattr(site, 'TS_path', '')}",
                )

                # Check each attribute
                current_enabled = getattr(site, "enabled", None)
                if saved_site.get("enabled") != current_enabled:
                    changes.append(
                        ConfigChange(
                            ChangeType.SITE_SETTINGS,
                            f"supported_sites.{site_name}.enabled",
                            saved_site.get("enabled"),
                            current_enabled,
                        ),
                    )

                current_screen_name = getattr(site, "screen_name", "")
                if saved_site.get("screen_name") != current_screen_name:
                    changes.append(
                        ConfigChange(
                            ChangeType.SITE_SETTINGS,
                            f"supported_sites.{site_name}.screen_name",
                            saved_site.get("screen_name"),
                            current_screen_name,
                        ),
                    )

                current_hh_path = getattr(site, "HH_path", "")
                if saved_site.get("HH_path") != current_hh_path:
                    changes.append(
                        ConfigChange(
                            ChangeType.SITE_SETTINGS,
                            f"supported_sites.{site_name}.HH_path",
                            saved_site.get("HH_path"),
                            current_hh_path,
                        ),
                    )

                current_ts_path = getattr(site, "TS_path", "")
                if saved_site.get("TS_path") != current_ts_path:
                    changes.append(
                        ConfigChange(
                            ChangeType.SITE_SETTINGS,
                            f"supported_sites.{site_name}.TS_path",
                            saved_site.get("TS_path"),
                            current_ts_path,
                        ),
                    )

                # Compare favorite seats
                current_fav_seat = getattr(site, "fav_seat", {})
                saved_fav_seat = saved_site.get("fav_seat", {})
                if current_fav_seat != saved_fav_seat:
                    changes.append(
                        ConfigChange(
                            ChangeType.SEAT_PREFERENCES,
                            f"supported_sites.{site_name}.fav_seat",
                            saved_fav_seat,
                            current_fav_seat,
                        ),
                    )

        # Compare import filters
        try:
            current_filters = current_config.get_import_parameters().get("importFilters", [])
            saved_filters = self._last_saved_state.get("import", {}).get("filters", [])
            if current_filters != saved_filters:
                changes.append(
                    ConfigChange(
                        ChangeType.IMPORT_SETTINGS,
                        "import.ImportFilters",
                        saved_filters,
                        current_filters,
                    ),
                )
        except Exception as e:
            log.warning("Error loading copyFromFilter: %s", e)

        # Compare HUD UI parameters
        try:
            if hasattr(current_config, "get_hud_ui_parameters"):
                current_hud_ui = current_config.get_hud_ui_parameters()
                saved_hud_ui = self._last_saved_state.get("hud_ui", {})

                # Compare each HUD UI parameter
                all_keys = set(current_hud_ui.keys()) | set(saved_hud_ui.keys())
                for key in all_keys:
                    current_value = current_hud_ui.get(key)
                    saved_value = saved_hud_ui.get(key)

                    if current_value != saved_value:
                        changes.append(
                            ConfigChange(
                                ChangeType.HUD_SETTINGS,
                                f"hud_ui.{key}",
                                saved_value,
                                current_value,
                            ),
                        )
                        log.debug(f"HUD UI change detected: {key}: {saved_value} -> {current_value}")
        except Exception as e:
            log.warning("Error comparing HUD UI parameters: %s", e)

        return changes
