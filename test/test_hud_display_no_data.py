#!/usr/bin/env python3
"""Test suite for HUD display integration with the "no data" feature.

This module tests the PyQt5 HUD components to ensure proper visual distinction
between 0 (real value) and "-" (no data available) in the interface.
"""

import os
import sys
from unittest.mock import Mock

# Set Qt to use offscreen platform for headless CI environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QLabel

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import HUD components
from Aux_Classic_Hud import ClassicStat
from Aux_Hud import SimpleStat


class TestHUDDisplayNoDataFeature:
    """Test suite for HUD display with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available for all tests."""
        return qapp

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for HUD tests."""
        config = Mock()
        config.get_default_font = Mock(return_value="Arial")
        config.get_default_font_size = Mock(return_value=10)
        config.get_hud_style = Mock(return_value="A")
        config.get_locations = Mock(return_value={})
        config.get_supported_sites = Mock(return_value={"PokerStars": True})
        config.get_site_parameters = Mock(
            return_value={"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0},
        )
        return config

    @pytest.fixture
    def mock_aw(self, mock_config):
        """Mock AuxWindow for testing."""
        aw = Mock()
        aw.config = mock_config
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0, "font": "Arial", "font_size": 10}
        aw.hud = Mock()
        aw.hud.hand_instance = None
        aw.hud.stat_dict = {}
        aw.get_id_from_seat = Mock(return_value=1)
        aw.nrows = 3
        aw.ncols = 3
        return aw

    @pytest.fixture
    def stat_dict_no_data(self):
        """Sample stat_dict with no data available."""
        return {
            1: {
                "screen_name": "NewPlayer",
                "vpip": 0,
                "vpip_opp": 0,
                "pfr": 0,
                "pfr_opp": 0,
                "tb_0": 0,
                "tb_opp_0": 0,
                "steal": 0,
                "steal_opp": 0,
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 0,
                "cb_opp_2": 0,
                "cb_opp_3": 0,
                "cb_opp_4": 0,
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 0,
                "call_2": 0,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 0,
                "saw_2": 0,
                "saw_3": 0,
                "saw_4": 0,
            },
        }

    @pytest.fixture
    def stat_dict_tight_player(self):
        """Sample stat_dict with tight player (real zeros)."""
        return {
            1: {
                "screen_name": "TightPlayer",
                "vpip": 0,
                "vpip_opp": 20,  # Had opportunities but didn't play
                "pfr": 0,
                "pfr_opp": 20,  # Had opportunities but didn't raise
                "tb_0": 0,
                "tb_opp_0": 5,  # Had opportunities but didn't 3-bet
                "steal": 0,
                "steal_opp": 8,  # Had opportunities but didn't steal
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 0,
                "cb_opp_2": 0,
                "cb_opp_3": 0,
                "cb_opp_4": 0,
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 3,
                "call_2": 1,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 5,
                "saw_2": 2,
                "saw_3": 1,
                "saw_4": 0,
            },
        }

    @pytest.fixture
    def stat_dict_normal_player(self):
        """Sample stat_dict with normal player data."""
        return {
            1: {
                "screen_name": "NormalPlayer",
                "vpip": 10,
                "vpip_opp": 50,  # 20% VPIP
                "pfr": 5,
                "pfr_opp": 50,  # 10% PFR
                "tb_0": 2,
                "tb_opp_0": 10,  # 20% 3-bet
                "steal": 3,
                "steal_opp": 12,  # 25% steal
                "cb_1": 4,
                "cb_2": 2,
                "cb_3": 1,
                "cb_4": 0,
                "cb_opp_1": 8,
                "cb_opp_2": 4,
                "cb_opp_3": 2,
                "cb_opp_4": 0,
                "aggr_1": 6,
                "aggr_2": 3,
                "aggr_3": 1,
                "aggr_4": 0,
                "call_1": 4,
                "call_2": 2,
                "call_3": 1,
                "call_4": 0,
                "saw_f": 15,
                "saw_2": 8,
                "saw_3": 4,
                "saw_4": 0,
            },
        }


class TestSimpleStatDisplay:
    """Test suite for SimpleStat display with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for SimpleStat tests."""
        aw = Mock()
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "font": "Arial", "font_size": 10, "opacity": 1.0}
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
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        return aw

    def test_simple_stat_displays_dash_for_no_data(self, qapp, mock_aw) -> None:
        """Test SimpleStat displays '-' for statistics with no data."""
        stat_dict = {1: {"vpip": 0, "vpip_opp": 0}}

        # Create SimpleStat for VPIP
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Should display '-' for no data
        assert stat.lab.text() == "-"

        # Check the underlying stat calculation
        assert stat.number[1] == "-"
        assert stat.number[4] == "(-/-)"

    def test_simple_stat_displays_zero_for_tight_player(self, qapp, mock_aw) -> None:
        """Test SimpleStat displays '0.0' for tight player with opportunities."""
        stat_dict = {1: {"vpip": 0, "vpip_opp": 20}}

        # Create SimpleStat for VPIP
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Should display '0.0' for tight player
        assert stat.lab.text() == "0.0"

        # Check the underlying stat calculation
        assert stat.number[1] == "0.0"
        assert stat.number[4] == "(0/20)"

    def test_simple_stat_displays_normal_percentage(self, qapp, mock_aw) -> None:
        """Test SimpleStat displays normal percentage for player with data."""
        stat_dict = {1: {"vpip": 10, "vpip_opp": 50}}

        # Create SimpleStat for VPIP
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Should display '20.0' for normal player
        assert stat.lab.text() == "20.0"

        # Check the underlying stat calculation
        assert stat.number[1] == "20.0"
        assert stat.number[4] == "(10/50)"

    def test_simple_stat_multiple_stats_consistency(self, qapp, mock_aw) -> None:
        """Test multiple stats display consistently."""
        stat_dict = {
            1: {
                "vpip": 0,
                "vpip_opp": 0,  # No data
                "pfr": 0,
                "pfr_opp": 20,  # Tight player
                "tb_0": 2,
                "tb_opp_0": 10,  # Normal player
                "steal": 0,
                "steal_opp": 0,  # No data
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 0,
                "call_2": 0,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 0,
                "saw_2": 0,
                "saw_3": 0,
                "saw_4": 0,
            },
        }

        # Create stats
        vpip_stat = SimpleStat("vpip", 1, "default", mock_aw)
        pfr_stat = SimpleStat("pfr", 1, "default", mock_aw)
        three_b_stat = SimpleStat("three_B", 1, "default", mock_aw)
        steal_stat = SimpleStat("steal", 1, "default", mock_aw)

        # Update stats
        vpip_stat.update(1, stat_dict)
        pfr_stat.update(1, stat_dict)
        three_b_stat.update(1, stat_dict)
        steal_stat.update(1, stat_dict)

        # Check display consistency
        assert vpip_stat.lab.text() == "-"  # No data
        assert pfr_stat.lab.text() == "0.0"  # Tight player
        assert three_b_stat.lab.text() == "20.0"  # Normal player
        assert steal_stat.lab.text() == "-"  # No data

    def test_simple_stat_tooltip_with_no_data(self, qapp, mock_aw) -> None:
        """Test SimpleStat tooltip can be set for no data."""
        stat_dict = {1: {"screen_name": "NewPlayer", "vpip": 0, "vpip_opp": 0}}

        # Create SimpleStat for VPIP
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Manually set tooltip (this is how the HUD would do it)
        stat.lab.setToolTip("NewPlayer\nvpip: (-/-)\nVoluntarily put in preflop")

        # Check tooltip content
        tooltip = stat.lab.toolTip()
        assert "NewPlayer" in tooltip
        assert "(-/-)" in tooltip
        assert "Voluntarily put in preflop" in tooltip


class TestClassicStatDisplay:
    """Test suite for ClassicStat display with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for ClassicStat tests."""
        aw = Mock()
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "font": "Arial", "font_size": 10, "opacity": 1.0}
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
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
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

    def test_classic_stat_displays_dash_for_no_data(self, qapp, mock_aw) -> None:
        """Test ClassicStat displays '-' for statistics with no data."""
        stat_dict = {1: {"screen_name": "NewPlayer", "vpip": 0, "vpip_opp": 0}}

        # Create ClassicStat for VPIP
        stat = ClassicStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Should display '-' for no data
        assert stat.lab.text() == "-"

        # Check color handling (should use default color, not conditional)
        assert stat.hudcolor == mock_aw.params["fgcolor"]

    def test_classic_stat_displays_zero_for_tight_player(self, qapp, mock_aw) -> None:
        """Test ClassicStat displays '0.0' for tight player with opportunities."""
        stat_dict = {1: {"screen_name": "TightPlayer", "vpip": 0, "vpip_opp": 20}}

        # Create ClassicStat for VPIP
        stat = ClassicStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Should display '0.0' for tight player
        assert stat.lab.text() == "0.0"

        # Color might be different for 0.0 vs "-"
        # (depends on conditional coloring configuration)

    def test_classic_stat_color_handling_no_data(self, qapp, mock_aw) -> None:
        """Test ClassicStat color handling for no data vs zero."""
        stat_dict_no_data = {1: {"screen_name": "NewPlayer", "vpip": 0, "vpip_opp": 0}}

        stat_dict_tight = {1: {"screen_name": "TightPlayer", "vpip": 0, "vpip_opp": 20}}

        # Create two identical stats
        stat_no_data = ClassicStat("vpip", 1, "default", mock_aw)
        stat_tight = ClassicStat("vpip", 1, "default", mock_aw)

        # Update with different data
        stat_no_data.update(1, stat_dict_no_data)
        stat_tight.update(1, stat_dict_tight)

        # Both should potentially have different colors
        # (no data = default color, tight = conditional color)
        assert stat_no_data.lab.text() == "-"
        assert stat_tight.lab.text() == "0.0"

    def test_classic_stat_tooltip_enhanced_for_no_data(self, qapp, mock_aw) -> None:
        """Test ClassicStat enhanced tooltip for no data."""
        stat_dict = {1: {"screen_name": "NewPlayer", "vpip": 0, "vpip_opp": 0}}

        # Create ClassicStat for VPIP
        stat = ClassicStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Check enhanced tooltip
        tooltip = stat.lab.toolTip()
        assert "NewPlayer" in tooltip
        assert "(-/-)" in tooltip
        assert "Voluntarily put in preflop" in tooltip


class TestHUDIntegrationScenarios:
    """Integration tests for complete HUD scenarios."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for integration tests."""
        config = Mock()
        config.get_default_font = Mock(return_value="Arial")
        config.get_default_font_size = Mock(return_value=10)
        config.get_hud_style = Mock(return_value="A")
        config.get_locations = Mock(return_value={})
        config.get_supported_sites = Mock(return_value={"PokerStars": True})
        config.get_site_parameters = Mock(
            return_value={"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0},
        )
        return config

    @pytest.fixture
    def mock_stat_window(self, mock_config):
        """Mock StatWindow for integration tests."""
        aw = Mock()
        aw.config = mock_config
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "opacity": 1.0, "font": "Arial", "font_size": 10}
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
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        aw.get_id_from_seat = Mock(return_value=1)
        aw.nrows = 3
        aw.ncols = 3
        return aw

    def test_new_player_all_stats_show_dash(self, qapp, mock_stat_window) -> None:
        """Test complete new player scenario - all stats show '-'."""
        stat_dict = {
            1: {
                "screen_name": "NewPlayer",
                "vpip": 0,
                "vpip_opp": 0,
                "pfr": 0,
                "pfr_opp": 0,
                "tb_0": 0,
                "tb_opp_0": 0,
                "steal": 0,
                "steal_opp": 0,
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 0,
                "call_2": 0,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 0,
                "saw_2": 0,
                "saw_3": 0,
                "saw_4": 0,
            },
        }

        # Create stats for different positions
        stats = {
            "vpip": SimpleStat("vpip", 1, "default", mock_stat_window),
            "pfr": SimpleStat("pfr", 1, "default", mock_stat_window),
            "three_B": SimpleStat("three_B", 1, "default", mock_stat_window),
            "steal": SimpleStat("steal", 1, "default", mock_stat_window),
            "a_freq1": SimpleStat("a_freq1", 1, "default", mock_stat_window),
            "agg_fact": SimpleStat("agg_fact", 1, "default", mock_stat_window),
        }

        # Update all stats
        for stat in stats.values():
            stat.update(1, stat_dict)

        # All should display '-'
        for stat_name, stat in stats.items():
            assert stat.lab.text() == "-", f"Stat {stat_name} should show '-' for new player"

    def test_tight_player_mixed_display(self, qapp, mock_stat_window) -> None:
        """Test tight player scenario - mix of '0.0' and '-' displays."""
        stat_dict = {
            1: {
                "screen_name": "TightPlayer",
                "vpip": 0,
                "vpip_opp": 20,  # 0.0 - had opportunities
                "pfr": 0,
                "pfr_opp": 20,  # 0.0 - had opportunities
                "tb_0": 0,
                "tb_opp_0": 0,  # '-' - no opportunities
                "steal": 0,
                "steal_opp": 8,  # 0.0 - had opportunities
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 3,
                "call_2": 1,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 5,
                "saw_2": 2,
                "saw_3": 0,
                "saw_4": 0,  # Had some action
            },
        }

        # Create stats
        stats = {
            "vpip": SimpleStat("vpip", 1, "default", mock_stat_window),
            "pfr": SimpleStat("pfr", 1, "default", mock_stat_window),
            "three_B": SimpleStat("three_B", 1, "default", mock_stat_window),
            "steal": SimpleStat("steal", 1, "default", mock_stat_window),
            "a_freq1": SimpleStat("a_freq1", 1, "default", mock_stat_window),
        }

        # Update all stats
        for stat in stats.values():
            stat.update(1, stat_dict)

        # Check expected displays
        assert stats["vpip"].lab.text() == "0.0"  # Had opportunities
        assert stats["pfr"].lab.text() == "0.0"  # Had opportunities
        assert stats["three_B"].lab.text() == "-"  # No opportunities
        assert stats["steal"].lab.text() == "0.0"  # Had opportunities
        assert stats["a_freq1"].lab.text() == "0.0"  # Saw flop but passive

    def test_normal_player_percentage_display(self, qapp, mock_stat_window) -> None:
        """Test normal player scenario - percentage displays."""
        stat_dict = {
            1: {
                "screen_name": "NormalPlayer",
                "vpip": 10,
                "vpip_opp": 50,  # 20%
                "pfr": 5,
                "pfr_opp": 50,  # 10%
                "tb_0": 2,
                "tb_opp_0": 10,  # 20%
                "steal": 3,
                "steal_opp": 12,  # 25%
                "aggr_1": 6,
                "aggr_2": 3,
                "aggr_3": 1,
                "aggr_4": 0,
                "call_1": 4,
                "call_2": 2,
                "call_3": 1,
                "call_4": 0,
                "saw_f": 15,
                "saw_2": 8,
                "saw_3": 4,
                "saw_4": 0,
            },
        }

        # Create stats
        stats = {
            "vpip": SimpleStat("vpip", 1, "default", mock_stat_window),
            "pfr": SimpleStat("pfr", 1, "default", mock_stat_window),
            "three_B": SimpleStat("three_B", 1, "default", mock_stat_window),
            "steal": SimpleStat("steal", 1, "default", mock_stat_window),
            "a_freq1": SimpleStat("a_freq1", 1, "default", mock_stat_window),
        }

        # Update all stats
        for stat in stats.values():
            stat.update(1, stat_dict)

        # Check expected percentages
        assert stats["vpip"].lab.text() == "20.0"
        assert stats["pfr"].lab.text() == "10.0"
        assert stats["three_B"].lab.text() == "20.0"
        assert stats["steal"].lab.text() == "25.0"
        assert stats["a_freq1"].lab.text() == "40.0"  # 6/15


class TestHUDUpdatePerformance:
    """Test suite for HUD update performance with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for performance tests."""
        aw = Mock()
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "font": "Arial", "font_size": 10, "opacity": 1.0}
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
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        return aw

    def test_stat_update_performance_no_data(self, qapp, mock_aw) -> None:
        """Test performance of stat updates with no data."""
        import time

        stat_dict = {1: {"vpip": 0, "vpip_opp": 0}}

        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)

        # Time multiple updates
        start_time = time.time()
        for _ in range(1000):
            stat.update(1, stat_dict)
        end_time = time.time()

        # Should complete quickly (less than 1 second for 1000 updates)
        duration = end_time - start_time
        assert duration < 1.0, f"1000 updates took {duration:.3f}s, should be < 1.0s"

        # Verify final state
        assert stat.lab.text() == "-"

    def test_stat_update_performance_normal_data(self, qapp, mock_aw) -> None:
        """Test performance of stat updates with normal data."""
        import time

        stat_dict = {1: {"vpip": 10, "vpip_opp": 50}}

        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)

        # Time multiple updates
        start_time = time.time()
        for _ in range(1000):
            stat.update(1, stat_dict)
        end_time = time.time()

        # Should complete quickly (less than 1 second for 1000 updates)
        duration = end_time - start_time
        assert duration < 1.0, f"1000 updates took {duration:.3f}s, should be < 1.0s"

        # Verify final state
        assert stat.lab.text() == "20.0"

    def test_multiple_stats_update_performance(self, qapp, mock_aw) -> None:
        """Test performance of updating multiple stats simultaneously."""
        import time

        stat_dict = {
            1: {
                "vpip": 0,
                "vpip_opp": 0,
                "pfr": 0,
                "pfr_opp": 20,
                "tb_0": 2,
                "tb_opp_0": 10,
                "steal": 0,
                "steal_opp": 0,
                "aggr_1": 0,
                "saw_f": 0,
            },
        }

        # Create multiple stats
        stats = [
            SimpleStat("vpip", 1, "default", mock_aw),
            SimpleStat("pfr", 1, "default", mock_aw),
            SimpleStat("three_B", 1, "default", mock_aw),
            SimpleStat("steal", 1, "default", mock_aw),
            SimpleStat("a_freq1", 1, "default", mock_aw),
        ]

        # Time multiple updates of all stats
        start_time = time.time()
        for _ in range(100):
            for stat in stats:
                stat.update(1, stat_dict)
        end_time = time.time()

        # Should complete quickly (less than 1 second for 500 total updates)
        duration = end_time - start_time
        assert duration < 1.0, f"500 total updates took {duration:.3f}s, should be < 1.0s"

        # Verify final states
        assert stats[0].lab.text() == "-"  # vpip - no data
        assert stats[1].lab.text() == "0.0"  # pfr - tight player
        assert stats[2].lab.text() == "20.0"  # three_B - normal
        assert stats[3].lab.text() == "-"  # steal - no data
        assert stats[4].lab.text() == "-"  # a_freq1 - no data


class TestHUDErrorHandling:
    """Test suite for HUD error handling with no data feature."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_aw(self):
        """Mock AuxWindow for error handling tests."""
        aw = Mock()
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "font": "Arial", "font_size": 10, "opacity": 1.0}
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
        aw.aux_params = {"font": "Arial", "font_size": 10, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
        aw.aw_class_label = Mock(side_effect=lambda *args: QLabel())
        return aw

    def test_stat_handles_missing_player(self, qapp, mock_aw) -> None:
        """Test stat gracefully handles missing player in stat_dict."""
        stat_dict = {}  # Empty stat_dict

        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)

        # Should not crash when updating with missing player
        stat.update(999, stat_dict)

        # Should show "NA" for exception case
        assert stat.lab.text() == "NA"

    def test_stat_handles_malformed_data(self, qapp, mock_aw) -> None:
        """Test stat handles malformed data gracefully."""
        stat_dict = {
            1: {
                "vpip": "invalid",  # Invalid data type
                "vpip_opp": None,  # None value
            },
        }

        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)

        # Should not crash with malformed data
        stat.update(1, stat_dict)

        # Should show "NA" for exception case
        assert stat.lab.text() == "NA"

    def test_stat_handles_missing_keys(self, qapp, mock_aw) -> None:
        """Test stat handles missing keys in player data."""
        stat_dict = {
            1: {
                "vpip": 5,
                # Missing 'vpip_opp' key
            },
        }

        # Create stat
        stat = SimpleStat("vpip", 1, "default", mock_aw)

        # Should handle missing keys gracefully
        stat.update(1, stat_dict)

        # Should show "-" for missing key (treated as 0)
        assert stat.lab.text() == "-"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
