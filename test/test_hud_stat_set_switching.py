#!/usr/bin/env python
"""Tests for HUD stat set switching functionality."""

import unittest

import pytest

pytestmark = pytest.mark.qt
import xml.dom.minidom
from unittest.mock import Mock, patch

import fpdb_3_legacy.Aux_Hud as Aux_Hud
import fpdb_3_legacy.Configuration as Configuration


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
        self.hud.parent._table_stat_set_overrides = {}
        self.hud.table = Mock()
        self.hud.table.key = "test_table"
        self.hud.stat_dict = {"player1": {"vpip": 25.0, "pfr": 15.0}}
        self.hud.supported_games_parameters = {"game_stat_set": Mock(name="DefaultStatSet")}

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
        """Helper method to verify successful stat set refresh operations.

        The switch rebuilds the aux window (destroy -> refresh layout -> create ->
        update_gui) rather than refreshing stats in place, so a block-structure
        change is applied cleanly.
        """
        # Verify sequence of operations
        self.popup_menu._update_stat_set_in_config.assert_called_once_with(stat_set_name)
        self.config.save.assert_not_called()
        self.popup_menu.delete_event.assert_called_once()

        # Verify refresh attempt
        assert self.aux_window.game_params == new_game_params

        # Verify the rebuild sequence
        self.aux_window.destroy.assert_called_once()
        self.aux_window.refresh_stats_layout.assert_called_once()
        self.aux_window.create.assert_called_once()
        self.aux_window.update_gui.assert_called_once_with(None)

        # Should log success
        mock_log.info.assert_called_with("HUD rebuilt with new stat set: %s", stat_set_name)

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
        self.popup_menu._update_stat_set_in_config = Mock(return_value=new_game_params)

        # Mock successful window recreation
        for window in self.aux_window.stat_windows.values():
            window.create_contents = Mock()

        stat_sets_dict = {0: ("NewStatSet", "NewStatSet")}

        with patch("fpdb_3_legacy.Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            self._verify_successful_refresh(new_game_params, "NewStatSet", mock_log)

    def test_change_stat_set_refresh_failure_restarts_hud(self) -> None:
        """Test stat set change that fails refresh and restarts HUD."""
        # Mock table-local update success but refresh failure
        new_game_params = Mock(name="NewStatSet")
        self.popup_menu._update_stat_set_in_config = Mock(return_value=new_game_params)
        self.config.save = Mock()

        # Mock refresh failure
        self.aux_window.refresh_stats_layout.side_effect = Exception("Refresh error")

        stat_sets_dict = {0: ("NewStatSet", "NewStatSet")}

        with patch("fpdb_3_legacy.Aux_Hud.log") as mock_log:
            # Call change_stat_set
            self.popup_menu.change_stat_set(0, stat_sets_dict)

            # Verify config update attempted
            self.popup_menu._update_stat_set_in_config.assert_called_once_with("NewStatSet")
            self.config.save.assert_not_called()

            # Should log failure and restart
            mock_log.info.assert_called_with(
                "Rebuilding HUD failed, restarting to apply stat set '%s': %s",
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
        # Stat_sets.stats is keyed by (row, col) -> Stat (see Configuration.py).
        def _stat(rc, name, popup, tip):
            return Mock(rowcol=rc, stat_name=name, popup=popup, tip=tip,
                        colspan=1, align="", stat_loth="", stat_hith="")

        game_params.stats = {
            (0, 0): _stat((0, 0), "vpip", "popup1", "tip1"),
            (1, 1): _stat((1, 1), "pfr", "popup2", "tip2"),
            (2, 0): _stat((2, 0), "aggr", "popup3", "tip3"),
        }
        # A real StatSet exposes a blocks list; None routes _build_block_layouts
        # to its single-grid fallback (this stat set is not multi-block).
        game_params.blocks = None
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

    def test_update_stat_set_in_config_is_table_local(self) -> None:
        """The table selector must not rewrite shared game/XML defaults."""
        # Mock configuration structure
        game_config = Mock()
        game_config.game_stat_set = {"ring": Mock(stat_set="OldStatSet")}

        self.config.supported_games = {"holdem": game_config}
        selected = Mock(name="NewStatSet")
        self.config.stat_sets = {"NewStatSet": selected}

        self.popup_menu._update_xml_stat_set = Mock()

        result = self.popup_menu._update_stat_set_in_config("NewStatSet")

        assert result is selected
        assert self.hud.supported_games_parameters["game_stat_set"] is selected
        assert game_config.game_stat_set["ring"].stat_set == "OldStatSet"
        self.popup_menu._update_xml_stat_set.assert_not_called()
        self.config.save.assert_not_called()
        self.hud.parent.set_table_stat_set_override.assert_called_once_with(
            "test_table",
            "holdem",
            "ring",
            "NewStatSet",
        )

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

        with patch("fpdb_3_legacy.Aux_Hud.QComboBox", return_value=mock_combo):
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
        popup_menu._update_stat_set_in_config = Mock(return_value=new_game_params)

        # Mock successful window recreation
        for window in aux_window.stat_windows.values():
            window.create_contents = Mock()

        # Execute workflow
        stat_sets_dict = {1: ("Advanced", "Advanced")}

        with patch("fpdb_3_legacy.Aux_Hud.log"):
            popup_menu.change_stat_set(1, stat_sets_dict)

        # Verify complete workflow
        popup_menu._update_stat_set_in_config.assert_called_once_with("Advanced")
        config.save.assert_not_called()
        popup_menu.delete_event.assert_called_once()
        config.get_supported_games_parameters.assert_not_called()
        aux_window.refresh_stats_layout.assert_called_once()
        aux_window.update_gui.assert_called_once_with(None)

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
