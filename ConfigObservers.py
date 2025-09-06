"""ConfigObservers.py.

Configuration observer implementations for different fpdb components.
"""

import threading
from typing import Any

from ConfigurationManager import ChangeType, ConfigChange, ConfigObserver
from loggingFpdb import get_logger

log = get_logger("config_observers")


class HUDConfigObserver(ConfigObserver):
    """Observer for HUD - manages HUD configuration changes."""

    def __init__(self, hud_main_instance: Any) -> None:
        """Initialize HUD config observer.

        Args:
            hud_main_instance: The HUD main instance to observe.
        """
        self.hud_main = hud_main_instance
        self._lock = threading.Lock()

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply HUD configuration changes in response to observed updates.

        Handles HUD, stat, and hero name changes by updating the relevant HUD components.
        Returns True if the change was applied successfully, otherwise False.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the change was applied successfully, False otherwise.
        """
        try:
            with self._lock:
                if change.type == ChangeType.HUD_SETTINGS:
                    return self._update_hud_settings(change)
                if change.type == ChangeType.STAT_SETTINGS:
                    return self._update_stat_settings(change)
                if change.path.startswith("supported_sites") and change.path.endswith(".screen_name"):
                    return self._update_hero_name(change)

                return True

        except Exception:
            log.exception("HUD error while applying change")
            return False

    def get_observed_paths(self) -> list[str]:
        """Return the list of configuration paths observed by this HUD observer.

        Provides the configuration paths that this observer monitors for changes.

        Returns:
            A list of configuration path strings.
        """
        return ["stat_sets", "supported_sites", "hud_ui", "layout_sets"]

    def _update_hud_settings(self, change: ConfigChange) -> bool:  # noqa: ARG002
        """Update HUD settings for all active HUD instances.

        Notifies all active HUDs to reconfigure themselves in response to a configuration change.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the HUDs were updated successfully, False otherwise.
        """
        try:
            # Notify all active HUDs
            if hasattr(self.hud_main, "hud_instances"):
                for hud in self.hud_main.hud_instances.values():
                    hud.reconfig()
                log.info("HUD configuration updated for all tables")
                return True
        except Exception:
            log.exception("Error updating HUD")
        return False

    def _update_stat_settings(self, change: ConfigChange) -> bool:
        """Update stat settings for relevant HUD instances.

        Updates stat windows for HUDs that match the affected stat set when a configuration change is detected.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the stat settings were updated successfully, False otherwise.
        """
        try:
            # Parse path to extract info
            # Format: stat_sets.{name}.stats.{position}
            parts = change.path.split(".")
            min_parts_for_stat_set = 4  # stat_sets.{name}.stats.{position}
            if len(parts) >= min_parts_for_stat_set:
                stat_set_name = parts[1]
                # Update existing stat windows
                if hasattr(self.hud_main, "hud_instances"):
                    for hud in self.hud_main.hud_instances.values():
                        if hud.stat_set_name == stat_set_name:
                            hud.update_stat_windows()

                log.info("Stats updated for %s", stat_set_name)
                return True
        except Exception:
            log.exception("Error updating stats")
        return False

    def _update_hero_name(self, change: ConfigChange) -> bool:
        """Update the hero name for all HUDs associated with a specific site.

        Sets the hero name and updates hero stats for all active HUD instances matching
        the site in the configuration change.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the hero name was updated successfully, False otherwise.
        """
        try:
            site_name = change.path.split(".")[1]
            # Update in all active HUDs for this site
            if hasattr(self.hud_main, "hud_instances"):
                for hud in self.hud_main.hud_instances.values():
                    if hud.site == site_name:
                        hud.hero = change.new_value
                        hud.update_hero_stats()

            log.info("Hero name updated for %s: %s", site_name, change.new_value)
        except Exception:
            log.exception("Error updating hero")
            return False
        else:
            return True
        return False


class DatabaseConfigObserver(ConfigObserver):
    """Observer for database - manages DB connection changes."""

    def __init__(self, database_instance: Any) -> None:
        """Initialize database config observer.

        Args:
            database_instance: The database instance to observe.
        """
        self.database = database_instance

    def on_config_change(self, change: ConfigChange) -> bool:
        """Handle database configuration changes.

        Logs the detected database configuration change. Always returns False as database changes require a restart.

        Args:
            change: The configuration change event to process.

        Returns:
            False, as database changes are not applied dynamically.
        """
        log.info("Database change detected: %s", change.path)
        # DB changes are marked as requiring restart
        # by ConfigurationManager, so we do nothing here
        return False

    def get_observed_paths(self) -> list[str]:
        """Return the list of configuration paths observed by this database observer.

        Provides the configuration paths that this observer monitors for changes.

        Returns:
            A list of configuration path strings.
        """
        return ["database"]


class GuiPrefsObserver(ConfigObserver):
    """Observer for GUI preferences - manages interface changes."""

    def __init__(self, main_window: Any) -> None:
        """Initialize GUI preferences observer.

        Args:
            main_window: The main window instance to observe.
        """
        self.main_window = main_window

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply GUI configuration changes in response to observed updates.

        Handles theme, GUI, and seat preference changes by updating the relevant GUI components.
        Returns True if the change was applied successfully, otherwise False.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the change was applied successfully, False otherwise.
        """
        try:
            if change.type == ChangeType.THEME_SETTINGS:
                return self._update_theme(change)
            if change.type == ChangeType.GUI_SETTINGS:
                return self._update_gui_settings(change)
            if change.type == ChangeType.SEAT_PREFERENCES:
                return self._update_seat_preferences(change)

        except Exception:
            log.exception("GUI error while applying change")
            return False
        else:
            return True

    def get_observed_paths(self) -> list[str]:
        """Return the list of configuration paths observed by this GUI preferences observer.

        Provides the configuration paths that this observer monitors for changes.

        Returns:
            A list of configuration path strings.
        """
        return [
            "general",
            "gui_cash_stats",
            "gui_tour_stats",
            "supported_sites",
        ]

    def _update_theme(self, change: ConfigChange) -> bool:
        """Update the application theme in response to a configuration change.

        Handles both qt_material theme and popup theme changes using the ThemeManager.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the theme was updated successfully, False otherwise.
        """
        try:
            # Import ThemeManager here to avoid circular imports
            from ThemeManager import ThemeManager

            theme_manager = ThemeManager()

            if change.path == "general.qt_material_theme":
                # Use ThemeManager to set qt_material theme (also auto-syncs popup theme)
                success = theme_manager.set_qt_material_theme(change.new_value, save=True)
                if success:
                    log.info("Qt material theme updated: %s", change.new_value)
                return success

            elif change.path == "general.popup_theme":
                # Set popup theme only
                success = theme_manager.set_popup_theme(change.new_value, save=True)
                if success:
                    log.info("Popup theme updated: %s", change.new_value)
                return success

            else:
                # Fallback to original behavior for backward compatibility
                if hasattr(self.main_window, "change_theme"):
                    self.main_window.change_theme(change.new_value)
                    log.info("Theme updated (legacy): %s", change.new_value)
                    return True

        except Exception:
            log.exception("Error changing theme")
            return False

        return False

    def _update_gui_settings(self, change: ConfigChange) -> bool:  # noqa: ARG002
        """Update GUI settings in response to a configuration change.

        Refreshes affected windows or tabs in the main window when GUI settings are updated.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the GUI was updated successfully, False otherwise.
        """
        try:
            # Refresh affected windows
            if hasattr(self.main_window, "refresh_tabs"):
                self.main_window.refresh_tabs()
        except Exception:
            log.exception("Error updating GUI")
            return False
        else:
            return True
        return False

    def _update_seat_preferences(self, change: ConfigChange) -> bool:
        """Update seat preferences in response to a configuration change.

        Logs the update of seat preferences and notifies relevant components if necessary.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the seat preferences were updated successfully, False otherwise.
        """
        try:
            # Seat preferences mainly affect HUD
            # Notify HUD via its observer
            log.info("Seat preferences updated: %s", change.path)
        except Exception:
            log.exception("Error updating seats")
            return False
        else:
            return True


class BulkImportConfigObserver(ConfigObserver):
    """Observer for bulk import."""

    def __init__(self, bulk_import_instance: Any) -> None:
        """Initialize bulk import config observer.

        Args:
            bulk_import_instance: The bulk import instance to observe.
        """
        self.bulk_import = bulk_import_instance

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply bulk import configuration changes in response to observed updates.

        Updates the default or bulk import path for hand histories when relevant configuration changes are detected.

        Args:
            change: The configuration change event to process.

        Returns:
            True if the change was applied successfully, False otherwise.
        """
        try:
            if change.path.endswith(".HH_path"):
                # Update default path
                if hasattr(self.bulk_import, "updateDefaultPath"):
                    self.bulk_import.updateDefaultPath(change.new_value)
                return True
            if change.path == "import.hhBulkPath":
                # Update bulk import path
                if hasattr(self.bulk_import, "setImportPath"):
                    self.bulk_import.setImportPath(change.new_value)
                return True

        except Exception:
            log.exception("BulkImport error while applying change")
            return False
        else:
            return True

    def get_observed_paths(self) -> list[str]:
        """Return the list of configuration paths observed by this bulk import observer.

        Provides the configuration paths that this observer monitors for changes.

        Returns:
            A list of configuration path strings.
        """
        return ["supported_sites", "import.hhBulkPath", "import.ResultsDirectory"]
