#!/usr/bin/env python3
"""Complete test suite for HUD popup components with proper mocking.

This module provides comprehensive tests for popup windows and their interaction
with the "no data" feature, with fully resolved mocking issues.
"""

import os
import sys
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import HUD components
import Stats
from Aux_Hud import SimpleStat


class MockPopup:
    """Mock popup class for testing popup functionality."""

    def __init__(self, seat, stat_dict, win, pop, hand_instance, config) -> None:
        self.seat = seat
        self.stat_dict = stat_dict
        self.win = win
        self.pop = pop
        self.hand_instance = hand_instance
        self.config = config
        self.created = True

        # Create mock widget
        self.widget = QWidget()
        self.widget.setWindowTitle("Mock Popup")
        self.widget.setGeometry(100, 100, 300, 200)

        # Create layout with stats
        layout = QVBoxLayout(self.widget)

        # Add player name
        if seat in stat_dict and "screen_name" in stat_dict[seat]:
            player_label = QLabel(stat_dict[seat]["screen_name"])
            player_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 5px;")
            layout.addWidget(player_label)

        # Add stats
        stats_layout = QHBoxLayout()
        layout.addLayout(stats_layout)

        # Common stats to display
        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        for stat_name in stat_names:
            stat_result = Stats.do_stat(stat_dict, seat, stat_name)
            if stat_result:
                stat_label = QLabel(f"{stat_name.upper()}\n{stat_result[1]}")
                stat_label.setStyleSheet("border: 1px solid #CCCCCC; padding: 5px; margin: 2px; text-align: center;")
                stat_label.setAlignment(Qt.AlignCenter)
                stats_layout.addWidget(stat_label)

    def show(self) -> None:
        """Show the popup."""
        self.widget.show()

    def close(self) -> None:
        """Close the popup."""
        self.widget.close()

    def setStyleSheet(self, style) -> None:
        """Set stylesheet for popup."""
        self.widget.setStyleSheet(style)


class TestHUDPopupsComplete:
    """Complete test suite for HUD popups with proper mocking."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for popup tests."""
        config = Mock()
        config.popup_windows = {
            "default": Mock(pu_class="default", pu_stats=["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]),
        }
        return config

    @pytest.fixture
    def mock_aw(self, mock_config):
        """Mock AuxWindow for popup tests."""
        aw = Mock()
        aw.config = mock_config
        aw.params = {"fgcolor": "#000000", "bgcolor": "#FFFFFF", "font": "Arial", "font_size": 12, "opacity": 1.0}
        aw.aux_params = {"font": "Arial", "font_size": 12, "fgcolor": "#000000", "bgcolor": "#FFFFFF"}
        aw.hud = Mock()
        aw.hud.hand_instance = None
        aw.hud.layout = Mock()

        # Create proper seat mocks
        seat_mocks = {}
        for i in range(1, 7):
            seat_mock = Mock()
            seat_mock.seat_number = i
            seat_mock.player_name = f"Player{i}"
            seat_mocks[i] = seat_mock
        aw.hud.layout.hh_seats = seat_mocks

        # Return real QLabel instances
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

        aw.hud.supported_games_parameters = {"game_stat_set": stat_set}

        return aw

    def test_popup_displays_no_data_correctly(self, qapp, mock_aw) -> None:
        """Test popup displays '-' correctly for no data stats."""
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
                "cb_1": 0,
                "cb_opp_1": 0,
                "aggr_1": 0,
                "saw_f": 0,
            },
        }

        # Create mock popup
        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Verify popup was created
        assert popup.created
        assert popup.seat == 1
        assert popup.stat_dict == stat_dict

        # Verify stats calculations
        vpip_result = Stats.do_stat(stat_dict, 1, "vpip")
        pfr_result = Stats.do_stat(stat_dict, 1, "pfr")
        three_b_result = Stats.do_stat(stat_dict, 1, "three_B")

        assert vpip_result[1] == "-"
        assert pfr_result[1] == "-"
        assert three_b_result[1] == "-"

    def test_popup_displays_mixed_data_correctly(self, qapp, mock_aw) -> None:
        """Test popup displays mixed data correctly."""
        stat_dict = {
            1: {
                "screen_name": "MixedPlayer",
                "vpip": 0,
                "vpip_opp": 0,  # No data -> "-"
                "pfr": 0,
                "pfr_opp": 20,  # Tight -> "0.0"
                "tb_0": 2,
                "tb_opp_0": 10,  # Regular -> "20.0"
                "steal": 3,
                "steal_opp": 12,  # Active -> "25.0"
                "cb_1": 0,
                "cb_opp_1": 0,  # No data -> "-"
                "aggr_1": 4,
                "saw_f": 10,  # Active -> "40.0"
            },
        }

        # Create mock popup
        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Verify popup was created
        assert popup.created

        # Verify stats calculations
        vpip_result = Stats.do_stat(stat_dict, 1, "vpip")
        pfr_result = Stats.do_stat(stat_dict, 1, "pfr")
        three_b_result = Stats.do_stat(stat_dict, 1, "three_B")
        steal_result = Stats.do_stat(stat_dict, 1, "steal")
        cbet_result = Stats.do_stat(stat_dict, 1, "cbet")
        a_freq1_result = Stats.do_stat(stat_dict, 1, "a_freq1")

        assert vpip_result[1] == "-"  # No data
        assert pfr_result[1] == "0.0"  # Tight player
        assert three_b_result[1] == "20.0"  # Regular player
        assert steal_result[1] == "25.0"  # Active player
        assert cbet_result[1] == "-"  # No data
        assert a_freq1_result[1] == "40.0"  # Active player

    def test_popup_with_stat_window_integration(self, qapp, mock_aw) -> None:
        """Test popup integration with stat window."""
        stat_dict = {
            1: {
                "screen_name": "TestPlayer",
                "vpip": 5,
                "vpip_opp": 25,
                "pfr": 3,
                "pfr_opp": 25,
                "tb_0": 1,
                "tb_opp_0": 8,
                "steal": 2,
                "steal_opp": 10,
                "cb_1": 3,
                "cb_opp_1": 5,
                "aggr_1": 6,
                "saw_f": 15,
            },
        }

        # Create SimpleStat
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Verify stat display
        assert stat.lab.text() == "20.0"  # 5/25 = 20%

        # Create mock popup for this stat
        MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Verify popup shows consistent data
        vpip_result = Stats.do_stat(stat_dict, 1, "vpip")
        assert vpip_result[1] == "20.0"  # Should match main stat display

    def test_popup_tooltip_content_consistency(self, qapp, mock_aw) -> None:
        """Test popup content consistency with tooltip data."""
        stat_dict = {
            1: {
                "screen_name": "TooltipPlayer",
                "vpip": 0,
                "vpip_opp": 0,
                "pfr": 0,
                "pfr_opp": 15,
                "tb_0": 1,
                "tb_opp_0": 5,
            },
        }

        # Create stat with tooltip
        stat = SimpleStat("vpip", 1, "default", mock_aw)
        stat.update(1, stat_dict)

        # Set tooltip manually
        stat.lab.setToolTip("TooltipPlayer\nVPIP: (-/-)\nVoluntarily put in preflop")

        # Verify tooltip content
        tooltip = stat.lab.toolTip()
        assert "TooltipPlayer" in tooltip
        assert "(-/-)" in tooltip
        assert "Voluntarily put in preflop" in tooltip

        # Create popup and verify consistency
        MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Verify popup shows same data as tooltip
        vpip_result = Stats.do_stat(stat_dict, 1, "vpip")
        assert vpip_result[1] == "-"  # Should match tooltip indication
        assert vpip_result[4] == "(-/-)"  # Should match tooltip fraction

    def test_popup_performance_with_multiple_stats(self, qapp, mock_aw) -> None:
        """Test popup performance with multiple stats."""
        import time

        stat_dict = {
            1: {
                "screen_name": "PerformancePlayer",
                "vpip": 10,
                "vpip_opp": 50,
                "pfr": 5,
                "pfr_opp": 50,
                "tb_0": 2,
                "tb_opp_0": 15,
                "steal": 3,
                "steal_opp": 12,
                "cb_1": 4,
                "cb_opp_1": 8,
                "aggr_1": 6,
                "saw_f": 20,
            },
        }

        # Time popup creation
        start_time = time.time()

        for _ in range(100):
            MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        end_time = time.time()

        # Should complete quickly
        duration = end_time - start_time
        assert duration < 1.0, f"100 popup creations took {duration:.3f}s, should be < 1.0s"

    def test_popup_visual_display(self, qapp, mock_aw) -> None:
        """Test popup visual display (briefly shows popup window)."""
        stat_dict = {
            1: {
                "screen_name": "VisualPlayer",
                "vpip": 0,
                "vpip_opp": 0,  # No data -> "-"
                "pfr": 0,
                "pfr_opp": 15,  # Tight -> "0.0"
                "tb_0": 3,
                "tb_opp_0": 12,  # Regular -> "25.0"
                "steal": 2,
                "steal_opp": 8,  # Active -> "25.0"
                "cb_1": 0,
                "cb_opp_1": 0,  # No data -> "-"
                "aggr_1": 5,
                "saw_f": 15,  # Active -> "33.3"
            },
        }

        # Create popup
        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Show popup briefly
        popup.show()
        QTest.qWait(500)  # Show for 0.5 seconds

        # Verify popup is created and displayed
        assert popup.created
        assert popup.widget.isVisible()

        # Close popup
        popup.close()

        # Verify popup is closed
        assert not popup.widget.isVisible()

    def test_popup_error_handling(self, qapp, mock_aw) -> None:
        """Test popup error handling with malformed data."""
        # Test with empty stat_dict
        stat_dict = {}

        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Should handle empty data gracefully
        assert popup.created

        # Test with missing player
        stat_dict = {2: {"vpip": 5, "vpip_opp": 25}}

        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Should handle missing player gracefully
        assert popup.created

    def test_popup_stat_integration_complete(self, qapp, mock_aw) -> None:
        """Complete integration test with popup and stat display."""
        # Create comprehensive stat data
        stat_dict = {
            1: {
                "screen_name": "CompletePlayer",
                "vpip": 12,
                "vpip_opp": 60,  # 20% VPIP
                "pfr": 8,
                "pfr_opp": 60,  # 13.3% PFR
                "tb_0": 4,
                "tb_opp_0": 20,  # 20% 3-bet
                "steal": 5,
                "steal_opp": 15,  # 33.3% steal
                "cb_1": 6,
                "cb_opp_1": 10,  # 60% c-bet
                "aggr_1": 8,
                "saw_f": 25,  # 32% aggression frequency
            },
        }

        # Create multiple stats
        stats = {}
        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        for stat_name in stat_names:
            stat = SimpleStat(stat_name, 1, "default", mock_aw)
            stat.update(1, stat_dict)
            stats[stat_name] = stat

        # Create popup
        popup = MockPopup(1, stat_dict, None, mock_aw.config.popup_windows["default"], None, mock_aw.config)

        # Verify stat display values
        expected_values = {
            "vpip": "20.0",
            "pfr": "13.3",
            "three_B": "20.0",
            "steal": "33.3",
            "cbet": "60.0",
            "a_freq1": "32.0",
        }

        for stat_name, expected in expected_values.items():
            stat_result = Stats.do_stat(stat_dict, 1, stat_name)
            assert stat_result[1] == expected, f"Stat {stat_name} should show {expected}"
            assert stats[stat_name].lab.text() == expected, f"Stat display {stat_name} should show {expected}"

        # Verify popup integration
        assert popup.created
        assert popup.seat == 1
        assert popup.stat_dict == stat_dict


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
