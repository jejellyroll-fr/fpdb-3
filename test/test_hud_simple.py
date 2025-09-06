#!/usr/bin/env python
"""Simplified tests for Hud.py.

Simplified test suite for the HUD management system.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestImportName(unittest.TestCase):
    """Test the importName utility function."""

    @classmethod
    def setUpClass(cls):
        """Set up mocks for this test class only."""
        cls._original_modules = {}
        modules_to_mock = ["Database", "Hand", "loggingFpdb"]

        for module_name in modules_to_mock:
            if module_name in sys.modules:
                cls._original_modules[module_name] = sys.modules[module_name]
            sys.modules[module_name] = Mock()

    @classmethod
    def tearDownClass(cls):
        """Clean up mocks after this test class."""
        modules_to_mock = ["Database", "Hand", "loggingFpdb"]

        for module_name in modules_to_mock:
            if module_name in cls._original_modules:
                sys.modules[module_name] = cls._original_modules[module_name]
            elif module_name in sys.modules:
                del sys.modules[module_name]

    def setUp(self):
        """Import the module to test after mocks are set up."""
        # Import here to ensure mocks are active
        global importName
        from Hud import importName

    def test_import_valid_module(self) -> None:
        """Test importing a valid module and class."""
        # Import a real module for testing
        result = importName("sys", "version")
        assert result is not None
        assert result == sys.version

    def test_import_invalid_module(self) -> None:
        """Test importing an invalid module."""
        with patch("Hud.log") as mock_log:
            result = importName("nonexistent_module", "some_class")
            assert result is None
            mock_log.exception.assert_called_once()


class TestHudBasics(unittest.TestCase):
    """Test basic HUD functionality without complex mocking."""

    def test_import_name_function_exists(self) -> None:
        """Test that importName function exists and is callable."""
        assert callable(importName)

    def test_hud_class_exists(self) -> None:
        """Test that Hud class can be imported."""
        from Hud import Hud

        assert callable(Hud)


if __name__ == "__main__":
    unittest.main(verbosity=2)
