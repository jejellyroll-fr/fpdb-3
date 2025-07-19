#!/usr/bin/env python
"""Simplified tests for Aux_Classic_Hud.py

Simplified test suite for the Classic HUD auxiliary module.
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock PyQt5 and other dependencies
sys.modules['PyQt5'] = Mock()
sys.modules['PyQt5.QtWidgets'] = Mock()
sys.modules['PyQt5.QtCore'] = Mock()
sys.modules['PyQt5.QtGui'] = Mock()
sys.modules['Aux_Hud'] = Mock()
sys.modules['Configuration'] = Mock()
sys.modules['Database'] = Mock()
sys.modules['Stats'] = Mock()
sys.modules['loggingFpdb'] = Mock()


class TestAuxClassicHudBasics(unittest.TestCase):
    """Test basic Aux_Classic_Hud functionality."""
    
    def test_import_classic_hud_classes(self):
        """Test that Classic HUD classes can be imported."""
        from Aux_Classic_Hud import ClassicHud, ClassicStatWindow, ClassicStat
        
        self.assertTrue(callable(ClassicHud))
        self.assertTrue(callable(ClassicStatWindow))
        self.assertTrue(callable(ClassicStat))
    
    @patch('Aux_Classic_Hud.Database.Database')
    def test_comment_functionality_methods(self, mock_db_class):
        """Test comment-related methods exist and can be called."""
        from Aux_Classic_Hud import ClassicStat
        
        # Mock database
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.sql.query = {'get_player_comment': 'SELECT comment FROM players WHERE id = %s'}
        mock_cursor.fetchone.return_value = ('Test comment',)
        mock_db_class.return_value = mock_db
        
        # Test that we can create a ClassicStat instance with minimal mocking
        with patch('Aux_Classic_Hud.Aux_Hud.SimpleStat'):
            mock_aw = Mock()
            mock_aw.params = {'fgcolor': '#FFFFFF'}
            mock_aw.hud.supported_games_parameters = None
            
            stat = ClassicStat('vpip', 2, Mock(), mock_aw)
            
            # Test comment methods
            comment = stat.get_current_comment(123)
            self.assertEqual(comment, 'Test comment')
            
            has_comment = stat.has_comment(123)
            self.assertTrue(has_comment)


if __name__ == '__main__':
    unittest.main(verbosity=2)