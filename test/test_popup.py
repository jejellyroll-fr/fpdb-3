#!/usr/bin/env python
"""Tests for Popup.py

Test suite for popup window functionality.
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock PyQt5 to avoid GUI dependencies in tests
sys.modules['PyQt5'] = Mock()
sys.modules['PyQt5.QtCore'] = Mock()
sys.modules['PyQt5.QtGui'] = Mock()
sys.modules['PyQt5.QtWidgets'] = Mock()
sys.modules['AppKit'] = Mock()

# Mock other dependencies
sys.modules['Stats'] = Mock()
sys.modules['loggingFpdb'] = Mock()
sys.modules['ModernPopup'] = Mock()
sys.modules['past'] = Mock()
sys.modules['past.utils'] = Mock()

# Set up Qt mocks
Qt = Mock()
Qt.Window = 1
Qt.FramelessWindowHint = 2
Qt.WindowDoesNotAcceptFocus = 4

QWidget = Mock()
QLabel = Mock()
QVBoxLayout = Mock()
QGridLayout = Mock()
QCursor = Mock()
QCursor.pos.return_value = Mock()

sys.modules['PyQt5.QtCore'].Qt = Qt
sys.modules['PyQt5.QtWidgets'].QWidget = QWidget
sys.modules['PyQt5.QtWidgets'].QLabel = QLabel
sys.modules['PyQt5.QtWidgets'].QVBoxLayout = QVBoxLayout
sys.modules['PyQt5.QtWidgets'].QGridLayout = QGridLayout
sys.modules['PyQt5.QtGui'].QCursor = QCursor

# Import the module to test
from Popup import Popup, default, Submenu, Multicol


class TestPopupBase(unittest.TestCase):
    """Test the base Popup class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock dependencies
        self.mock_win = Mock()
        self.mock_win.popup_count = 0
        self.mock_win.destroyed = Mock()
        self.mock_win.destroyed.connect = Mock()
        self.mock_win.effectiveWinId.return_value = 12345
        self.mock_win.windowHandle.return_value = Mock()
        
        self.mock_config = Mock()
        self.mock_config.os_family = "Linux"
        
        self.mock_pop = Mock()
        self.mock_stat_dict = {
            1: {'seat': 2, 'screen_name': 'Player1'},
            2: {'seat': 3, 'screen_name': 'Player2'}
        }
        
        self.mock_hand_instance = Mock()
    
    @patch('Popup.QWidget.__init__')
    def test_popup_initialization(self, mock_qwidget_init):
        """Test Popup class initialization."""
        with patch.object(Popup, 'create') as mock_create, \
             patch.object(Popup, 'show') as mock_show, \
             patch.object(Popup, 'move') as mock_move, \
             patch.object(Popup, 'effectiveWinId') as mock_winid, \
             patch.object(Popup, 'parent') as mock_parent, \
             patch.object(Popup, 'windowHandle') as mock_window_handle:
            
            mock_winid.return_value = 54321
            mock_parent.return_value = self.mock_win
            mock_window_handle.return_value = Mock()
            
            popup = Popup(
                seat=2,
                stat_dict=self.mock_stat_dict,
                win=self.mock_win,
                pop=self.mock_pop,
                hand_instance=self.mock_hand_instance,
                config=self.mock_config
            )
            
            # Check initialization
            self.assertEqual(popup.seat, 2)
            self.assertEqual(popup.stat_dict, self.mock_stat_dict)
            self.assertEqual(popup.win, self.mock_win)
            self.assertEqual(popup.pop, self.mock_pop)
            self.assertEqual(popup.hand_instance, self.mock_hand_instance)
            self.assertEqual(popup.config, self.mock_config)
            self.assertIsNone(popup.parent_popup)
            self.assertEqual(popup.submenu_count, 0)
            
            # Check that create and show were called
            mock_create.assert_called_once()
            mock_show.assert_called_once()
            mock_move.assert_called_once()
    
    @patch('Popup.QWidget.__init__')
    def test_popup_with_parent_popup(self, mock_qwidget_init):
        """Test Popup initialization with parent popup."""
        mock_parent_popup = Mock()
        mock_parent_popup.submenu_count = 0
        
        with patch.object(Popup, 'create') as mock_create, \
             patch.object(Popup, 'show') as mock_show, \
             patch.object(Popup, 'move') as mock_move, \
             patch.object(Popup, 'effectiveWinId') as mock_winid, \
             patch.object(Popup, 'parent') as mock_parent, \
             patch.object(Popup, 'windowHandle') as mock_window_handle:
            
            mock_winid.return_value = 54321
            mock_parent.return_value = mock_parent_popup
            mock_window_handle.return_value = Mock()
            
            popup = Popup(
                seat=2,
                stat_dict=self.mock_stat_dict,
                win=self.mock_win,
                pop=self.mock_pop,
                hand_instance=self.mock_hand_instance,
                config=self.mock_config,
                parent_popup=mock_parent_popup
            )
            
            self.assertEqual(popup.parent_popup, mock_parent_popup)
    
    @patch('Popup.QWidget.__init__')
    @patch('Popup.NSView')
    def test_popup_mac_initialization(self, mock_nsview, mock_qwidget_init):
        """Test Popup initialization on Mac OS."""
        self.mock_config.os_family = "Mac"
        
        # Mock NSView setup
        mock_selfview = Mock()
        mock_parentview = Mock()
        mock_window = Mock()
        mock_selfview.window.return_value = mock_window
        mock_parentview.window.return_value = Mock()
        mock_nsview.side_effect = [mock_selfview, mock_parentview]
        
        with patch.object(Popup, 'create') as mock_create, \
             patch.object(Popup, 'show') as mock_show, \
             patch.object(Popup, 'move') as mock_move, \
             patch.object(Popup, 'effectiveWinId') as mock_winid, \
             patch.object(Popup, 'parent') as mock_parent:
            
            mock_winid.return_value = 54321
            mock_parent.return_value = self.mock_win
            
            popup = Popup(
                seat=2,
                stat_dict=self.mock_stat_dict,
                win=self.mock_win,
                pop=self.mock_pop,
                hand_instance=self.mock_hand_instance,
                config=self.mock_config
            )
            
            # Check that Mac-specific window setup was called
            self.assertEqual(mock_nsview.call_count, 2)
    
    def test_mouse_press_event(self):
        """Test mouse press event handling."""
        with patch.object(Popup, '__init__', return_value=None):
            popup = Popup()
            
            with patch.object(popup, 'destroy_pop') as mock_destroy:
                popup.mousePressEvent(Mock())
                mock_destroy.assert_called_once()
    
    def test_create_method(self):
        """Test create method increments popup count."""
        with patch.object(Popup, '__init__', return_value=None):
            popup = Popup()
            popup.win = self.mock_win
            popup.parent_popup = None
            
            popup.create()
            
            self.assertEqual(self.mock_win.popup_count, 1)
    
    def test_create_method_with_parent(self):
        """Test create method with parent popup."""
        mock_parent_popup = Mock()
        mock_parent_popup.submenu_count = 0
        
        with patch.object(Popup, '__init__', return_value=None):
            popup = Popup()
            popup.parent_popup = mock_parent_popup
            
            popup.create()
            
            self.assertEqual(mock_parent_popup.submenu_count, 1)
    
    def test_destroy_pop_method(self):
        """Test destroy_pop method decrements popup count."""
        with patch.object(Popup, '__init__', return_value=None):
            popup = Popup()
            popup.win = self.mock_win
            popup.parent_popup = None
            self.mock_win.popup_count = 1
            
            with patch.object(popup, 'destroy') as mock_destroy:
                popup.destroy_pop()
                
                self.assertEqual(self.mock_win.popup_count, 0)
                mock_destroy.assert_called_once()
    
    def test_destroy_pop_with_parent(self):
        """Test destroy_pop method with parent popup."""
        mock_parent_popup = Mock()
        mock_parent_popup.submenu_count = 1
        
        with patch.object(Popup, '__init__', return_value=None):
            popup = Popup()
            popup.parent_popup = mock_parent_popup
            
            with patch.object(popup, 'destroy') as mock_destroy:
                popup.destroy_pop()
                
                self.assertEqual(mock_parent_popup.submenu_count, 0)
                mock_destroy.assert_called_once()


class TestDefaultPopup(unittest.TestCase):
    """Test the default popup class."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_win = Mock()
        self.mock_win.popup_count = 0
        
        self.mock_config = Mock()
        self.mock_config.os_family = "Linux"
        
        self.mock_pop = Mock()
        self.mock_pop.pu_stats = ['vpip', 'pfr', 'hands']
        
        self.mock_stat_dict = {
            123: {'seat': 2, 'screen_name': 'Player1'},
            456: {'seat': 3, 'screen_name': 'Player2'}
        }
    
    @patch('Popup.Stats.do_stat')
    @patch('Popup.Stats.do_tip')
    def test_default_popup_create(self, mock_do_tip, mock_do_stat):
        """Test default popup creation."""
        # Mock Stats responses
        mock_do_stat.side_effect = [
            ('vpip', '25.0', '25.0%', 'VPIP 25.0%', 'details', 'tip'),
            ('pfr', '18.0', '18.0%', 'PFR 18.0%', 'details', 'tip'),
            ('hands', '100', '100', '100 hands', 'details', 'tip')
        ]
        mock_do_tip.side_effect = ['VPIP tip', 'PFR tip', 'Hands tip']
        
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 2
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            # Mock QLabel and layout
            mock_label = Mock()
            mock_layout = Mock()
            
            with patch('Popup.QLabel', return_value=mock_label) as mock_qlabel, \
                 patch('Popup.QVBoxLayout', return_value=mock_layout) as mock_qvbox, \
                 patch.object(popup, 'setLayout') as mock_set_layout, \
                 patch.object(popup, 'layout', return_value=mock_layout) as mock_get_layout, \
                 patch.object(popup, 'destroy_pop') as mock_destroy:
                
                popup.create()
                
                # Should find player and create content
                mock_set_layout.assert_called_once_with(mock_layout)
                mock_get_layout.assert_called()
                mock_label.setText.assert_called()
                mock_label.setToolTip.assert_called()
    
    def test_default_popup_no_player(self):
        """Test default popup when player not found."""
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 99  # Non-existent seat
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            with patch.object(popup, 'destroy_pop') as mock_destroy:
                popup.create()
                
                # Should destroy popup when player not found
                mock_destroy.assert_called_once()
    
    @patch('Popup.Stats.do_stat')
    def test_default_popup_with_na_stats(self, mock_do_stat):
        """Test default popup with NA stat values."""
        # Mock some stats returning NA
        mock_do_stat.side_effect = [
            ('vpip', 'NA', 'NA', 'VPIP NA', 'details', 'tip'),
            ('pfr', '18.0', '18.0%', 'PFR 18.0%', 'details', 'tip')
        ]
        
        self.mock_pop.pu_stats = ['vpip', 'pfr']
        
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 2
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            mock_label = Mock()
            mock_layout = Mock()
            
            with patch('Popup.QLabel', return_value=mock_label), \
                 patch('Popup.QVBoxLayout', return_value=mock_layout), \
                 patch.object(popup, 'setLayout'), \
                 patch.object(popup, 'layout', return_value=mock_layout), \
                 patch('Popup.Stats.do_tip', return_value='tip'):
                
                popup.create()
                
                # Should include both valid and NA stats
                self.assertEqual(mock_do_stat.call_count, 2)


class TestSubmenuPopup(unittest.TestCase):
    """Test the Submenu popup class."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_win = Mock()
        self.mock_win.popup_count = 0
        
        self.mock_config = Mock()
        self.mock_config.os_family = "Linux"
        
        self.mock_pop = Mock()
        self.mock_pop.pu_stats_submenu = [
            ('vpip', 'default'),
            ('pfr', 'default'),
            ('hands', 'default')
        ]
        
        self.mock_stat_dict = {
            123: {'seat': 2, 'screen_name': 'Player1'},
            456: {'seat': 3, 'screen_name': 'Player2'}
        }
    
    @patch('Popup.Stats.do_stat')
    def test_submenu_popup_create(self, mock_do_stat):
        """Test submenu popup creation."""
        mock_do_stat.side_effect = [
            ('vpip', '25.0', '25.0%', 'VPIP 25.0%', 'details', 'tip'),
            ('pfr', '18.0', '18.0%', 'PFR 18.0%', 'details', 'tip'),
            ('hands', '100', '100', '100 hands', 'details', 'tip')
        ]
        
        with patch.object(Submenu, '__init__', return_value=None):
            popup = Submenu()
            popup.seat = 2
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            mock_layout = Mock()
            
            with patch('Popup.QGridLayout', return_value=mock_layout) as mock_grid, \
                 patch.object(popup, 'setLayout') as mock_set_layout, \
                 patch.object(popup, 'destroy_pop') as mock_destroy, \
                 patch('Popup.QLabel') as mock_qlabel:
                
                popup.create()
                
                # Should create grid layout and add stats
                mock_set_layout.assert_called_once_with(mock_layout)
                self.assertEqual(mock_do_stat.call_count, 3)
    
    def test_submenu_popup_no_player(self):
        """Test submenu popup when player not found."""
        with patch.object(Submenu, '__init__', return_value=None):
            popup = Submenu()
            popup.seat = 99  # Non-existent seat
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            with patch.object(popup, 'destroy_pop') as mock_destroy:
                popup.create()
                
                # Should destroy popup when player not found
                mock_destroy.assert_called_once()


class TestMulticolPopup(unittest.TestCase):
    """Test the Multicol popup class."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_win = Mock()
        self.mock_win.popup_count = 0
        
        self.mock_config = Mock()
        self.mock_config.os_family = "Linux"
        
        self.mock_pop = Mock()
        self.mock_pop.pu_stats = ['vpip', 'pfr', 'hands', 'cb1', 'f_cb1', 'steal']
        
        self.mock_stat_dict = {
            123: {'seat': 2, 'screen_name': 'Player1'},
            456: {'seat': 3, 'screen_name': 'Player2'}
        }
    
    @patch('Popup.Stats.do_stat')
    @patch('Popup.Stats.do_tip')
    def test_multicol_popup_create(self, mock_do_tip, mock_do_stat):
        """Test multicol popup creation."""
        mock_do_stat.side_effect = [
            ('vpip', '25.0', '25.0%', 'VPIP 25.0%', 'details', 'tip'),
            ('pfr', '18.0', '18.0%', 'PFR 18.0%', 'details', 'tip'),
            ('hands', '100', '100', '100 hands', 'details', 'tip'),
            ('cb1', '70.0', '70.0%', 'CB1 70.0%', 'details', 'tip'),
            ('f_cb1', '30.0', '30.0%', 'FCB1 30.0%', 'details', 'tip'),
            ('steal', '25.0', '25.0%', 'Steal 25.0%', 'details', 'tip')
        ]
        mock_do_tip.return_value = 'Test tip'
        
        with patch.object(Multicol, '__init__', return_value=None):
            popup = Multicol()
            popup.seat = 2
            popup.stat_dict = self.mock_stat_dict
            popup.pop = self.mock_pop
            
            mock_layout = Mock()
            
            with patch('Popup.QGridLayout', return_value=mock_layout) as mock_grid, \
                 patch.object(popup, 'setLayout') as mock_set_layout, \
                 patch.object(popup, 'destroy_pop') as mock_destroy, \
                 patch('Popup.QLabel') as mock_qlabel:
                
                popup.create()
                
                # Should create grid layout and organize stats in columns
                mock_set_layout.assert_called_once_with(mock_layout)
                self.assertEqual(mock_do_stat.call_count, 6)
    
    def test_multicol_popup_column_organization(self):
        """Test that multicol popup organizes stats in columns."""
        # Test with different numbers of stats
        test_cases = [
            (3, 1),  # 3 stats -> 1 column
            (6, 2),  # 6 stats -> 2 columns  
            (12, 3), # 12 stats -> 3 columns
            (20, 4)  # 20 stats -> 4 columns
        ]
        
        for num_stats, expected_cols in test_cases:
            with patch.object(Multicol, '__init__', return_value=None):
                popup = Multicol()
                popup.seat = 2
                popup.stat_dict = self.mock_stat_dict
                
                # Create mock pop with specified number of stats
                popup.pop = Mock()
                popup.pop.pu_stats = [f'stat_{i}' for i in range(num_stats)]
                
                mock_layout = Mock()
                
                with patch('Popup.Stats.do_stat') as mock_do_stat, \
                     patch('Popup.Stats.do_tip'), \
                     patch('Popup.QGridLayout', return_value=mock_layout), \
                     patch.object(popup, 'setLayout'), \
                     patch('Popup.QLabel'):
                    
                    # Mock all stats to return valid data
                    mock_do_stat.side_effect = [
                        (f'stat_{i}', '25.0', '25.0%', f'Stat {i}', 'details', 'tip')
                        for i in range(num_stats)
                    ]
                    
                    popup.create()
                    
                    # Check that appropriate number of stats were processed
                    self.assertEqual(mock_do_stat.call_count, num_stats)


class TestPopupErrorHandling(unittest.TestCase):
    """Test error handling in popup classes."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_win = Mock()
        self.mock_win.popup_count = 0
        
        self.mock_config = Mock()
        self.mock_config.os_family = "Linux"
        
        self.mock_stat_dict = {
            123: {'seat': 2, 'screen_name': 'Player1'}
        }
    
    def test_stats_exception_handling(self):
        """Test handling of Stats module exceptions."""
        mock_pop = Mock()
        mock_pop.pu_stats = ['vpip', 'pfr']
        
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 2
            popup.stat_dict = self.mock_stat_dict
            popup.pop = mock_pop
            
            with patch('Popup.Stats.do_stat') as mock_do_stat, \
                 patch('Popup.log') as mock_log:
                
                # Make Stats.do_stat raise an exception
                mock_do_stat.side_effect = Exception("Stats error")
                
                mock_label = Mock()
                mock_layout = Mock()
                
                with patch('Popup.QLabel', return_value=mock_label), \
                     patch('Popup.QVBoxLayout', return_value=mock_layout), \
                     patch.object(popup, 'setLayout'), \
                     patch.object(popup, 'layout', return_value=mock_layout):
                    
                    # Should handle exception gracefully
                    try:
                        popup.create()
                    except Exception:
                        self.fail("Popup should handle Stats exceptions gracefully")
    
    def test_missing_stat_dict_data(self):
        """Test handling of missing or malformed stat_dict data."""
        # Test with malformed stat_dict
        malformed_stat_dict = {
            123: {'no_seat_key': 2}  # Missing 'seat' key
        }
        
        mock_pop = Mock()
        mock_pop.pu_stats = ['vpip']
        
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 2
            popup.stat_dict = malformed_stat_dict
            popup.pop = mock_pop
            
            with patch.object(popup, 'destroy_pop') as mock_destroy:
                # Should handle malformed data gracefully
                try:
                    popup.create()
                except Exception:
                    self.fail("Popup should handle malformed stat_dict gracefully")
    
    def test_empty_stat_dict(self):
        """Test handling of empty stat_dict."""
        mock_pop = Mock()
        mock_pop.pu_stats = ['vpip']
        
        with patch.object(default, '__init__', return_value=None):
            popup = default()
            popup.seat = 2
            popup.stat_dict = {}  # Empty dict
            popup.pop = mock_pop
            
            with patch.object(popup, 'destroy_pop') as mock_destroy:
                popup.create()
                
                # Should destroy popup when no players found
                mock_destroy.assert_called_once()


class TestPopupIntegration(unittest.TestCase):
    """Test popup integration scenarios."""
    
    @patch('Popup.Stats.do_stat')
    @patch('Popup.Stats.do_tip')
    def test_popup_lifecycle(self, mock_do_tip, mock_do_stat):
        """Test complete popup lifecycle."""
        # Setup
        mock_win = Mock()
        mock_win.popup_count = 0
        mock_win.destroyed = Mock()
        mock_win.destroyed.connect = Mock()
        mock_win.effectiveWinId.return_value = 12345
        mock_win.windowHandle.return_value = Mock()
        
        mock_config = Mock()
        mock_config.os_family = "Linux"
        
        mock_pop = Mock()
        mock_pop.pu_stats = ['vpip', 'hands']
        
        stat_dict = {123: {'seat': 2, 'screen_name': 'TestPlayer'}}
        
        # Mock Stats responses
        mock_do_stat.side_effect = [
            ('vpip', '25.0', '25.0%', 'VPIP 25.0%', 'details', 'tip'),
            ('hands', '100', '100', '100 hands', 'details', 'tip')
        ]
        mock_do_tip.return_value = 'Test tip'
        
        with patch('Popup.QWidget.__init__') as mock_qwidget_init, \
             patch.object(Popup, 'show') as mock_show, \
             patch.object(Popup, 'move') as mock_move, \
             patch.object(Popup, 'effectiveWinId') as mock_winid, \
             patch.object(Popup, 'parent') as mock_parent, \
             patch.object(Popup, 'windowHandle') as mock_window_handle:
            
            mock_winid.return_value = 54321
            mock_parent.return_value = mock_win
            mock_window_handle.return_value = Mock()
            
            # 1. Create popup
            popup = default(
                seat=2,
                stat_dict=stat_dict,
                win=mock_win,
                pop=mock_pop,
                hand_instance=Mock(),
                config=mock_config
            )
            
            # Verify popup was created and shown
            mock_show.assert_called_once()
            self.assertEqual(mock_win.popup_count, 1)
            
            # 2. Test mouse click destroys popup
            with patch.object(popup, 'destroy') as mock_destroy:
                popup.mousePressEvent(Mock())
                mock_destroy.assert_called_once()
                self.assertEqual(mock_win.popup_count, 0)


class TestModernPopupImport(unittest.TestCase):
    """Test modern popup import handling."""
    
    def test_modern_popup_import_success(self):
        """Test successful import of modern popup classes."""
        # This test verifies that the import handling works
        # The actual classes are mocked, so we just check the structure
        with patch('Popup.log') as mock_log:
            # Re-import to test import handling
            import importlib
            import Popup
            importlib.reload(Popup)
            
            # Should not log warning if import succeeds (mocked)
            # In real scenario with missing ModernPopup, it would log warning


if __name__ == '__main__':
    unittest.main(verbosity=2)