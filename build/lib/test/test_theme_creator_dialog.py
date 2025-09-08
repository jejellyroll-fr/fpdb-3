#!/usr/bin/env python

"""test_theme_creator_dialog.py

Unit tests for the ThemeCreatorDialog.
Tests the UI components and theme creation functionality.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Only run GUI tests if we're in a GUI environment
try:
    from PyQt5.QtWidgets import QApplication

    # Try to create a QApplication to test if GUI is available
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    GUI_AVAILABLE = True

except Exception:
    GUI_AVAILABLE = False
    print("Skipping GUI tests - no display available")


@unittest.skipUnless(GUI_AVAILABLE, "GUI not available")
class TestThemeCreatorDialog(unittest.TestCase):
    """Test cases for ThemeCreatorDialog."""

    @classmethod
    def setUpClass(cls):
        """Setup QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        from ThemeCreatorDialog import ThemeCreatorDialog

        self.dialog = ThemeCreatorDialog()

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, "dialog"):
            self.dialog.close()

    def test_dialog_initialization(self):
        """Test that dialog initializes correctly."""
        self.assertEqual(self.dialog.windowTitle(), "Create Custom Theme")
        self.assertTrue(self.dialog.isModal())

        # Check that all required widgets are present
        self.assertIsNotNone(self.dialog.name_input)
        self.assertIsNotNone(self.dialog.description_input)
        self.assertIsNotNone(self.dialog.author_input)
        self.assertIsNotNone(self.dialog.preset_combo)
        self.assertIsNotNone(self.dialog.preview_text)
        self.assertIsNotNone(self.dialog.create_button)
        self.assertIsNotNone(self.dialog.cancel_button)

    def test_color_pickers_exist(self):
        """Test that all color pickers are created."""
        expected_pickers = ["primary", "secondary", "background", "surface", "text", "text_secondary"]

        for picker_name in expected_pickers:
            self.assertIn(picker_name, self.dialog.color_pickers)
            picker = self.dialog.color_pickers[picker_name]
            self.assertIsNotNone(picker)

    def test_preset_loading(self):
        """Test loading different presets."""
        # Test Dark preset (Qt normalizes colors to lowercase)
        self.dialog.load_preset("Dark")
        self.assertEqual(self.dialog.color_pickers["primary"].get_color(), "#3f51b5")
        self.assertEqual(self.dialog.color_pickers["background"].get_color(), "#2b2b2b")
        self.assertEqual(self.dialog.color_pickers["text"].get_color(), "#ffffff")

        # Test Light preset
        self.dialog.load_preset("Light")
        self.assertEqual(self.dialog.color_pickers["primary"].get_color(), "#3f51b5")
        self.assertEqual(self.dialog.color_pickers["background"].get_color(), "#fafafa")
        self.assertEqual(self.dialog.color_pickers["text"].get_color(), "#212121")

    def test_color_change_updates_preview(self):
        """Test that changing colors updates the preview."""
        original_preview = self.dialog.preview_text.toPlainText()

        # Change primary color
        self.dialog.color_pickers["primary"].set_color("#FF0000")
        self.dialog.on_color_changed("primary", "#FF0000")

        # Preview should be updated (Qt normalizes to lowercase)
        updated_preview = self.dialog.preview_text.toPlainText()
        self.assertIn("#ff0000", updated_preview)

    def test_theme_xml_generation(self):
        """Test generating theme XML."""
        name = "test_theme.xml"
        description = "Test theme"
        author = "Test Author"
        colors = {
            "primary": "#FF0000",
            "secondary": "#00FF00",
            "background": "#0000FF",
            "surface": "#FFFF00",
            "text": "#FF00FF",
            "text_secondary": "#00FFFF",
        }

        xml_content = self.dialog.generate_theme_xml(name, description, author, colors)

        # Check that XML contains expected content (qt_material format)
        self.assertIn('<!--?xml version="1.0" encoding="UTF-8"?-->', xml_content)
        self.assertIn("<resources>", xml_content)
        self.assertIn('name="primaryColor"', xml_content)
        self.assertIn(description, xml_content)
        self.assertIn(author, xml_content)

        # Check that primary colors are included (may be transformed)
        self.assertIn(colors["primary"], xml_content)  # Should be in primaryColor
        # Background color should be in secondaryColor
        self.assertIn(colors["background"], xml_content)
        # Text color should be in primaryTextColor or secondaryTextColor
        self.assertIn(colors["text"], xml_content)

    def test_validation_empty_name(self):
        """Test validation with empty theme name."""
        # Clear name input
        self.dialog.name_input.setText("")

        with patch("ThemeCreatorDialog.QMessageBox.warning") as mock_warning:
            self.dialog.create_theme()
            mock_warning.assert_called_once()
            args = mock_warning.call_args[0]
            self.assertIn("Please enter a theme name", args[2])

    def test_theme_creation_validation(self):
        """Test theme creation validation and XML generation parts."""
        # Test validation - empty name should be caught before trying to create
        self.dialog.name_input.setText("")

        with patch("PyQt5.QtWidgets.QMessageBox.warning") as mock_warning:
            self.dialog.create_theme()
            mock_warning.assert_called_once()

        # Test valid input generates correct XML
        self.dialog.name_input.setText("test_theme")
        self.dialog.description_input.setText("Test Description")
        self.dialog.author_input.setText("Test Author")

        # Collect colors
        colors = {}
        for key, picker in self.dialog.color_pickers.items():
            colors[key] = picker.get_color()

        # Test XML generation
        xml_content = self.dialog.generate_theme_xml("test_theme.xml", "Test Description", "Test Author", colors)

        # Verify XML content (qt_material format)
        self.assertIn('<!--?xml version="1.0" encoding="UTF-8"?-->', xml_content)
        self.assertIn("<resources>", xml_content)
        self.assertIn('name="primaryColor"', xml_content)
        self.assertIn("Test Description", xml_content)
        self.assertIn("Test Author", xml_content)

        # Check key colors are present
        self.assertIn(colors["primary"], xml_content)
        self.assertIn(colors["background"], xml_content)
        self.assertIn(colors["text"], xml_content)


@unittest.skipUnless(GUI_AVAILABLE, "GUI not available")
class TestColorPickerWidget(unittest.TestCase):
    """Test cases for ColorPickerWidget."""

    @classmethod
    def setUpClass(cls):
        """Setup QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        from ThemeCreatorDialog import ColorPickerWidget

        self.picker = ColorPickerWidget("Test Color", "#FF0000")

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, "picker"):
            self.picker.close()

    def test_initialization(self):
        """Test widget initialization."""
        self.assertEqual(self.picker.get_color(), "#ff0000")  # Qt normalizes to lowercase
        self.assertEqual(self.picker.hex_input.text(), "#FF0000")

    def test_set_color(self):
        """Test setting color programmatically."""
        self.picker.set_color("#00FF00")
        self.assertEqual(self.picker.get_color(), "#00ff00")
        self.assertEqual(self.picker.hex_input.text(), "#00FF00")

    def test_hex_input_change(self):
        """Test changing color via hex input."""
        # Simulate user typing in hex input
        self.picker.hex_input.setText("#0000FF")
        self.picker.on_hex_changed("#0000FF")

        self.assertEqual(self.picker.get_color(), "#0000ff")

    def test_invalid_hex_input(self):
        """Test invalid hex input doesn't crash."""
        original_color = self.picker.get_color()

        # Try invalid hex codes
        self.picker.on_hex_changed("invalid")
        self.picker.on_hex_changed("#GGGGGG")
        self.picker.on_hex_changed("#FF")

        # Color should remain unchanged
        self.assertEqual(self.picker.get_color(), original_color)


@unittest.skipUnless(GUI_AVAILABLE, "GUI not available")
class TestThemeCreatorIntegration(unittest.TestCase):
    """Integration tests for theme creator."""

    @classmethod
    def setUpClass(cls):
        """Setup QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_show_theme_creator_function(self):
        """Test the show_theme_creator function."""
        from ThemeCreatorDialog import show_theme_creator

        # Test the function doesn't crash
        # We can't easily test the dialog interaction without user input
        # but we can test that it creates the dialog
        with patch("ThemeCreatorDialog.ThemeCreatorDialog") as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.exec_.return_value = 0  # Cancelled
            mock_dialog_class.return_value = mock_dialog

            result = show_theme_creator()

            mock_dialog_class.assert_called_once()
            mock_dialog.exec_.assert_called_once()
            self.assertEqual(result, 0)


if __name__ == "__main__":
    # Only run tests if GUI is available
    if GUI_AVAILABLE:
        unittest.main()
    else:
        print("Skipping all tests - GUI not available")
