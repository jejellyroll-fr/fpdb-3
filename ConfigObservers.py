#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ConfigObservers.py

Configuration observer implementations for different fpdb components.
"""

import threading
from typing import List

from ConfigurationManager import ChangeType, ConfigChange, ConfigObserver
from loggingFpdb import get_logger

log = get_logger("configobs")


class HUDConfigObserver(ConfigObserver):
    """Observer for HUD - manages HUD configuration changes"""

    def __init__(self, hud_main_instance):
        self.hud_main = hud_main_instance
        self._lock = threading.Lock()

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply configuration changes for HUD"""
        try:
            with self._lock:
                if change.type == ChangeType.HUD_SETTINGS:
                    return self._update_hud_settings(change)
                elif change.type == ChangeType.STAT_SETTINGS:
                    return self._update_stat_settings(change)
                elif change.path.startswith("supported_sites") and change.path.endswith(".screen_name"):
                    return self._update_hero_name(change)

                return True

        except Exception as e:
            log.error(f"HUD error while applying change: {e}")
            return False

    def get_observed_paths(self) -> List[str]:
        """Returns paths observed by HUD"""
        return ["stat_sets", "supported_sites", "hud_ui", "layout_sets"]

    def _update_hud_settings(self, change: ConfigChange) -> bool:
        """Update general HUD settings"""
        try:
            # Notifier tous les HUD actifs
            if hasattr(self.hud_main, "hud_instances"):
                for table_id, hud in self.hud_main.hud_instances.items():
                    hud.reconfig()
                log.info("HUD configuration updated for all tables")
                return True
        except Exception as e:
            log.error(f"Error updating HUD: {e}")
        return False

    def _update_stat_settings(self, change: ConfigChange) -> bool:
        """Update displayed statistics"""
        try:
            # Parse path to extract info
            # Format: stat_sets.{name}.stats.{position}
            parts = change.path.split(".")
            if len(parts) >= 4:
                stat_set_name = parts[1]
                # position = parts[3]

                # Update existing stat windows
                if hasattr(self.hud_main, "hud_instances"):
                    for table_id, hud in self.hud_main.hud_instances.items():
                        if hud.stat_set_name == stat_set_name:
                            hud.update_stat_windows()

                log.info(f"Stats updated for {stat_set_name}")
                return True
        except Exception as e:
            log.error(f"Error updating stats: {e}")
        return False

    def _update_hero_name(self, change: ConfigChange) -> bool:
        """Update hero name for a site"""
        try:
            site_name = change.path.split(".")[1]
            # Update in all active HUDs for this site
            if hasattr(self.hud_main, "hud_instances"):
                for table_id, hud in self.hud_main.hud_instances.items():
                    if hud.site == site_name:
                        hud.hero = change.new_value
                        hud.update_hero_stats()

            log.info(f"Hero name updated for {site_name}: {change.new_value}")
            return True
        except Exception as e:
            log.error(f"Error updating hero: {e}")
        return False


class DatabaseConfigObserver(ConfigObserver):
    """Observer for database - manages DB connection changes"""

    def __init__(self, database_instance):
        self.database = database_instance

    def on_config_change(self, change: ConfigChange) -> bool:
        """DB changes require restart - always returns False"""
        log.info(f"Database change detected: {change.path}")
        # DB changes are marked as requiring restart
        # by ConfigurationManager, so we do nothing here
        return False

    def get_observed_paths(self) -> List[str]:
        """Returns observed paths for database"""
        return ["database"]


class GuiPrefsObserver(ConfigObserver):
    """Observer for GUI preferences - manages interface changes"""

    def __init__(self, main_window):
        self.main_window = main_window

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply GUI configuration changes"""
        try:
            if change.type == ChangeType.THEME_SETTINGS:
                return self._update_theme(change)
            elif change.type == ChangeType.GUI_SETTINGS:
                return self._update_gui_settings(change)
            elif change.type == ChangeType.SEAT_PREFERENCES:
                return self._update_seat_preferences(change)

            return True

        except Exception as e:
            log.error(f"GUI error while applying change: {e}")
            return False

    def get_observed_paths(self) -> List[str]:
        """Returns observed paths for interface"""
        return [
            "general",
            "gui_cash_stats",
            "gui_tour_stats",
            "supported_sites",
        ]

    def _update_theme(self, change: ConfigChange) -> bool:
        """Update interface theme"""
        try:
            if hasattr(self.main_window, "change_theme"):
                self.main_window.change_theme(change.new_value)
                log.info(f"Theme updated: {change.new_value}")
                return True
        except Exception as e:
            log.error(f"Error changing theme: {e}")
        return False

    def _update_gui_settings(self, change: ConfigChange) -> bool:
        """Update general interface settings"""
        try:
            # Refresh affected windows
            if hasattr(self.main_window, "refresh_tabs"):
                self.main_window.refresh_tabs()
            return True
        except Exception as e:
            log.error(f"Error updating GUI: {e}")
        return False

    def _update_seat_preferences(self, change: ConfigChange) -> bool:
        """Update seat preferences"""
        try:
            # Seat preferences mainly affect HUD
            # Notify HUD via its observer
            log.info(f"Seat preferences updated: {change.path}")
            return True
        except Exception as e:
            log.error(f"Error updating seats: {e}")
        return False


class BulkImportConfigObserver(ConfigObserver):
    """Observer for bulk import"""

    def __init__(self, bulk_import_instance):
        self.bulk_import = bulk_import_instance

    def on_config_change(self, change: ConfigChange) -> bool:
        """Apply changes for bulk import"""
        try:
            if change.path.endswith(".HH_path"):
                # Update default path
                if hasattr(self.bulk_import, "updateDefaultPath"):
                    self.bulk_import.updateDefaultPath(change.new_value)
                return True
            elif change.path == "import.hhBulkPath":
                # Update bulk import path
                if hasattr(self.bulk_import, "setImportPath"):
                    self.bulk_import.setImportPath(change.new_value)
                return True

            return True

        except Exception as e:
            log.error(f"BulkImport error while applying change: {e}")
            return False

    def get_observed_paths(self) -> List[str]:
        """Returns observed paths for bulk import"""
        return ["supported_sites", "import.hhBulkPath", "import.ResultsDirectory"]
