#!/usr/bin/env python

"""test_theme_config_integration.py

Integration tests for theme functionality with ConfigurationManager and ConfigObservers.
Tests the complete configuration change workflow for themes.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys

# Add the parent directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ConfigurationManager import ConfigurationManager, ConfigChange, ChangeType
from ConfigObservers import GuiPrefsObserver
from ThemeManager import ThemeManager


class TestThemeConfigIntegration(unittest.TestCase):
    """Integration tests for theme configuration management."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset singletons
        if hasattr(ConfigurationManager, '_instance'):
            ConfigurationManager._instance = None
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
        
        # Create mock config
        self.mock_config = Mock()
        self.mock_config.general = {
            'qt_material_theme': 'dark_purple.xml',
            'popup_theme': 'material_dark'
        }
        self.mock_config.save = Mock()
        # Mock supported_sites to avoid iteration errors
        self.mock_config.supported_sites = {}
        # Mock methods that might be called during state capture
        self.mock_config.get_import_parameters = Mock(return_value={'importFilters': []})
        self.mock_config.get_hud_ui_parameters = Mock(return_value={})
        
        # Create mock main window
        self.mock_main_window = Mock()
        self.mock_main_window.change_theme = Mock()
        
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(ConfigurationManager, '_instance'):
            ConfigurationManager._instance = None
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
    
    def test_gui_prefs_observer_qt_material_theme_change(self):
        """Test GuiPrefsObserver handling qt_material theme changes."""
        observer = GuiPrefsObserver(self.mock_main_window)
        
        # Create a theme change
        change = ConfigChange(
            ChangeType.THEME_SETTINGS,
            "general.qt_material_theme",
            "dark_purple.xml",
            "light_blue.xml"
        )
        
        with patch('ThemeManager.ThemeManager') as mock_theme_manager_class:
            mock_theme_manager = Mock()
            mock_theme_manager.set_qt_material_theme.return_value = True
            mock_theme_manager_class.return_value = mock_theme_manager
            
            result = observer._update_theme(change)
            
            self.assertTrue(result, "Theme update should succeed")
            mock_theme_manager.set_qt_material_theme.assert_called_once_with("light_blue.xml", save=True)
    
    def test_gui_prefs_observer_popup_theme_change(self):
        """Test GuiPrefsObserver handling popup theme changes."""
        observer = GuiPrefsObserver(self.mock_main_window)
        
        # Create a popup theme change
        change = ConfigChange(
            ChangeType.THEME_SETTINGS,
            "general.popup_theme",
            "material_dark",
            "classic"
        )
        
        with patch('ThemeManager.ThemeManager') as mock_theme_manager_class:
            mock_theme_manager = Mock()
            mock_theme_manager.set_popup_theme.return_value = True
            mock_theme_manager_class.return_value = mock_theme_manager
            
            result = observer._update_theme(change)
            
            self.assertTrue(result, "Popup theme update should succeed")
            mock_theme_manager.set_popup_theme.assert_called_once_with("classic", save=True)
    
    def test_gui_prefs_observer_legacy_theme_change(self):
        """Test GuiPrefsObserver fallback to legacy theme handling."""
        observer = GuiPrefsObserver(self.mock_main_window)
        
        # Create a legacy theme change (not specific qt_material or popup)
        change = ConfigChange(
            ChangeType.THEME_SETTINGS,
            "legacy.theme",
            "old_theme",
            "new_theme"
        )
        
        result = observer._update_theme(change)
        
        self.assertTrue(result, "Legacy theme update should succeed")
        self.mock_main_window.change_theme.assert_called_once_with("new_theme")
    
    def test_gui_prefs_observer_theme_change_error_handling(self):
        """Test GuiPrefsObserver error handling during theme changes."""
        observer = GuiPrefsObserver(self.mock_main_window)
        
        change = ConfigChange(
            ChangeType.THEME_SETTINGS,
            "general.qt_material_theme",
            "dark_purple.xml",
            "light_blue.xml"
        )
        
        with patch('ThemeManager.ThemeManager') as mock_theme_manager_class:
            # Simulate ThemeManager throwing an exception
            mock_theme_manager_class.side_effect = Exception("Theme manager error")
            
            result = observer._update_theme(change)
            
            self.assertFalse(result, "Theme update should fail gracefully")
    
    def test_configuration_manager_theme_change_detection(self):
        """Test ConfigurationManager detecting theme changes."""
        config_manager = ConfigurationManager()
        config_manager.initialize()
        config_manager._config = self.mock_config
        
        # Capture initial state
        config_manager._capture_current_state()
        
        # Simulate theme change in config
        new_config = Mock()
        new_config.general = {
            'qt_material_theme': 'light_amber.xml',  # Changed
            'popup_theme': 'material_light'  # Changed
        }
        new_config.supported_sites = {}
        
        # Detect changes
        changes = config_manager.detect_changes_from_saved_state(new_config)
        
        # Should detect both theme changes
        theme_changes = [c for c in changes if c.type == ChangeType.THEME_SETTINGS]
        self.assertEqual(len(theme_changes), 2, "Should detect both theme changes")
        
        # Verify specific changes
        qt_theme_change = next((c for c in theme_changes if c.path == "general.qt_material_theme"), None)
        popup_theme_change = next((c for c in theme_changes if c.path == "general.popup_theme"), None)
        
        self.assertIsNotNone(qt_theme_change, "Should detect qt_material theme change")
        self.assertIsNotNone(popup_theme_change, "Should detect popup theme change")
        
        self.assertEqual(qt_theme_change.old_value, "dark_purple.xml")
        self.assertEqual(qt_theme_change.new_value, "light_amber.xml")
        
        self.assertEqual(popup_theme_change.old_value, "material_dark")
        self.assertEqual(popup_theme_change.new_value, "material_light")
    
    def test_configuration_manager_no_theme_changes(self):
        """Test ConfigurationManager when no theme changes occur."""
        config_manager = ConfigurationManager()
        config_manager.initialize()
        config_manager._config = self.mock_config
        
        # Capture initial state
        config_manager._capture_current_state()
        
        # Simulate no changes in config
        new_config = Mock()
        new_config.general = {
            'qt_material_theme': 'dark_purple.xml',  # Same
            'popup_theme': 'material_dark'  # Same
        }
        new_config.supported_sites = {}
        
        # Detect changes
        changes = config_manager.detect_changes_from_saved_state(new_config)
        
        # Should detect no theme changes
        theme_changes = [c for c in changes if c.type == ChangeType.THEME_SETTINGS]
        self.assertEqual(len(theme_changes), 0, "Should detect no theme changes")
    
    def test_configuration_manager_theme_paths_are_dynamic(self):
        """Test that theme paths are marked as dynamic changes."""
        # Verify theme paths are in DYNAMIC_CHANGE_PATHS
        self.assertIn("general.qt_material_theme", ConfigurationManager.DYNAMIC_CHANGE_PATHS)
        self.assertIn("general.popup_theme", ConfigurationManager.DYNAMIC_CHANGE_PATHS)
        
        # Verify they are not in RESTART_REQUIRED_PATHS
        for path in ConfigurationManager.RESTART_REQUIRED_PATHS:
            self.assertNotEqual("general.qt_material_theme", path)
            self.assertNotEqual("general.popup_theme", path)
    
    def test_end_to_end_theme_change_workflow(self):
        """Test complete end-to-end theme change workflow."""
        # This test simulates a complete workflow:
        # 1. ConfigurationManager detects theme change
        # 2. Notifies GuiPrefsObserver
        # 3. Observer uses ThemeManager to apply change
        # 4. ThemeManager updates main window and saves config
        
        # Setup
        config_manager = ConfigurationManager()
        config_manager.initialize()
        config_manager._config = self.mock_config
        
        observer = GuiPrefsObserver(self.mock_main_window)
        config_manager.register_observer(observer)
        
        # Step 1: Capture initial state
        config_manager._capture_current_state()
        
        # Step 2: Simulate config change
        new_config = Mock()
        new_config.general = {
            'qt_material_theme': 'light_cyan.xml',
            'popup_theme': 'material_light'
        }
        new_config.supported_sites = {}
        
        # Step 3: Detect changes
        changes = config_manager.detect_changes_from_saved_state(new_config)
        theme_changes = [c for c in changes if c.type == ChangeType.THEME_SETTINGS]
        
        # Step 4: Apply changes through observer
        with patch('ThemeManager.ThemeManager') as mock_theme_manager_class:
            mock_theme_manager = Mock()
            mock_theme_manager.set_qt_material_theme.return_value = True
            mock_theme_manager.set_popup_theme.return_value = True
            mock_theme_manager_class.return_value = mock_theme_manager
            
            # Apply each theme change
            all_success = True
            for change in theme_changes:
                success = observer.on_config_change(change)
                all_success = all_success and success
            
            self.assertTrue(all_success, "All theme changes should be applied successfully")
            
            # Verify ThemeManager methods were called
            self.assertTrue(
                mock_theme_manager.set_qt_material_theme.called or mock_theme_manager.set_popup_theme.called,
                "ThemeManager methods should be called"
            )


class TestThemeConfigErrorHandling(unittest.TestCase):
    """Test error handling in theme configuration integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset singletons
        if hasattr(ConfigurationManager, '_instance'):
            ConfigurationManager._instance = None
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(ConfigurationManager, '_instance'):
            ConfigurationManager._instance = None
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
    
    def test_configuration_manager_missing_general_section(self):
        """Test ConfigurationManager handling missing general section."""
        config_manager = ConfigurationManager()
        config_manager.initialize()
        
        # Create config without general section
        mock_config = Mock()
        mock_config.supported_sites = {}
        mock_config.get_import_parameters = Mock(return_value={'importFilters': []})
        mock_config.get_hud_ui_parameters = Mock(return_value={})
        # Remove general attribute
        if hasattr(mock_config, 'general'):
            del mock_config.general
        config_manager._config = mock_config
        
        # This should not crash
        config_manager._capture_current_state()
        
        # Detect changes with missing general section
        new_config = Mock()
        new_config.general = {'qt_material_theme': 'dark_blue.xml'}
        new_config.supported_sites = {}
        
        changes = config_manager.detect_changes_from_saved_state(new_config)
        
        # Should handle gracefully
        self.assertIsInstance(changes, list, "Should return list even with missing general section")
    
    def test_gui_prefs_observer_import_error(self):
        """Test GuiPrefsObserver handling ThemeManager import errors."""
        observer = GuiPrefsObserver(Mock())
        
        change = ConfigChange(
            ChangeType.THEME_SETTINGS,
            "general.qt_material_theme",
            "dark_purple.xml",
            "light_blue.xml"
        )
        
        with patch('ThemeManager.ThemeManager', side_effect=ImportError("Module not found")):
            result = observer._update_theme(change)
            
            self.assertFalse(result, "Should fail gracefully on import error")


if __name__ == '__main__':
    unittest.main()