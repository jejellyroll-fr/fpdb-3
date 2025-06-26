#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GuiConfigObserver.py

Configuration observer for the main fpdb graphical interface.
Handles configuration changes that can be applied without restart.
"""

from ConfigurationManager import ConfigChange, ConfigObserver
from loggingFpdb import get_logger

log = get_logger("guiconfig")


class GuiConfigObserver(ConfigObserver):
    """
    Observer for configuration changes in the graphical interface.

    Handles changes that can be applied dynamically such as:
    - Themes
    - Display preferences
    - Language settings
    - Default paths
    """

    def __init__(self, main_window):
        """
        Initializes the GUI observer.

        Args:
            main_window: Reference to the main fpdb window
        """
        self.main_window = main_window
        self.observed_paths = [
            "gui",  # All GUI settings
            "theme",  # Theme settings
            "supported_sites.*.screen_name",  # Hero names (display only)
            "supported_sites.*.HH_path",  # Paths (for dialogs)
            "supported_sites.*.TS_path",  # Tournament paths
            "import.ImportFilters",  # Import filters
            "seats",  # Seat preferences
            "hud_ui",  # HUD UI settings
            "HUD_config",  # HUD configuration
        ]

    def get_observed_paths(self):
        """Returns the observed configuration paths"""
        return self.observed_paths

    def on_config_change(self, change: ConfigChange) -> bool:
        """
        Applies a configuration change to the interface.

        Args:
            change: The change to apply

        Returns:
            bool: True if the change was successfully applied
        """
        try:
            log.info(f"Applying GUI change: {change}")

            # Theme changes
            if change.path.startswith("theme"):
                return self._apply_theme_change(change)

            # Hero name changes
            elif "screen_name" in change.path:
                return self._apply_hero_name_change(change)

            # Path changes
            elif "HH_path" in change.path or "TS_path" in change.path:
                return self._apply_path_change(change)

            # Import filters
            elif "ImportFilters" in change.path:
                return self._apply_filter_change(change)

            # Seat preferences
            elif change.path.startswith("seats"):
                return self._apply_seat_change(change)

            # HUD settings
            elif change.path.startswith("hud_ui") or change.path.startswith("HUD_config"):
                return self._apply_hud_change(change)

            # Other GUI settings
            elif change.path.startswith("gui"):
                return self._apply_gui_setting_change(change)

            else:
                log.warning(f"Unhandled change: {change.path}")
                return True  # Considered OK

        except Exception as e:
            log.error(f"Error applying change {change}: {e}")
            return False

    def _apply_theme_change(self, change: ConfigChange) -> bool:
        """Applies a theme change"""
        try:
            if hasattr(self.main_window, "change_theme"):
                # Extract theme name from value
                theme_name = change.new_value
                if isinstance(theme_name, dict) and "name" in theme_name:
                    theme_name = theme_name["name"]

                self.main_window.change_theme(theme_name)
                log.info(f"Theme changed: {theme_name}")
                return True
            else:
                log.warning("Theme change not supported in this version")
                return False
        except Exception as e:
            log.error(f"Error during theme change: {e}")
            return False

    def _apply_hero_name_change(self, change: ConfigChange) -> bool:
        """Applies a hero name change"""
        try:
            # Extract site name from path
            parts = change.path.split(".")
            if len(parts) >= 2:
                site_name = parts[1]
                log.info(
                    f"Hero name updated for {site_name}: {change.new_value}"
                )

                # Update open windows if necessary
                for thread in self.main_window.threads:
                    if hasattr(thread, "update_hero_name"):
                        thread.update_hero_name(site_name, change.new_value)

            return True
        except Exception as e:
            log.error(f"Error during hero name change: {e}")
            return False

    def _apply_path_change(self, change: ConfigChange) -> bool:
        """Applies a path change"""
        try:
            # Paths are mainly used for dialogs
            # No immediate update needed
            log.info(f"Path updated: {change.path} = {change.new_value}")
            return True
        except Exception as e:
            log.error(f"Error during path change: {e}")
            return False

    def _apply_filter_change(self, change: ConfigChange) -> bool:
        """Applies an import filter change"""
        try:
            log.info(f"Import filters updated: {change.new_value}")

            # Update import windows if open
            for thread in self.main_window.threads:
                if hasattr(thread, "update_import_filters"):
                    thread.update_import_filters(change.new_value)

            return True
        except Exception as e:
            log.error(f"Error during filter change: {e}")
            return False

    def _apply_seat_change(self, change: ConfigChange) -> bool:
        """Applies a seat preference change"""
        try:
            log.info(f"Seat preference updated: {change.path}")

            # Seat preferences are used by the HUD
            # No update needed in the main interface
            return True
        except Exception as e:
            log.error(f"Error during seat change: {e}")
            return False

    def _apply_gui_setting_change(self, change: ConfigChange) -> bool:
        """Applies a general GUI setting change"""
        try:
            log.info(f"GUI setting updated: {change.path} = {change.new_value}")

            # Handle specific GUI settings
            if "window_size" in change.path:
                # Resize window
                if (
                    isinstance(change.new_value, (list, tuple))
                    and len(change.new_value) == 2
                ):
                    self.main_window.resize(change.new_value[0], change.new_value[1])

            elif "window_position" in change.path:
                # Move window
                if (
                    isinstance(change.new_value, (list, tuple))
                    and len(change.new_value) == 2
                ):
                    self.main_window.move(change.new_value[0], change.new_value[1])

            return True
        except Exception as e:
            log.error(f"Error during GUI setting change: {e}")
            return False

    def _apply_hud_change(self, change: ConfigChange) -> bool:
        """Applies a HUD configuration change"""
        try:
            log.info(f"HUD configuration updated: {change.path} = {change.new_value}")
            
            # Reload active HUD displays
            if hasattr(self.main_window, 'reload_hud_displays'):
                self.main_window.reload_hud_displays()
                log.info("HUD displays reloaded after configuration change")
            else:
                log.warning("The method reload_hud_displays is not available")
                
            return True
        except Exception as e:
            log.error(f"Error during HUD configuration change: {e}")
            return False
