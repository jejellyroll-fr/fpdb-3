"""Observe auto-import configuration changes.

This module defines ``AutoImportConfigObserver``, which listens for
configuration updates that can be applied without restarting the application.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from ConfigurationManager import ConfigChange, ConfigObserver
from loggingFpdb import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from GuiAutoImport import GuiAutoImport

log = get_logger("auto_import_config_observer")

MIN_PATH_PARTS = 2  # minimum length for path.split(".")
SITE_INDEX = 1  # site name index in path.split(".")


class AutoImportConfigObserver(ConfigObserver):
    """Observer for auto-import configuration changes."""

    def __init__(self, auto_import_gui: GuiAutoImport) -> None:
        """Initialize the auto-import observer.

        Args:
            auto_import_gui: instance de GuiAutoImport

        """
        self.auto_import = auto_import_gui
        self._lock = threading.Lock()
        self.observed_paths: list[str] = [
            "supported_sites.*.HH_path",  # Hand-history paths
            "import.ImportFilters",  # Import filters
            "import.fastStoreHudCache",  # Cache options
            "import.saveActions",  # Save actions
            "import.cacheSessions",  # Session cache
            "import.sessionTimeout",  # Session timeout
        ]

    def get_observed_paths(self) -> list[str]:
        """Return the list of configuration paths observed by this observer.

        This method provides the set of configuration keys that the observer monitors for changes.

        Returns:
            list[str]: The list of observed configuration paths.
        """
        return self.observed_paths

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply a configuration change to auto-import.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: ``True`` if the change was applied ,
                ``False`` in case of exception.

        """
        # Mapping “ keyword in path → handler ”
        handlers: dict[str, Callable[[ConfigChange], bool]] = {
            "HH_path": self._apply_path_change,
            "ImportFilters": self._apply_filter_change,
            "fastStoreHudCache": self._apply_cache_option_change,
            "saveActions": self._apply_action_option_change,
            "cacheSessions": self._apply_session_option_change,
            "sessionTimeout": self._apply_session_option_change,
        }

        applied = False  # dafult result

        try:
            with self._lock:
                log.info("Applying auto-import change: %s", change)

                # Browse the mapping and apply the first handler that matches
                for key, handler in handlers.items():
                    if key in change.path:
                        applied = handler(change)
                        break
                else:  # No handler found
                    log.warning("Unhandled change: %s", change.path)
                    applied = True  # The “neutral” operation is considered successful

        except Exception:
            log.exception("Error applying change %s", change)
            applied = False

        return applied

    def _apply_path_change(self, change: ConfigChange) -> bool:
        """Apply a hand-history path change for a specific site.

        Updates the import directory for the relevant site and refreshes the interface if needed.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: True if the change was applied successfully, False otherwise.
        """
        try:
            # Extract site name -- e.g.: “supported_sites.PokerStars.HH_path”
            parts = change.path.split(".")
            if len(parts) < MIN_PATH_PARTS:
                log.warning("Unexpected path format: %s", change.path)
                return True  # Neutral operation

            site_name = parts[SITE_INDEX]

            importer = getattr(self.auto_import, "import", None)
            add_dir = getattr(importer, "addImportDirectory", None)
            remove_dir = getattr(importer, "removeImportDirectory", None)

            if importer and add_dir:
                # Removes old directory, if any
                if change.old_value and remove_dir:
                    remove_dir(change.old_value)

                # Adds the new directory
                add_dir(change.new_value, monitor=True)

                log.info(
                    "Import path updated for %s: %s → %s",
                    site_name,
                    change.old_value,
                    change.new_value,
                )

            # Refreshes interface, if available
            if hasattr(self.auto_import, "updatePaths"):
                self.auto_import.updatePaths()

        except Exception:  # pragma: no cover - logs and returns False
            log.exception("Error changing HH_path for %s", change)
            return False
        else:
            return True

    def _apply_filter_change(self, change: ConfigChange) -> bool:
        """Apply an import filter change to the auto-importer.

        Updates the import filters for the importer based on the configuration change.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: True if the change was applied successfully, False otherwise.
        """
        try:
            log.info("Import filters updated: %s", change.new_value)
            # Update filters in importer
            importer = getattr(self.auto_import, "import", None)

            if set_filters := getattr(importer, "setImportFilters", None):
                set_filters(change.new_value)

        except Exception:
            log.exception("Error changing filters for %s", change)
            return False
        else:
            return True

    def _apply_cache_option_change(self, change: ConfigChange) -> bool:
        """Apply a cache option change to the auto-importer.

        Updates the fast store HUD cache option for the importer based on the configuration change.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: True if the change was applied successfully, False otherwise.
        """
        try:
            log.info("Cache option updated: %s", change.new_value)

            # Retrieves setter if attribute string exists
            if set_cache := getattr(
                getattr(self.auto_import, "import", None),
                "setFastStoreHudCache",
                None,
            ):
                set_cache(change.new_value)

        except Exception:
            log.exception("Error changing cache option for %s", change)
            return False
        else:
            return True

    def _apply_action_option_change(self, change: ConfigChange) -> bool:
        """Apply an action option change to the auto-importer.

        Updates the save actions option for the importer based on the configuration change.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: True if the change was applied successfully, False otherwise.
        """
        try:
            log.info("Action option updated: %s", change.new_value)

            if set_actions := getattr(
                getattr(self.auto_import, "import", None),
                "setSaveActions",
                None,
            ):
                set_actions(change.new_value)

        except Exception:
            log.exception("Error changing action option for %s", change)
            return False
        else:
            return True

    def _apply_session_option_change(self, change: ConfigChange) -> bool:
        """Apply a session option change to the auto-importer.

        Updates the session cache or timeout option for the importer based on the configuration change.

        Args:
            change: The configuration change to apply.

        Returns:
            bool: True if the change was applied successfully, False otherwise.
        """
        try:
            log.info("Session option updated: %s", change.new_value)

            importer = getattr(self.auto_import, "import", None)

            set_cache_sessions = getattr(importer, "setCacheSessions", None)
            set_timeout = getattr(importer, "setSessionTimeout", None)

            if "cacheSessions" in change.path and set_cache_sessions:
                set_cache_sessions(change.new_value)
            elif "sessionTimeout" in change.path and set_timeout:
                set_timeout(change.new_value)

        except Exception:
            log.exception("Error changing session option for %s", change)
            return False
        else:
            return True
