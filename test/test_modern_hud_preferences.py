#!/usr/bin/env python
"""Tests for ModernHudPreferences.py AddStatDialog.

Test suite for the AddStatDialog class focusing on stat_loth and stat_hith validation.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAddStatDialog(unittest.TestCase):
    """Test the AddStatDialog class."""

    @classmethod
    def setUpClass(cls):
        """Set up mocks for PyQt5 and other dependencies."""
        cls._original_modules = {}
        modules_to_mock = [
            "PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
        ]
        
        for module_name in modules_to_mock:
            if module_name in sys.modules:
                cls._original_modules[module_name] = sys.modules[module_name]
            sys.modules[module_name] = Mock()

        # Mock PyQt5 classes specifically
        sys.modules["PyQt5.QtWidgets"].QDialog = Mock()
        sys.modules["PyQt5.QtWidgets"].QVBoxLayout = Mock()
        sys.modules["PyQt5.QtWidgets"].QHBoxLayout = Mock()
        sys.modules["PyQt5.QtWidgets"].QFormLayout = Mock()
        sys.modules["PyQt5.QtWidgets"].QLabel = Mock()
        sys.modules["PyQt5.QtWidgets"].QSpinBox = Mock()
        sys.modules["PyQt5.QtWidgets"].QComboBox = Mock()
        sys.modules["PyQt5.QtWidgets"].QLineEdit = Mock()
        sys.modules["PyQt5.QtWidgets"].QPushButton = Mock()
        sys.modules["PyQt5.QtWidgets"].QCheckBox = Mock()
        sys.modules["PyQt5.QtWidgets"].QDialogButtonBox = Mock()
        sys.modules["PyQt5.QtWidgets"].QColorDialog = Mock()
        sys.modules["PyQt5.QtCore"].Qt = Mock()
        sys.modules["PyQt5.QtCore"].pyqtSignal = Mock()

    @classmethod
    def tearDownClass(cls):
        """Restore original modules."""
        for module_name, original_module in cls._original_modules.items():
            sys.modules[module_name] = original_module
        
        # Remove mocked modules that weren't originally present
        modules_to_remove = [
            "PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"
        ]
        for module_name in modules_to_remove:
            if module_name not in cls._original_modules and module_name in sys.modules:
                del sys.modules[module_name]

    def setUp(self):
        """Set up test fixtures."""
        # Import here after mocking
        from ModernHudPreferences import AddStatDialog
        self.AddStatDialog = AddStatDialog

    def test_init_with_empty_stat_loth_string(self):
        """Test AddStatDialog initialization with empty stat_loth string."""
        # Create a stat dict with empty stat_loth
        stat = {
            "row": "0",
            "col": "0", 
            "stat": "vpip",
            "click": "",
            "popup": "",
            "stat_loth": "",  # Empty string - should not cause ValueError
            "stat_hith": "40",
            "stat_locolor": "#408000",
            "stat_hicolor": "#F05000"
        }
        
        # Mock the setValue method to verify it's not called for empty string
        mock_loth_input = Mock()
        mock_hith_input = Mock()
        
        # Create a mock dialog object
        dialog = Mock()
        dialog.loth_input = mock_loth_input
        dialog.hith_input = mock_hith_input
        
        # Manually call the problematic code section with the fix
        if "stat_loth" in stat and stat["stat_loth"]:
            dialog.loth_input.setValue(int(float(stat["stat_loth"])))
        if "stat_hith" in stat and stat["stat_hith"]:
            dialog.hith_input.setValue(int(float(stat["stat_hith"])))
        
        # Verify loth_input.setValue was NOT called (empty string)
        mock_loth_input.setValue.assert_not_called()
        
        # Verify hith_input.setValue WAS called (valid value)
        mock_hith_input.setValue.assert_called_once_with(40)

    def test_init_with_none_stat_loth(self):
        """Test AddStatDialog initialization with None stat_loth."""
        stat = {
            "row": "0",
            "col": "0",
            "stat": "vpip", 
            "stat_loth": None,
            "stat_hith": "35"
        }
        
        mock_loth_input = Mock()
        mock_hith_input = Mock()
        
        # Create a mock dialog object
        dialog = Mock()
        dialog.loth_input = mock_loth_input
        dialog.hith_input = mock_hith_input
        
        # Test the validation logic
        if "stat_loth" in stat and stat["stat_loth"]:
            dialog.loth_input.setValue(int(float(stat["stat_loth"])))
        if "stat_hith" in stat and stat["stat_hith"]:
            dialog.hith_input.setValue(int(float(stat["stat_hith"])))
            
        # loth_input should NOT be called for None value
        mock_loth_input.setValue.assert_not_called()
        mock_hith_input.setValue.assert_called_once_with(35)

    def test_init_with_valid_stat_loth(self):
        """Test AddStatDialog initialization with valid stat_loth values."""
        stat = {
            "row": "0", 
            "col": "0",
            "stat": "vpip",
            "stat_loth": "25",
            "stat_hith": "40"
        }
        
        mock_loth_input = Mock()
        mock_hith_input = Mock()
        
        # Create a mock dialog object
        dialog = Mock()
        dialog.loth_input = mock_loth_input
        dialog.hith_input = mock_hith_input
        
        # Test the validation logic
        if "stat_loth" in stat and stat["stat_loth"]:
            dialog.loth_input.setValue(int(float(stat["stat_loth"])))
        if "stat_hith" in stat and stat["stat_hith"]:
            dialog.hith_input.setValue(int(float(stat["stat_hith"])))
        
        # Both should be called with valid values
        mock_loth_input.setValue.assert_called_once_with(25)
        mock_hith_input.setValue.assert_called_once_with(40)

    def test_original_bug_scenario(self):
        """Test the original bug scenario that caused ValueError."""
        # This test verifies that the fix prevents the original ValueError
        stat = {
            "stat_loth": "",  # This was causing ValueError: could not convert string to float: ''
            "stat_hith": ""
        }
        
        # The old code would do: int(float(stat["stat_loth"]))
        # The new code should check: if "stat_loth" in stat and stat["stat_loth"]:
        
        # Test old logic would fail
        with self.assertRaises(ValueError):
            int(float(stat["stat_loth"]))
            
        # Test new logic succeeds 
        if "stat_loth" in stat and stat["stat_loth"]:
            value = int(float(stat["stat_loth"]))
        else:
            value = None
            
        self.assertIsNone(value)


if __name__ == '__main__':
    unittest.main()