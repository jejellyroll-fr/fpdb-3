#!/usr/bin/env python

"""test_config_initializer.py

Unit tests for the ConfigInitializer class.
Tests configuration initialization, fallback mechanisms, and error handling.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ConfigInitializer import ConfigInitializer, ensure_config_initialized


class TestConfigInitializer(unittest.TestCase):
    """Test cases for ConfigInitializer functionality."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Reset class state for clean tests
        ConfigInitializer._initialized = False
        ConfigInitializer._config = None
        ConfigInitializer._config_file = None

    def tearDown(self):
        """Clean up after each test method."""
        # Reset class state after tests
        ConfigInitializer._initialized = False
        ConfigInitializer._config = None
        ConfigInitializer._config_file = None

    def test_singleton_behavior(self):
        """Test that initialize returns the same config when called multiple times."""
        mock_config = Mock()

        with patch("builtins.__import__") as mock_import:
            mock_configuration = Mock()
            mock_configuration.get_config.return_value = "/path/to/config.xml"
            mock_configuration.Config.return_value = mock_config
            mock_import.return_value = mock_configuration

            with patch.object(ConfigInitializer, "_find_config_path", return_value="/path/to/config.xml"):
                # First call
                config1 = ConfigInitializer.initialize()

                # Second call should return the same instance
                config2 = ConfigInitializer.initialize()

                self.assertIs(config1, config2)
                self.assertTrue(ConfigInitializer.is_initialized())

    @patch("ConfigInitializer.Path")
    def test_find_config_path_absolute(self, mock_path):
        """Test _find_config_path with absolute path."""
        absolute_path = "/absolute/path/to/config.xml"
        mock_path.return_value.is_absolute.return_value = True

        result = ConfigInitializer._find_config_path(absolute_path)

        self.assertEqual(result, absolute_path)

    @patch("ConfigInitializer.Path")
    def test_find_config_path_existing_file(self, mock_path):
        """Test _find_config_path when file exists in search paths."""
        config_file = "HUD_config.xml"

        # Mock path behaviors
        mock_path.return_value.is_absolute.return_value = False
        mock_cwd_path = Mock()
        mock_cwd_path.exists.return_value = True
        mock_path.cwd.return_value.__truediv__.return_value = mock_cwd_path

        result = ConfigInitializer._find_config_path(config_file)

        # Should find the file in current directory
        mock_path.cwd.assert_called_once()

    def test_find_config_path_create_new(self):
        """Test _find_config_path when file doesn't exist and needs to be created."""
        config_file = "test_nonexistent_config.xml"

        # Call the method - it should create the path in ~/.fpdb/
        result = ConfigInitializer._find_config_path(config_file)

        # Should return a path in the user's home/.fpdb directory
        self.assertIn(".fpdb", result)
        self.assertIn(config_file, result)

    @patch("ConfigInitializer.sys")
    @patch("ConfigInitializer.Path")
    def test_initialize_success(self, mock_path, mock_sys):
        """Test successful initialization."""
        mock_config = Mock()
        config_path = "/path/to/config.xml"

        # Mock path setup
        mock_path.return_value.parent = "/fpdb/dir"
        mock_sys.path = ["/other/path"]

        with patch.object(ConfigInitializer, "_find_config_path", return_value=config_path):
            with patch("builtins.__import__") as mock_import:
                mock_configuration = Mock()
                mock_configuration.get_config.return_value = config_path
                mock_configuration.Config.return_value = mock_config
                mock_import.return_value = mock_configuration

                result = ConfigInitializer.initialize()

                self.assertEqual(result, mock_config)
                self.assertEqual(ConfigInitializer._config, mock_config)
                self.assertEqual(ConfigInitializer._config_file, config_path)
                self.assertTrue(ConfigInitializer._initialized)

    @patch("ConfigInitializer.sys")
    @patch("ConfigInitializer.Path")
    def test_initialize_with_tuple_result(self, mock_path, mock_sys):
        """Test initialization when get_config returns a tuple."""
        mock_config = Mock()
        config_path = "/path/to/config.xml"
        tuple_result = (config_path, "example_copy", "example_path")

        # Mock path setup
        mock_path.return_value.parent = "/fpdb/dir"
        mock_sys.path = ["/other/path"]

        with patch.object(ConfigInitializer, "_find_config_path", return_value=config_path):
            with patch("builtins.__import__") as mock_import:
                mock_configuration = Mock()
                mock_configuration.get_config.return_value = tuple_result
                mock_configuration.Config.return_value = mock_config
                mock_import.return_value = mock_configuration

                result = ConfigInitializer.initialize()

                self.assertEqual(result, mock_config)
                self.assertEqual(ConfigInitializer._config_file, config_path)

    @patch("ConfigInitializer.sys")
    @patch("ConfigInitializer.Path")
    def test_initialize_fallback_to_default(self, mock_path, mock_sys):
        """Test initialization with fallback to default config."""
        mock_config = Mock()

        # Mock path setup
        mock_path.return_value.parent = "/fpdb/dir"
        mock_sys.path = ["/other/path"]

        with patch.object(ConfigInitializer, "_find_config_path", side_effect=Exception("Config error")):
            with patch("builtins.__import__") as mock_import:
                mock_configuration = Mock()
                mock_configuration.Config.return_value = mock_config
                mock_import.return_value = mock_configuration

                result = ConfigInitializer.initialize(fallback_to_default=True)

                self.assertEqual(result, mock_config)
                self.assertTrue(ConfigInitializer._initialized)

    @patch("ConfigInitializer.sys")
    @patch("ConfigInitializer.Path")
    def test_initialize_no_fallback_raises_exception(self, mock_path, mock_sys):
        """Test initialization without fallback raises exception on error."""
        # Mock path setup
        mock_path.return_value.parent = "/fpdb/dir"
        mock_sys.path = ["/other/path"]

        with patch.object(ConfigInitializer, "_find_config_path", side_effect=Exception("Config error")):
            with self.assertRaises(Exception):
                ConfigInitializer.initialize(fallback_to_default=False)

    @patch("ConfigInitializer.sys")
    @patch("ConfigInitializer.Path")
    def test_initialize_fallback_import_error(self, mock_path, mock_sys):
        """Test initialization fallback fails with ImportError."""
        # Mock path setup
        mock_path.return_value.parent = "/fpdb/dir"
        mock_sys.path = ["/other/path"]

        with patch.object(ConfigInitializer, "_find_config_path", side_effect=Exception("Config error")):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                with self.assertRaises(ImportError):
                    ConfigInitializer.initialize(fallback_to_default=True)

    def test_get_config_when_initialized(self):
        """Test get_config returns existing config when initialized."""
        mock_config = Mock()
        ConfigInitializer._initialized = True
        ConfigInitializer._config = mock_config

        result = ConfigInitializer.get_config()

        self.assertEqual(result, mock_config)

    def test_get_config_when_not_initialized(self):
        """Test get_config initializes config when not initialized."""
        mock_config = Mock()

        with patch.object(ConfigInitializer, "initialize", return_value=mock_config) as mock_init:
            result = ConfigInitializer.get_config()

            self.assertEqual(result, mock_config)
            mock_init.assert_called_once()

    def test_reload_config_success(self):
        """Test successful config reload."""
        mock_config = Mock()
        config_file = "/path/to/config.xml"

        ConfigInitializer._config_file = config_file

        with patch.object(ConfigInitializer, "initialize", return_value=mock_config) as mock_init:
            result = ConfigInitializer.reload_config()

            self.assertEqual(result, mock_config)
            mock_init.assert_called_once_with(config_file)
            self.assertFalse(ConfigInitializer._initialized)
            self.assertIsNone(ConfigInitializer._config)

    def test_reload_config_no_file(self):
        """Test reload_config raises error when no config file is set."""
        ConfigInitializer._config_file = None

        with self.assertRaises(RuntimeError) as context:
            ConfigInitializer.reload_config()

        self.assertIn("No configuration file to reload", str(context.exception))

    def test_is_initialized_true(self):
        """Test is_initialized returns True when properly initialized."""
        ConfigInitializer._initialized = True
        ConfigInitializer._config = Mock()

        self.assertTrue(ConfigInitializer.is_initialized())

    def test_is_initialized_false_no_init(self):
        """Test is_initialized returns False when not initialized."""
        ConfigInitializer._initialized = False
        ConfigInitializer._config = None

        self.assertFalse(ConfigInitializer.is_initialized())

    def test_is_initialized_false_no_config(self):
        """Test is_initialized returns False when initialized but no config."""
        ConfigInitializer._initialized = True
        ConfigInitializer._config = None

        self.assertFalse(ConfigInitializer.is_initialized())

    def test_get_config_path_with_file(self):
        """Test get_config_path returns file path when set."""
        config_file = "/path/to/config.xml"
        ConfigInitializer._config_file = config_file

        result = ConfigInitializer.get_config_path()

        self.assertEqual(result, config_file)

    def test_get_config_path_no_file(self):
        """Test get_config_path returns None when no file is set."""
        ConfigInitializer._config_file = None

        result = ConfigInitializer.get_config_path()

        self.assertIsNone(result)

    def test_ensure_config_initialized_function(self):
        """Test the convenience function ensure_config_initialized."""
        mock_config = Mock()
        config_file = "custom_config.xml"

        with patch.object(ConfigInitializer, "initialize", return_value=mock_config) as mock_init:
            result = ensure_config_initialized(config_file)

            self.assertEqual(result, mock_config)
            mock_init.assert_called_once_with(config_file)


if __name__ == "__main__":
    unittest.main()
