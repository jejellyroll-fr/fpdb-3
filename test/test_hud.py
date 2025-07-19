#!/usr/bin/env python
"""Tests for Hud.py

Test suite for the HUD management system.
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies that are hard to test
sys.modules['Database'] = Mock()
sys.modules['Hand'] = Mock()
sys.modules['loggingFpdb'] = Mock()

# Import the module to test
from Hud import Hud, importName


class TestImportName(unittest.TestCase):
    """Test the importName utility function."""
    
    def test_import_valid_module(self):
        """Test importing a valid module and class."""
        # Import a real module for testing
        result = importName('sys', 'version')
        self.assertIsNotNone(result)
        self.assertEqual(result, sys.version)
    
    def test_import_invalid_module(self):
        """Test importing an invalid module."""
        with patch('Hud.log') as mock_log:
            result = importName('nonexistent_module', 'some_class')
            self.assertIsNone(result)
            mock_log.exception.assert_called_once()
    
    def test_import_invalid_attribute(self):
        """Test importing a valid module but invalid attribute."""
        result = importName('sys', 'nonexistent_attribute')
        # Should raise AttributeError, but we can test it gracefully
        try:
            self.assertIsNone(result)
        except AttributeError:
            pass  # Expected behavior


class TestHudInitialization(unittest.TestCase):
    """Test HUD initialization."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock the parent object
        self.mock_parent = Mock()
        self.mock_parent.hud_params = {'test_param': 'value'}
        
        # Mock the table object
        self.mock_table = Mock()
        self.mock_table.site = 'PokerStars'
        
        # Mock the config object
        self.mock_config = Mock()
        self.mock_config.get_site_parameters.return_value = {'site_param': 'value'}
        self.mock_config.get_supported_games_parameters.return_value = {
            'aux': 'ClassicHud',
            'stat_set': 'holdem_6max_pro'
        }
        self.mock_config.get_layout.return_value = Mock()
        self.mock_config.get_layout.return_value.layout = {
            6: Mock()  # Mock layout for 6-max
        }
        self.mock_config.get_aux_parameters.return_value = Mock()
        self.mock_config.get_aux_parameters.return_value.__getitem__ = Mock(side_effect=lambda x: {
            'module': 'Aux_Classic_Hud',
            'class': 'Hud'
        }[x])
    
    def test_hud_initialization_success(self):
        """Test successful HUD initialization."""
        with patch('Hud.importName') as mock_import:
            mock_import.return_value = Mock()
            
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            # Check basic attributes
            self.assertEqual(hud.parent, self.mock_parent)
            self.assertEqual(hud.table, self.mock_table)
            self.assertEqual(hud.config, self.mock_config)
            self.assertEqual(hud.poker_game, 'holdem')
            self.assertEqual(hud.game_type, 'ring')
            self.assertEqual(hud.max, 6)
            self.assertEqual(hud.site, 'PokerStars')
            
            # Check that hud_params is a copy, not reference
            self.assertEqual(hud.hud_params, self.mock_parent.hud_params)
            self.assertIsNot(hud.hud_params, self.mock_parent.hud_params)
            
            # Check that config methods were called
            self.mock_config.get_site_parameters.assert_called_once_with('PokerStars')
            self.mock_config.get_supported_games_parameters.assert_called_once_with('holdem', 'ring')
            self.mock_config.get_layout.assert_called_once_with('PokerStars', 'ring')
    
    def test_hud_initialization_no_supported_games(self):
        """Test HUD initialization when no supported games config exists."""
        self.mock_config.get_supported_games_parameters.return_value = None
        
        with patch('Hud.log') as mock_log:
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            mock_log.warning.assert_called_once()
            self.assertIn("No <game_stat_set> found", mock_log.warning.call_args[0][0])
    
    def test_hud_initialization_no_layout(self):
        """Test HUD initialization when no layout exists."""
        self.mock_config.get_layout.return_value = None
        
        with patch('Hud.log') as mock_log:
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            mock_log.warning.assert_called_once()
            self.assertIn("No layout found", mock_log.warning.call_args[0][0])
    
    def test_hud_initialization_no_max_layout(self):
        """Test HUD initialization when no layout exists for max players."""
        self.mock_config.get_layout.return_value.layout = {9: Mock()}  # Only 9-max layout
        
        with patch('Hud.log') as mock_log:
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,  # Requesting 6-max but only 9-max available
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            mock_log.warning.assert_called_once()
            self.assertIn("No layout found for 6-max", mock_log.warning.call_args[0][0])
    
    def test_aux_windows_initialization(self):
        """Test that aux windows are properly initialized."""
        with patch('Hud.importName') as mock_import:
            mock_aux_class = Mock()
            mock_import.return_value = mock_aux_class
            mock_aux_instance = Mock()
            mock_aux_class.return_value = mock_aux_instance
            
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            # Check that aux was imported and instantiated
            mock_import.assert_called_once_with('Aux_Classic_Hud', 'Hud')
            mock_aux_class.assert_called_once_with(hud, self.mock_config, self.mock_config.get_aux_parameters.return_value)
            self.assertIn(mock_aux_instance, hud.aux_windows)
    
    def test_multiple_aux_windows(self):
        """Test initialization with multiple aux windows."""
        self.mock_config.get_supported_games_parameters.return_value = {
            'aux': 'ClassicHud, mucked',
            'stat_set': 'holdem_6max_pro'
        }
        def mock_get_aux_params(aux_name):
            mock_result = Mock()
            if aux_name.strip() == 'ClassicHud':
                mock_result.__getitem__ = Mock(side_effect=lambda x: {'module': 'Aux_Classic_Hud', 'class': 'Hud'}[x])
            else:
                mock_result.__getitem__ = Mock(side_effect=lambda x: {'module': 'Mucked', 'class': 'Mucked'}[x])
            return mock_result
        
        self.mock_config.get_aux_parameters.side_effect = mock_get_aux_params
        
        with patch('Hud.importName') as mock_import:
            mock_import.side_effect = [Mock(), Mock()]
            
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            # Should have imported and created 2 aux windows
            self.assertEqual(mock_import.call_count, 2)
            self.assertEqual(len(hud.aux_windows), 2)
    
    def test_empty_aux_parameter(self):
        """Test initialization with empty aux parameter."""
        self.mock_config.get_supported_games_parameters.return_value = {
            'aux': [''],  # Empty aux list
            'stat_set': 'holdem_6max_pro'
        }
        
        hud = Hud(
            parent=self.mock_parent,
            table=self.mock_table,
            max_players=6,
            poker_game='holdem',
            game_type='ring',
            config=self.mock_config
        )
        
        # Should have no aux windows
        self.assertEqual(len(hud.aux_windows), 0)
    
    def test_failed_aux_import(self):
        """Test initialization when aux import fails."""
        with patch('Hud.importName') as mock_import:
            mock_import.return_value = None  # Import failed
            
            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=self.mock_config
            )
            
            # Should handle failed import gracefully
            mock_import.assert_called_once()
            self.assertEqual(len(hud.aux_windows), 0)


class TestHudMethods(unittest.TestCase):
    """Test HUD methods."""
    
    def setUp(self):
        """Set up test HUD instance."""
        # Create a minimal HUD instance for testing
        self.mock_parent = Mock()
        self.mock_parent.hud_params = {}
        
        self.mock_table = Mock()
        self.mock_table.site = 'PokerStars'
        
        self.mock_config = Mock()
        self.mock_config.get_site_parameters.return_value = {}
        self.mock_config.get_supported_games_parameters.return_value = {
            'aux': '',
            'stat_set': 'holdem_6max_pro'
        }
        self.mock_config.get_layout.return_value = Mock()
        self.mock_config.get_layout.return_value.layout = {6: Mock()}
        
        # Create HUD instance
        self.hud = Hud(
            parent=self.mock_parent,
            table=self.mock_table,
            max_players=6,
            poker_game='holdem',
            game_type='ring',
            config=self.mock_config
        )
        
        # Add mock aux windows for testing
        self.mock_aux1 = Mock()
        self.mock_aux2 = Mock()
        self.hud.aux_windows = [self.mock_aux1, self.mock_aux2]
    
    def test_move_table_position(self):
        """Test move_table_position method."""
        # Currently just a stub method, should not raise exception
        try:
            self.hud.move_table_position()
        except Exception as e:
            self.fail(f"move_table_position raised an exception: {e}")
    
    def test_kill_method(self):
        """Test kill method calls kill on all aux windows."""
        self.hud.kill()
        
        # Check that kill was called on all aux windows
        self.mock_aux1.kill.assert_called_once()
        self.mock_aux2.kill.assert_called_once()
    
    def test_resize_windows(self):
        """Test resize_windows method."""
        self.hud.resize_windows()
        
        # Check that resize_windows was called on all aux windows
        self.mock_aux1.resize_windows.assert_called_once()
        self.mock_aux2.resize_windows.assert_called_once()
    
    def test_reposition_windows(self):
        """Test reposition_windows method."""
        self.hud.reposition_windows()
        
        # Check that reposition_windows was called on all aux windows
        self.mock_aux1.reposition_windows.assert_called_once()
        self.mock_aux2.reposition_windows.assert_called_once()
    
    def test_save_layout(self):
        """Test save_layout method."""
        mock_layout = Mock()
        self.hud.layout = mock_layout
        
        self.hud.save_layout()
        
        # Check that save_layout was called on all aux windows with layout
        self.mock_aux1.save_layout.assert_called_once_with(mock_layout)
        self.mock_aux2.save_layout.assert_called_once_with(mock_layout)
    
    def test_create_method(self):
        """Test create method."""
        hand_id = 12345
        stat_dict = {'player1': {'vpip': 25.0}}
        
        with patch.object(self.hud, 'get_cards') as mock_get_cards:
            mock_get_cards.return_value = {'hand': 'cards'}
            
            self.hud.create(hand_id, self.mock_config, stat_dict)
            
            # Check that get_cards was called
            mock_get_cards.assert_called_once_with(hand_id)
            
            # Check that create was called on all aux windows
            self.mock_aux1.create.assert_called_once()
            self.mock_aux2.create.assert_called_once()
            
            # Verify cards were set
            self.assertEqual(self.hud.cards, {'hand': 'cards'})
    
    def test_update_method(self):
        """Test update method."""
        hand_id = 12345
        
        with patch.object(self.hud, 'get_cards') as mock_get_cards:
            mock_get_cards.return_value = {'updated': 'cards'}
            
            self.hud.update(hand_id, self.mock_config)
            
            # Check that get_cards was called
            mock_get_cards.assert_called_once_with(hand_id)
            
            # Check that update was called on all aux windows
            self.mock_aux1.update.assert_called_once()
            self.mock_aux2.update.assert_called_once()
            
            # Verify cards were updated
            self.assertEqual(self.hud.cards, {'updated': 'cards'})
    
    def test_get_cards_with_database(self):
        """Test get_cards method with database connection."""
        hand_id = 12345
        expected_cards = {'hole': ['Ah', 'Kh'], 'flop': ['Qh', 'Jh', 'Th']}
        
        # Mock database connection
        mock_db = Mock()
        mock_db.get_cards.return_value = expected_cards
        self.hud.db_hud_connection = mock_db
        
        result = self.hud.get_cards(hand_id)
        
        # Check that database method was called
        mock_db.get_cards.assert_called_once_with(hand_id)
        self.assertEqual(result, expected_cards)
    
    def test_get_cards_without_database(self):
        """Test get_cards method without database connection."""
        hand_id = 12345
        
        # No database connection
        self.hud.db_hud_connection = None
        
        result = self.hud.get_cards(hand_id)
        
        # Should return empty dict when no database
        self.assertEqual(result, {})
    
    def test_get_cards_database_exception(self):
        """Test get_cards method when database raises exception."""
        hand_id = 12345
        
        # Mock database that raises exception
        mock_db = Mock()
        mock_db.get_cards.side_effect = Exception("Database error")
        self.hud.db_hud_connection = mock_db
        
        with patch('Hud.log') as mock_log:
            result = self.hud.get_cards(hand_id)
            
            # Should return empty dict and log error
            self.assertEqual(result, {})
            mock_log.exception.assert_called_once()


class TestHudIntegration(unittest.TestCase):
    """Test HUD integration scenarios."""
    
    def test_full_hud_lifecycle(self):
        """Test complete HUD lifecycle from creation to destruction."""
        # Setup
        mock_parent = Mock()
        mock_parent.hud_params = {'param1': 'value1'}
        
        mock_table = Mock()
        mock_table.site = 'PokerStars'
        
        mock_config = Mock()
        mock_config.get_site_parameters.return_value = {'site_setting': 'value'}
        mock_config.get_supported_games_parameters.return_value = {
            'aux': 'ClassicHud',
            'stat_set': 'holdem_6max_pro'
        }
        mock_layout = Mock()
        mock_layout.layout = {6: Mock()}
        mock_config.get_layout.return_value = mock_layout
        mock_config.get_aux_parameters.return_value = {
            'module': 'Aux_Classic_Hud',
            'class': 'Hud'
        }
        
        with patch('Hud.importName') as mock_import:
            mock_aux_class = Mock()
            mock_aux_instance = Mock()
            mock_aux_class.return_value = mock_aux_instance
            mock_import.return_value = mock_aux_class
            
            # 1. Create HUD
            hud = Hud(
                parent=mock_parent,
                table=mock_table,
                max_players=6,
                poker_game='holdem',
                game_type='ring',
                config=mock_config
            )
            
            # Verify initialization
            self.assertEqual(len(hud.aux_windows), 1)
            self.assertIn(mock_aux_instance, hud.aux_windows)
            
            # 2. Create/Update cycle
            hand_id = 12345
            stat_dict = {'player1': {'vpip': 25.0}}
            
            with patch.object(hud, 'get_cards') as mock_get_cards:
                mock_get_cards.return_value = {'cards': 'data'}
                
                hud.create(hand_id, mock_config, stat_dict)
                mock_aux_instance.create.assert_called_once()
                
                hud.update(hand_id, mock_config)
                mock_aux_instance.update.assert_called_once()
            
            # 3. Layout operations
            hud.resize_windows()
            mock_aux_instance.resize_windows.assert_called_once()
            
            hud.reposition_windows()
            mock_aux_instance.reposition_windows.assert_called_once()
            
            hud.save_layout()
            mock_aux_instance.save_layout.assert_called_once()
            
            # 4. Cleanup
            hud.kill()
            mock_aux_instance.kill.assert_called_once()


class TestHudErrorHandling(unittest.TestCase):
    """Test HUD error handling scenarios."""
    
    def test_aux_method_exceptions(self):
        """Test that HUD handles exceptions in aux window methods gracefully."""
        # Setup HUD with mock aux that raises exceptions
        mock_parent = Mock()
        mock_parent.hud_params = {}
        
        mock_table = Mock()
        mock_table.site = 'PokerStars'
        
        mock_config = Mock()
        mock_config.get_site_parameters.return_value = {}
        mock_config.get_supported_games_parameters.return_value = {
            'aux': '',
            'stat_set': 'test'
        }
        mock_config.get_layout.return_value = Mock()
        mock_config.get_layout.return_value.layout = {6: Mock()}
        
        hud = Hud(
            parent=mock_parent,
            table=mock_table,
            max_players=6,
            poker_game='holdem',
            game_type='ring',
            config=mock_config
        )
        
        # Add mock aux that raises exceptions
        mock_aux = Mock()
        mock_aux.kill.side_effect = Exception("Kill failed")
        mock_aux.resize_windows.side_effect = Exception("Resize failed")
        mock_aux.update.side_effect = Exception("Update failed")
        hud.aux_windows = [mock_aux]
        
        # Test that methods don't crash when aux methods fail
        with patch('Hud.log') as mock_log:
            # These should not raise exceptions
            try:
                hud.kill()
                hud.resize_windows()
                hud.update(12345, mock_config)
            except Exception as e:
                self.fail(f"HUD method should handle aux exceptions gracefully: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)