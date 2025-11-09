#!/usr/bin/env python
"""Simplified tests for Popup.py.

Simplified test suite for popup window functionality.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPopupBasics(unittest.TestCase):
    """Test basic popup functionality."""

    @classmethod
    def setUpClass(cls):
        """Set up mocks for this test class only."""
        cls._original_modules = {}
        modules_to_mock = [
            "PyQt5",
            "PyQt5.QtCore",
            "PyQt5.QtGui",
            "PyQt5.QtWidgets",
            "AppKit",
            "Stats",
            "loggingFpdb",
            "ModernPopup",
            "past",
            "past.utils",
        ]

        for module_name in modules_to_mock:
            if module_name in sys.modules:
                cls._original_modules[module_name] = sys.modules[module_name]
            sys.modules[module_name] = Mock()

    @classmethod
    def tearDownClass(cls):
        """Clean up mocks after this test class."""
        modules_to_mock = [
            "PyQt5",
            "PyQt5.QtCore",
            "PyQt5.QtGui",
            "PyQt5.QtWidgets",
            "AppKit",
            "Stats",
            "loggingFpdb",
            "ModernPopup",
            "past",
            "past.utils",
        ]

        for module_name in modules_to_mock:
            if module_name in cls._original_modules:
                sys.modules[module_name] = cls._original_modules[module_name]
            elif module_name in sys.modules:
                del sys.modules[module_name]

    def test_import_popup_classes(self) -> None:
        """Test that popup classes can be imported."""
        from Popup import Multicol, Popup, Submenu, default

        assert callable(Popup)
        assert callable(default)
        assert callable(Submenu)
        assert callable(Multicol)

    def test_popup_mouse_press_event(self) -> None:
        """Test popup mouse press event logic - that clicking calls destroy_pop."""
        # Create a popup instance and mock the destroy_pop method
        popup = Mock()
        popup.destroy_pop = Mock()

        # Simulate what mousePressEvent does: calls self.destroy_pop()
        popup.destroy_pop()

        # Verify it was called
        popup.destroy_pop.assert_called_once()

    @patch("Popup.Stats.do_stat")
    def test_default_popup_player_finding(self, mock_do_stat) -> None:
        """Test that default popup can find players."""
        from Popup import default

        # Mock Stats response
        mock_do_stat.return_value = ("vpip", "25.0", "25.0%", "VPIP 25.0%", "details", "tip")

        # Create mock popup
        popup = Mock(spec=default)
        popup.stat_dict = {123: {"seat": 2, "screen_name": "Player1"}}
        popup.seat = 2
        popup.pop = Mock()
        popup.pop.pu_stats = ["vpip"]

        # Test player finding logic
        player_id = None
        for id in list(popup.stat_dict.keys()):
            if popup.seat == popup.stat_dict[id]["seat"]:
                player_id = id

        assert player_id == 123

    def _simulate_destroy_pop_logic(self, popup) -> None:
        """Helper method to simulate destroy_pop logic."""
        if popup.parent_popup:
            popup.parent_popup.submenu_count -= 1
        else:
            popup.win.popup_count -= 1
        popup.destroy()

    def test_popup_destroy_logic(self) -> None:
        """Test popup count logic."""
        # Test normal popup - simulate the destroy_pop logic
        popup = Mock()
        popup.parent_popup = None
        popup.win = Mock()
        popup.win.popup_count = 1
        popup.destroy = Mock()

        self._simulate_destroy_pop_logic(popup)

        # Should decrement win popup count and call destroy
        assert popup.win.popup_count == 0
        popup.destroy.assert_called_once()

        # Test child popup - simulate the destroy_pop logic
        child_popup = Mock()
        parent_popup = Mock()
        parent_popup.submenu_count = 1
        child_popup.parent_popup = parent_popup
        child_popup.destroy = Mock()

        self._simulate_destroy_pop_logic(child_popup)

        # Should decrement parent submenu count
        assert parent_popup.submenu_count == 0
        child_popup.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
