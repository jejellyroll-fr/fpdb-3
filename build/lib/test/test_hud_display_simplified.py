#!/usr/bin/env python3
"""Simplified test suite for HUD display integration with the "no data" feature.

This module focuses on testing the core Stats.py functionality integration
with HUD display without complex PyQt5 mocking.
"""

import os
import sys

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import only what we need
import Stats


class TestStatsBase:
    """Test Stats.py integration for HUD display."""

    @staticmethod
    def _create_no_data_stat_dict() -> dict:
        """Helper to create stat_dict with no data."""
        return {1: {"vpip": 0, "vpip_opp": 0}}

    @staticmethod
    def _create_tight_player_stat_dict() -> dict:
        """Helper to create stat_dict for tight player."""
        return {1: {"vpip": 0, "vpip_opp": 20}}

    @staticmethod
    def _create_normal_player_stat_dict() -> dict:
        """Helper to create stat_dict for normal player."""
        return {1: {"vpip": 10, "vpip_opp": 50}}

    @staticmethod
    def _create_comprehensive_no_data_stat_dict() -> dict:
        """Helper to create comprehensive stat_dict with no data."""
        return {
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

    @staticmethod
    def _create_comprehensive_tight_player_stat_dict() -> dict:
        """Helper to create comprehensive stat_dict for tight player."""
        return {
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
                "saw_3": 0,
                "saw_4": 0,
            },
        }

    @staticmethod
    def _create_comprehensive_normal_player_stat_dict() -> dict:
        """Helper to create comprehensive stat_dict for normal player."""
        return {
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

    def _assert_stat_result_basic(self, result, expected_display: str, expected_fraction: str) -> None:
        """Helper to assert basic stat result properties."""
        assert result is not None
        assert result[1] == expected_display
        assert result[4] == expected_fraction

    def _assert_stat_result_with_description(
        self, result, expected_display: str, expected_fraction: str, expected_description: str
    ) -> None:
        """Helper to assert stat result with description."""
        self._assert_stat_result_basic(result, expected_display, expected_fraction)
        assert result[5] == expected_description


class TestStatsIntegrationForHUD(TestStatsBase):
    """Test Stats.py integration for HUD display."""

    def test_stats_do_stat_with_no_data(self) -> None:
        """Test Stats.do_stat() with no data scenarios."""
        stat_dict = self._create_no_data_stat_dict()

        # Test VPIP with no data
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_basic(result, "-", "(-/-)")

    def test_stats_do_stat_with_tight_player(self) -> None:
        """Test Stats.do_stat() with tight player data."""
        stat_dict = self._create_tight_player_stat_dict()

        # Test VPIP with tight player
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_basic(result, "0.0", "(0/20)")

    def test_stats_do_stat_with_normal_player(self) -> None:
        """Test Stats.do_stat() with normal player data."""
        stat_dict = self._create_normal_player_stat_dict()

        # Test VPIP with normal player
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_basic(result, "20.0", "(10/50)")

    def test_stats_do_stat_multiple_stats_consistency(self) -> None:
        """Test multiple stats consistency through do_stat."""
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
            },
        }

        # Test different stat types
        vpip_result = Stats.do_stat(stat_dict, 1, "vpip")
        pfr_result = Stats.do_stat(stat_dict, 1, "pfr")
        three_b_result = Stats.do_stat(stat_dict, 1, "three_B")
        steal_result = Stats.do_stat(stat_dict, 1, "steal")
        agg_fact_result = Stats.do_stat(stat_dict, 1, "agg_fact")

        # Check display values
        assert vpip_result[1] == "-"  # No data
        assert pfr_result[1] == "0.0"  # Tight player
        assert three_b_result[1] == "20.0"  # Normal player
        assert steal_result[1] == "-"  # No data
        assert agg_fact_result[1] == "-"  # No data (no post-flop actions)

    def test_stats_do_stat_with_exception_handling(self) -> None:
        """Test Stats.do_stat() exception handling."""
        stat_dict = {}  # Empty stat_dict

        # Test with missing player
        result = Stats.do_stat(stat_dict, 1, "vpip")
        assert result is not None
        assert result[1] == "NA"  # Should return "NA" for exceptions

    def test_stats_do_stat_with_malformed_data(self) -> None:
        """Test Stats.do_stat() with malformed data."""
        stat_dict = {
            1: {
                "vpip": "invalid",  # Invalid data type
                "vpip_opp": None,  # None value
            },
        }

        # Test with malformed data
        result = Stats.do_stat(stat_dict, 1, "vpip")
        assert result is not None
        assert result[1] == "NA"  # Should return "NA" for exceptions

    def test_stats_all_priority_stats_no_data(self) -> None:
        """Test all priority stats with no data."""
        stat_dict = self._create_comprehensive_no_data_stat_dict()

        priority_stats = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1", "agg_fact"]

        # Test all priority stats
        for stat_name in priority_stats:
            result = Stats.do_stat(stat_dict, 1, stat_name)
            assert result is not None
            assert result[1] == "-", f"Stat {stat_name} should show '-' for no data"

    def test_stats_all_priority_stats_tight_player(self) -> None:
        """Test all priority stats with tight player."""
        stat_dict = self._create_comprehensive_tight_player_stat_dict()

        # Test stats with expected results
        stats_expected = {
            "vpip": "0.0",  # Had opportunities
            "pfr": "0.0",  # Had opportunities
            "three_B": "0.0",  # Had opportunities
            "steal": "0.0",  # Had opportunities
            "cbet": "-",  # No opportunities
            "a_freq1": "0.0",  # Saw flop but passive
            "agg_fact": "0.00",  # Only calls, no aggression
        }

        for stat_name, expected in stats_expected.items():
            result = Stats.do_stat(stat_dict, 1, stat_name)
            assert result is not None
            assert result[1] == expected, f"Stat {stat_name} should show '{expected}' for tight player"

    def test_stats_all_priority_stats_normal_player(self) -> None:
        """Test all priority stats with normal player."""
        stat_dict = self._create_comprehensive_normal_player_stat_dict()

        # Test stats with expected results
        stats_expected = {
            "vpip": "20.0",
            "pfr": "10.0",
            "three_B": "20.0",
            "steal": "25.0",
            "cbet": "50.0",
            "a_freq1": "40.0",  # 6/15
        }

        for stat_name, expected in stats_expected.items():
            result = Stats.do_stat(stat_dict, 1, stat_name)
            assert result is not None
            assert result[1] == expected, f"Stat {stat_name} should show '{expected}' for normal player"

    def test_stats_tooltip_content_no_data(self) -> None:
        """Test tooltip content for no data stats."""
        stat_dict = self._create_no_data_stat_dict()
        stat_dict[1]["screen_name"] = "NewPlayer"

        # Test VPIP tooltip content
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_with_description(result, "-", "(-/-)", "Voluntarily put in preflop/3rd street %")

    def test_stats_tooltip_content_tight_player(self) -> None:
        """Test tooltip content for tight player stats."""
        stat_dict = self._create_tight_player_stat_dict()
        stat_dict[1]["screen_name"] = "TightPlayer"

        # Test VPIP tooltip content
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_with_description(result, "0.0", "(0/20)", "Voluntarily put in preflop/3rd street %")

    def test_stats_tooltip_content_normal_player(self) -> None:
        """Test tooltip content for normal player stats."""
        stat_dict = self._create_normal_player_stat_dict()
        stat_dict[1]["screen_name"] = "NormalPlayer"

        # Test VPIP tooltip content
        result = Stats.do_stat(stat_dict, 1, "vpip")
        self._assert_stat_result_with_description(result, "20.0", "(10/50)", "Voluntarily put in preflop/3rd street %")

    def test_stats_fraction_consistency(self) -> None:
        """Test fraction consistency for tooltip display."""
        # Test no data
        stat_dict_no_data = self._create_no_data_stat_dict()
        result_no_data = Stats.do_stat(stat_dict_no_data, 1, "vpip")
        assert result_no_data[4] == "(-/-)"

        # Test tight player
        stat_dict_tight = self._create_tight_player_stat_dict()
        result_tight = Stats.do_stat(stat_dict_tight, 1, "vpip")
        assert result_tight[4] == "(0/20)"

        # Test normal player
        stat_dict_normal = self._create_normal_player_stat_dict()
        result_normal = Stats.do_stat(stat_dict_normal, 1, "vpip")
        assert result_normal[4] == "(10/50)"

    def test_stats_description_consistency(self) -> None:
        """Test description consistency across different data states."""
        stat_dicts = [
            self._create_no_data_stat_dict(),  # No data
            self._create_tight_player_stat_dict(),  # Tight player
            self._create_normal_player_stat_dict(),  # Normal player
        ]

        expected_description = "Voluntarily put in preflop/3rd street %"

        for stat_dict in stat_dicts:
            result = Stats.do_stat(stat_dict, 1, "vpip")
            assert result[5] == expected_description

    def test_stats_format_consistency_across_stats(self) -> None:
        """Test format consistency across different stat types."""
        stat_dict = self._create_comprehensive_no_data_stat_dict()

        stats_to_test = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        for stat_name in stats_to_test:
            result = Stats.do_stat(stat_dict, 1, stat_name)
            assert result is not None
            assert result[1] == "-", f"Stat {stat_name} should consistently show '-' for no data"
            assert result[4] == "(-/-)", f"Stat {stat_name} should consistently show '(-/-)' for no data"


class TestStatsPerformanceForHUD(TestStatsBase):
    """Test performance of Stats.py for HUD integration."""

    def test_stats_performance_single_stat(self) -> None:
        """Test performance of single stat calculation."""
        import time

        stat_dict = self._create_normal_player_stat_dict()

        # Time multiple calculations
        start_time = time.time()
        for _ in range(1000):
            Stats.do_stat(stat_dict, 1, "vpip")
        end_time = time.time()

        # Should complete quickly
        duration = end_time - start_time
        assert duration < 1.0, f"1000 stat calculations took {duration:.3f}s, should be < 1.0s"

    def test_stats_performance_multiple_stats(self) -> None:
        """Test performance of multiple stat calculations."""
        import itertools
        import time

        stat_dict = self._create_comprehensive_normal_player_stat_dict()

        stats_to_test = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        # Time multiple calculations
        start_time = time.time()
        for _, stat_name in itertools.product(range(100), stats_to_test):
            Stats.do_stat(stat_dict, 1, stat_name)
        end_time = time.time()

        # Should complete quickly (600 total calculations)
        duration = end_time - start_time
        assert duration < 1.0, f"600 stat calculations took {duration:.3f}s, should be < 1.0s"

    def test_stats_performance_no_data(self) -> None:
        """Test performance with no data stats."""
        import itertools
        import time

        stat_dict = self._create_comprehensive_no_data_stat_dict()

        stats_to_test = ["vpip", "pfr", "three_B", "steal", "cbet", "a_freq1"]

        # Time multiple calculations
        start_time = time.time()
        for _, stat_name in itertools.product(range(100), stats_to_test):
            Stats.do_stat(stat_dict, 1, stat_name)
        end_time = time.time()

        # Should complete quickly (600 total calculations)
        duration = end_time - start_time
        assert duration < 1.0, f"600 no-data stat calculations took {duration:.3f}s, should be < 1.0s"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
