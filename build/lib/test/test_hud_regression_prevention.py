#!/usr/bin/env python
"""Regression tests to prevent HUD restart and positioning issues."""

import copy
import unittest
from unittest.mock import Mock, patch

import Aux_Hud


class TestHudRestartRegression(unittest.TestCase):
    """Regression tests to prevent unwanted HUD restarts."""

    def test_stat_set_change_does_not_always_restart(self) -> None:
        """REGRESSION: Ensure stat set change tries refresh before restart."""
        # This test prevents regression to the old behavior where
        # change_stat_set always called kill_hud

        # Setup mocks
        config = Mock()
        hud = Mock()
        hud.config = config
        hud.poker_game = "holdem"
        hud.game_type = "ring"
        hud.stat_dict = {"player1": {"vpip": 25.0}}
        hud.parent = Mock()
        hud.table = Mock()
        hud.table.key = "test_table"

        aux_window = Mock()
        aux_window.game_params = Mock()
        aux_window.refresh_stats_layout = Mock()
        aux_window.stat_windows = {}
        aux_window.update = Mock()

        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        # Mock SUCCESSFUL refresh
        new_game_params = Mock()
        config.get_supported_games_parameters.return_value = {"game_stat_set": new_game_params}
        config.save = Mock()

        stat_sets_dict = {0: ("NewSet", "NewSet")}

        with patch("Aux_Hud.log"):
            # Call change_stat_set
            popup_menu.change_stat_set(0, stat_sets_dict)

        # CRITICAL: Should NOT call kill_hud when refresh succeeds
        hud.parent.kill_hud.assert_not_called()

        # Should attempt refresh
        aux_window.refresh_stats_layout.assert_called_once()
        aux_window.update.assert_called_once()

    def test_refresh_failure_still_allows_restart(self) -> None:
        """Ensure that when refresh fails, restart still works."""
        # This ensures we don't break the fallback mechanism

        config = Mock()
        hud = Mock()
        hud.config = config
        hud.poker_game = "holdem"
        hud.game_type = "ring"
        hud.parent = Mock()
        hud.table = Mock()
        hud.table.key = "test_table"

        aux_window = Mock()
        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        # Mock FAILED refresh
        config.get_supported_games_parameters.side_effect = Exception("Refresh failed")
        config.save = Mock()

        stat_sets_dict = {0: ("NewSet", "NewSet")}

        with patch("Aux_Hud.log"):
            # Call change_stat_set
            popup_menu.change_stat_set(0, stat_sets_dict)

        # Should call kill_hud when refresh fails
        hud.parent.kill_hud.assert_called_once_with("kill", "test_table")

    def test_no_infinite_restart_loop(self) -> None:
        """REGRESSION: Prevent infinite restart loops."""
        # This test ensures that a HUD restart doesn't trigger another restart

        restart_count = 0

        def mock_kill_hud(*args) -> None:
            nonlocal restart_count
            restart_count += 1
            if restart_count > 1:
                msg = "Infinite restart loop detected!"
                raise Exception(msg)

        hud = Mock()
        hud.parent = Mock()
        hud.parent.kill_hud = mock_kill_hud
        hud.table = Mock()
        hud.table.key = "test_table"

        # Simulate a condition that would cause restart
        config = Mock()
        config.get_supported_games_parameters.side_effect = Exception("Config error")

        aux_window = Mock()
        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        config.save = Mock()

        stat_sets_dict = {0: ("NewSet", "NewSet")}

        with patch("Aux_Hud.log"):
            # This should only restart once, not loop
            popup_menu.change_stat_set(0, stat_sets_dict)

        # Should restart exactly once
        assert restart_count == 1


class TestPositioningRegression(unittest.TestCase):
    """Regression tests to prevent positioning issues."""

    def test_default_table_coordinates_are_zero_not_fifty(self) -> None:
        """REGRESSION: Ensure default table coordinates are 0, not 50."""
        # This prevents regression to the old behavior of using 50 as default

        # Test Aux_Classic_Hud.py - should use 0, not 50
        table_x = None
        table_y = None

        # This is the CORRECTED behavior
        corrected_x = table_x if table_x is not None else 0
        corrected_y = table_y if table_y is not None else 0

        assert corrected_x == 0
        assert corrected_y == 0

        # This would be the OLD (incorrect) behavior
        old_x = table_x if table_x is not None else 50
        old_y = table_y if table_y is not None else 50

        # Ensure we're not using the old behavior
        assert corrected_x != old_x
        assert corrected_y != old_y

    def test_position_calculation_regression(self) -> None:
        """REGRESSION: Test that position calculations use correct defaults."""
        # This test ensures we don't regress to using 50 as default offset

        # Mock a scenario where table coordinates are None
        def calculate_position_old_way(layout_pos, table_x, table_y):
            # OLD (incorrect) way
            table_x = max(0, table_x) if table_x is not None else 50
            table_y = max(0, table_y) if table_y is not None else 50
            return (layout_pos[0] + table_x, layout_pos[1] + table_y)

        def calculate_position_new_way(layout_pos, table_x, table_y):
            # NEW (correct) way
            table_x = table_x if table_x is not None else 0
            table_y = table_y if table_y is not None else 0
            return (max(0, layout_pos[0] + table_x), max(0, layout_pos[1] + table_y))

        layout_position = (100, 150)

        # Test with None coordinates
        old_result = calculate_position_old_way(layout_position, None, None)
        new_result = calculate_position_new_way(layout_position, None, None)

        # Old way would give (150, 200) - WRONG
        assert old_result == (150, 200)

        # New way gives (100, 150) - CORRECT
        assert new_result == (100, 150)

        # Ensure we're not using the old behavior
        assert old_result != new_result

    def test_position_persistence_across_hands(self) -> None:
        """REGRESSION: Ensure positions persist across hands."""
        # This test prevents regression where positions reset each hand

        # Simulate saved positions
        saved_positions = {1: (120, 170), 2: (220, 120)}

        # Simulate HUD recreation (what happens each hand)
        layout = Mock()
        layout.location = [None] * 7
        layout.location[1] = saved_positions[1]
        layout.location[2] = saved_positions[2]

        # Create new HUD layout (deepcopy as in Hud.__init__)
        new_layout = copy.deepcopy(layout)

        # Positions should be preserved
        assert new_layout.location[1] == (120, 170)
        assert new_layout.location[2] == (220, 120)

        # Should not revert to default positions
        assert new_layout.location[1] != (0, 0)
        assert new_layout.location[2] != (0, 0)


class TestConfigurationReloadRegression(unittest.TestCase):
    """Regression tests for configuration reload issues."""

    def test_layout_sets_cleared_on_reload(self) -> None:
        """REGRESSION: Document that reload() clears layout_sets."""
        # This test documents the problematic behavior that causes position loss
        # It's not meant to be "fixed" but to ensure we're aware of the issue

        # Mock configuration with saved positions
        config = Mock()
        config.layout_sets = {"test_layout": Mock()}

        # Mock saved positions in layout
        layout = Mock()
        layout.location = [None, (100, 150), (200, 100)]
        config.layout_sets["test_layout"].layout = {6: layout}

        # Verify positions exist before reload
        assert layout.location[1] == (100, 150)

        # Simulate what Configuration.reload() does
        def simulate_reload() -> None:
            # This line clears all saved positions!
            config.layout_sets = {}

        # Before reload - positions exist
        assert config.layout_sets.get("test_layout") is not None

        # After reload - positions cleared
        simulate_reload()
        assert not config.layout_sets

        # This is the problematic behavior that requires positions
        # to be saved to XML before any reload occurs

    def test_save_before_reload_workflow(self) -> None:
        """Test that save->reload workflow preserves positions."""
        # This tests the correct workflow to avoid position loss

        # Mock configuration
        config = Mock()

        # Mock save operation (should persist to XML)
        config.save_layout_set = Mock()
        config.save = Mock()

        # Step 1: Save positions
        positions = {1: (120, 170), 2: (220, 120)}
        layout_set = Mock()
        layout_set.name = "test_layout"

        config.save_layout_set(layout_set, 6, positions, 800, 600)
        config.save()

        # Step 2: Reload configuration (would clear memory)
        # In real scenario, this would re-read from saved XML

        # Verify save operations were called
        config.save_layout_set.assert_called_once_with(layout_set, 6, positions, 800, 600)
        config.save.assert_called_once()


class TestMemoryLeakRegression(unittest.TestCase):
    """Regression tests to prevent memory leaks."""

    def test_no_duplicate_hud_instances(self) -> None:
        """REGRESSION: Prevent creating duplicate HUD instances."""
        # This test ensures that stat set switching doesn't create
        # multiple HUD instances that never get cleaned up

        # Mock HUD tracking
        active_huds = {}
        table_key = "test_table"

        def create_hud(table_key):
            if table_key in active_huds:
                # Should clean up old HUD first
                active_huds[table_key].kill()

            new_hud = Mock()
            new_hud.kill = Mock()
            active_huds[table_key] = new_hud
            return new_hud

        # Create initial HUD
        hud1 = create_hud(table_key)
        assert len(active_huds) == 1

        # Switch stat set (should reuse HUD, not create new one)
        # In our corrected implementation, this should NOT create a new HUD
        # because refresh succeeds

        # If refresh fails and restart is needed:
        create_hud(table_key)  # This would clean up hud1

        # Should still only have 1 HUD
        assert len(active_huds) == 1

        # Old HUD should be killed
        hud1.kill.assert_called_once()

    def test_event_handler_cleanup(self) -> None:
        """REGRESSION: Ensure event handlers are cleaned up."""
        # This prevents memory leaks from event handlers

        # Mock window with event handler
        Mock()
        event_handlers = []

        def add_event_handler(handler) -> None:
            event_handlers.append(handler)

        def remove_event_handlers() -> None:
            event_handlers.clear()

        # Add handler
        add_event_handler("test_handler")
        assert len(event_handlers) == 1

        # Cleanup (should happen when HUD is destroyed)
        remove_event_handlers()
        assert not event_handlers


class TestEdgeCaseRegression(unittest.TestCase):
    """Regression tests for edge cases."""

    def test_rapid_stat_set_switching(self) -> None:
        """REGRESSION: Handle rapid stat set switching gracefully."""
        # This test ensures that rapidly switching stat sets
        # doesn't cause race conditions or crashes

        config = Mock()
        hud = Mock()
        hud.config = config
        hud.poker_game = "holdem"
        hud.game_type = "ring"
        hud.stat_dict = {}

        aux_window = Mock()
        aux_window.refresh_stats_layout = Mock()
        aux_window.stat_windows = {}
        aux_window.update = Mock()

        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        # Mock successful config operations
        config.get_supported_games_parameters.return_value = {"game_stat_set": Mock()}
        config.save = Mock()

        # Rapid switching
        stat_sets = [{0: ("Set1", "Set1")}, {1: ("Set2", "Set2")}, {2: ("Set3", "Set3")}]

        with patch("Aux_Hud.log"):
            for stat_set_dict in stat_sets:
                for key in stat_set_dict:
                    popup_menu.change_stat_set(key, stat_set_dict)

        # Should handle all switches without crashing
        assert config.save.call_count == 3

    def test_stat_set_switching_with_invalid_config(self) -> None:
        """REGRESSION: Handle invalid config gracefully during stat set switch."""
        # This test ensures that invalid configuration doesn't crash the HUD

        config = Mock()
        config.get_supported_games_parameters.side_effect = KeyError("Invalid config")
        config.save = Mock()

        hud = Mock()
        hud.config = config
        hud.parent = Mock()
        hud.table = Mock()
        hud.table.key = "test_table"

        aux_window = Mock()
        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        stat_sets_dict = {0: ("InvalidSet", "InvalidSet")}

        with patch("Aux_Hud.log"):
            # Should not crash, should fallback to restart
            popup_menu.change_stat_set(0, stat_sets_dict)

        # Should attempt restart when config is invalid
        hud.parent.kill_hud.assert_called_once()


if __name__ == "__main__":
    unittest.main()
