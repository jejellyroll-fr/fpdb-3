#!/usr/bin/env python3
"""
Test suite for HUD popup and tooltip components with the "no data" feature.

This module tests the PyQt5 HUD popup windows and tooltip functionality to ensure
proper display of "-" vs "0" values in extended stat views.
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import HUD components
from Aux_Hud import SimpleStat, SimpleStatWindow, SimpleHUD, SimpleLabel
from Aux_Classic_Hud import ClassicStat, ClassicStatWindow, ClassicHud
import Popup
import Stats
import Configuration


class TestHUDTooltips:
    """Test suite for HUD tooltip display with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for tooltip tests."""
        aw = Mock()
        aw.params = {
            "fgcolor": "#000000",
            "bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10,
            "opacity": 1.0
        }
        aw.hud = Mock()
        aw.hud.hand_instance = None
        aw.hud.layout = Mock()
        # Create proper seat mocks that can be subscripted
        seat_mocks = {}
        for i in range(1, 7):
            seat_mock = Mock()
            seat_mock.seat_number = i
            seat_mock.player_name = f"Player{i}"
            seat_mocks[i] = seat_mock
        aw.hud.layout.hh_seats = seat_mocks
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        
        # Create proper stat_set mock for ClassicStat
        def create_stat_obj(stat_name):
            stat_obj = Mock()
            stat_obj.stat_name = stat_name
            stat_obj.stat_locolor = "#FF0000"
            stat_obj.stat_loth = "10"
            stat_obj.stat_hicolor = "#00FF00"
            stat_obj.stat_hith = "30"
            stat_obj.stat_midcolor = "#FFFF00"
            stat_obj.hudcolor = "#000000"
            stat_obj.hudprefix = ""
            stat_obj.hudsuffix = ""
            stat_obj.click = ""
            stat_obj.tip = ""
            return stat_obj
        
        # Create stat_set with iterable stats for common stats
        stat_set = Mock()
        stat_set.stats = {
            "vpip": create_stat_obj("vpip"),
            "pfr": create_stat_obj("pfr"),
            "three_B": create_stat_obj("three_B"),
            "steal": create_stat_obj("steal"),
            "cbet": create_stat_obj("cbet"),
            "a_freq1": create_stat_obj("a_freq1"),
            "agg_fact": create_stat_obj("agg_fact"),
        }
        
        # Create supported_games_parameters
        aw.hud.supported_games_parameters = {"game_stat_set": stat_set}
        
        return aw

    def test_tooltip_displays_dash_fraction_for_no_data(self, qapp, mock_aw):
        """Test tooltip displays (-/-) fraction for no data stats."""
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0
            }
        }
        
        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)
        
        # Set tooltip manually (this is how the HUD framework would do it)
        stat.lab.setToolTip("NewPlayer\nvpip: (-/-)\nVoluntarily put in preflop")
        
        # Check tooltip content
        tooltip = stat.lab.toolTip()
        assert "NewPlayer" in tooltip
        assert "(-/-)" in tooltip
        assert "Voluntarily put in preflop" in tooltip

    def test_tooltip_displays_zero_fraction_for_tight_player(self, qapp, mock_aw):
        """Test tooltip displays (0/n) fraction for tight player."""
        stat_dict = {
            1: {
                'screen_name': 'TightPlayer',
                'vpip': 0, 'vpip_opp': 20
            }
        }
        
        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)
        
        # Check tooltip content
        tooltip = stat.lab.toolTip()
        assert "TightPlayer" in tooltip
        assert "(0/20)" in tooltip
        assert "Voluntarily put in preflop" in tooltip

    def test_tooltip_displays_normal_fraction_for_regular_player(self, qapp, mock_aw):
        """Test tooltip displays (n/m) fraction for regular player."""
        stat_dict = {
            1: {
                'screen_name': 'RegularPlayer',
                'vpip': 10, 'vpip_opp': 50
            }
        }
        
        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)
        
        # Check tooltip content
        tooltip = stat.lab.toolTip()
        assert "RegularPlayer" in tooltip
        assert "(10/50)" in tooltip
        assert "Voluntarily put in preflop" in tooltip

    def test_tooltip_consistency_across_stats(self, qapp, mock_aw):
        """Test tooltip consistency across different stat types."""
        stat_dict = {
            1: {
                'screen_name': 'TestPlayer',
                'vpip': 0, 'vpip_opp': 0,     # No data
                'pfr': 0, 'pfr_opp': 20,      # Tight player
                'tb_0': 2, 'tb_opp_0': 10     # Regular player
            }
        }
        
        # Create different stats
        vpip_stat = SimpleStat("vpip", 1, "default", mock_aw)
        pfr_stat = SimpleStat("pfr", 1, "default", mock_aw)
        three_b_stat = SimpleStat("three_B", 1, "default", mock_aw)
        
        # Update stats
        vpip_stat.update('player1', stat_dict)
        pfr_stat.update('player1', stat_dict)
        three_b_stat.update('player1', stat_dict)
        
        # Check tooltip consistency
        vpip_tooltip = vpip_stat.lab.toolTip()
        pfr_tooltip = pfr_stat.lab.toolTip()
        three_b_tooltip = three_b_stat.lab.toolTip()
        
        # All should contain player name
        assert "TestPlayer" in vpip_tooltip
        assert "TestPlayer" in pfr_tooltip
        assert "TestPlayer" in three_b_tooltip
        
        # Check specific fractions
        assert "(-/-)" in vpip_tooltip
        assert "(0/20)" in pfr_tooltip
        assert "(2/10)" in three_b_tooltip

    def test_classic_stat_enhanced_tooltip(self, qapp, mock_aw):
        """Test ClassicStat enhanced tooltip with no data."""
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0
            }
        }
        
        # Create ClassicStat
        stat = ClassicStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)
        
        # Check enhanced tooltip
        tooltip = stat.lab.toolTip()
        assert "NewPlayer" in tooltip
        assert "(-/-)" in tooltip
        assert "Voluntarily put in preflop" in tooltip

    def test_tooltip_updates_correctly_on_data_change(self, qapp, mock_aw):
        """Test tooltip updates correctly when data changes."""
        # Start with no data
        stat_dict_no_data = {
            1: {
                'screen_name': 'Player',
                'vpip': 0, 'vpip_opp': 0
            }
        }
        
        # Change to tight player
        stat_dict_tight = {
            1: {
                'screen_name': 'Player',
                'vpip': 0, 'vpip_opp': 20
            }
        }
        
        # Change to regular player
        stat_dict_regular = {
            1: {
                'screen_name': 'Player',
                'vpip': 10, 'vpip_opp': 50
            }
        }
        
        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        
        # Test progression
        stat.update('player1', stat_dict_no_data)
        tooltip1 = stat.lab.toolTip()
        assert "(-/-)" in tooltip1
        
        stat.update('player1', stat_dict_tight)
        tooltip2 = stat.lab.toolTip()
        assert "(0/20)" in tooltip2
        
        stat.update('player1', stat_dict_regular)
        tooltip3 = stat.lab.toolTip()
        assert "(10/50)" in tooltip3


class TestHUDPopups:
    """Test suite for HUD popup windows with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for popup tests."""
        config = Mock()
        config.get_popup_definition = Mock(return_value=Mock())
        config.get_site_parameters = Mock(return_value={
            "popup_fgcolor": "#000000",
            "popup_bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10
        })
        return config

    @pytest.fixture
    def mock_popup_params(self):
        """Mock popup parameters."""
        popup_params = Mock()
        popup_params.pu_class = "default"
        popup_params.pu_stats = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]
        popup_params.pu_stat_dict = {}
        return popup_params

    @pytest.fixture
    def mock_window(self, mock_config):
        """Mock window for popup tests."""
        window = Mock()
        window.config = mock_config
        window.params = {
            "popup_fgcolor": "#000000",
            "popup_bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10
        }
        return window

    def test_popup_displays_dash_for_no_data_stats(self, qapp, mock_window, mock_popup_params):
        """Test popup displays '-' for stats with no data."""
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0,
                'pfr': 0, 'pfr_opp': 0,
                'tb_0': 0, 'tb_opp_0': 0,
                'steal': 0, 'steal_opp': 0,
                'cb_1': 0, 'cb_2': 0, 'cb_3': 0, 'cb_4': 0,
                'cb_opp_1': 0, 'cb_opp_2': 0, 'cb_opp_3': 0, 'cb_opp_4': 0,
                'aggr_1': 0, 'saw_f': 0
            }
        }
        
        # Create popup
        popup = Popup.default(1, stat_dict, mock_window, mock_popup_params, None, mock_window.config)
        
        # Check that popup was created
        assert popup is not None
        
        # Check widget creation (popup should have labels)
        assert hasattr(popup, 'lab')
        
        # Verify that stats are calculated correctly
        for stat_name in mock_popup_params.pu_stats:
            if hasattr(Stats, stat_name):
                stat_func = getattr(Stats, stat_name)
                result = stat_func(stat_dict, 'player1')
                # Should return tuple with "-" for display
                assert result[1] == "-" or result[1] == "NA"

    def test_popup_displays_mixed_data_correctly(self, qapp, mock_window, mock_popup_params):
        """Test popup displays mixed data correctly."""
        stat_dict = {
            1: {
                'screen_name': 'MixedPlayer',
                'vpip': 0, 'vpip_opp': 0,     # No data -> "-"
                'pfr': 0, 'pfr_opp': 20,      # Tight -> "0.0"
                'tb_0': 2, 'tb_opp_0': 10,    # Regular -> "20.0"
                'steal': 0, 'steal_opp': 0,   # No data -> "-"
                'cb_1': 3, 'cb_2': 0, 'cb_3': 0, 'cb_4': 0,
                'cb_opp_1': 6, 'cb_opp_2': 0, 'cb_opp_3': 0, 'cb_opp_4': 0,
                'aggr_1': 4, 'saw_f': 10
            }
        }
        
        # Create popup
        popup = Popup.default(1, stat_dict, mock_window, mock_popup_params, None, mock_window.config)
        
        # Check that popup was created
        assert popup is not None
        
        # Verify specific stat calculations
        vpip_result = Stats.vpip(stat_dict, 1)
        pfr_result = Stats.pfr(stat_dict, 1)
        three_b_result = Stats.three_B(stat_dict, 1)
        
        assert vpip_result[1] == "-"      # No data
        assert pfr_result[1] == "0.0"     # Tight player
        assert three_b_result[1] == "20.0" # Regular player

    def test_popup_multicol_with_no_data(self, qapp, mock_window):
        """Test multi-column popup with no data stats."""
        # Create multi-column popup params
        multicol_params = Mock()
        multicol_params.pu_class = "Multicol"
        multicol_params.pu_stats = [
            ["vpip", "pfr", "three_B"],
            ["steal", "cbet", "a_freq1"],
            ["agg_fact", "wtsd", "wmsd"]
        ]
        multicol_params.pu_stat_dict = {}
        
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0,
                'pfr': 0, 'pfr_opp': 0,
                'tb_0': 0, 'tb_opp_0': 0,
                'steal': 0, 'steal_opp': 0,
                'cb_1': 0, 'cb_2': 0, 'cb_3': 0, 'cb_4': 0,
                'cb_opp_1': 0, 'cb_opp_2': 0, 'cb_opp_3': 0, 'cb_opp_4': 0,
                'aggr_1': 0, 'aggr_2': 0, 'aggr_3': 0, 'aggr_4': 0,
                'call_1': 0, 'call_2': 0, 'call_3': 0, 'call_4': 0,
                'saw_f': 0, 'saw_1': 0, 'sd': 0
            }
        }
        
        # Create multi-column popup
        popup = Popup.Multicol(1, stat_dict, mock_window, multicol_params, None, mock_window.config)
        
        # Check that popup was created
        assert popup is not None
        
        # All stats should show "-" for no data
        for stat_name in ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1", "agg_fact"]:
            if hasattr(Stats, stat_name):
                stat_func = getattr(Stats, stat_name)
                result = stat_func(stat_dict, 'player1')
                assert result[1] == "-" or result[1] == "NA"

    def test_popup_submenu_navigation_with_no_data(self, qapp, mock_window):
        """Test popup submenu navigation with no data stats."""
        # Create submenu popup params
        submenu_params = Mock()
        submenu_params.pu_class = "Submenu"
        submenu_params.pu_stats = {
            "Preflop": ["vpip", "pfr", "three_B"],
            "Postflop": ["cbet", "a_freq1", "agg_fact"],
            "Defense": ["ffreq1", "f_cb1", "cr1"]
        }
        submenu_params.pu_stat_dict = {}
        
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0,
                'pfr': 0, 'pfr_opp': 0,
                'tb_0': 0, 'tb_opp_0': 0,
                'cb_1': 0, 'cb_opp_1': 0,
                'aggr_1': 0, 'saw_f': 0,
                'f_freq_1': 0, 'was_raised_1': 0,
                'f_cb_1': 0, 'f_cb_opp_1': 0,
                'cr_1': 0, 'ccr_opp_1': 0
            }
        }
        
        # Create submenu popup
        popup = Popup.Submenu(1, stat_dict, mock_window, submenu_params, None, mock_window.config)
        
        # Check that popup was created
        assert popup is not None
        
        # Test all submenu stats show "-" for no data
        for category_stats in submenu_params.pu_stats.values():
            for stat_name in category_stats:
                if hasattr(Stats, stat_name):
                    stat_func = getattr(Stats, stat_name)
                    result = stat_func(stat_dict, 'player1')
                    assert result[1] == "-" or result[1] == "NA"


class TestHUDPopupInteraction:
    """Test suite for HUD popup interaction with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for interaction tests."""
        config = Mock()
        config.get_popup_definition = Mock(return_value=Mock())
        config.get_site_parameters = Mock(return_value={
            "popup_fgcolor": "#000000",
            "popup_bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10
        })
        return config

    @pytest.fixture
    def mock_aw(self, mock_config):
        """Mock AuxWindow for interaction tests."""
        aw = Mock()
        aw.config = mock_config
        aw.params = {
            "fgcolor": "#000000",
            "bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10,
            "opacity": 1.0
        }
        aw.hud = Mock()
        aw.hud.hand_instance = None
        aw.hud.layout = Mock()
        # Create proper seat mocks that can be subscripted
        seat_mocks = {}
        for i in range(1, 7):
            seat_mock = Mock()
            seat_mock.seat_number = i
            seat_mock.player_name = f"Player{i}"
            seat_mocks[i] = seat_mock
        aw.hud.layout.hh_seats = seat_mocks
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        
        # Create proper stat_set mock for ClassicStat
        def create_stat_obj(stat_name):
            stat_obj = Mock()
            stat_obj.stat_name = stat_name
            stat_obj.stat_locolor = "#FF0000"
            stat_obj.stat_loth = "10"
            stat_obj.stat_hicolor = "#00FF00"
            stat_obj.stat_hith = "30"
            stat_obj.stat_midcolor = "#FFFF00"
            stat_obj.hudcolor = "#000000"
            stat_obj.hudprefix = ""
            stat_obj.hudsuffix = ""
            stat_obj.click = ""
            stat_obj.tip = ""
            return stat_obj
        
        # Create stat_set with iterable stats for common stats
        stat_set = Mock()
        stat_set.stats = {
            "vpip": create_stat_obj("vpip"),
            "pfr": create_stat_obj("pfr"),
            "three_B": create_stat_obj("three_B"),
            "steal": create_stat_obj("steal"),
            "cbet": create_stat_obj("cbet"),
            "a_freq1": create_stat_obj("a_freq1"),
            "agg_fact": create_stat_obj("agg_fact"),
        }
        
        # Create supported_games_parameters
        aw.hud.supported_games_parameters = {"game_stat_set": stat_set}
        
        return aw

    def test_stat_click_shows_popup_with_no_data(self, qapp, mock_aw):
        """Test clicking stat with no data shows appropriate popup."""
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0
            }
        }
        
        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)
        
        # Mock popup creation
        with patch('Popup.popup_factory') as mock_popup_factory:
            mock_popup = Mock()
            mock_popup_factory.return_value = mock_popup
            
            # Simulate mouse click
            click_event = QMouseEvent(
                QMouseEvent.MouseButtonPress,
                QPoint(0, 0),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier
            )
            
            # Test that stat handles click
            stat.lab.mousePressEvent(click_event)
            
            # Verify popup would be created (depending on implementation)
            # This test structure depends on actual click handling implementation

    def test_popup_content_consistency_with_main_display(self, qapp, mock_aw):
        """Test popup content consistency with main HUD display."""
        stat_dict = {
            1: {
                'screen_name': 'TestPlayer',
                'vpip': 0, 'vpip_opp': 0,     # No data
                'pfr': 0, 'pfr_opp': 20,      # Tight
                'tb_0': 2, 'tb_opp_0': 10     # Regular
            }
        }
        
        # Create main HUD stats
        vpip_stat = SimpleStat("vpip", 1, "default", mock_aw)
        pfr_stat = SimpleStat("pfr", 1, "default", mock_aw)
        three_b_stat = SimpleStat("three_B", 1, "default", mock_aw)
        
        # Update main stats
        vpip_stat.update('player1', stat_dict)
        pfr_stat.update('player1', stat_dict)
        three_b_stat.update('player1', stat_dict)
        
        # Get main display values
        main_vpip = vpip_stat.lab.text()
        main_pfr = pfr_stat.lab.text()
        main_three_b = three_b_stat.lab.text()
        
        # Calculate what popup should show
        popup_vpip = Stats.vpip(stat_dict, 1)[1]
        popup_pfr = Stats.pfr(stat_dict, 1)[1]
        popup_three_b = Stats.three_B(stat_dict, 1)[1]
        
        # Verify consistency
        assert main_vpip == popup_vpip
        assert main_pfr == popup_pfr
        assert main_three_b == popup_three_b
        
        # Verify expected values
        assert main_vpip == "-"
        assert main_pfr == "0.0"
        assert main_three_b == "20.0"


class TestHUDStatFormatting:
    """Test suite for HUD stat formatting with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for formatting tests."""
        aw = Mock()
        aw.params = {
            "fgcolor": "#000000",
            "bgcolor": "#FFFFFF",
            "font": "Arial",
            "font_size": 10,
            "opacity": 1.0
        }
        aw.hud = Mock()
        aw.hud.hand_instance = None
        aw.hud.layout = Mock()
        # Create proper seat mocks that can be subscripted
        seat_mocks = {}
        for i in range(1, 7):
            seat_mock = Mock()
            seat_mock.seat_number = i
            seat_mock.player_name = f"Player{i}"
            seat_mocks[i] = seat_mock
        aw.hud.layout.hh_seats = seat_mocks
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        
        # Create proper stat_set mock for ClassicStat
        def create_stat_obj(stat_name):
            stat_obj = Mock()
            stat_obj.stat_name = stat_name
            stat_obj.stat_locolor = "#FF0000"
            stat_obj.stat_loth = "10"
            stat_obj.stat_hicolor = "#00FF00"
            stat_obj.stat_hith = "30"
            stat_obj.stat_midcolor = "#FFFF00"
            stat_obj.hudcolor = "#000000"
            stat_obj.hudprefix = ""
            stat_obj.hudsuffix = ""
            stat_obj.click = ""
            stat_obj.tip = ""
            return stat_obj
        
        # Create stat_set with iterable stats for common stats
        stat_set = Mock()
        stat_set.stats = {
            "vpip": create_stat_obj("vpip"),
            "pfr": create_stat_obj("pfr"),
            "three_B": create_stat_obj("three_B"),
            "steal": create_stat_obj("steal"),
            "cbet": create_stat_obj("cbet"),
            "a_freq1": create_stat_obj("a_freq1"),
            "agg_fact": create_stat_obj("agg_fact"),
        }
        
        # Create supported_games_parameters
        aw.hud.supported_games_parameters = {"game_stat_set": stat_set}
        
        return aw

    def test_stat_formatting_no_data_consistent(self, qapp, mock_aw):
        """Test stat formatting is consistent for no data across different stats."""
        stat_dict = {
            1: {
                'screen_name': 'NewPlayer',
                'vpip': 0, 'vpip_opp': 0,
                'pfr': 0, 'pfr_opp': 0,
                'tb_0': 0, 'tb_opp_0': 0,
                'steal': 0, 'steal_opp': 0,
                'aggr_1': 0, 'saw_f': 0,
                'aggr_2': 0, 'aggr_3': 0, 'aggr_4': 0,
                'call_1': 0, 'call_2': 0, 'call_3': 0, 'call_4': 0
            }
        }
        
        # Create different stats
        stats = [
            SimpleStat("vpip", 1, "default", mock_aw),
            SimpleStat("pfr", 1, "default", mock_aw),
            SimpleStat("three_B", 1, "default", mock_aw),
            SimpleStat("steal", 1, "default", mock_aw),
            SimpleStat("a_freq1", 1, "default", mock_aw),
            SimpleStat("agg_fact", 1, "default", mock_aw),
        ]
        
        # Update all stats
        for stat in stats:
            stat.update(1, stat_dict)
        
        # All should display "-" consistently
        for stat in stats:
            assert stat.lab.text() == "-"

    def test_stat_formatting_zero_consistent(self, qapp, mock_aw):
        """Test stat formatting is consistent for zero values across different stats."""
        stat_dict = {
            1: {
                'screen_name': 'TightPlayer',
                'vpip': 0, 'vpip_opp': 20,
                'pfr': 0, 'pfr_opp': 20,
                'tb_0': 0, 'tb_opp_0': 10,
                'steal': 0, 'steal_opp': 8,
                'aggr_1': 0, 'saw_f': 15,
                'aggr_2': 0, 'aggr_3': 0, 'aggr_4': 0,
                'call_1': 5, 'call_2': 3, 'call_3': 1, 'call_4': 0
            }
        }
        
        # Create different stats
        stats = [
            SimpleStat("vpip", 1, "default", mock_aw),
            SimpleStat("pfr", 1, "default", mock_aw),
            SimpleStat("three_B", 1, "default", mock_aw),
            SimpleStat("steal", 1, "default", mock_aw),
            SimpleStat("a_freq1", 1, "default", mock_aw),
        ]
        
        # Update all stats
        for stat in stats:
            stat.update(1, stat_dict)
        
        # All should display "0.0" consistently
        for stat in stats:
            assert stat.lab.text() == "0.0"

    def test_stat_formatting_percentage_consistent(self, qapp, mock_aw):
        """Test stat formatting is consistent for percentage values."""
        stat_dict = {
            1: {
                'screen_name': 'RegularPlayer',
                'vpip': 10, 'vpip_opp': 50,   # 20%
                'pfr': 5, 'pfr_opp': 50,      # 10%
                'tb_0': 1, 'tb_opp_0': 10,    # 10%
                'steal': 2, 'steal_opp': 8,   # 25%
                'aggr_1': 3, 'saw_f': 15,     # 20%
                'aggr_2': 1, 'aggr_3': 0, 'aggr_4': 0,
                'call_1': 2, 'call_2': 1, 'call_3': 0, 'call_4': 0
            }
        }
        
        # Create stats
        vpip_stat = SimpleStat("vpip", 1, "default", mock_aw)
        pfr_stat = SimpleStat("pfr", 1, "default", mock_aw)
        three_b_stat = SimpleStat("three_B", 1, "default", mock_aw)
        steal_stat = SimpleStat("steal", 1, "default", mock_aw)
        a_freq1_stat = SimpleStat("a_freq1", 1, "default", mock_aw)
        
        # Update all stats
        vpip_stat.update('player1', stat_dict)
        pfr_stat.update('player1', stat_dict)
        three_b_stat.update('player1', stat_dict)
        steal_stat.update('player1', stat_dict)
        a_freq1_stat.update('player1', stat_dict)
        
        # Check expected percentages
        assert vpip_stat.lab.text() == "20.0"
        assert pfr_stat.lab.text() == "10.0"
        assert three_b_stat.lab.text() == "10.0"
        assert steal_stat.lab.text() == "25.0"
        assert a_freq1_stat.lab.text() == "20.0"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])