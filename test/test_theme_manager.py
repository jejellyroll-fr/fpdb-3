#!/usr/bin/env python

"""test_theme_manager.py

Unit tests for the ThemeManager class.
Tests theme persistence, synchronization, and configuration integration.
"""

import os

# Add the parent directory to the path to import our modules
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ThemeManager import ThemeManager


class TestThemeManager(unittest.TestCase):
    """Test cases for ThemeManager functionality."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Reset singleton instance for clean tests
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None
        # Reset class variable for clean tests
        ThemeManager.AVAILABLE_QT_THEMES = None

        # Create mock config
        self.mock_config = Mock()
        self.mock_config.general = {"qt_material_theme": "dark_purple.xml", "popup_theme": "material_dark"}
        self.mock_config.save = Mock()
        # Mock XML DOM structure
        self.mock_doc = Mock()
        self.mock_general_node = Mock()
        self.mock_doc.getElementsByTagName = Mock(return_value=[self.mock_general_node])
        self.mock_config.doc = self.mock_doc

        # Create mock main window
        self.mock_main_window = Mock()
        self.mock_main_window.change_theme = Mock()

        # Create ThemeManager instance
        self.theme_manager = ThemeManager()

    def tearDown(self):
        """Clean up after each test method."""
        # Reset singleton
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None
        # Reset class variable
        ThemeManager.AVAILABLE_QT_THEMES = None

    def test_singleton_pattern(self):
        """Test that ThemeManager implements singleton pattern correctly."""
        manager1 = ThemeManager()
        manager2 = ThemeManager()

        self.assertIs(manager1, manager2, "ThemeManager should be a singleton")

    def test_initialization(self):
        """Test ThemeManager initialization."""
        self.theme_manager.initialize(config=self.mock_config, main_window=self.mock_main_window)

        self.assertTrue(self.theme_manager.initialized, "ThemeManager should be initialized")
        self.assertEqual(self.theme_manager._config, self.mock_config)
        self.assertEqual(self.theme_manager._main_window, self.mock_main_window)

    def test_load_saved_themes(self):
        """Test loading saved themes from configuration."""
        # Test with valid saved themes
        self.mock_config.general = {"qt_material_theme": "light_blue.xml", "popup_theme": "material_light"}

        self.theme_manager.initialize(config=self.mock_config)

        self.assertEqual(self.theme_manager.get_qt_material_theme(), "light_blue.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_light")

    def test_load_invalid_themes_fallback(self):
        """Test fallback to defaults when invalid themes are saved."""
        # Test with invalid saved themes
        self.mock_config.general = {"qt_material_theme": "invalid_theme.xml", "popup_theme": "invalid_popup"}

        self.theme_manager.initialize(config=self.mock_config)

        # Should fallback to defaults
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "dark_purple.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_dark")

    def test_set_qt_material_theme_valid(self):
        """Test setting a valid qt_material theme."""
        self.theme_manager.initialize(config=self.mock_config, main_window=self.mock_main_window)

        result = self.theme_manager.set_qt_material_theme("light_amber.xml")

        self.assertTrue(result, "Setting valid theme should succeed")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "light_amber.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_light")  # Auto-synced

        # Verify main window theme was changed
        self.mock_main_window.change_theme.assert_called_once_with("light_amber.xml")

        # Verify config was saved
        self.mock_config.save.assert_called_once()

    def test_set_qt_material_theme_invalid(self):
        """Test setting an invalid qt_material theme."""
        self.theme_manager.initialize(config=self.mock_config)

        result = self.theme_manager.set_qt_material_theme("invalid_theme.xml")

        self.assertFalse(result, "Setting invalid theme should fail")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "dark_purple.xml")  # Should remain unchanged

    def test_set_popup_theme_valid(self):
        """Test setting a valid popup theme."""
        self.theme_manager.initialize(config=self.mock_config)

        result = self.theme_manager.set_popup_theme("classic")

        self.assertTrue(result, "Setting valid popup theme should succeed")
        self.assertEqual(self.theme_manager.get_popup_theme(), "classic")

        # Verify config was saved
        self.mock_config.save.assert_called_once()

    def test_set_popup_theme_invalid(self):
        """Test setting an invalid popup theme."""
        self.theme_manager.initialize(config=self.mock_config)

        result = self.theme_manager.set_popup_theme("invalid_popup")

        self.assertFalse(result, "Setting invalid popup theme should fail")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_dark")  # Should remain unchanged

    def test_set_global_theme(self):
        """Test setting a global theme (both qt_material and popup)."""
        self.theme_manager.initialize(config=self.mock_config, main_window=self.mock_main_window)

        result = self.theme_manager.set_global_theme("light_cyan.xml", "classic")

        self.assertTrue(result, "Setting global theme should succeed")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "light_cyan.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "classic")

        # Verify main window theme was changed
        self.mock_main_window.change_theme.assert_called_once_with("light_cyan.xml")

        # Verify config was saved only once (not twice)
        self.mock_config.save.assert_called_once()

    def test_set_global_theme_auto_popup(self):
        """Test setting global theme with auto-determined popup theme."""
        self.theme_manager.initialize(config=self.mock_config, main_window=self.mock_main_window)

        result = self.theme_manager.set_global_theme("dark_red.xml")  # No popup theme specified

        self.assertTrue(result, "Setting global theme with auto popup should succeed")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "dark_red.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_dark")  # Auto-determined

    def test_qt_to_popup_mapping(self):
        """Test the qt_material to popup theme mapping."""
        # Test dark themes map to material_dark
        dark_themes = ["dark_purple.xml", "dark_amber.xml", "dark_blue.xml"]
        for theme in dark_themes:
            mapped = ThemeManager.QT_TO_POPUP_MAPPING.get(theme)
            self.assertEqual(mapped, "material_dark", f"{theme} should map to material_dark")

        # Test light themes map to material_light
        light_themes = ["light_amber.xml", "light_blue.xml", "light_cyan.xml"]
        for theme in light_themes:
            mapped = ThemeManager.QT_TO_POPUP_MAPPING.get(theme)
            self.assertEqual(mapped, "material_light", f"{theme} should map to material_light")

    def test_get_available_themes(self):
        """Test getting available theme lists."""
        qt_themes = self.theme_manager.get_available_qt_themes()
        popup_themes = self.theme_manager.get_available_popup_themes()

        self.assertIsInstance(qt_themes, list, "Qt themes should be a list")
        self.assertIsInstance(popup_themes, list, "Popup themes should be a list")

        self.assertIn("dark_purple.xml", qt_themes, "Should include default qt theme")
        self.assertIn("material_dark", popup_themes, "Should include default popup theme")

        # Verify they are copies (not references to original lists)
        qt_themes.append("test_theme")
        qt_themes_2 = self.theme_manager.get_available_qt_themes()
        self.assertNotIn("test_theme", qt_themes_2, "Should return copies, not references")

    def test_reset_to_defaults(self):
        """Test resetting themes to defaults."""
        self.theme_manager.initialize(config=self.mock_config, main_window=self.mock_main_window)

        # Change to non-default themes first
        self.theme_manager.set_global_theme("light_pink.xml", "classic")

        # Reset to defaults
        result = self.theme_manager.reset_to_defaults()

        self.assertTrue(result, "Reset to defaults should succeed")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "dark_purple.xml")
        self.assertEqual(self.theme_manager.get_popup_theme(), "material_dark")

    def test_save_themes_no_config(self):
        """Test saving themes when no config is available."""
        # Initialize without config
        self.theme_manager.initialize()

        # This should not crash, just log a warning
        result = self.theme_manager.set_qt_material_theme("light_blue.xml")

        # Should still succeed in setting the theme, just not save it
        self.assertTrue(result, "Setting theme should succeed even without config")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "light_blue.xml")

    def test_save_themes_config_without_save_method(self):
        """Test saving themes when config doesn't have save method."""
        mock_config_no_save = Mock()
        mock_config_no_save.general = {}
        # Remove save method
        del mock_config_no_save.save

        self.theme_manager.initialize(config=mock_config_no_save)

        # This should not crash, just log a warning
        result = self.theme_manager.set_qt_material_theme("light_blue.xml")

        self.assertTrue(result, "Setting theme should succeed even without save method")

    def test_xml_dom_update(self):
        """Test that XML DOM is updated with theme attributes."""
        # Create mock config with XML DOM
        mock_config = Mock()
        mock_config.general = {}
        mock_config.save = Mock()

        # Create mock XML DOM
        mock_doc = Mock()
        mock_general_node = Mock()
        mock_doc.getElementsByTagName.return_value = [mock_general_node]
        mock_config.doc = mock_doc

        self.theme_manager.initialize(config=mock_config)

        # Set theme
        result = self.theme_manager.set_qt_material_theme("light_cyan.xml")

        self.assertTrue(result, "Setting theme should succeed")

        # Verify XML DOM was updated
        mock_doc.getElementsByTagName.assert_called_with("general")
        mock_general_node.setAttribute.assert_any_call("qt_material_theme", "light_cyan.xml")
        mock_general_node.setAttribute.assert_any_call("popup_theme", "material_light")

    def test_xml_dom_no_general_element(self):
        """Test handling when no general element exists in XML DOM."""
        # Create mock config with XML DOM but no general element
        mock_config = Mock()
        mock_config.general = {}
        mock_config.save = Mock()

        # Create mock XML DOM with no general elements
        mock_doc = Mock()
        mock_doc.getElementsByTagName.return_value = []  # No general elements
        mock_config.doc = mock_doc

        self.theme_manager.initialize(config=mock_config)

        # This should not crash, just log a warning
        result = self.theme_manager.set_qt_material_theme("dark_amber.xml")

        self.assertTrue(result, "Setting theme should succeed even with no general XML element")

    def test_ui_theme_change_no_recursion(self):
        """Test that UI-initiated theme changes don't cause recursion."""
        # Create mock config
        mock_config = Mock()
        mock_config.general = {}
        mock_config.save = Mock()

        # Create mock main window with change_theme method
        mock_main_window = Mock()
        call_count = 0

        def mock_change_theme(theme):
            nonlocal call_count
            call_count += 1
            # Simulate what the real change_theme does - call ThemeManager with apply_to_ui=False
            self.theme_manager.set_qt_material_theme(theme, save=True, apply_to_ui=False)

        mock_main_window.change_theme = mock_change_theme

        self.theme_manager.initialize(config=mock_config, main_window=mock_main_window)

        # This simulates a programmatic theme change (should call UI)
        result = self.theme_manager.set_qt_material_theme("light_cyan.xml", apply_to_ui=True)

        self.assertTrue(result, "Theme change should succeed")
        self.assertEqual(call_count, 1, "change_theme should be called exactly once (no recursion)")
        self.assertEqual(self.theme_manager.get_qt_material_theme(), "light_cyan.xml")

    def test_apply_to_ui_parameter(self):
        """Test the apply_to_ui parameter works correctly."""
        # Create mock config and main window
        mock_config = Mock()
        mock_config.general = {}
        mock_config.save = Mock()

        mock_main_window = Mock()
        self.theme_manager.initialize(config=mock_config, main_window=mock_main_window)

        # Test with apply_to_ui=True (default)
        result = self.theme_manager.set_qt_material_theme("dark_red.xml", apply_to_ui=True)
        self.assertTrue(result)
        mock_main_window.change_theme.assert_called_once_with("dark_red.xml")

        # Reset mock
        mock_main_window.reset_mock()

        # Test with apply_to_ui=False
        result = self.theme_manager.set_qt_material_theme("light_pink.xml", apply_to_ui=False)
        self.assertTrue(result)
        mock_main_window.change_theme.assert_not_called()


class TestThemeManagerIntegration(unittest.TestCase):
    """Integration tests for ThemeManager with other components."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None

    @patch("ThemeManager.log")
    def test_theme_manager_logging(self, mock_log):
        """Test that ThemeManager logs appropriately."""
        theme_manager = ThemeManager()
        mock_config = Mock()
        mock_config.general = {"qt_material_theme": "dark_blue.xml", "popup_theme": "material_dark"}

        theme_manager.initialize(config=mock_config)

        # Verify initialization was logged
        mock_log.info.assert_called_with("ThemeManager initialized")

    def test_theme_persistence_workflow(self):
        """Test the complete workflow of theme persistence."""
        # This test simulates the complete workflow:
        # 1. Load saved theme
        # 2. Change theme
        # 3. Save theme
        # 4. Reload and verify persistence

        theme_manager = ThemeManager()

        # Step 1: Initialize with saved theme
        mock_config = Mock()
        mock_config.general = {"qt_material_theme": "light_purple.xml", "popup_theme": "material_light"}
        mock_config.save = Mock()

        theme_manager.initialize(config=mock_config)

        # Verify loaded theme
        self.assertEqual(theme_manager.get_qt_material_theme(), "light_purple.xml")
        self.assertEqual(theme_manager.get_popup_theme(), "material_light")

        # Step 2: Change theme
        theme_manager.set_global_theme("dark_teal.xml")

        # Step 3: Verify save was called
        mock_config.save.assert_called()

        # Step 4: Verify config was updated
        self.assertEqual(mock_config.general["qt_material_theme"], "dark_teal.xml")
        self.assertEqual(mock_config.general["popup_theme"], "material_dark")


if __name__ == "__main__":
    unittest.main()
