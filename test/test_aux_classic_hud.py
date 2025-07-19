#!/usr/bin/env python
"""Tests for Aux_Classic_Hud.py

Test suite for the Classic HUD auxiliary module.
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock PyQt5 to avoid GUI dependencies in tests
sys.modules['PyQt5'] = Mock()
sys.modules['PyQt5.QtWidgets'] = Mock()
sys.modules['PyQt5.QtCore'] = Mock()
sys.modules['PyQt5.QtGui'] = Mock()

# Mock other dependencies
sys.modules['Aux_Hud'] = Mock()
sys.modules['Configuration'] = Mock()
sys.modules['Database'] = Mock()
sys.modules['Stats'] = Mock()
sys.modules['loggingFpdb'] = Mock()

# Import after mocking
from Aux_Classic_Hud import ClassicHud, ClassicStatWindow, ClassicStat, ClassicLabel, ClassicTableMw


class TestClassicHud(unittest.TestCase):
    """Test the ClassicHud class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock the parent class
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleHUD'):
            self.mock_hud = Mock()
            self.mock_config = Mock()
            self.mock_aux_params = Mock()
            
            self.classic_hud = ClassicHud(self.mock_hud, self.mock_config, self.mock_aux_params)
    
    def test_initialization(self):
        """Test ClassicHud initialization."""
        # Test that it can be instantiated
        self.assertIsNotNone(self.classic_hud)


class TestClassicStatWindow(unittest.TestCase):
    """Test the ClassicStatWindow class."""
    
    def setUp(self):
        """Set up test environment."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStatWindow'):
            self.mock_aw = Mock()
            self.stat_window = ClassicStatWindow(self.mock_aw)
    
    def test_initialization(self):
        """Test ClassicStatWindow initialization."""
        self.assertIsNotNone(self.stat_window)
        self.assertEqual(self.stat_window.aw, self.mock_aw)
    
    def test_mousePressEvent(self):
        """Test mouse press event handling."""
        mock_event = Mock()
        mock_event.button.return_value = 4  # Middle mouse button
        
        with patch.object(self.stat_window, 'hide') as mock_hide:
            self.stat_window.mousePressEvent(mock_event)
            mock_hide.assert_called_once()


class TestClassicStat(unittest.TestCase):
    """Test the ClassicStat class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock the parent class and dependencies
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'):
            # Mock auxiliary window
            self.mock_aw = Mock()
            self.mock_aw.params = {
                'fgcolor': '#FFFFFF',
                'bgcolor': '#000000'
            }
            
            # Mock HUD and its configuration
            self.mock_hud = Mock()
            self.mock_hud.supported_games_parameters = None
            self.mock_aw.hud = self.mock_hud
            
            # Mock popup and other parameters
            self.mock_popup = Mock()
            
            # Create ClassicStat instance
            self.classic_stat = ClassicStat(
                stat='vpip',
                seat=2,
                popup=self.mock_popup,
                aw=self.mock_aw
            )
    
    def test_initialization_without_config(self):
        """Test ClassicStat initialization without stat configuration."""
        self.assertEqual(self.classic_stat.stat, 'vpip')
        self.assertEqual(self.classic_stat.seat, 2)
        self.assertEqual(self.classic_stat.popup, self.mock_popup)
        self.assertEqual(self.classic_stat.aw, self.mock_aw)
        
        # Should use default colors when no config
        self.assertEqual(self.classic_stat.hudcolor, '#FFFFFF')
        self.assertEqual(self.classic_stat.stat_locolor, "")
        self.assertEqual(self.classic_stat.stat_hicolor, "")
    
    def test_initialization_with_config(self):
        """Test ClassicStat initialization with stat configuration."""
        # Mock stat configuration
        mock_stat_obj = Mock()
        mock_stat_obj.stat_name = 'vpip'
        mock_stat_obj.stat_locolor = '#00FF00'
        mock_stat_obj.stat_hicolor = '#FF0000'
        mock_stat_obj.stat_midcolor = '#FFFF00'
        mock_stat_obj.stat_loth = '20'
        mock_stat_obj.stat_hith = '35'
        mock_stat_obj.hudcolor = '#CCCCCC'
        mock_stat_obj.hudprefix = '('
        mock_stat_obj.hudsuffix = ')'
        mock_stat_obj.click = 'test_click'
        mock_stat_obj.tip = 'Test tooltip'
        
        # Mock supported games parameters
        mock_stat_set = Mock()
        mock_stat_set.stats = {'(1,1)': mock_stat_obj}
        
        self.mock_hud.supported_games_parameters = {
            'game_stat_set': mock_stat_set
        }
        
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'):
            stat = ClassicStat('vpip', 2, self.mock_popup, self.mock_aw)
            
            # Should use configured colors
            self.assertEqual(stat.stat_locolor, '#00FF00')
            self.assertEqual(stat.stat_hicolor, '#FF0000')
            self.assertEqual(stat.stat_midcolor, '#FFFF00')
            self.assertEqual(stat.hudcolor, '#CCCCCC')
            self.assertEqual(stat.hudprefix, '(')
            self.assertEqual(stat.hudsuffix, ')')
    
    def test_comment_dialog_setup(self):
        """Test setup of comment dialog for appropriate stats."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'):
            # Test with open_comment_dialog click action
            mock_lab = Mock()
            self.mock_aw.hud.supported_games_parameters = None
            
            stat = ClassicStat('playershort', 2, self.mock_popup, self.mock_aw)
            stat.lab = mock_lab
            stat.click = "open_comment_dialog"
            
            # Should set up double click event
            with patch.object(stat, 'open_comment_dialog'):
                stat.__init__('playershort', 2, self.mock_popup, self.mock_aw)
    
    def test_get_player_id(self):
        """Test getting player ID from seat."""
        # Mock stat_dict
        self.classic_stat.stat_dict = {
            1: {'seat': 1, 'screen_name': 'Player1'},
            2: {'seat': 2, 'screen_name': 'Player2'},
            3: {'seat': 3, 'screen_name': 'Player3'}
        }
        
        # Mock the lab object
        self.classic_stat.lab = Mock()
        self.classic_stat.lab.aw_seat = 2
        
        player_id = self.classic_stat.get_player_id()
        self.assertEqual(player_id, 2)
    
    def test_get_player_id_not_found(self):
        """Test getting player ID when seat not found."""
        self.classic_stat.stat_dict = {
            1: {'seat': 1, 'screen_name': 'Player1'}
        }
        
        self.classic_stat.lab = Mock()
        self.classic_stat.lab.aw_seat = 99  # Non-existent seat
        
        player_id = self.classic_stat.get_player_id()
        self.assertIsNone(player_id)
    
    def test_get_player_name(self):
        """Test getting player name by ID."""
        self.classic_stat.stat_dict = {
            123: {'seat': 2, 'screen_name': 'TestPlayer'}
        }
        
        name = self.classic_stat.get_player_name(123)
        self.assertEqual(name, 'TestPlayer')
    
    def test_get_player_name_not_found(self):
        """Test getting player name when ID not found."""
        self.classic_stat.stat_dict = {}
        
        name = self.classic_stat.get_player_name(999)
        self.assertEqual(name, 'Unknown')
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_get_current_comment(self, mock_db_class):
        """Test getting current comment for a player."""
        # Mock database
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'get_player_comment': 'SELECT comment FROM players WHERE id = %s'}
        mock_cursor.fetchone.return_value = ('Test comment',)
        mock_db_class.return_value = mock_db
        
        comment = self.classic_stat.get_current_comment(123)
        
        self.assertEqual(comment, 'Test comment')
        mock_cursor.execute.assert_called_once()
        mock_db.close_connection.assert_called_once()
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_get_current_comment_no_result(self, mock_db_class):
        """Test getting comment when no comment exists."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'get_player_comment': 'SELECT comment FROM players WHERE id = %s'}
        mock_cursor.fetchone.return_value = None
        mock_db_class.return_value = mock_db
        
        comment = self.classic_stat.get_current_comment(123)
        
        self.assertEqual(comment, '')
        mock_db.close_connection.assert_called_once()
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_save_comment(self, mock_db_class):
        """Test saving a comment for a player."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'save_player_comment': 'UPDATE players SET comment = %s WHERE id = %s'}
        mock_db_class.return_value = mock_db
        
        self.classic_stat.save_comment(123, 'New comment')
        
        mock_cursor.execute.assert_called_once()
        mock_db.connection.commit.assert_called_once()
        mock_db.close_connection.assert_called_once()
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_has_comment_true(self, mock_db_class):
        """Test checking if player has comment when comment exists."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'get_player_comment': 'SELECT comment FROM players WHERE id = %s'}
        mock_cursor.fetchone.return_value = ('Some comment',)
        mock_db_class.return_value = mock_db
        
        has_comment = self.classic_stat.has_comment(123)
        
        self.assertTrue(has_comment)
        mock_db.close_connection.assert_called_once()
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_has_comment_false(self, mock_db_class):
        """Test checking if player has comment when no comment exists."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'get_player_comment': 'SELECT comment FROM players WHERE id = %s'}
        mock_cursor.fetchone.return_value = None
        mock_db_class.return_value = mock_db
        
        has_comment = self.classic_stat.has_comment(123)
        
        self.assertFalse(has_comment)
        mock_db.close_connection.assert_called_once()
    
    @patch('Aux_Classic_Hud.QInputDialog')
    def test_open_comment_dialog_playershort(self, mock_dialog):
        """Test opening comment dialog for playershort stat."""
        # Setup mock dialog
        mock_dialog.getMultiLineText.return_value = ('New comment', True)
        
        # Setup stat
        self.classic_stat.stat = 'playershort'
        self.classic_stat.stat_dict = {123: {'seat': 2, 'screen_name': 'TestPlayer'}}
        self.classic_stat.lab = Mock()
        self.classic_stat.lab.aw_seat = 2
        
        # Mock methods
        with patch.object(self.classic_stat, 'get_current_comment') as mock_get_comment, \
             patch.object(self.classic_stat, 'save_comment') as mock_save_comment:
            
            mock_get_comment.return_value = 'Old comment'
            
            # Call the method
            self.classic_stat.open_comment_dialog(Mock())
            
            # Verify dialog was called
            mock_dialog.getMultiLineText.assert_called_once()
            mock_save_comment.assert_called_once_with(123, 'New comment')
    
    @patch('Aux_Classic_Hud.QInputDialog')
    def test_open_comment_dialog_wrong_stat(self, mock_dialog):
        """Test that comment dialog doesn't open for wrong stats."""
        self.classic_stat.stat = 'vpip'  # Not a player stat
        
        self.classic_stat.open_comment_dialog(Mock())
        
        # Dialog should not be called
        mock_dialog.getMultiLineText.assert_not_called()
    
    def test_update_normal_stat(self):
        """Test updating a normal stat display."""
        # Mock parent update
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            # Setup stat with thresholds
            self.classic_stat.stat_loth = '20'
            self.classic_stat.stat_hith = '35'
            self.classic_stat.stat_locolor = '#00FF00'
            self.classic_stat.stat_midcolor = '#FFFF00'
            self.classic_stat.stat_hicolor = '#FF0000'
            self.classic_stat.hudcolor = '#FFFFFF'
            self.classic_stat.hudprefix = '('
            self.classic_stat.hudsuffix = ')'
            self.classic_stat.number = ('', '25.5', '', '', '', '')
            
            # Mock the label
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            result = self.classic_stat.update(123, {})
            
            # Should call parent update
            mock_super_update.assert_called_once_with(123, {})
            
            # Should set appropriate color and text
            mock_label.set_color.assert_called()
            mock_label.set_text.assert_called_with('(25.5)')
    
    def test_update_player_note_with_comment(self):
        """Test updating player_note stat when player has comment."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.stat = 'player_note'
            self.classic_stat.number = ('', '📝', '', '', '', '')
            
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            with patch.object(self.classic_stat, 'has_comment') as mock_has_comment:
                mock_has_comment.return_value = True
                
                self.classic_stat.update(123, {})
                
                # Should set orange color for note icon
                expected_text = '<span style="color: #FFA500; font-size: 16px;">📝</span>'
                mock_label.set_text.assert_called_with(expected_text)
    
    def test_update_player_note_without_comment(self):
        """Test updating player_note stat when player has no comment."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.stat = 'player_note'
            self.classic_stat.number = ('', '📝', '', '', '', '')
            
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            with patch.object(self.classic_stat, 'has_comment') as mock_has_comment:
                mock_has_comment.return_value = False
                
                self.classic_stat.update(123, {})
                
                # Should set gray color for note icon
                expected_text = '<span style="color: #808080; font-size: 16px;">📝</span>'
                mock_label.set_text.assert_called_with(expected_text)
    
    def test_update_no_number(self):
        """Test updating when stat has no number (failed to create)."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.number = None
            
            result = self.classic_stat.update(123, {})
            
            # Should return False when no number
            self.assertFalse(result)
    
    def test_color_selection_low_value(self):
        """Test color selection for low stat values."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.stat_loth = '20'
            self.classic_stat.stat_hith = '35'
            self.classic_stat.stat_locolor = '#00FF00'
            self.classic_stat.number = ('', '15.0', '', '', '', '')  # Low value
            
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            self.classic_stat.update(123, {})
            
            # Should use low color
            mock_label.set_color.assert_called_with('#00FF00')
    
    def test_color_selection_high_value(self):
        """Test color selection for high stat values."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.stat_loth = '20'
            self.classic_stat.stat_hith = '35'
            self.classic_stat.stat_hicolor = '#FF0000'
            self.classic_stat.number = ('', '45.0', '', '', '', '')  # High value
            
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            self.classic_stat.update(123, {})
            
            # Should use high color
            mock_label.set_color.assert_called_with('#FF0000')
    
    def test_color_selection_na_value(self):
        """Test color selection for NA values."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update:
            self.classic_stat.stat_loth = '20'
            self.classic_stat.stat_hith = '35'
            self.classic_stat.incolor = 'rgba(0, 0, 0, 0)'
            self.classic_stat.number = ('', 'NA', '', '', '', '')
            
            mock_label = Mock()
            self.classic_stat.lab = mock_label
            
            self.classic_stat.update(123, {})
            
            # Should use incolor for NA
            mock_label.set_color.assert_called_with('rgba(0, 0, 0, 0)')


class TestClassicLabel(unittest.TestCase):
    """Test the ClassicLabel class."""
    
    def setUp(self):
        """Set up test environment."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleLabel'):
            self.mock_aw = Mock()
            self.classic_label = ClassicLabel(self.mock_aw)
    
    def test_initialization(self):
        """Test ClassicLabel initialization."""
        self.assertIsNotNone(self.classic_label)
        self.assertEqual(self.classic_label.aw, self.mock_aw)


class TestClassicTableMw(unittest.TestCase):
    """Test the ClassicTableMw class."""
    
    def setUp(self):
        """Set up test environment."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleTableMW'):
            self.mock_hud = Mock()
            self.classic_table_mw = ClassicTableMw(self.mock_hud)
    
    def test_initialization(self):
        """Test ClassicTableMw initialization."""
        self.assertIsNotNone(self.classic_table_mw)


class TestClassicHudIntegration(unittest.TestCase):
    """Test integration scenarios for Classic HUD."""
    
    def test_full_stat_lifecycle(self):
        """Test complete stat lifecycle from creation to update."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'):
            # Mock environment
            mock_aw = Mock()
            mock_aw.params = {'fgcolor': '#FFFFFF'}
            mock_aw.hud.supported_games_parameters = None
            
            # Create stat
            stat = ClassicStat('vpip', 2, Mock(), mock_aw)
            stat.lab = Mock()
            stat.number = ('', '25.0', '', '', '', '')
            
            # Update stat
            with patch.object(stat, 'has_comment', return_value=False):
                result = stat.update(123, {})
                
                # Should succeed
                self.assertIsNone(result)  # Normal update returns None
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_comment_system_integration(self, mock_db_class):
        """Test complete comment system workflow."""
        # Setup database mock
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {
            'get_player_comment': 'SELECT comment FROM players WHERE id = %s',
            'save_player_comment': 'UPDATE players SET comment = %s WHERE id = %s'
        }
        mock_db_class.return_value = mock_db
        
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'), \
             patch('Aux_Classic_Hud.QInputDialog') as mock_dialog:
            
            # Setup stat
            mock_aw = Mock()
            mock_aw.params = {'fgcolor': '#FFFFFF'}
            mock_aw.hud.supported_games_parameters = None
            
            stat = ClassicStat('playershort', 2, Mock(), mock_aw)
            stat.stat_dict = {123: {'seat': 2, 'screen_name': 'TestPlayer'}}
            stat.lab = Mock()
            stat.lab.aw_seat = 2
            stat.click = "open_comment_dialog"
            
            # Test 1: Check no existing comment
            mock_cursor.fetchone.return_value = None
            has_comment = stat.has_comment(123)
            self.assertFalse(has_comment)
            
            # Test 2: Add new comment
            mock_dialog.getMultiLineText.return_value = ('New comment', True)
            stat.open_comment_dialog(Mock())
            
            # Verify save was called
            self.assertTrue(mock_cursor.execute.called)
            mock_db.connection.commit.assert_called()
            
            # Test 3: Check comment now exists
            mock_cursor.fetchone.return_value = ('New comment',)
            has_comment = stat.has_comment(123)
            self.assertTrue(has_comment)


class TestErrorHandling(unittest.TestCase):
    """Test error handling in Classic HUD components."""
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_database_error_handling(self, mock_db_class):
        """Test handling of database errors."""
        # Mock database that raises exceptions
        mock_db = Mock()
        mock_db.cursor.execute.side_effect = Exception("Database error")
        mock_db_class.return_value = mock_db
        
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'), \
             patch('Aux_Classic_Hud.log') as mock_log:
            
            mock_aw = Mock()
            mock_aw.params = {'fgcolor': '#FFFFFF'}
            mock_aw.hud.supported_games_parameters = None
            
            stat = ClassicStat('vpip', 2, Mock(), mock_aw)
            
            # Should handle database errors gracefully
            has_comment = stat.has_comment(123)
            self.assertFalse(has_comment)  # Should return False on error
            mock_log.exception.assert_called()
    
    def test_invalid_stat_values(self):
        """Test handling of invalid stat values."""
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat.update') as mock_super_update, \
             patch('Aux_Classic_Hud.log') as mock_log:
            
            mock_aw = Mock()
            mock_aw.params = {'fgcolor': '#FFFFFF'}
            mock_aw.hud.supported_games_parameters = None
            
            stat = ClassicStat('vpip', 2, Mock(), mock_aw)
            stat.stat_loth = '20'
            stat.stat_hith = '35'
            stat.number = ('', 'invalid_number', '', '', '', '')  # Invalid number
            stat.lab = Mock()
            
            # Should handle invalid numbers gracefully
            stat.update(123, {})
            
            # Should log the error but not crash
            mock_log.exception.assert_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)