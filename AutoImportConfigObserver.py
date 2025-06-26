#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
AutoImportConfigObserver.py

Configuration observer for the auto-import module.
Manages configuration changes that can be applied without restart.
"""

import threading
from ConfigurationManager import ConfigChange, ConfigObserver
from loggingFpdb import get_logger

log = get_logger("autoimportconfig")


class AutoImportConfigObserver(ConfigObserver):
    """
    Observer for auto-import configuration changes.

    Manages changes that can be applied dynamically such as:
    - Import paths
    - Game filters
    - Import options (except interval)
    """

    def __init__(self, auto_import_gui):
        """
        Initialize the auto-import observer.

        Args:
            auto_import_gui: Reference to GuiAutoImport
        """
        self.auto_import = auto_import_gui
        self._lock = threading.Lock()
        self.observed_paths = [
            "supported_sites.*.HH_path",  # Hand history paths
            "import.ImportFilters",  # Import filters
            "import.fastStoreHudCache",  # Cache options
            "import.saveActions",  # Save actions
            "import.cacheSessions",  # Session cache
            "import.sessionTimeout",  # Session timeout
        ]

    def get_observed_paths(self):
        """Returns the observed configuration paths"""
        return self.observed_paths

    def on_config_change(self, change: ConfigChange) -> bool:
        """
        Apply a configuration change to auto-import.

        Args:
            change: The change to apply

        Returns:
            bool: True if the change was successfully applied
        """
        try:
            with self._lock:
                log.info(f"Applying auto-import change: {change}")

                # Import path changes
                if "HH_path" in change.path:
                    return self._apply_path_change(change)

                # Filter changes
                elif "ImportFilters" in change.path:
                    return self._apply_filter_change(change)

                # Cache options
                elif "fastStoreHudCache" in change.path:
                    return self._apply_cache_option_change(change)

                # Action options
                elif "saveActions" in change.path:
                    return self._apply_action_option_change(change)

                # Session options
                elif "cacheSessions" in change.path or "sessionTimeout" in change.path:
                    return self._apply_session_option_change(change)

                else:
                    log.warning(f"Unhandled change: {change.path}")
                    return True

        except Exception as e:
            log.error(f"Error applying change {change}: {e}")
            return False

    def _apply_path_change(self, change: ConfigChange) -> bool:
        """Apply an import path change"""
        try:
            # Extract site name from path
            parts = change.path.split(".")
            if len(parts) >= 2:
                site_name = parts[1]

                # If auto-import is running, update monitored paths
                if hasattr(self.auto_import, "importer") and self.auto_import.importer:
                    if hasattr(self.auto_import.importer, "addImportDirectory"):
                        # Remove old path if present
                        if change.old_value and hasattr(self.auto_import.importer, "removeImportDirectory"):
                            self.auto_import.importer.removeImportDirectory(change.old_value)

                        # Add new path
                        if change.new_value:
                            self.auto_import.importer.addImportDirectory(change.new_value, monitor=True)

                        log.info(f"Import path updated for {site_name}: {change.old_value} → {change.new_value}")

                # Update interface if necessary
                if hasattr(self.auto_import, "updatePaths"):
                    self.auto_import.updatePaths()

            return True
        except Exception as e:
            log.error(f"Error changing path: {e}")
            return False

    def _apply_filter_change(self, change: ConfigChange) -> bool:
        """Apply an import filter change"""
        try:
            log.info(f"Import filters updated: {change.new_value}")

            # Update filters in importer
            if hasattr(self.auto_import, "importer") and self.auto_import.importer:
                if hasattr(self.auto_import.importer, "setImportFilters"):
                    self.auto_import.importer.setImportFilters(change.new_value)

            return True
        except Exception as e:
            log.error(f"Error changing filters: {e}")
            return False

    def _apply_cache_option_change(self, change: ConfigChange) -> bool:
        """Apply a cache option change"""
        try:
            log.info(f"Cache option updated: fastStoreHudCache = {change.new_value}")

            # Update option in importer
            if hasattr(self.auto_import, "importer") and self.auto_import.importer:
                if hasattr(self.auto_import.importer, "setFastStoreHudCache"):
                    self.auto_import.importer.setFastStoreHudCache(change.new_value)

            return True
        except Exception as e:
            log.error(f"Error changing cache option: {e}")
            return False

    def _apply_action_option_change(self, change: ConfigChange) -> bool:
        """Apply an action option change"""
        try:
            log.info(f"Action option updated: saveActions = {change.new_value}")

            # Update option in importer
            if hasattr(self.auto_import, "importer") and self.auto_import.importer:
                if hasattr(self.auto_import.importer, "setSaveActions"):
                    self.auto_import.importer.setSaveActions(change.new_value)

            return True
        except Exception as e:
            log.error(f"Error changing action option: {e}")
            return False

    def _apply_session_option_change(self, change: ConfigChange) -> bool:
        """Apply a session option change"""
        try:
            log.info(f"Session option updated: {change.path} = {change.new_value}")

            # Update option in importer
            if hasattr(self.auto_import, "importer") and self.auto_import.importer:
                if "cacheSessions" in change.path and hasattr(self.auto_import.importer, "setCacheSessions"):
                    self.auto_import.importer.setCacheSessions(change.new_value)
                elif "sessionTimeout" in change.path and hasattr(self.auto_import.importer, "setSessionTimeout"):
                    self.auto_import.importer.setSessionTimeout(change.new_value)

            return True
        except Exception as e:
            log.error(f"Error changing session option: {e}")
            return False
