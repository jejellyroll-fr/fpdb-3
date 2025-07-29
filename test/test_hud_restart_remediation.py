#!/usr/bin/env python3
"""
Tests for HUD restart remediation features.

This module tests the improved error handling, smart restart logic,
and statistics persistence to prevent regressions.
"""

import pytest
import os
import sys
import json
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules to test
from HudStatsPersistence import HudStatsPersistence, get_hud_stats_persistence
from ImprovedErrorHandler import ImprovedErrorHandler, ErrorSeverity, get_improved_error_handler
from SmartHudManager import SmartHudManager, RestartReason, get_smart_hud_manager


class TestHudStatsPersistence:
    """Test cases for HUD statistics persistence."""
    
    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for testing."""
        return tmp_path / "test_fpdb"
    
    @pytest.fixture
    def persistence_manager(self, temp_dir):
        """Create persistence manager with temp directory."""
        return HudStatsPersistence(str(temp_dir))
    
    def test_save_and_load_hud_stats(self, persistence_manager):
        """Test saving and loading HUD statistics."""
        table_key = "test_table_1"
        test_data = {
            "stat_dict": {
                "player1": {"vpip": 25, "pfr": 20, "screen_name": "TestPlayer1"},
                "player2": {"vpip": 15, "pfr": 10, "screen_name": "TestPlayer2"}
            },
            "poker_game": "holdem",
            "game_type": "ring",
            "max_seats": 6,
            "last_hand_id": "12345"
        }
        
        # Save stats
        result = persistence_manager.save_hud_stats(table_key, test_data)
        assert result is True
        
        # Load stats
        loaded_data = persistence_manager.load_hud_stats(table_key)
        assert loaded_data is not None
        assert loaded_data["table_key"] == table_key
        assert loaded_data["stat_dict"] == test_data["stat_dict"]
        assert loaded_data["poker_game"] == test_data["poker_game"]
    
    def test_stats_expiration(self, persistence_manager):
        """Test that expired stats are cleaned up."""
        table_key = "test_table_expire"
        test_data = {"stat_dict": {}, "poker_game": "holdem"}
        
        # Save stats
        persistence_manager.save_hud_stats(table_key, test_data)
        
        # Modify TTL to make stats expire immediately
        persistence_manager.stats_ttl = 0
        
        # Try to load expired stats
        loaded_data = persistence_manager.load_hud_stats(table_key)
        assert loaded_data is None
    
    def test_merge_stats(self, persistence_manager):
        """Test merging cached stats with new stats."""
        cached_stats = {
            "stat_dict": {
                "player1": {"vpip": 25, "pfr": 20, "hands": 100},
                "player2": {"vpip": 15, "pfr": 10, "hands": 50}
            }
        }
        
        new_stats = {
            "stat_dict": {
                "player1": {"vpip": 30, "pfr": 25, "hands": 120},
                "player3": {"vpip": 35, "pfr": 30, "hands": 20}
            }
        }
        
        merged = persistence_manager.merge_stats(cached_stats, new_stats)
        
        # Should have all players
        assert "player1" in merged["stat_dict"]
        assert "player2" in merged["stat_dict"]
        assert "player3" in merged["stat_dict"]
        
        # Player1 should have new stats (more recent)
        assert merged["stat_dict"]["player1"]["vpip"] == 30
        
        # Player2 should be preserved from cache
        assert merged["stat_dict"]["player2"]["vpip"] == 15
    
    def test_cleanup_expired_stats(self, persistence_manager):
        """Test cleanup of expired statistics."""
        # Create multiple test files
        test_tables = ["table1", "table2", "table3"]
        
        for table in test_tables:
            persistence_manager.save_hud_stats(table, {"stat_dict": {}})
        
        # Make all stats expire
        persistence_manager.stats_ttl = 0
        
        # Run cleanup
        persistence_manager.cleanup_expired_stats()
        
        # All should be cleaned up
        for table in test_tables:
            assert persistence_manager.load_hud_stats(table) is None


class TestImprovedErrorHandler:
    """Test cases for improved error handling."""
    
    @pytest.fixture
    def error_handler(self):
        """Create error handler for testing."""
        return ImprovedErrorHandler()
    
    def test_classify_permanent_error(self, error_handler):
        """Test classification of permanent errors."""
        error_message = "Invalid format detected in hand history"
        hand_text = "corrupted data..."
        
        severity = error_handler.classify_error(error_message, hand_text)
        assert severity == ErrorSeverity.PERMANENT
    
    def test_classify_temporary_error(self, error_handler):
        """Test classification of temporary errors."""
        error_message = "Connection timeout while parsing"
        hand_text = "valid hand data..."
        
        severity = error_handler.classify_error(error_message, hand_text)
        assert severity == ErrorSeverity.TEMPORARY
    
    def test_classify_recoverable_error(self, error_handler):
        """Test classification of recoverable errors."""
        error_message = "Unknown parsing issue"
        hand_text = "Hand #123456: Hold'em..."
        
        severity = error_handler.classify_error(error_message, hand_text)
        assert severity == ErrorSeverity.RECOVERABLE
    
    def test_should_reset_file_position(self, error_handler):
        """Test file position reset decision."""
        file_path = "/test/file.txt"
        
        # Permanent error should reset
        permanent_error = error_handler.record_error(
            file_path, "error", "invalid format", "corrupted"
        )
        assert error_handler.should_reset_file_position(file_path, permanent_error) is True
        
        # Temporary error should not reset
        temp_error = error_handler.record_error(
            file_path, "error", "connection timeout", "valid data"
        )
        assert error_handler.should_reset_file_position(file_path, temp_error) is False
    
    def test_error_history_cleanup(self, error_handler):
        """Test automatic cleanup of old errors."""
        file_path = "/test/cleanup.txt"
        
        # Record error
        error_handler.record_error(file_path, "error", "test error", "test hand")
        
        # Verify error is recorded
        assert file_path in error_handler.error_history
        assert len(error_handler.error_history[file_path]) == 1
        
        # Cleanup
        error_handler.cleanup_file_history(file_path)
        
        # Verify cleanup
        assert file_path not in error_handler.error_history


class TestSmartHudManager:
    """Test cases for smart HUD management."""
    
    @pytest.fixture
    def hud_manager(self):
        """Create smart HUD manager for testing."""
        return SmartHudManager()
    
    def test_should_restart_for_game_change(self, hud_manager):
        """Test restart decision for game type changes."""
        table_key = "test_table"
        current_state = {"poker_game": "holdem", "max_seats": 6}
        new_state = {"poker_game": "omaha", "max_seats": 6}
        
        should_restart, reason = hud_manager.should_restart_hud(
            table_key, RestartReason.GAME_TYPE_CHANGE, current_state, new_state
        )
        
        assert should_restart is True
        assert "holdem" in reason and "omaha" in reason
    
    def test_should_not_restart_for_minor_seats_change(self, hud_manager):
        """Test that minor seat changes don't trigger restart."""
        table_key = "test_table"
        current_state = {"poker_game": "holdem", "max_seats": 6}
        new_state = {"poker_game": "holdem", "max_seats": 7}  # Minor change
        
        should_restart, reason = hud_manager.should_restart_hud(
            table_key, RestartReason.MAX_SEATS_CHANGE, current_state, new_state
        )
        
        assert should_restart is False
        assert "Minor seat change" in reason
    
    def test_should_restart_for_major_seats_change(self, hud_manager):
        """Test that major seat changes trigger restart."""
        table_key = "test_table"
        current_state = {"poker_game": "holdem", "max_seats": 6}
        new_state = {"poker_game": "holdem", "max_seats": 10}  # Major change
        
        should_restart, reason = hud_manager.should_restart_hud(
            table_key, RestartReason.MAX_SEATS_CHANGE, current_state, new_state
        )
        
        assert should_restart is True
        assert "significantly" in reason
    
    def test_restart_cooldown(self, hud_manager):
        """Test restart cooldown period."""
        table_key = "test_table"
        
        # Update table state (simulates recent restart)
        hud_manager.update_table_state(table_key, "holdem", "ring", 6, "PokerStars")
        
        # Try to restart immediately
        should_restart, reason = hud_manager.should_restart_hud(
            table_key, RestartReason.GAME_TYPE_CHANGE
        )
        
        assert should_restart is False
        assert "cooldown" in reason
    
    def test_table_title_change_detection(self, hud_manager):
        """Test table title change detection."""
        table_key = "test_table"
        
        # First title
        old_title = "Hold'em $1/$2 - Table 1 (6 players)"
        assert hud_manager.has_table_title_changed(table_key, old_title) is False
        
        # Minor change (player count) - should not trigger
        new_title = "Hold'em $1/$2 - Table 1 (5 players)"
        assert hud_manager.has_table_title_changed(table_key, new_title) is False
        
        # Major change (different table) - should trigger
        different_title = "Hold'em $2/$4 - Table 2 (6 players)"
        assert hud_manager.has_table_title_changed(table_key, different_title) is True
    
    def test_error_count_tracking(self, hud_manager):
        """Test error count tracking and forced restart."""
        table_key = "test_table"
        
        # Create table state without resetting error count and disable cooldown
        from SmartHudManager import TableState
        import time
        
        # Disable cooldown for this test
        original_cooldown = hud_manager.restart_cooldown
        hud_manager.restart_cooldown = 0
        
        hud_manager.table_states[table_key] = TableState(
            table_key=table_key,
            poker_game="holdem",
            game_type="ring", 
            max_seats=6,
            site_name="PokerStars",
            table_title="Test Table",
            last_update=time.time() - 100  # Set to past to avoid cooldown
        )
        
        try:
            # First few errors should not trigger restart
            for i in range(4):
                should_restart, reason = hud_manager.should_restart_hud(
                    table_key, RestartReason.ERROR_RECOVERY
                )
                assert should_restart is False
            
            # 5th error should trigger restart
            should_restart, reason = hud_manager.should_restart_hud(
                table_key, RestartReason.ERROR_RECOVERY
            )
            assert should_restart is True
            assert "threshold" in reason
        finally:
            # Restore original cooldown
            hud_manager.restart_cooldown = original_cooldown
    
    def test_restart_statistics(self, hud_manager):
        """Test restart statistics tracking."""
        table_key = "test_table"
        
        # Update table state
        hud_manager.update_table_state(table_key, "holdem", "ring", 6, "PokerStars")
        
        # Record some restarts
        hud_manager.record_restart(table_key, "test restart 1")
        hud_manager.record_restart(table_key, "test restart 2")
        
        # Get statistics
        stats = hud_manager.get_restart_statistics()
        
        assert table_key in stats
        assert stats[table_key]["restart_count"] == 2
        assert "uptime" in stats[table_key]


class TestIntegration:
    """Integration tests for the complete remediation system."""
    
    def test_import_error_to_hud_restart_prevention(self):
        """Test that import errors don't cause unnecessary HUD restarts."""
        # This would be a more complex integration test
        # that simulates the full chain: import error -> no file position reset -> no HUD restart
        pass
    
    def test_stats_persistence_across_restart(self):
        """Test that stats are preserved across HUD restarts."""
        # This would test the complete flow:
        # 1. HUD has stats
        # 2. Restart is triggered
        # 3. Stats are saved before kill
        # 4. New HUD loads and merges cached stats
        pass


# Test configuration
@pytest.fixture(autouse=True)
def reset_global_instances():
    """Reset global instances before each test."""
    # Reset global instances to avoid test interference
    import HudStatsPersistence
    import ImprovedErrorHandler
    import SmartHudManager
    
    HudStatsPersistence._persistence_instance = None
    ImprovedErrorHandler._error_handler_instance = None
    SmartHudManager._smart_hud_manager_instance = None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])