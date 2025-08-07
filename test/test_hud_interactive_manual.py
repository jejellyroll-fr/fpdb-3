#!/usr/bin/env python3
"""Interactive manual test for HUD visual verification.

This script creates a real HUD display window that stays open for manual verification
of the "-" vs "0" distinction. Close the window to exit.
"""

import os
import sys
from unittest.mock import Mock

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Aux_Hud import SimpleStat


class HUDManualTestWindow(QMainWindow):
    """Manual test window for HUD display verification."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FPDB HUD Manual Test - No Data vs Zero Display")
        self.setGeometry(100, 100, 800, 600)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Add title
        title = QLabel("FPDB HUD Manual Test - Verify '-' vs '0' Display")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin: 10px; color: #333333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Add instructions
        instructions = QLabel("""
        Instructions:
        1. Verify that stats with NO DATA show '-' (dash/hyphen)
        2. Verify that stats with ZERO VALUE show '0.0' (zero with decimal)
        3. Verify that stats with NORMAL VALUES show percentages like '20.0'
        4. Close this window when verification is complete
        """)
        instructions.setStyleSheet(
            "font-size: 12px; margin: 10px; color: #666666; background-color: #F0F0F0; padding: 10px;",
        )
        layout.addWidget(instructions)

        # Create test scenarios
        self.create_test_scenarios(layout)

        # Add close button
        close_button = QPushButton("Close Test Window")
        close_button.clicked.connect(self.close)
        close_button.setStyleSheet("font-size: 14px; padding: 10px; margin: 10px;")
        layout.addWidget(close_button)

    def create_mock_aw(self):
        """Create mock AuxWindow for testing."""
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
            stat_obj.stat_locolor = "#FF0000"  # Red for low values
            stat_obj.stat_loth = "10"
            stat_obj.stat_hicolor = "#00FF00"  # Green for high values
            stat_obj.stat_hith = "30"
            stat_obj.stat_midcolor = "#FFFF00"  # Yellow for mid values
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

    def create_test_scenarios(self, layout) -> None:
        """Create different test scenarios."""
        scenarios = [
            {
                "title": "Scenario 1: New Player (No Data Available)",
                "description": "All stats should show '-' because no data is available",
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
                "expected": "All stats should show '-'",
                "color": "#FFE0E0",  # Light red background
            },
            {
                "title": "Scenario 2: Tight/Passive Player (Zero Actions)",
                "description": "Player had opportunities but took zero actions",
                "data": {
                    1: {
                        "vpip": 0,
                        "vpip_opp": 25,  # 0 VPIP from 25 opportunities
                        "pfr": 0,
                        "pfr_opp": 25,  # 0 PFR from 25 opportunities
                        "tb_0": 0,
                        "tb_opp_0": 8,  # 0 3-bets from 8 opportunities
                        "steal": 0,
                        "steal_opp": 10,  # 0 steals from 10 opportunities
                        "cb_1": 0,
                        "cb_opp_1": 0,  # No c-bet opportunities
                        "aggr_1": 0,
                        "saw_f": 12,  # 0 aggression, saw 12 flops
                    },
                },
                "expected": "Stats with opportunities should show '0.0', no opportunities should show '-'",
                "color": "#E0E0FF",  # Light blue background
            },
            {
                "title": "Scenario 3: Regular Player (Normal Values)",
                "description": "Player with typical poker statistics",
                "data": {
                    1: {
                        "vpip": 12,
                        "vpip_opp": 50,  # 24% VPIP
                        "pfr": 8,
                        "pfr_opp": 50,  # 16% PFR
                        "tb_0": 3,
                        "tb_opp_0": 15,  # 20% 3-bet
                        "steal": 4,
                        "steal_opp": 12,  # 33% steal
                        "cb_1": 6,
                        "cb_opp_1": 10,  # 60% c-bet
                        "aggr_1": 8,
                        "saw_f": 20,  # 40% aggression frequency
                    },
                },
                "expected": "All stats should show percentages like '24.0', '16.0', etc.",
                "color": "#E0FFE0",  # Light green background
            },
            {
                "title": "Scenario 4: Mixed Data (Real-World Example)",
                "description": "Mix of no data, zero actions, and normal values",
                "data": {
                    1: {
                        "vpip": 0,
                        "vpip_opp": 0,  # No data -> '-'
                        "pfr": 0,
                        "pfr_opp": 15,  # Tight -> '0.0'
                        "tb_0": 2,
                        "tb_opp_0": 10,  # Normal -> '20.0'
                        "steal": 0,
                        "steal_opp": 0,  # No data -> '-'
                        "cb_1": 5,
                        "cb_opp_1": 8,  # Active -> '62.5'
                        "aggr_1": 0,
                        "saw_f": 0,  # No data -> '-'
                    },
                },
                "expected": "Mixed: '-', '0.0', '20.0', '-', '62.5', '-'",
                "color": "#FFF0E0",  # Light orange background
            },
        ]

        for scenario in scenarios:
            self.create_scenario_widget(layout, scenario)

    def create_scenario_widget(self, layout, scenario) -> None:
        """Create a widget for a specific test scenario."""
        # Create scenario container
        scenario_widget = QWidget()
        scenario_widget.setStyleSheet(
            f"background-color: {scenario['color']}; border: 1px solid #CCCCCC; margin: 5px; padding: 5px;",
        )
        scenario_layout = QVBoxLayout(scenario_widget)

        # Add title
        title_label = QLabel(scenario["title"])
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 5px; color: #333333;")
        scenario_layout.addWidget(title_label)

        # Add description
        desc_label = QLabel(scenario["description"])
        desc_label.setStyleSheet("font-size: 12px; margin: 5px; color: #666666;")
        scenario_layout.addWidget(desc_label)

        # Add expected result
        expected_label = QLabel(f"Expected: {scenario['expected']}")
        expected_label.setStyleSheet("font-size: 11px; margin: 5px; color: #444444; font-style: italic;")
        scenario_layout.addWidget(expected_label)

        # Create stats display
        stats_layout = QHBoxLayout()
        scenario_layout.addLayout(stats_layout)

        # Create mock AuxWindow
        aw = self.create_mock_aw()

        # Define stats to test
        stat_names = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]
        stat_labels = ["VPIP", "PFR", "3-Bet", "Steal", "C-Bet", "Agg"]

        for stat_name, stat_label in zip(stat_names, stat_labels, strict=False):
            # Create stat container
            stat_container = QWidget()
            stat_container.setStyleSheet(
                "background-color: #FFFFFF; border: 1px solid #DDDDDD; margin: 2px; padding: 2px;",
            )
            stat_layout = QVBoxLayout(stat_container)

            # Create stat label
            name_label = QLabel(stat_label)
            name_label.setStyleSheet("font-size: 10px; text-align: center; margin: 1px; font-weight: bold;")
            name_label.setAlignment(Qt.AlignCenter)
            stat_layout.addWidget(name_label)

            # Create stat
            stat = SimpleStat(stat_name, 1, "default", aw)
            stat.update(1, scenario["data"])

            # Style the stat based on its value
            stat_value = stat.lab.text()
            if stat_value == "-":
                stat_color = "#FF0000"  # Red for no data
                bg_color = "#FFEEEE"
            elif stat_value == "0.0":
                stat_color = "#0000FF"  # Blue for zero
                bg_color = "#EEEEFF"
            else:
                stat_color = "#00AA00"  # Green for normal values
                bg_color = "#EEFFEE"

            stat.lab.setStyleSheet(f"""
                QLabel {{
                    font-family: Arial;
                    font-size: 14px;
                    font-weight: bold;
                    color: {stat_color};
                    background-color: {bg_color};
                    border: 1px solid #CCCCCC;
                    padding: 5px;
                    margin: 1px;
                    text-align: center;
                }}
            """)

            stat_layout.addWidget(stat.lab)
            stats_layout.addWidget(stat_container)

        layout.addWidget(scenario_widget)


def main() -> None:
    """Main function to run the interactive test."""
    app = QApplication(sys.argv)

    # Create and show the test window
    window = HUDManualTestWindow()
    window.show()


    # Run the application
    app.exec_()


if __name__ == "__main__":
    main()
