"""ConfigObservers.py.

Configuration observer implementations for different fpdb components.
"""

import threading
from typing import Any

from ConfigurationManager import ChangeType, ConfigChange, ConfigObserver
from loggingFpdb import get_logger

log = get_logger("configobs")


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
        """Apply configuration changes for HUD."""
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
        """Returns paths observed by HUD."""
        return ["stat_sets", "supported_sites", "hud_ui", "layout_sets"]

    def _update_hud_settings(self, change: ConfigChange) -> bool:  # noqa: ARG002
        """Update general HUD settings."""
        try:
            # Notifier tous les HUD actifs
            if hasattr(self.hud_main, "hud_instances"):
                for hud in self.hud_main.hud_instances.values():
                    hud.reconfig()
                log.info("HUD configuration updated for all tables")
                return True
        except Exception:
            log.exception("Error updating HUD")
        return False

    def _update_stat_settings(self, change: ConfigChange) -> bool:
        """Update displayed statistics."""
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
        """Update hero name for a site."""
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
        """DB changes require restart - always returns False."""
        log.info("Database change detected: %s", change.path)
        # DB changes are marked as requiring restart
        # by ConfigurationManager, so we do nothing here
        return False

    def get_observed_paths(self) -> list[str]:
        """Returns observed paths for database."""
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
        """Apply GUI configuration changes."""
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
        """Returns observed paths for interface."""
        return [
            "general",
            "gui_cash_stats",
            "gui_tour_stats",
            "supported_sites",
        ]

    def _update_theme(self, change: ConfigChange) -> bool:
        """Update interface theme."""
        try:
            if hasattr(self.main_window, "change_theme"):
                self.main_window.change_theme(change.new_value)
                log.info("Theme updated: %s", change.new_value)
        except Exception:
            log.exception("Error changing theme")
            return False
        else:
            return True
        return False

    def _update_gui_settings(self, change: ConfigChange) -> bool:  # noqa: ARG002
        """Update general interface settings."""
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
        """Update seat preferences."""
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
        """Apply changes for bulk import."""
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
        """Returns observed paths for bulk import."""
        return ["supported_sites", "import.hhBulkPath", "import.ResultsDirectory"]
