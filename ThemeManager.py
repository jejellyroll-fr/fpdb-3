#!/usr/bin/env python

"""ThemeManager.py

Centralized theme manager for fpdb.
Unifies the three theme systems: qt_material, PopupThemes and settings.json.
"""

import threading
import os
from pathlib import Path
from typing import Optional

from loggingFpdb import get_logger

log = get_logger("theme_manager")

# Custom themes directory
CUSTOM_THEMES_DIR = Path.home() / ".fpdb" / "themes"


class ThemeManager:
    """Centralized theme manager for fpdb.
    
    Manages synchronization between:
    - qt_material themes (main application theme)
    - PopupThemes (HUD popup windows)
    - XML Configuration (persistence)
    """
    
    _instance = None
    _lock = threading.RLock()
    
    # Available qt_material themes (dynamically detected)
    AVAILABLE_QT_THEMES = None  # Will be populated on first access
    
    # Mapping qt_material to popup themes
    QT_TO_POPUP_MAPPING = {
        "dark_purple.xml": "material_dark",
        "dark_amber.xml": "material_dark", 
        "dark_blue.xml": "material_dark",
        "dark_cyan.xml": "material_dark",
        "dark_lightgreen.xml": "material_dark",
        "dark_pink.xml": "material_dark",
        "dark_red.xml": "material_dark",
        "dark_teal.xml": "material_dark",
        "dark_yellow.xml": "material_dark",
        "light_amber.xml": "material_light",
        "light_blue.xml": "material_light", 
        "light_cyan.xml": "material_light",
        "light_lightgreen.xml": "material_light",
        "light_pink.xml": "material_light",
        "light_purple.xml": "material_light",
        "light_red.xml": "material_light",
        "light_teal.xml": "material_light",
        "light_yellow.xml": "material_light"
    }
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = False
            self._qt_material_theme = "dark_purple.xml"
            self._popup_theme = "material_dark"
            self._config = None
            self._main_window = None
            # Initialize available themes list on first instance
            if ThemeManager.AVAILABLE_QT_THEMES is None:
                ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()
            
    def initialize(self, config=None, main_window=None):
        """Initialize the ThemeManager.
        
        Args:
            config: Configuration instance
            main_window: Main window instance
        """
        with self._lock:
            if self.initialized:
                log.warning("ThemeManager already initialized")
                return
                
            self._config = config
            self._main_window = main_window
            
            # Load saved themes
            self._load_saved_themes()
            
            self.initialized = True
            log.info("ThemeManager initialized")
    
    def _load_saved_themes(self):
        """Load saved themes from configuration."""
        if not self._config:
            return
            
        try:
            # Load from XML configuration
            general = getattr(self._config, 'general', {})
            
            saved_qt_theme = general.get('qt_material_theme', 'dark_purple.xml')
            saved_popup_theme = general.get('popup_theme', 'material_dark')
            
            # Validate themes
            if saved_qt_theme in self.AVAILABLE_QT_THEMES:
                self._qt_material_theme = saved_qt_theme
            else:
                log.warning(f"Invalid qt_material theme: {saved_qt_theme}, using default")
                
            if saved_popup_theme in ["material_dark", "material_light", "classic"]:
                self._popup_theme = saved_popup_theme
            else:
                log.warning(f"Invalid popup theme: {saved_popup_theme}, using default")
                
            log.info(f"Loaded themes: qt={self._qt_material_theme}, popup={self._popup_theme}")
            
        except Exception as e:
            log.exception(f"Error loading saved themes: {e}")
    
    def _detect_available_themes(self) -> list[str]:
        """Detect all available qt_material themes dynamically.
        
        Returns:
            list[str]: List of available theme names (including custom themes)
        """
        try:
            # Get built-in qt_material themes
            builtin_themes = self._get_builtin_qt_themes()
            
            # Get custom themes
            custom_themes = self._get_custom_themes()
            
            # Combine and sort
            all_themes = builtin_themes + custom_themes
            return sorted(all_themes)
                
        except Exception as e:
            log.exception(f"Error in theme detection: {e}")
            return self._get_fallback_themes()
    
    def _get_builtin_qt_themes(self) -> list[str]:
        """Get built-in qt_material themes.
        
        Returns:
            list[str]: List of built-in theme names
        """
        try:
            from PyQt5.QtWidgets import QApplication
            # Ensure QApplication exists (required for qt_material)
            if QApplication.instance() is None:
                app = QApplication.instance() or QApplication([])
            
            import qt_material
            available_themes = qt_material.list_themes()
            log.info(f"Detected {len(available_themes)} built-in qt_material themes")
            return available_themes
            
        except ImportError:
            log.warning("qt_material not available, using fallback theme list")
            return self._get_fallback_themes()
        except Exception as e:
            log.warning(f"Error detecting qt_material themes: {e}, using fallback")
            return self._get_fallback_themes()
    
    def _get_custom_themes(self) -> list[str]:
        """Get custom themes from user directory.
        
        Returns:
            list[str]: List of custom theme names
        """
        custom_themes = []
        
        try:
            if not CUSTOM_THEMES_DIR.exists():
                # Create custom themes directory if it doesn't exist
                CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)
                log.info(f"Created custom themes directory: {CUSTOM_THEMES_DIR}")
                return custom_themes
            
            # Scan for .xml files in custom themes directory
            for theme_file in CUSTOM_THEMES_DIR.glob("*.xml"):
                if self._validate_custom_theme(theme_file):
                    custom_themes.append(theme_file.name)
                    log.debug(f"Found valid custom theme: {theme_file.name}")
                else:
                    log.warning(f"Invalid custom theme file: {theme_file.name}")
            
            if custom_themes:
                log.info(f"Detected {len(custom_themes)} custom themes")
            
        except Exception as e:
            log.exception(f"Error scanning custom themes: {e}")
        
        return custom_themes
    
    def _validate_custom_theme(self, theme_file: Path) -> bool:
        """Validate a custom theme file.
        
        Args:
            theme_file: Path to theme file
            
        Returns:
            bool: True if valid
        """
        try:
            # Basic validation - check if it's a valid XML file
            if not theme_file.is_file():
                log.info(f"Theme file does not exist: {theme_file}")
                return False
            
            if theme_file.suffix.lower() != '.xml':
                log.info(f"Theme file is not .xml: {theme_file}")
                return False
            
            # Try to read and parse as XML (basic validation)
            import xml.etree.ElementTree as ET
            with open(theme_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if file has content
            if not content.strip():
                log.info(f"Theme file is empty: {theme_file}")
                return False
            
            # Attempt to parse XML
            root = ET.fromstring(content)
            log.info(f"Successfully parsed XML for {theme_file}, root element: {root.tag}")
            
            # Check if it's a qt_material format theme (resources element) or our old format (theme element)
            if root.tag not in ['resources', 'theme']:
                log.info(f"Invalid root element {root.tag}, expected 'resources' or 'theme'")
                return False
            
            # Additional validation could be added here
            # (e.g., check for required color elements in qt_material format)
            
            return True
            
        except Exception as e:
            log.info(f"Custom theme validation failed for {theme_file}: {e}")
            log.info(f"Theme file content preview: {content[:200] if 'content' in locals() else 'Could not read content'}")
            return False
    
    def _get_fallback_themes(self) -> list[str]:
        """Return fallback theme list if qt_material detection fails.
        
        Returns:
            list[str]: Fallback theme list
        """
        return [
            "dark_purple.xml", "dark_amber.xml", "dark_blue.xml", "dark_cyan.xml",
            "dark_lightgreen.xml", "dark_pink.xml", "dark_red.xml", "dark_teal.xml",
            "dark_yellow.xml", "light_amber.xml", "light_blue.xml", "light_cyan.xml",
            "light_lightgreen.xml", "light_pink.xml", "light_purple.xml",
            "light_red.xml", "light_teal.xml", "light_yellow.xml"
        ]
    
    def get_qt_material_theme(self) -> str:
        """Return the current qt_material theme."""
        return self._qt_material_theme
    
    def get_popup_theme(self) -> str:
        """Return the current popup theme.""" 
        return self._popup_theme
        
    def set_qt_material_theme(self, theme_name: str, save: bool = True, apply_to_ui: bool = True) -> bool:
        """Set the qt_material theme.
        
        Args:
            theme_name: qt_material theme name
            save: If True, save to configuration
            apply_to_ui: If True, apply theme to UI (avoid for UI-initiated changes)
            
        Returns:
            bool: True if successful
        """
        if theme_name not in self.AVAILABLE_QT_THEMES:
            log.error(f"Unknown qt_material theme: {theme_name}")
            return False
            
        try:
            old_theme = self._qt_material_theme
            self._qt_material_theme = theme_name
            
            # Auto-sync popup theme based on mapping
            auto_popup_theme = self.QT_TO_POPUP_MAPPING.get(theme_name, "material_dark")
            self._popup_theme = auto_popup_theme
            
            # Apply theme to application (only if not called from UI)
            if apply_to_ui and self._main_window and hasattr(self._main_window, 'change_theme'):
                try:
                    self._main_window.change_theme(theme_name)
                    log.info(f"Called main_window.change_theme({theme_name})")
                except Exception as e:
                    log.warning(f"Error calling main_window.change_theme: {e}")
                    # Fallback to direct application
                    self._apply_theme_to_application(theme_name)
                
            # Save if requested
            if save:
                self._save_themes()
                
            log.info(f"Theme changed: {old_theme} -> {theme_name} (popup: {auto_popup_theme})")
            return True
            
        except Exception as e:
            log.exception(f"Error setting qt_material theme: {e}")
            return False
    
    def set_popup_theme(self, theme_name: str, save: bool = True) -> bool:
        """Set the popup theme only.
        
        Args:
            theme_name: Popup theme name
            save: If True, save to configuration
            
        Returns:
            bool: True if successful
        """
        if theme_name not in ["material_dark", "material_light", "classic"]:
            log.error(f"Unknown popup theme: {theme_name}")
            return False
            
        try:
            old_theme = self._popup_theme
            self._popup_theme = theme_name
            
            # Save if requested
            if save:
                self._save_themes()
                
            log.info(f"Popup theme changed: {old_theme} -> {theme_name}")
            return True
            
        except Exception as e:
            log.exception(f"Error setting popup theme: {e}")
            return False
    
    def set_global_theme(self, qt_theme: str, popup_theme: Optional[str] = None, apply_to_ui: bool = True) -> bool:
        """Set a global theme (qt_material + popup).
        
        Args:
            qt_theme: qt_material theme
            popup_theme: Popup theme (optional, auto-determined if None)
            apply_to_ui: If True, apply theme to UI
            
        Returns:
            bool: True if successful
        """
        if popup_theme is None:
            popup_theme = self.QT_TO_POPUP_MAPPING.get(qt_theme, "material_dark")
            
        # Apply both themes without saving individually
        qt_success = self.set_qt_material_theme(qt_theme, save=False, apply_to_ui=apply_to_ui)
        popup_success = self.set_popup_theme(popup_theme, save=False)
        
        if qt_success and popup_success:
            # Save only once
            self._save_themes()
            return True
            
        return False
    
    def _save_themes(self):
        """Save themes to configuration."""
        if not self._config:
            log.warning("No config available for saving themes")
            return
            
        try:
            # Save to general configuration dictionary
            if not hasattr(self._config, 'general'):
                self._config.general = {}
                
            self._config.general['qt_material_theme'] = self._qt_material_theme
            self._config.general['popup_theme'] = self._popup_theme
            
            # Update XML DOM structure for persistence
            if hasattr(self._config, 'doc') and self._config.doc:
                self._update_xml_theme_attributes()
            
            # Save configuration file
            if hasattr(self._config, 'save'):
                self._config.save()
                log.info("Themes saved to configuration")
            else:
                log.warning("Config.save() method not available")
                
        except Exception as e:
            log.exception(f"Error saving themes: {e}")
    
    def _update_xml_theme_attributes(self):
        """Update XML DOM with theme attributes."""
        try:
            # Find the general element in the XML DOM
            general_nodes = self._config.doc.getElementsByTagName("general")
            
            if general_nodes:
                general_node = general_nodes[0]
                # Set theme attributes in XML DOM
                general_node.setAttribute("qt_material_theme", self._qt_material_theme)
                general_node.setAttribute("popup_theme", self._popup_theme)
                log.debug(f"Updated XML general node with themes: qt={self._qt_material_theme}, popup={self._popup_theme}")
            else:
                log.warning("No general element found in XML DOM")
                
        except Exception as e:
            log.exception(f"Error updating XML theme attributes: {e}")
    
    def get_available_qt_themes(self) -> list[str]:
        """Return the list of available qt_material themes."""
        return self.AVAILABLE_QT_THEMES.copy()
    
    def get_available_popup_themes(self) -> list[str]:
        """Return the list of available popup themes."""
        return ["material_dark", "material_light", "classic"]
    
    def reset_to_defaults(self) -> bool:
        """Reset to default themes.
        
        Returns:
            bool: True if successful
        """
        return self.set_global_theme("dark_purple.xml", "material_dark")
    
    def install_custom_theme(self, theme_file_path: str, theme_name: Optional[str] = None) -> bool:
        """Install a custom theme from file.
        
        Args:
            theme_file_path: Path to the theme file to install
            theme_name: Optional custom name (defaults to filename)
            
        Returns:
            bool: True if successfully installed
        """
        try:
            source_path = Path(theme_file_path)
            
            if not source_path.exists():
                log.error(f"Theme file not found: {theme_file_path}")
                return False
            
            # Validate the theme file
            if not self._validate_custom_theme(source_path):
                log.error(f"Invalid theme file: {theme_file_path}")
                return False
            
            # Determine destination filename
            if theme_name:
                if not theme_name.endswith('.xml'):
                    theme_name += '.xml'
                dest_filename = theme_name
            else:
                dest_filename = source_path.name
            
            # Ensure custom themes directory exists
            CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)
            
            # Copy theme file to custom themes directory
            dest_path = CUSTOM_THEMES_DIR / dest_filename
            
            import shutil
            shutil.copy2(source_path, dest_path)
            
            # Refresh available themes list
            ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()
            
            log.info(f"Custom theme installed: {dest_filename}")
            return True
            
        except Exception as e:
            log.exception(f"Error installing custom theme: {e}")
            return False
    
    def remove_custom_theme(self, theme_name: str) -> bool:
        """Remove a custom theme.
        
        Args:
            theme_name: Name of the custom theme to remove
            
        Returns:
            bool: True if successfully removed
        """
        try:
            theme_path = CUSTOM_THEMES_DIR / theme_name
            
            if not theme_path.exists():
                log.error(f"Custom theme not found: {theme_name}")
                return False
            
            # Don't allow removing if it's the current theme
            if self._qt_material_theme == theme_name:
                log.error(f"Cannot remove currently active theme: {theme_name}")
                return False
            
            # Remove the file
            theme_path.unlink()
            
            # Refresh available themes list
            ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()
            
            log.info(f"Custom theme removed: {theme_name}")
            return True
            
        except Exception as e:
            log.exception(f"Error removing custom theme: {e}")
            return False
    
    def list_custom_themes(self) -> list[str]:
        """List all installed custom themes.
        
        Returns:
            list[str]: List of custom theme names
        """
        return self._get_custom_themes()
    
    def is_custom_theme(self, theme_name: str) -> bool:
        """Check if a theme is a custom theme.
        
        Args:
            theme_name: Theme name to check
            
        Returns:
            bool: True if it's a custom theme
        """
        return theme_name in self._get_custom_themes()
    
    def get_custom_themes_directory(self) -> Path:
        """Get the custom themes directory path.
        
        Returns:
            Path: Path to custom themes directory
        """
        return CUSTOM_THEMES_DIR
    
    def _apply_theme_to_application(self, theme_name: str) -> bool:
        """Apply theme to the application, handling both built-in and custom themes.
        
        Args:
            theme_name: Theme name to apply
            
        Returns:
            bool: True if successfully applied
        """
        try:
            from PyQt5.QtWidgets import QApplication
            
            if self.is_custom_theme(theme_name):
                # For custom themes, copy to qt_material directory temporarily and use qt_material
                theme_path = CUSTOM_THEMES_DIR / theme_name
                
                app = QApplication.instance()
                if not app:
                    log.warning("No QApplication instance found")
                    return False
                
                try:
                    import qt_material
                    import tempfile
                    import shutil
                    
                    # Get qt_material themes directory
                    qt_material_themes_dir = Path(qt_material.__file__).parent / "themes"
                    
                    # Create a temporary copy in qt_material themes directory
                    temp_theme_path = qt_material_themes_dir / theme_name
                    
                    # Copy our custom theme to qt_material directory
                    shutil.copy2(theme_path, temp_theme_path)
                    
                    try:
                        # Now apply using qt_material
                        qt_material.apply_stylesheet(app, theme=theme_name)
                        log.info(f"Applied custom theme via qt_material: {theme_name}")
                    finally:
                        # Clean up - remove the temporary file
                        if temp_theme_path.exists():
                            temp_theme_path.unlink()
                            
                except Exception as e:
                    log.error(f"Error applying custom theme {theme_name}: {e}")
                    return False
            else:
                # For built-in themes, use qt_material directly
                app = QApplication.instance()
                if not app:
                    log.warning("No QApplication instance found")
                    return False
                
                try:
                    import qt_material
                    qt_material.apply_stylesheet(app, theme=theme_name)
                    log.info(f"Applied built-in theme: {theme_name}")
                except Exception as e:
                    log.error(f"Error applying built-in theme {theme_name}: {e}")
                    return False
            
            return True
            
        except Exception as e:
            log.exception(f"Error applying theme to application: {e}")
            return False