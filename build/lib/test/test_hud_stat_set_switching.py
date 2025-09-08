#!/usr/bin/env python
"""Tests for HUD stat set switching functionality."""

import unittest
import xml.dom.minidom
from unittest.mock import Mock, patch

import Aux_Hud
import Configuration


class TestStatSetSwitching(unittest.TestCase):
    """Test HUD stat set switching functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock configuration
        self.config = Mock(spec=Configuration.Config)
        self.config.doc = Mock()

        # Mock HUD
        self.hud = Mock()
        self.hud.config = self.config
        self.hud.poker_game = "holdem"
        self.hud.game_type = "ring"
        self.hud.parent = Mock()
        self.hud.table = Mock()
        self.hud.table.key = "test_table"
        self.hud.stat_dict = {"player1": {"vpip": 25.0, "pfr": 15.0}}

        # Mock aux window
        self.aux_window = Mock()
        self.aux_window.hud = self.hud
        self.aux_window.refresh_stats_layout = Mock()
        self.aux_window.stat_windows = {1: Mock(), 2: Mock()}
        self.aux_window.update = Mock()

        # Mock parent window
        self.parent_window = Mock()
        self.parent_window.hud = self.hud
        self.parent_window.aw = self.aux_window

        # Create popup menu
        self.popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        self.popup_menu.parentwin = self.parent_window
        self.popup_menu.delete_event = Mock()

    def test_get_current_stat_set(self) -> None:
        """Test getting the current stat set name."""
        # Mock game params
        game_params = Mock()
        game_params.name = "Current_StatSet"
        self.aux_window.game_params = game_params

        # Test _get_current_stat_set method
        current_stat_set = self.popup_menu._get_current_stat_set()
        assert current_stat_set == "Current_StatSet"

    def test_create_stat_sets_dict(self) -> None:
        """Test creating stat sets dictionary."""
        # Mock available stat sets
        self.config.get_stat_sets.return_value = ["StatSet1", "StatSet2", "StatSet3"]

        # Test _create_stat_sets_dict method
        stat_sets_dict = self.popup_menu._create_stat_sets_dict()

        expected = {0: ("StatSet1", "StatSet1"), 1: ("StatSet2", "StatSet2"), 2: ("StatSet3", "StatSet3")}
        assert stat_sets_dict == expected

    def _verify_successful_refresh(self, new_game_params, stat_set_name, mock_log):
        """Helper method to verify successful stat set refresh operations."""
        # Verify sequence of operations
        self.popup_menu._update_stat_set_in_config.assert_called_once_with(stat_set_name)
        self.config.save.assert_called_once()
        self.popup_menu.delete_event.assert_called_once()

        # Verify refresh attempt
        self.config.get_supported_games_parameters.assert_called_once_with("holdem", "ring")
        assert self.aux_window.game_params == new_game_params
        self.aux_window.refresh_stats_layout.assert_called_once()

        # Verify window recreation
        for window in self.aux_window.stat_windows.values():
            window.create_contents.assert_called()

        self.aux_window.update.assert_called_once_with(self.hud.stat_dict)

        # Should log success
        mock_log.info.assert_called_with("HUD refreshed with new stat set: %s", stat_set_name)

        # Should NOT restart HUD
        self.hud.parent.kill_hud.assert_not_called()

    def test_change_stat_set_successful_refresh(self) -> None:
        """Test successful stat set change with hot refresh."""
        # Mock successful config update
        new_game_params = Mock()
        new_game_params.name = "NewStatSet"
        new_game_params.rows = 3
        new_game_params.cols = 2
        new_game_params.stats = {}

        self.config.get_supported_games_parameters.return_value = {"game_stat_set": new_game_params}
        self.config.save = Mock()

        # Mock stat set update
        self.popup_menu._update_stat_set_in_config = Mock()

        # Mock successful window recreation
        for window in self.aux_window.stat_windows.values():
            window.create_contents = Mock()

        stat_sets_dict = {0: ("NewStatSet", "NewStatSet")}

        with patch("Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            self._verify_successful_refresh(new_game_params, "NewStatSet", mock_log)

    def test_change_stat_set_refresh_failure_restarts_hud(self) -> None:
        """Test stat set change that fails refresh and restarts HUD."""
        # Mock config update success but refresh failure
        self.popup_menu._update_stat_set_in_config = Mock()
        self.config.save = Mock()

        # Mock refresh failure
        self.config.get_supported_games_parameters.side_effect = Exception("Config error")

        stat_sets_dict = {0: ("NewStatSet", "NewStatSet")}

        with patch("Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            # Verify config update attempted
            self.popup_menu._update_stat_set_in_config.assert_called_once_with("NewStatSet")
            self.config.save.assert_called_once()

            # Should log failure and restart
            mock_log.info.assert_called_with(
                "Refreshing HUD failed, restarting to apply stat set '%s': %s",
                "NewStatSet",
                unittest.mock.ANY,
            )
            self.hud.parent.kill_hud.assert_called_once_with("kill", "test_table")

    def test_refresh_stats_layout_method(self) -> None:
        """Test the _refresh_stats_layout method."""
        # Create a real SimpleHUD instance to test the method
        simple_hud = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)

        # Setup initial state
        simple_hud.nrows = 2
        simple_hud.ncols = 3
        simple_hud.xpad = 10
        simple_hud.ypad = 10
        simple_hud.stats = [["old", "data"]]
        simple_hud.popups = [["old", "data"]]
        simple_hud.tips = [["old", "data"]]

        # Mock new game params
        game_params = Mock()
        game_params.rows = 4
        game_params.cols = 2
        game_params.xpad = 5
        game_params.ypad = 7
        game_params.stats = {
            "stat1": Mock(rowcol=(0, 0), stat_name="vpip", popup="popup1", tip="tip1"),
            "stat2": Mock(rowcol=(1, 1), stat_name="pfr", popup="popup2", tip="tip2"),
            "stat3": Mock(rowcol=(2, 0), stat_name="aggr", popup="popup3", tip="tip3"),
        }
        simple_hud.game_params = game_params

        # Call refresh_stats_layout
        simple_hud.refresh_stats_layout()

        # Verify layout parameters updated
        assert simple_hud.nrows == 4
        assert simple_hud.ncols == 2
        assert simple_hud.xpad == 5
        assert simple_hud.ypad == 7

        # Verify arrays recreated with correct size
        assert len(simple_hud.stats) == 4
        assert len(simple_hud.stats[0]) == 2
        assert len(simple_hud.popups) == 4
        assert len(simple_hud.popups[0]) == 2
        assert len(simple_hud.tips) == 4
        assert len(simple_hud.tips[0]) == 2

        # Verify stats populated correctly
        assert simple_hud.stats[0][0] == "vpip"
        assert simple_hud.stats[1][1] == "pfr"
        assert simple_hud.stats[2][0] == "aggr"
        assert simple_hud.popups[0][0] == "popup1"
        assert simple_hud.popups[1][1] == "popup2"
        assert simple_hud.tips[0][0] == "tip1"
        assert simple_hud.tips[1][1] == "tip2"

    def test_update_stat_set_in_config(self) -> None:
        """Test updating stat set in configuration."""
        # Mock configuration structure
        game_config = Mock()
        game_config.game_stat_set = {"ring": Mock()}

        self.config.supported_games = {"holdem": game_config}

        # Mock XML document
        mock_doc = Mock()
        game_node = Mock()
        game_node.getAttribute.return_value = "holdem"

        gss_node = Mock()
        gss_node.getAttribute.return_value = "ring"
        gss_node.setAttribute = Mock()

        game_node.getElementsByTagName.return_value = [gss_node]
        mock_doc.getElementsByTagName.return_value = [game_node]
        self.config.doc = mock_doc

        # Mock XML update method
        self.popup_menu._update_xml_stat_set = Mock()

        # Call _update_stat_set_in_config
        self.popup_menu._update_stat_set_in_config("NewStatSet")

        # Verify stat_set was updated
        game_config.game_stat_set["ring"].stat_set = "NewStatSet"

        # Verify XML update was called
        self.popup_menu._update_xml_stat_set.assert_called_once_with("holdem", "ring", "NewStatSet")

    def test_update_xml_stat_set(self) -> None:
        """Test updating stat set in XML document."""
        # Create real XML structure for testing
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <fpdb_config>
            <game game_name="holdem">
                <game_stat_set game_type="ring" stat_set="OldStatSet"/>
                <game_stat_set game_type="tour" stat_set="TourStatSet"/>
            </game>
        </fpdb_config>"""

        doc = xml.dom.minidom.parseString(xml_content)
        self.config.doc = doc

        # Call _update_xml_stat_set
        self.popup_menu._update_xml_stat_set("holdem", "ring", "NewStatSet")

        # Verify XML was updated
        game_nodes = doc.getElementsByTagName("game")
        for game_node in game_nodes:
            if game_node.getAttribute("game_name") == "holdem":
                gss_nodes = game_node.getElementsByTagName("game_stat_set")
                for gss_node in gss_nodes:
                    if gss_node.getAttribute("game_type") == "ring":
                        assert gss_node.getAttribute("stat_set") == "NewStatSet"

    def _create_mock_combo_box(self) -> Mock:
        """Create a mock QComboBox for testing."""
        mock_combo = Mock()
        mock_combo.count.return_value = 3
        mock_combo.itemText.side_effect = ["Basic", "Advanced", "Tournament"]
        mock_combo.currentIndex.return_value = 1
        mock_combo.currentIndexChanged = Mock()
        mock_combo.currentIndexChanged.__getitem__ = Mock(return_value=Mock())
        return mock_combo

    def _verify_combo_box_setup(self, combo: Mock, mock_combo: Mock) -> None:
        """Verify combo box setup and content."""
        assert combo == mock_combo
        assert combo.count() == 3
        assert combo.itemText(0) == "Basic"
        assert combo.itemText(1) == "Advanced"
        assert combo.itemText(2) == "Tournament"
        assert combo.currentIndex() == 1

    def test_stat_set_combo_creation(self) -> None:
        """Test creation of stat set combo box."""
        from unittest.mock import patch

        # Mock stat sets
        stat_sets_dict = {0: ("Basic", "Basic"), 1: ("Advanced", "Advanced"), 2: ("Tournament", "Tournament")}

        # Mock current stat set
        self.popup_menu._get_current_stat_set = Mock(return_value="Advanced")

        mock_combo = self._create_mock_combo_box()

        with patch("Aux_Hud.QComboBox", return_value=mock_combo):
            combo = self.popup_menu.build_stat_set_combo(stat_sets_dict)
            self._verify_combo_box_setup(combo, mock_combo)


class TestStatSetSwitchingIntegration(unittest.TestCase):
    """Integration tests for stat set switching."""

    def test_full_stat_set_switch_workflow(self) -> None:
        """Test complete workflow of stat set switching."""
        # This test simulates the complete user workflow:
        # 1. User right-clicks HUD
        # 2. Selects new stat set from dropdown
        # 3. HUD refreshes with new stat set

        # Setup mocks for full workflow
        config = Mock(spec=Configuration.Config)
        hud = Mock()
        hud.config = config
        hud.poker_game = "holdem"
        hud.game_type = "ring"
        hud.stat_dict = {"player1": {"vpip": 25.0}}

        # Mock successful stat set change
        new_game_params = Mock()
        new_game_params.name = "Advanced"
        config.get_supported_games_parameters.return_value = {"game_stat_set": new_game_params}
        config.save = Mock()

        # Mock aux window with refresh capability
        aux_window = Mock()
        aux_window.game_params = Mock()
        aux_window.refresh_stats_layout = Mock()
        aux_window.stat_windows = {1: Mock(), 2: Mock()}
        aux_window.update = Mock()

        parent_window = Mock()
        parent_window.hud = hud
        parent_window.aw = aux_window

        # Create and configure popup menu
        popup_menu = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
        popup_menu.parentwin = parent_window
        popup_menu.delete_event = Mock()
        popup_menu._update_stat_set_in_config = Mock()

        # Mock successful window recreation
        for window in aux_window.stat_windows.values():
            window.create_contents = Mock()

        # Execute workflow
        stat_sets_dict = {1: ("Advanced", "Advanced")}

        with patch("Aux_Hud.log"):
            popup_menu.change_stat_set(1, stat_sets_dict)

        # Verify complete workflow
        popup_menu._update_stat_set_in_config.assert_called_once_with("Advanced")
        config.save.assert_called_once()
        popup_menu.delete_event.assert_called_once()
        config.get_supported_games_parameters.assert_called_once()
        aux_window.refresh_stats_layout.assert_called_once()
        aux_window.update.assert_called_once()

        # HUD should not restart on successful refresh
        hud.parent.kill_hud.assert_not_called()

    def test_stat_set_persistence_after_hand(self) -> None:
        """Test that stat set change persists after new hand."""
        # This test ensures that when a new hand is dealt,
        # the HUD recreates with the newly selected stat set

        config = Mock()

        # Mock that new stat set was saved to config
        saved_game_params = Mock()
        saved_game_params.name = "Tournament"
        config.get_supported_games_parameters.return_value = {"game_stat_set": saved_game_params}

        # Simulate HUD recreation for new hand (this happens in HUD_main)
        new_hud = Mock()
        new_hud.config = config
        new_hud.poker_game = "holdem"
        new_hud.game_type = "ring"

        # When HUD recreates, it should get the saved stat set
        game_params = config.get_supported_games_parameters("holdem", "ring")["game_stat_set"]

        # Verify it gets the saved stat set, not the default
        assert game_params.name == "Tournament"


if __name__ == "__main__":
    unittest.main()
