#!/usr/bin/env python
"""Tests for popup XML configuration.

Test suite for validating HUD_config.xml popup configurations.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPopupXMLConfiguration(unittest.TestCase):
    """Test popup configurations in HUD_config.xml."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up XML parsing for all tests."""
        cls.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "HUD_config.xml")

        # Parse the XML file
        try:
            cls.tree = ET.parse(cls.config_path)
            cls.root = cls.tree.getroot()
        except ET.ParseError as e:
            cls.fail(f"Failed to parse HUD_config.xml: {e}")
        except FileNotFoundError:
            cls.fail(f"HUD_config.xml not found at {cls.config_path}")

    def test_xml_is_well_formed(self) -> None:
        """Test that XML is well-formed and parseable."""
        assert self.tree is not None
        assert self.root is not None

    def test_popup_windows_section_exists(self) -> None:
        """Test that popup_windows section exists."""
        popup_windows = self.root.find("popup_windows")
        assert popup_windows is not None, "popup_windows section not found in XML"

    def test_modern_popups_are_defined(self) -> None:
        """Test that all modern popup configurations are defined."""
        popup_windows = self.root.find("popup_windows")
        popup_names = [pu.get("pu_name") for pu in popup_windows.findall("pu")]

        # Expected modern popups
        expected_modern_popups = [
            "holdring_modern",
            "holdring_modern_light",
            "cash_6max_complete",
            "cash_9max_complete",
            "cash_headsup_complete",
            "tournament_early",
            "tournament_middle",
            "tournament_bubble_late",
            "omaha_complete",
            "omaha_hilo_complete",
            "stud_complete",
            "razz_complete",
            "draw_complete",
            "mixed_games_complete",
            "short_stack_specialist",
            "postflop_specialist",
            "preflop_specialist",
        ]

        for popup_name in expected_modern_popups:
            assert popup_name in popup_names, f"Modern popup '{popup_name}' not found in configuration"

    def test_modern_popups_use_modern_classes(self) -> None:
        """Test that modern popups use ModernSubmenu classes."""
        popup_windows = self.root.find("popup_windows")
        modern_classes = ["ModernSubmenu", "ModernSubmenuLight", "ModernSubmenuClassic"]

        modern_popup_names = [
            "holdring_modern",
            "holdring_modern_light",
            "cash_6max_complete",
            "tournament_middle",
            "omaha_complete",
            "stud_complete",
        ]

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")
            pu_class = pu.get("pu_class")

            if pu_name in modern_popup_names:
                assert pu_class in modern_classes, f"Modern popup '{pu_name}' should use ModernSubmenu class, got '{pu_class}'"

    def test_popup_stat_elements(self) -> None:
        """Test that popup stat elements are properly configured."""
        popup_windows = self.root.find("popup_windows")

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")
            pu_stats = pu.findall("pu_stat")

            # Each popup should have at least one stat
            assert len(pu_stats) > 0, f"Popup '{pu_name}' has no pu_stat elements"

            # Check that each pu_stat has pu_stat_name
            for pu_stat in pu_stats:
                stat_name = pu_stat.get("pu_stat_name")
                assert stat_name is not None, f"pu_stat in popup '{pu_name}' missing pu_stat_name attribute"
                assert stat_name.strip() != "", f"pu_stat in popup '{pu_name}' has empty pu_stat_name"

    def test_comprehensive_popup_stats(self) -> None:
        """Test that comprehensive popups contain expected stat categories."""
        popup_windows = self.root.find("popup_windows")

        # Test comprehensive popups
        comprehensive_popups = {
            "cash_6max_complete": {"required_stats": ["playername", "vpip", "pfr", "cb1", "steal"], "min_stats": 30},
            "postflop_specialist": {"required_stats": ["cb1", "cb2", "cb3", "f_cb1", "float_bet"], "min_stats": 20},
            "preflop_specialist": {"required_stats": ["vpip", "pfr", "three_B", "rfi_early_position"], "min_stats": 15},
        }

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")

            if pu_name in comprehensive_popups:
                pu_stats = pu.findall("pu_stat")
                stat_names = [stat.get("pu_stat_name") for stat in pu_stats]

                config = comprehensive_popups[pu_name]

                # Check required stats
                for required_stat in config["required_stats"]:
                    assert required_stat in stat_names, f"Popup '{pu_name}' missing required stat '{required_stat}'"

                # Check minimum number of stats
                assert len(stat_names) >= config["min_stats"], f"Popup '{pu_name}' should have at least {config['min_stats']} stats, got {len(stat_names)}"

    def test_tournament_popups_have_m_ratio(self) -> None:
        """Test that tournament popups include M-ratio stat."""
        popup_windows = self.root.find("popup_windows")
        tournament_popups = ["tournament_early", "tournament_middle", "tournament_bubble_late"]

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")

            if pu_name in tournament_popups:
                pu_stats = pu.findall("pu_stat")
                stat_names = [stat.get("pu_stat_name") for stat in pu_stats]

                assert "m_ratio" in stat_names, f"Tournament popup '{pu_name}' should include m_ratio stat"

    def test_all_popups_have_player_info(self) -> None:
        """Test that all modern popups include basic player info."""
        popup_windows = self.root.find("popup_windows")
        modern_popup_classes = ["ModernSubmenu", "ModernSubmenuLight", "ModernSubmenuClassic"]

        for pu in popup_windows.findall("pu"):
            pu_class = pu.get("pu_class")
            pu_name = pu.get("pu_name")

            if pu_class in modern_popup_classes:
                pu_stats = pu.findall("pu_stat")
                stat_names = [stat.get("pu_stat_name") for stat in pu_stats]

                # Should have playername and player_note
                assert "playername" in stat_names, f"Modern popup '{pu_name}' should include playername stat"

                # Most should have player_note (some basic ones might not)
                if "complete" in pu_name or "specialist" in pu_name:
                    assert "player_note" in stat_names, f"Comprehensive popup '{pu_name}' should include player_note stat"

    def test_no_duplicate_popup_names(self) -> None:
        """Test that popup names are unique."""
        popup_windows = self.root.find("popup_windows")
        popup_names = [pu.get("pu_name") for pu in popup_windows.findall("pu")]

        unique_names = set(popup_names)
        assert len(popup_names) == len(unique_names), f"Duplicate popup names found: {[name for name in popup_names if popup_names.count(name) > 1]}"

    def test_stat_sets_use_modern_popups(self) -> None:
        """Test that stat sets are updated to use modern popups."""
        stat_sets = self.root.find("stat_sets")
        modern_popup_usage = {
            "holdem_6max_pro": "holdring_modern",
            "holdem_9max_pro": "cash_9max_complete",
            "holdem_headsup_pro": "cash_headsup_complete",
            "holdem_tournament_pro": "tournament_middle",
            "omaha_cg_expert": "omaha_complete",
            "stud_cg_expert": "stud_complete",
        }

        for ss in stat_sets.findall("ss"):
            ss_name = ss.get("name")

            if ss_name in modern_popup_usage:
                expected_popup = modern_popup_usage[ss_name]

                # Find playershort stat (which should use modern popup)
                playershort_stats = [stat for stat in ss.findall("stat") if stat.get("_stat_name") == "playershort"]

                assert playershort_stats, f"Stat set '{ss_name}' should have playershort stat"

                for stat in playershort_stats:
                    popup = stat.get("popup")
                    assert popup == expected_popup, f"Stat set '{ss_name}' playershort should use popup '{expected_popup}', got '{popup}'"


class TestPopupStatValidation(unittest.TestCase):
    """Test individual popup stat validation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up XML parsing for stat validation tests."""
        cls.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "HUD_config.xml")

        try:
            cls.tree = ET.parse(cls.config_path)
            cls.root = cls.tree.getroot()
        except (ET.ParseError, FileNotFoundError) as e:
            cls.fail(f"Failed to load HUD_config.xml: {e}")

    def get_known_stats(self) -> set[str]:
        """Get list of known stats from Stats.py."""
        # This would ideally import Stats.py and introspect, but for now use a known list
        return {
            "playername",
            "player_note",
            "n",
            "vpip",
            "pfr",
            "three_B",
            "four_B",
            "f_3bet",
            "fold_vs_4bet",
            "limp",
            "cold_call",
            "iso",
            "rfi_total",
            "rfi_early_position",
            "rfi_middle_position",
            "rfi_late_position",
            "cb1",
            "cb2",
            "cb3",
            "cb4",
            "f_cb1",
            "f_cb2",
            "f_cb3",
            "f_cb4",
            "cb_ip",
            "cb_oop",
            "triple_barrel",
            "float_bet",
            "probe_bet",
            "probe_bet_turn",
            "probe_bet_river",
            "check_raise_frequency",
            "bet_frequency_flop",
            "bet_frequency_turn",
            "raise_frequency_flop",
            "raise_frequency_turn",
            "avg_bet_size_flop",
            "avg_bet_size_turn",
            "avg_bet_size_river",
            "overbet_frequency",
            "steal",
            "f_steal",
            "call_vs_steal",
            "three_bet_vs_steal",
            "resteal",
            "wtsd",
            "wmsd",
            "sd_winrate",
            "non_sd_winrate",
            "river_call_efficiency",
            "totalprofit",
            "profit100",
            "agg_fact",
            "agg_freq",
            "agg_pct",
            "a_freq_123",
            "m_ratio",
            "saw_f",
            "game_abbr",
            "hands",
            "three_bet_range",
            "vpip_pfr_ratio",
            "blank",
        }

    def test_all_popup_stats_are_valid(self) -> None:
        """Test that all stats referenced in popups are valid."""
        popup_windows = self.root.find("popup_windows")
        known_stats = self.get_known_stats()
        modern_classes = ["ModernSubmenu", "ModernSubmenuLight", "ModernSubmenuClassic"]

        invalid_stats = []

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")
            pu_class = pu.get("pu_class")

            # Only check modern popups
            if pu_class in modern_classes:
                for pu_stat in pu.findall("pu_stat"):
                    stat_name = pu_stat.get("pu_stat_name")

                    if stat_name and stat_name not in known_stats:
                        invalid_stats.append(f"{pu_name}: {stat_name}")

        if invalid_stats:
            self.fail("Invalid stats found in modern popups:\n" + "\n".join(invalid_stats))

    def test_popup_stat_categorization(self) -> None:
        """Test that popup stats are logically categorized."""
        # Import categorization function
        try:
            from PopupIcons import get_stat_category
        except ImportError:
            self.skipTest("PopupIcons module not available")

        popup_windows = self.root.find("popup_windows")

        # Test specific popups for logical stat grouping
        category_tests = {
            "preflop_specialist": {
                "expected_categories": ["player_info", "preflop", "steal", "general"],
                "forbidden_categories": ["flop", "turn", "river"],
            },
            "postflop_specialist": {
                "expected_categories": ["player_info", "flop", "turn", "river", "general"],
                "forbidden_categories": [],
            },
        }

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")

            if pu_name in category_tests:
                test_config = category_tests[pu_name]
                stat_categories = set()

                for pu_stat in pu.findall("pu_stat"):
                    if stat_name := pu_stat.get("pu_stat_name"):
                        category = get_stat_category(stat_name)
                        stat_categories.add(category)

                # Check expected categories
                for expected_cat in test_config["expected_categories"]:
                    assert expected_cat in stat_categories, f"Popup '{pu_name}' should contain stats from category '{expected_cat}'"

                # Check forbidden categories
                for forbidden_cat in test_config["forbidden_categories"]:
                    assert forbidden_cat not in stat_categories, f"Popup '{pu_name}' should not contain stats from category '{forbidden_cat}'"

    def test_variant_specific_popups(self) -> None:
        """Test that variant-specific popups contain appropriate stats."""
        popup_windows = self.root.find("popup_windows")

        variant_tests = {
            "omaha_complete": {
                "should_have": ["saw_f"],  # Omaha sees more flops
                "should_not_have": [],
            },
            "stud_complete": {
                "should_have": ["cb1", "cb2", "cb3"],  # Street-based betting
                "should_not_have": ["steal"],  # No blinds in stud
            },
            "cash_headsup_complete": {
                "should_have": ["steal", "f_steal", "three_bet_vs_steal"],  # Button vs BB dynamics
                "should_not_have": [],
            },
        }

        for pu in popup_windows.findall("pu"):
            pu_name = pu.get("pu_name")

            if pu_name in variant_tests:
                test_config = variant_tests[pu_name]
                stat_names = [stat.get("pu_stat_name") for stat in pu.findall("pu_stat")]

                for should_have_stat in test_config["should_have"]:
                    assert should_have_stat in stat_names, f"Variant popup '{pu_name}' should include stat '{should_have_stat}'"

                for should_not_have_stat in test_config["should_not_have"]:
                    assert should_not_have_stat not in stat_names, f"Variant popup '{pu_name}' should not include stat '{should_not_have_stat}'"


class TestPopupUsageInStatSets(unittest.TestCase):
    """Test that popups are properly used in stat sets."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up XML parsing for stat set tests."""
        cls.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "HUD_config.xml")

        try:
            cls.tree = ET.parse(cls.config_path)
            cls.root = cls.tree.getroot()
        except (ET.ParseError, FileNotFoundError) as e:
            cls.fail(f"Failed to load HUD_config.xml: {e}")

    def test_all_referenced_popups_exist(self) -> None:
        """Test that all popups referenced in stat sets actually exist."""
        # Get all defined popup names
        popup_windows = self.root.find("popup_windows")
        defined_popups = {pu.get("pu_name") for pu in popup_windows.findall("pu")}

        # Get all referenced popup names
        stat_sets = self.root.find("stat_sets")
        referenced_popups = set()

        for ss in stat_sets.findall("ss"):
            for stat in ss.findall("stat"):
                popup = stat.get("popup")
                if popup and popup != "default":
                    referenced_popups.add(popup)

        # Check that all referenced popups are defined
        if undefined_popups := referenced_popups - defined_popups:
            self.fail(f"Undefined popups referenced in stat sets: {undefined_popups}")

    def test_modern_stat_sets_use_modern_popups(self) -> None:
        """Test that modernized stat sets use modern popup classes."""
        popup_windows = self.root.find("popup_windows")
        modern_popup_classes = {"ModernSubmenu", "ModernSubmenuLight", "ModernSubmenuClassic"}

        # Build map of popup name to class
        popup_class_map = {pu.get("pu_name"): pu.get("pu_class") for pu in popup_windows.findall("pu")}

        # Check modernized stat sets
        stat_sets = self.root.find("stat_sets")
        modernized_stat_sets = [
            "holdem_6max_pro",
            "holdem_9max_pro",
            "holdem_headsup_pro",
            "holdem_tournament_pro",
            "omaha_cg_expert",
            "stud_cg_expert",
        ]

        for ss in stat_sets.findall("ss"):
            ss_name = ss.get("name")

            if ss_name in modernized_stat_sets:
                # Find stats with popups
                for stat in ss.findall("stat"):
                    popup = stat.get("popup")
                    stat_name = stat.get("_stat_name")

                    if popup and popup in popup_class_map:
                        popup_class = popup_class_map[popup]

                        # If it's a main stat (like playershort), should use modern popup
                        if stat_name in ["playershort"] and popup_class not in modern_popup_classes:
                            self.fail(
                                f"Stat set '{ss_name}' stat '{stat_name}' uses non-modern popup '{popup}' (class: {popup_class})",
                            )

    def test_popup_consistency_across_variants(self) -> None:
        """Test popup usage consistency across game variants."""
        stat_sets = self.root.find("stat_sets")

        # Group stat sets by type
        holdem_sets = [ss for ss in stat_sets.findall("ss") if "holdem" in ss.get("name", "")]
        [ss for ss in stat_sets.findall("ss") if "omaha" in ss.get("name", "")]
        [ss for ss in stat_sets.findall("ss") if "stud" in ss.get("name", "")]

        # Test that similar stat sets use consistent popup patterns
        def get_popup_usage(stat_sets_list):
            """Get popup usage patterns for a list of stat sets."""
            usage = {}
            for ss in stat_sets_list:
                ss_name = ss.get("name")
                usage[ss_name] = {}

                for stat in ss.findall("stat"):
                    stat_name = stat.get("_stat_name")
                    popup = stat.get("popup")
                    if stat_name and popup:
                        usage[ss_name][stat_name] = popup
            return usage

        # For holdem variants, playershort should have consistent popup strategy
        holdem_usage = get_popup_usage(holdem_sets)
        for ss_name, stats in holdem_usage.items():
            if "playershort" in stats:
                popup = stats["playershort"]
                # Should either be a modern popup or 'holdring_main' (legacy)
                assert popup.startswith(("cash_", "tournament_")) or popup in ["holdring_main", "holdring_modern", "holdtour_main"], f"Holdem stat set '{ss_name}' uses unexpected popup for playershort: '{popup}'"


if __name__ == "__main__":
    unittest.main(verbosity=2)
