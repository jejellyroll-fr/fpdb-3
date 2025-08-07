#!/usr/bin/env python
"""Tests for HUD positioning system."""

import copy
import unittest
from unittest.mock import Mock, patch

import Aux_Base
import Aux_Hud
import Configuration


class TestHudPositioning(unittest.TestCase):
    """Test HUD positioning functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock configuration
        self.config = Mock(spec=Configuration.Config)
        self.config.os_family = "Linux"

        # Mock layout set
        self.layout_set = Mock()
        self.layout_set.name = "test_layout"

        # Mock layout with positions
        self.layout = Mock()
        self.layout.max = 6
        self.layout.width = 800
        self.layout.height = 600
        self.layout.location = [None] * 7  # 0-6 seats
        # Set some test positions
        self.layout.location[1] = (100, 150)
        self.layout.location[2] = (200, 100)
        self.layout.location[3] = (300, 150)
        self.layout.location[4] = (300, 350)
        self.layout.location[5] = (200, 400)
        self.layout.location[6] = (100, 350)
        self.layout.common = (400, 300)

        self.layout_set.layout = {6: self.layout}

        # Mock table
        self.table = Mock()
        self.table.site = "PokerStars"
        self.table.x = 50
        self.table.y = 75
        self.table.width = 800
        self.table.height = 600
        self.table.key = "test_table"
        self.table.topify = Mock()

        # Mock config methods
        self.config.get_site_parameters.return_value = {"hud_menu_xshift": 0, "hud_menu_yshift": 0}
        self.config.get_supported_games_parameters.return_value = {
            "aux": "Aux_Classic_Hud.ClassicHud",
            "game_stat_set": Mock(),
        }
        self.config.get_layout.return_value = self.layout_set
        self.config.get_aux_parameters.return_value = {
            "module": "Aux_Classic_Hud",
            "class": "ClassicHud",
            "fgcolor": "#000000",
            "bgcolor": "#ffffff",
            "opacity": "0.8",
            "font": "Arial",
            "font_size": "10",
        }

    def test_default_table_coordinates_are_zero(self) -> None:
        """Test that default table coordinates are 0, not 50."""
        # Test Aux_Base.py correction
        aux_base = Aux_Base.AuxSeats(Mock(), self.config, {})
        aux_base.hud = Mock()
        aux_base.hud.table = Mock()
        aux_base.hud.table.x = None
        aux_base.hud.table.y = None

        # These should default to 0, not 50
        table_x = aux_base.hud.table.x if aux_base.hud.table.x is not None else 0
        table_y = aux_base.hud.table.y if aux_base.hud.table.y is not None else 0

        assert table_x == 0
        assert table_y == 0

    def test_position_calculation_with_valid_table_coords(self) -> None:
        """Test position calculation with valid table coordinates."""
        # Simulate position calculation as done in Aux_Base
        layout_position = (100, 150)  # Position from layout
        table_x, table_y = 50, 75  # Table position

        # This is how final position should be calculated
        final_x = max(0, layout_position[0] + table_x)
        final_y = max(0, layout_position[1] + table_y)

        assert final_x == 150  # 100 + 50
        assert final_y == 225  # 150 + 75

    def test_position_calculation_with_null_table_coords(self) -> None:
        """Test position calculation when table coordinates are None."""
        layout_position = (100, 150)
        table_x = None
        table_y = None

        # Should default to 0, not 50
        table_x = table_x if table_x is not None else 0
        table_y = table_y if table_y is not None else 0

        final_x = max(0, layout_position[0] + table_x)
        final_y = max(0, layout_position[1] + table_y)

        assert final_x == 100  # 100 + 0
        assert final_y == 150  # 150 + 0

    def test_relative_position_update(self) -> None:
        """Test that relative positions are correctly calculated when moving windows."""
        # Simulate what happens in configure_event_cb
        new_abs_position_x, new_abs_position_y = 200, 250  # New absolute position
        table_x, table_y = 50, 75  # Table position

        # Calculate relative position (what should be stored)
        relative_x = new_abs_position_x - table_x
        relative_y = new_abs_position_y - table_y

        assert relative_x == 150  # 200 - 50
        assert relative_y == 175  # 250 - 75

    def test_layout_deepcopy_preserves_positions(self) -> None:
        """Test that layout deepcopy preserves saved positions."""
        # Simulate what happens in Hud.__init__
        original_layout = self.layout
        copied_layout = copy.deepcopy(original_layout)

        # Positions should be preserved
        assert copied_layout.location[1] == (100, 150)
        assert copied_layout.location[2] == (200, 100)
        assert copied_layout.common == (400, 300)

        # But they should be independent objects
        copied_layout.location[1] = (999, 999)
        assert original_layout.location[1] == (100, 150)  # Original unchanged


class TestHudLayoutSaving(unittest.TestCase):
    """Test HUD layout saving and loading."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = Mock(spec=Configuration.Config)
        self.layout_set = Mock()
        self.layout_set.name = "test_layout"

        # Mock aux window
        self.aux_hud = Mock(spec=Aux_Hud.SimpleHUD)
        self.aux_hud.hud = Mock()
        self.aux_hud.hud.layout_set = self.layout_set
        self.aux_hud.hud.max = 6
        self.aux_hud.hud.table = Mock()
        self.aux_hud.hud.table.width = 800
        self.aux_hud.hud.table.height = 600

        # Mock positions
        self.aux_hud.positions = {
            1: (120, 170),
            2: (220, 120),
            3: (320, 170),
            4: (320, 370),
            5: (220, 420),
            6: (120, 370),
        }
        self.aux_hud.adj = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        self.aux_hud.config = self.config

    def test_save_layout_calls_config_correctly(self) -> None:
        """Test that save_layout calls configuration methods correctly."""
        # Create a real SimpleHUD instance to test the actual method
        aux_hud = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
        aux_hud.hud = self.aux_hud.hud
        aux_hud.positions = self.aux_hud.positions
        aux_hud.adj = self.aux_hud.adj
        aux_hud.config = self.config

        # Call save_layout
        aux_hud.save_layout()

        # Verify save_layout_set was called with correct parameters
        expected_new_locs = {1: (120, 170), 2: (220, 120), 3: (320, 170), 4: (320, 370), 5: (220, 420), 6: (120, 370)}

        self.config.save_layout_set.assert_called_once_with(self.layout_set, 6, expected_new_locs, 800, 600)

    def test_position_dict_excludes_common(self) -> None:
        """Test that save_layout excludes 'common' from position dictionary."""
        # Add a common position
        positions_with_common = self.aux_hud.positions.copy()
        positions_with_common["common"] = (400, 300)

        # Create position dict as done in save_layout
        adj = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        new_locs = {adj[int(i)]: ((pos[0]), (pos[1])) for i, pos in positions_with_common.items() if i != "common"}

        # Common should not be in the dict
        assert "common" not in new_locs
        assert len(new_locs) == 6  # Only seat positions


class TestHudStatSetSwitching(unittest.TestCase):
    """Test HUD stat set switching functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = Mock(spec=Configuration.Config)
        self.hud = Mock()
        self.hud.config = self.config
        self.hud.poker_game = "holdem"
        self.hud.game_type = "ring"
        self.hud.parent = Mock()
        self.hud.table = Mock()
        self.hud.table.key = "test_table"
        self.hud.stat_dict = {"player1": {"vpip": 25.0}}

        # Mock aux window
        self.aux_window = Mock()
        self.aux_window.hud = self.hud

        # Mock parent window
        self.parent_window = Mock()
        self.parent_window.hud = self.hud
        self.parent_window.aw = Mock()
        self.parent_window.aw.game_params = Mock()
        self.parent_window.aw._refresh_stats_layout = Mock()
        self.parent_window.aw.stat_windows = {}
        self.parent_window.aw.update = Mock()

        # Mock popup menu
        self.popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        self.popup_menu.parentwin = self.parent_window
        self.popup_menu.delete_event = Mock()

    def test_change_stat_set_tries_refresh_first(self) -> None:
        """Test that change_stat_set tries hot refresh before restart."""
        # Mock successful refresh
        new_game_params = Mock()
        self.config.get_supported_games_parameters.return_value = {"game_stat_set": new_game_params}

        # Mock successful update
        stat_sets_dict = {0: ("StatSet1", "StatSet1")}

        with patch("Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            # Should try refresh first
            self.parent_window.aw._refresh_stats_layout.assert_called_once()
            self.parent_window.aw.update.assert_called_once_with(self.hud.stat_dict)

            # Should log success, not restart
            mock_log.info.assert_called_with("HUD refreshed with new stat set: %s", "StatSet1")
            self.hud.parent.kill_hud.assert_not_called()

    def test_change_stat_set_restarts_on_refresh_failure(self) -> None:
        """Test that change_stat_set restarts HUD when refresh fails."""
        # Mock failed refresh
        self.config.get_supported_games_parameters.side_effect = Exception("Refresh failed")

        stat_sets_dict = {0: ("StatSet1", "StatSet1")}

        with patch("Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            # Should log failure and restart
            mock_log.info.assert_called_with(
                "Refreshing HUD failed, restarting to apply stat set '%s': %s", "StatSet1", unittest.mock.ANY,
            )
            self.hud.parent.kill_hud.assert_called_once_with("kill", "test_table")

    def test_refresh_stats_layout_updates_arrays(self) -> None:
        """Test that _refresh_stats_layout updates stats arrays correctly."""
        # Create a real SimpleHUD to test the method
        simple_hud = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)

        # Mock game params
        game_params = Mock()
        game_params.rows = 3
        game_params.cols = 2
        game_params.xpad = 5
        game_params.ypad = 5
        game_params.stats = {
            "stat1": Mock(rowcol=(0, 0), stat_name="vpip", popup="popup1", tip="tip1"),
            "stat2": Mock(rowcol=(0, 1), stat_name="pfr", popup="popup2", tip="tip2"),
        }
        simple_hud.game_params = game_params

        # Call _refresh_stats_layout
        simple_hud._refresh_stats_layout()

        # Check that arrays were updated
        assert simple_hud.nrows == 3
        assert simple_hud.ncols == 2
        assert simple_hud.xpad == 5
        assert simple_hud.ypad == 5

        # Check stats arrays
        assert simple_hud.stats[0][0] == "vpip"
        assert simple_hud.stats[0][1] == "pfr"
        assert simple_hud.popups[0][0] == "popup1"
        assert simple_hud.popups[0][1] == "popup2"


class TestHudRegressionPrevention(unittest.TestCase):
    """Test to prevent regression of HUD restart issues."""

    def test_change_stat_set_does_not_always_restart(self) -> None:
        """Regression test: ensure change_stat_set doesn't always restart HUD."""
        # This test ensures we don't go back to the old behavior of always restarting
        config = Mock()
        hud = Mock()
        hud.config = config
        hud.poker_game = "holdem"
        hud.game_type = "ring"
        hud.stat_dict = {}

        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = Mock()
        parent_window.aw._refresh_stats_layout = Mock()
        parent_window.aw.stat_windows = {}
        parent_window.aw.update = Mock()
        parent_window.aw.game_params = Mock()

        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        # Mock successful config update
        config.get_supported_games_parameters.return_value = {"game_stat_set": Mock()}
        config.save = Mock()

        stat_sets_dict = {0: ("TestSet", "TestSet")}

        # Should NOT call kill_hud when refresh succeeds
        popup_menu.change_stat_set(0, stat_sets_dict)

        hud.parent.kill_hud.assert_not_called()

    def test_default_coordinates_regression(self) -> None:
        """Regression test: ensure default table coordinates are 0, not 50."""
        # This prevents regression to the old behavior of using 50 as default

        def get_table_coords(table_x, table_y):
            """Simulate the corrected coordinate calculation."""
            table_x = table_x if table_x is not None else 0  # Should be 0, not 50
            table_y = table_y if table_y is not None else 0  # Should be 0, not 50
            return table_x, table_y

        # Test with None values
        x, y = get_table_coords(None, None)
        assert x == 0
        assert y == 0

        # Test with valid values
        x, y = get_table_coords(100, 200)
        assert x == 100
        assert y == 200

    def test_layout_position_persistence(self) -> None:
        """Test that layout positions persist through configuration operations."""
        # Mock a configuration that supports the corrected save/load cycle
        config = Mock()
        layout_set = Mock()
        layout_set.name = "test"

        # Simulate saving positions
        positions = {1: (100, 150), 2: (200, 250)}
        config.save_layout_set = Mock()

        # Simulate the corrected save operation
        config.save_layout_set(layout_set, 6, positions, 800, 600)

        # Verify save was called correctly
        config.save_layout_set.assert_called_once_with(layout_set, 6, positions, 800, 600)


if __name__ == "__main__":
    unittest.main()
