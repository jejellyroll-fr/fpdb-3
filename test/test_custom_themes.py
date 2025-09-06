#!/usr/bin/env python

"""test_custom_themes.py

Unit tests for custom theme functionality in ThemeManager.
Tests custom theme installation, validation, removal, and application.
"""

import os
import shutil

# Add the parent directory to the path to import our modules
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ThemeManager import CUSTOM_THEMES_DIR, ThemeManager


class TestCustomThemes(unittest.TestCase):
    """Test cases for custom theme functionality."""

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

        # Create ThemeManager instance
        self.theme_manager = ThemeManager()
        self.theme_manager.initialize(config=self.mock_config)

        # Create temporary directory for testing
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_theme_file = self.temp_dir / "test_theme.xml"

        # Create a valid test theme file
        self.test_theme_content = """<?xml version="1.0" encoding="UTF-8"?>
<theme>
    <colors>
        <primary>#3F51B5</primary>
        <secondary>#FF4081</secondary>
        <background>#FAFAFA</background>
    </colors>
    <styles>
        <button background="#3F51B5" color="#FFFFFF"/>
        <window background="#FAFAFA"/>
    </styles>
</theme>"""

        with open(self.test_theme_file, "w", encoding="utf-8") as f:
            f.write(self.test_theme_content)

    def tearDown(self):
        """Clean up after each test method."""
        # Reset singleton
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None
        # Reset class variable
        ThemeManager.AVAILABLE_QT_THEMES = None

        # Clean up temporary directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_get_custom_themes_directory(self):
        """Test getting the custom themes directory."""
        directory = self.theme_manager.get_custom_themes_directory()
        self.assertEqual(directory, CUSTOM_THEMES_DIR)
        self.assertIsInstance(directory, Path)

    @patch.object(Path, "mkdir")
    @patch.object(Path, "exists")
    def test_get_custom_themes_no_directory(self, mock_exists, mock_mkdir):
        """Test getting custom themes when directory doesn't exist."""
        mock_exists.return_value = False

        custom_themes = self.theme_manager._get_custom_themes()

        self.assertEqual(custom_themes, [])
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch.object(Path, "glob")
    @patch.object(Path, "exists")
    def test_get_custom_themes_with_valid_themes(self, mock_exists, mock_glob):
        """Test getting custom themes with valid theme files."""
        mock_exists.return_value = True

        # Mock theme files
        mock_theme1 = Mock()
        mock_theme1.name = "custom1.xml"
        mock_theme2 = Mock()
        mock_theme2.name = "custom2.xml"
        mock_theme3 = Mock()
        mock_theme3.name = "invalid.xml"

        mock_glob.return_value = [mock_theme1, mock_theme2, mock_theme3]

        # Mock validation - first two are valid, third is invalid
        with patch.object(self.theme_manager, "_validate_custom_theme") as mock_validate:
            mock_validate.side_effect = [True, True, False]

            custom_themes = self.theme_manager._get_custom_themes()

        self.assertEqual(custom_themes, ["custom1.xml", "custom2.xml"])
        self.assertEqual(mock_validate.call_count, 3)

    def test_validate_custom_theme_valid(self):
        """Test validation of a valid custom theme file."""
        result = self.theme_manager._validate_custom_theme(self.test_theme_file)
        self.assertTrue(result)

    def test_validate_custom_theme_non_xml_extension(self):
        """Test validation fails for non-XML files."""
        non_xml_file = self.temp_dir / "theme.txt"
        with open(non_xml_file, "w") as f:
            f.write("not xml")

        result = self.theme_manager._validate_custom_theme(non_xml_file)
        self.assertFalse(result)

    def test_validate_custom_theme_invalid_xml(self):
        """Test validation fails for invalid XML."""
        invalid_xml_file = self.temp_dir / "invalid.xml"
        with open(invalid_xml_file, "w") as f:
            f.write("<?xml version='1.0'?><unclosed>")

        result = self.theme_manager._validate_custom_theme(invalid_xml_file)
        self.assertFalse(result)

    def test_validate_custom_theme_nonexistent_file(self):
        """Test validation fails for non-existent files."""
        nonexistent_file = self.temp_dir / "nonexistent.xml"

        result = self.theme_manager._validate_custom_theme(nonexistent_file)
        self.assertFalse(result)

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    @patch("shutil.copy2")
    def test_install_custom_theme_success(self, mock_copy, mock_custom_dir):
        """Test successful custom theme installation."""
        mock_custom_dir.mkdir = Mock()
        mock_custom_dir.__truediv__ = lambda self, other: self.temp_dir / other

        # Mock the _detect_available_themes method to avoid actual detection
        with patch.object(self.theme_manager, "_detect_available_themes") as mock_detect:
            mock_detect.return_value = ["dark_purple.xml", "test_theme.xml"]

            result = self.theme_manager.install_custom_theme(str(self.test_theme_file))

        self.assertTrue(result)
        mock_copy.assert_called_once()
        mock_custom_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_install_custom_theme_nonexistent_file(self):
        """Test installing non-existent theme file."""
        nonexistent_file = "/path/to/nonexistent/theme.xml"

        result = self.theme_manager.install_custom_theme(nonexistent_file)

        self.assertFalse(result)

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    def test_install_custom_theme_invalid_file(self, mock_custom_dir):
        """Test installing invalid theme file."""
        invalid_file = self.temp_dir / "invalid.xml"
        with open(invalid_file, "w") as f:
            f.write("invalid xml content")

        result = self.theme_manager.install_custom_theme(str(invalid_file))

        self.assertFalse(result)

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    @patch("shutil.copy2")
    def test_install_custom_theme_with_custom_name(self, mock_copy, mock_custom_dir):
        """Test installing theme with custom name."""
        mock_custom_dir.mkdir = Mock()
        expected_dest = self.temp_dir / "my_custom_theme.xml"
        mock_custom_dir.__truediv__ = Mock(return_value=expected_dest)

        with patch.object(self.theme_manager, "_detect_available_themes") as mock_detect:
            mock_detect.return_value = ["dark_purple.xml", "my_custom_theme.xml"]

            result = self.theme_manager.install_custom_theme(str(self.test_theme_file), "my_custom_theme")

        self.assertTrue(result)
        # Verify the copy was called with the custom name
        mock_copy.assert_called_once_with(self.test_theme_file, expected_dest)

    def test_is_custom_theme(self):
        """Test checking if a theme is custom."""
        # Mock _get_custom_themes to return some custom themes
        with patch.object(self.theme_manager, "_get_custom_themes") as mock_get_custom:
            mock_get_custom.return_value = ["custom1.xml", "custom2.xml"]

            self.assertTrue(self.theme_manager.is_custom_theme("custom1.xml"))
            self.assertTrue(self.theme_manager.is_custom_theme("custom2.xml"))
            self.assertFalse(self.theme_manager.is_custom_theme("dark_purple.xml"))

    def test_list_custom_themes(self):
        """Test listing custom themes."""
        with patch.object(self.theme_manager, "_get_custom_themes") as mock_get_custom:
            mock_get_custom.return_value = ["theme1.xml", "theme2.xml"]

            themes = self.theme_manager.list_custom_themes()

            self.assertEqual(themes, ["theme1.xml", "theme2.xml"])
            mock_get_custom.assert_called_once()

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    def test_remove_custom_theme_success(self, mock_custom_dir):
        """Test successful removal of custom theme."""
        # Mock theme file
        mock_theme_path = Mock()
        mock_theme_path.exists.return_value = True
        mock_theme_path.unlink = Mock()
        mock_custom_dir.__truediv__ = Mock(return_value=mock_theme_path)

        # Ensure we're not removing the current theme
        self.theme_manager._qt_material_theme = "dark_purple.xml"

        with patch.object(self.theme_manager, "_detect_available_themes") as mock_detect:
            mock_detect.return_value = ["dark_purple.xml"]

            result = self.theme_manager.remove_custom_theme("custom_theme.xml")

        self.assertTrue(result)
        mock_theme_path.unlink.assert_called_once()

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    def test_remove_custom_theme_nonexistent(self, mock_custom_dir):
        """Test removing non-existent custom theme."""
        mock_theme_path = Mock()
        mock_theme_path.exists.return_value = False
        mock_custom_dir.__truediv__ = Mock(return_value=mock_theme_path)

        result = self.theme_manager.remove_custom_theme("nonexistent.xml")

        self.assertFalse(result)

    @patch("ThemeManager.CUSTOM_THEMES_DIR")
    def test_remove_custom_theme_current_theme(self, mock_custom_dir):
        """Test removing currently active custom theme (should fail)."""
        mock_theme_path = Mock()
        mock_theme_path.exists.return_value = True
        mock_custom_dir.__truediv__ = Mock(return_value=mock_theme_path)

        # Set current theme to the one we're trying to remove
        self.theme_manager._qt_material_theme = "current_custom.xml"

        result = self.theme_manager.remove_custom_theme("current_custom.xml")

        self.assertFalse(result)
        mock_theme_path.unlink.assert_not_called()

    @patch("PyQt5.QtWidgets.QApplication")
    def test_apply_custom_theme_to_application(self, mock_qapp_class):
        """Test applying custom theme to application fails when theme file doesn't exist."""
        # Mock QApplication instance
        mock_app = Mock()
        mock_qapp_class.instance.return_value = mock_app

        # Mock is_custom_theme to return True
        with patch.object(self.theme_manager, "is_custom_theme", return_value=True):
            result = self.theme_manager._apply_theme_to_application("nonexistent_custom_theme.xml")

        # Should fail because the custom theme file doesn't exist
        self.assertFalse(result)

    @patch("qt_material.apply_stylesheet")
    @patch("PyQt5.QtWidgets.QApplication")
    def test_apply_builtin_theme_to_application(self, mock_qapp_class, mock_apply_stylesheet):
        """Test applying built-in theme to application."""
        # Mock QApplication instance
        mock_app = Mock()
        mock_qapp_class.instance.return_value = mock_app

        # Mock is_custom_theme to return False
        with patch.object(self.theme_manager, "is_custom_theme", return_value=False):
            result = self.theme_manager._apply_theme_to_application("dark_purple.xml")

        self.assertTrue(result)
        mock_apply_stylesheet.assert_called_once_with(mock_app, theme="dark_purple.xml")

    @patch("PyQt5.QtWidgets.QApplication")
    def test_apply_theme_no_qapplication(self, mock_qapp_class):
        """Test applying custom theme when no QApplication instance exists."""
        mock_qapp_class.instance.return_value = None

        with patch.object(self.theme_manager, "is_custom_theme", return_value=True):
            result = self.theme_manager._apply_theme_to_application("custom_theme.xml")

        self.assertFalse(result)

    def test_detect_available_themes_includes_custom(self):
        """Test that available themes detection includes custom themes."""
        builtin_themes = ["dark_purple.xml", "light_blue.xml"]
        custom_themes = ["custom1.xml", "custom2.xml"]

        with patch.object(self.theme_manager, "_get_builtin_qt_themes", return_value=builtin_themes):
            with patch.object(self.theme_manager, "_get_custom_themes", return_value=custom_themes):
                all_themes = self.theme_manager._detect_available_themes()

        expected_themes = sorted(builtin_themes + custom_themes)
        self.assertEqual(all_themes, expected_themes)


class TestCustomThemeIntegration(unittest.TestCase):
    """Integration tests for custom theme functionality."""

    def setUp(self):
        """Set up test fixtures."""
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(ThemeManager, "_instance"):
            ThemeManager._instance = None

    def test_custom_theme_workflow(self):
        """Test complete custom theme workflow."""
        theme_manager = ThemeManager()

        # Mock config
        mock_config = Mock()
        mock_config.general = {}
        mock_config.save = Mock()

        theme_manager.initialize(config=mock_config)

        # Test the workflow with mocked file operations
        with patch("ThemeManager.CUSTOM_THEMES_DIR") as mock_dir:
            with patch("shutil.copy2") as mock_copy:
                with patch("pathlib.Path.exists", return_value=True):  # Mock file exists
                    with patch.object(theme_manager, "_validate_custom_theme", return_value=True):
                        with patch.object(theme_manager, "_detect_available_themes") as mock_detect:
                            mock_detect.return_value = ["dark_purple.xml", "custom.xml"]
                            mock_dir.mkdir = Mock()

                            # Install custom theme
                            result = theme_manager.install_custom_theme("/fake/path/custom.xml")
                            self.assertTrue(result)

                            # List custom themes
                            with patch.object(theme_manager, "_get_custom_themes", return_value=["custom.xml"]):
                                custom_themes = theme_manager.list_custom_themes()
                                self.assertEqual(custom_themes, ["custom.xml"])

                            # Check if theme is custom
                            with patch.object(theme_manager, "_get_custom_themes", return_value=["custom.xml"]):
                                self.assertTrue(theme_manager.is_custom_theme("custom.xml"))
                                self.assertFalse(theme_manager.is_custom_theme("dark_purple.xml"))


if __name__ == "__main__":
    unittest.main()
