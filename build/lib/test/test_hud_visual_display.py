#!/usr/bin/env python3
"""Test suite for visual HUD display with the "no data" feature.

This module creates tests that actually show the HUD on screen for visual verification
of the "-" vs "0" distinction in real GUI components.
"""

import os
import sys
from unittest.mock import Mock

import pytest
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import HUD components
from Aux_Classic_Hud import ClassicStat
from Aux_Hud import SimpleStat


class TestVisualHUDDisplay:
    """Test suite for visual HUD display verification."""

    @pytest.fixture
    def qapp(self, qapp):
        """Ensure QApplication is available."""
        return qapp

    @pytest.fixture
    def real_aw(self):
        """Create a real AuxWindow-like object for visual tests."""
        aw = Mock()
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

    def test_visual_hud_no_data_display(self, qapp, real_aw) -> None:
        """Test visual HUD display for no data scenario."""
        # Create a main window to hold our HUD stats
        main_window = QMainWindow()
        main_window.setWindowTitle("HUD Test - No Data (should show '-')")
        main_window.setGeometry(100, 100, 400, 200)

        # Create central widget
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create stats layout
        stats_layout = QHBoxLayout()
        layout.addLayout(stats_layout)

        # Create stat data (no data scenario)
        stat_dict = {
            1: {
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

        # Create and configure stats
        stats = []
        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        for stat_name in stat_names:
            # Create stat
            stat = SimpleStat(stat_name, 1, "default", real_aw)
            stat.update(1, stat_dict)

            # Style the label
            stat.lab.setStyleSheet("""
                QLabel {
                    font-family: Arial;
                    font-size: 14px;
                    color: #000000;
                    background-color: #FFFFFF;
                    border: 1px solid #CCCCCC;
                    padding: 5px;
                    margin: 2px;
                }
            """)

            # Add to layout
            stats_layout.addWidget(stat.lab)
            stats.append(stat)

        # Add title
        title_label = QLabel("All stats should show '-' (no data)")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.insertWidget(0, title_label)

        # Show the window
        main_window.show()

        # Wait for a moment to see the display
        QTest.qWait(2000)  # 2 seconds

        # Verify all stats show "-"
        for i, stat in enumerate(stats):
            assert stat.lab.text() == "-", f"Stat {stat_names[i]} should show '-' for no data"

        main_window.close()

    def test_visual_hud_mixed_data_display(self, qapp, real_aw) -> None:
        """Test visual HUD display for mixed data scenario."""
        # Create a main window to hold our HUD stats
        main_window = QMainWindow()
        main_window.setWindowTitle("HUD Test - Mixed Data (should show '-', '0.0', and percentages)")
        main_window.setGeometry(100, 100, 500, 300)

        # Create central widget
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create stats layout
        stats_layout = QHBoxLayout()
        layout.addLayout(stats_layout)

        # Create stat data (mixed scenario)
        stat_dict = {
            1: {
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
                "aggr_1": 3,
                "saw_f": 10,  # Active -> "30.0"
            },
        }

        # Create and configure stats
        stats = []
        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]
        expected_values = ["-", "0.0", "20.0", "25.0", "-", "30.0"]

        for i, stat_name in enumerate(stat_names):
            # Create container for each stat
            stat_container = QWidget()
            stat_layout = QVBoxLayout(stat_container)

            # Create stat
            stat = SimpleStat(stat_name, 1, "default", real_aw)
            stat.update(1, stat_dict)

            # Style the label based on value
            if stat.lab.text() == "-":
                color = "#FF0000"  # Red for no data
            elif stat.lab.text() == "0.0":
                color = "#0000FF"  # Blue for tight/passive
            else:
                color = "#00AA00"  # Green for active

            stat.lab.setStyleSheet(f"""
                QLabel {{
                    font-family: Arial;
                    font-size: 16px;
                    color: {color};
                    background-color: #F0F0F0;
                    border: 2px solid #CCCCCC;
                    padding: 8px;
                    margin: 2px;
                    text-align: center;
                }}
            """)

            # Add label for stat name
            name_label = QLabel(stat_name.upper())
            name_label.setStyleSheet("font-size: 10px; text-align: center; margin: 2px;")

            # Add to container
            stat_layout.addWidget(name_label)
            stat_layout.addWidget(stat.lab)

            # Add to main layout
            stats_layout.addWidget(stat_container)
            stats.append(stat)

        # Add title and legend
        title_label = QLabel("Mixed Data Display Test")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.insertWidget(0, title_label)

        legend_label = QLabel("Red = No Data ('-'), Blue = Tight/Passive ('0.0'), Green = Active (percentage)")
        legend_label.setStyleSheet("font-size: 12px; margin: 5px; color: #666666;")
        layout.addWidget(legend_label)

        # Show the window
        main_window.show()

        # Wait for a moment to see the display
        QTest.qWait(3000)  # 3 seconds

        # Verify expected values
        for i, stat in enumerate(stats):
            assert stat.lab.text() == expected_values[i], f"Stat {stat_names[i]} should show '{expected_values[i]}'"

        main_window.close()

    def test_visual_hud_classic_stat_display(self, qapp, real_aw) -> None:
        """Test visual ClassicStat display with color coding."""
        # Create a main window to hold our HUD stats
        main_window = QMainWindow()
        main_window.setWindowTitle("HUD Test - ClassicStat with Color Coding")
        main_window.setGeometry(100, 100, 600, 250)

        # Create central widget
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create stats layout
        stats_layout = QHBoxLayout()
        layout.addLayout(stats_layout)

        # Create stat data for different scenarios
        stat_dicts = [
            {1: {"screen_name": "Player1", "vpip": 0, "vpip_opp": 0}},  # No data
            {1: {"screen_name": "Player2", "vpip": 0, "vpip_opp": 20}},  # Tight (0%)
            {1: {"screen_name": "Player3", "vpip": 3, "vpip_opp": 20}},  # Loose-passive (15%)
            {1: {"screen_name": "Player4", "vpip": 8, "vpip_opp": 20}},  # Normal (40%)
            {1: {"screen_name": "Player5", "vpip": 15, "vpip_opp": 20}},  # Loose (75%)
        ]

        labels = ["No Data", "Tight (0%)", "Loose-Passive (15%)", "Normal (40%)", "Loose (75%)"]

        for stat_dict, label in zip(stat_dicts, labels, strict=False):
            # Create container for each stat
            stat_container = QWidget()
            stat_layout = QVBoxLayout(stat_container)

            # Create ClassicStat
            stat = ClassicStat("vpip", 1, "default", real_aw)
            stat.update(1, stat_dict)

            # Style the label
            stat.lab.setStyleSheet("""
                QLabel {
                    font-family: Arial;
                    font-size: 14px;
                    background-color: #F8F8F8;
                    border: 1px solid #DDDDDD;
                    padding: 8px;
                    margin: 2px;
                    text-align: center;
                }
            """)

            # Add label for scenario
            scenario_label = QLabel(label)
            scenario_label.setStyleSheet("font-size: 10px; text-align: center; margin: 2px; font-weight: bold;")

            # Add to container
            stat_layout.addWidget(scenario_label)
            stat_layout.addWidget(stat.lab)

            # Add to main layout
            stats_layout.addWidget(stat_container)

        # Add title
        title_label = QLabel("ClassicStat VPIP Display - Different Scenarios")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.insertWidget(0, title_label)

        # Show the window
        main_window.show()

        # Wait for a moment to see the display
        QTest.qWait(3000)  # 3 seconds

        main_window.close()

    def test_visual_hud_tooltip_display(self, qapp, real_aw) -> None:
        """Test visual HUD tooltip display."""
        # Create a main window to hold our HUD stats
        main_window = QMainWindow()
        main_window.setWindowTitle("HUD Test - Tooltip Display (hover over stats)")
        main_window.setGeometry(100, 100, 500, 200)

        # Create central widget
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create stats layout
        stats_layout = QHBoxLayout()
        layout.addLayout(stats_layout)

        # Create stat data
        stat_dict = {
            1: {
                "screen_name": "TestPlayer",
                "vpip": 0,
                "vpip_opp": 0,
                "pfr": 0,
                "pfr_opp": 20,
                "tb_0": 2,
                "tb_opp_0": 10,
            },
        }

        # Create and configure stats with tooltips
        stats = []
        stat_names = ["vpip", "pfr", "three_B"]
        tooltip_contents = [
            "TestPlayer\nVPIP: (-/-)\nVoluntarily put in preflop/3rd street %",
            "TestPlayer\nPFR: (0/20)\nPreflop/3rd street raise %",
            "TestPlayer\n3-Bet: (2/10)\n% 3 bet preflop/3rd street",
        ]

        for i, stat_name in enumerate(stat_names):
            # Create stat
            stat = SimpleStat(stat_name, 1, "default", real_aw)
            stat.update(1, stat_dict)

            # Set tooltip
            stat.lab.setToolTip(tooltip_contents[i])

            # Style the label
            stat.lab.setStyleSheet("""
                QLabel {
                    font-family: Arial;
                    font-size: 14px;
                    color: #000000;
                    background-color: #E8E8E8;
                    border: 1px solid #CCCCCC;
                    padding: 10px;
                    margin: 5px;
                }
                QLabel:hover {
                    background-color: #D0D0D0;
                    border: 2px solid #888888;
                }
            """)

            # Add to layout
            stats_layout.addWidget(stat.lab)
            stats.append(stat)

        # Add instructions
        instruction_label = QLabel("Hover over each stat to see tooltip with player name and fraction")
        instruction_label.setStyleSheet("font-size: 12px; margin: 10px; color: #666666;")
        layout.insertWidget(0, instruction_label)

        # Show the window
        main_window.show()

        # Wait longer to allow for tooltip interaction
        QTest.qWait(5000)  # 5 seconds

        main_window.close()

    @pytest.mark.manual
    def test_visual_hud_interactive_display(self, qapp, real_aw) -> None:
        """Interactive test for manual verification - requires manual intervention."""
        # Create a main window to hold our HUD stats
        main_window = QMainWindow()
        main_window.setWindowTitle("HUD Test - Interactive (Close window when done)")
        main_window.setGeometry(100, 100, 700, 400)

        # Create central widget
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create multiple player scenarios
        scenarios = [
            {
                "name": "New Player (No Data)",
                "data": {
                    1: {
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
                },
                "expected": ["-", "-", "-", "-", "-", "-"],
            },
            {
                "name": "Tight Player",
                "data": {
                    1: {
                        "vpip": 0,
                        "vpip_opp": 20,
                        "pfr": 0,
                        "pfr_opp": 20,
                        "tb_0": 0,
                        "tb_opp_0": 5,
                        "steal": 0,
                        "steal_opp": 8,
                        "cb_1": 0,
                        "cb_opp_1": 0,
                        "aggr_1": 0,
                        "saw_f": 5,
                    },
                },
                "expected": ["0.0", "0.0", "0.0", "0.0", "-", "0.0"],
            },
            {
                "name": "Regular Player",
                "data": {
                    1: {
                        "vpip": 10,
                        "vpip_opp": 50,
                        "pfr": 5,
                        "pfr_opp": 50,
                        "tb_0": 2,
                        "tb_opp_0": 10,
                        "steal": 3,
                        "steal_opp": 12,
                        "cb_1": 4,
                        "cb_opp_1": 8,
                        "aggr_1": 6,
                        "saw_f": 15,
                    },
                },
                "expected": ["20.0", "10.0", "20.0", "25.0", "50.0", "40.0"],
            },
        ]

        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        for scenario in scenarios:
            # Create scenario section
            scenario_widget = QWidget()
            scenario_layout = QVBoxLayout(scenario_widget)

            # Scenario title
            title_label = QLabel(scenario["name"])
            title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px; color: #333333;")
            scenario_layout.addWidget(title_label)

            # Stats layout
            stats_layout = QHBoxLayout()
            scenario_layout.addLayout(stats_layout)

            # Create stats
            for i, stat_name in enumerate(stat_names):
                # Create container
                stat_container = QWidget()
                stat_container_layout = QVBoxLayout(stat_container)

                # Create stat
                stat = SimpleStat(stat_name, 1, "default", real_aw)
                stat.update(1, scenario["data"])

                # Style based on expected value
                expected_val = scenario["expected"][i]
                if expected_val == "-":
                    bg_color = "#FFE0E0"  # Light red
                elif expected_val == "0.0":
                    bg_color = "#E0E0FF"  # Light blue
                else:
                    bg_color = "#E0FFE0"  # Light green

                stat.lab.setStyleSheet(f"""
                    QLabel {{
                        font-family: Arial;
                        font-size: 12px;
                        color: #000000;
                        background-color: {bg_color};
                        border: 1px solid #CCCCCC;
                        padding: 5px;
                        margin: 1px;
                        text-align: center;
                    }}
                """)

                # Add stat name
                name_label = QLabel(stat_name.upper())
                name_label.setStyleSheet("font-size: 8px; text-align: center; margin: 1px;")

                # Add to container
                stat_container_layout.addWidget(name_label)
                stat_container_layout.addWidget(stat.lab)

                # Add to stats layout
                stats_layout.addWidget(stat_container)

            # Add scenario to main layout
            layout.addWidget(scenario_widget)

        # Add instructions
        instruction_label = QLabel(
            "Manual Test: Verify that each scenario shows correct values.\nClose window when verification is complete.",
        )
        instruction_label.setStyleSheet("font-size: 11px; margin: 10px; color: #666666; font-style: italic;")
        layout.insertWidget(0, instruction_label)

        # Show the window
        main_window.show()

        # Keep window open for manual verification
        # In a real test, this would be commented out, but for manual testing:
        # QTest.qWait(15000)  # 15 seconds for manual verification

        # For automated testing, just wait a moment
        QTest.qWait(2000)

        main_window.close()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
