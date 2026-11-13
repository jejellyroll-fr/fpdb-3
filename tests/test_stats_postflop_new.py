#!/usr/bin/env python3
"""Test suite for new postflop statistics implementation.

This module tests the newly implemented postflop statistics:
- Float Bet (float)
- Probe Bet (probe)
"""


import pytest

from fpdb_3_legacy.Stats import (
    float_bet,
    probe_bet,
)


class TestFloatBetStat:
    """Test suite for Float Bet statistic."""

    def test_float_bet_with_no_opportunities(self) -> None:
        """Test float_bet returns '-' when no opportunities to float."""
        stat_dict = {"player1": {"street1inposition": 0, "call_1": 0, "bet_2": 0, "saw_f": 0, "saw_2": 0}}
        result = float_bet(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "float=-"
        assert result[4] == "(-/-)"

    def test_float_bet_with_zero_but_opportunities(self) -> None:
        """Test float_bet returns '0.0' when player had opportunities but never floated."""
        stat_dict = {"player1": {"street1inposition": 5, "call_1": 5, "bet_2": 0, "saw_f": 5, "saw_2": 5}}
        result = float_bet(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "float=0.0%"
        assert result[4] == "(0/5)"

    def test_float_bet_with_normal_value(self) -> None:
        """Test float_bet returns normal percentage when player floated."""
        stat_dict = {"player1": {"street1inposition": 10, "call_1": 8, "bet_2": 3, "saw_f": 10, "saw_2": 8}}
        result = float_bet(stat_dict, "player1")

        assert result[1] == "37.5"  # 3/8 = 37.5%
        assert result[2] == "float=37.5%"
        assert result[4] == "(3/8)"

    def test_float_bet_exception_handling(self) -> None:
        """Test float_bet returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = float_bet(stat_dict, "nonexistent_player")

        assert result[1] == "-"
        assert result[2] == "float=-"


class TestProbeBetStat:
    """Test suite for Probe Bet statistic."""

    def test_probe_bet_with_no_opportunities(self) -> None:
        """Test probe_bet returns '-' when no opportunities to probe."""
        stat_dict = {"player1": {"bet_1": 0, "saw_f": 0, "cb_opp_1": 0, "cb_1": 0}}
        result = probe_bet(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "probe=-"
        assert result[4] == "(-/-)"

    def test_probe_bet_with_zero_but_opportunities(self) -> None:
        """Test probe_bet returns '0.0' when player had opportunities but never probed."""
        stat_dict = {
            "player1": {
                "bet_1": 0,
                "saw_f": 10,
                "cb_opp_1": 8,
                "cb_1": 3,  # 7 probe opportunities (10-3)
            },
        }
        result = probe_bet(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "probe=0.0%"
        assert result[4] == "(0/7)"

    def test_probe_bet_with_normal_value(self) -> None:
        """Test probe_bet returns normal percentage when player probed."""
        stat_dict = {
            "player1": {
                "bet_1": 2,
                "saw_f": 12,
                "cb_opp_1": 10,
                "cb_1": 4,  # 8 probe opportunities (12-4)
            },
        }
        result = probe_bet(stat_dict, "player1")

        assert result[1] == "25.0"  # 2/8 = 25%
        assert result[2] == "probe=25.0%"
        assert result[4] == "(2/8)"

    def test_probe_bet_exception_handling(self) -> None:
        """Test probe_bet returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = probe_bet(stat_dict, "nonexistent_player")

        assert result[1] == "-"
        assert result[2] == "probe=-"


class TestNewPostflopStatsIntegration:
    """Integration tests for the new postflop statistics."""

    def test_new_player_all_stats_no_data(self) -> None:
        """Test all new postflop stats return '-' for a completely new player."""
        stat_dict = {
            "new_player": {
                "street1inposition": 0,
                "call_1": 0,
                "bet_2": 0,
                "saw_f": 0,
                "saw_2": 0,
                "bet_1": 0,
                "cb_opp_1": 0,
                "cb_1": 0,
            },
        }

        # All new postflop stats should return '-' for display
        assert float_bet(stat_dict, "new_player")[1] == "-"
        assert probe_bet(stat_dict, "new_player")[1] == "-"

    def test_active_player_with_real_zeros(self) -> None:
        """Test new postflop stats return correct values for an active player."""
        stat_dict = {
            "active_player": {
                # Float: has opportunities but never floated
                "street1inposition": 8,
                "call_1": 6,
                "bet_2": 0,
                "saw_f": 8,
                "saw_2": 6,
                # Probe: has opportunities and probed sometimes
                "bet_1": 1,
                "cb_opp_1": 8,
                "cb_1": 3,  # 5 probe opportunities
            },
        }

        # These should show calculated values
        assert float_bet(stat_dict, "active_player")[1] == "0.0"  # 0/6 = 0%
        assert probe_bet(stat_dict, "active_player")[1] == "20.0"  # 1/5 = 20%

    def test_mixed_scenario_postflop_stats(self) -> None:
        """Test realistic scenario with various postflop stats."""
        stat_dict = {
            "mixed_player": {
                # Float: good opportunities and uses them
                "street1inposition": 15,
                "call_1": 10,
                "bet_2": 4,
                "saw_f": 15,
                "saw_2": 10,
                # Probe: moderate opportunities and uses them
                "bet_1": 2,
                "cb_opp_1": 15,
                "cb_1": 8,  # 7 probe opportunities
            },
        }

        # Should show percentages (has data)
        assert float_bet(stat_dict, "mixed_player")[1] == "40.0"  # 4/10 = 40%
        assert probe_bet(stat_dict, "mixed_player")[1] == "28.6"  # 2/7 = 28.6%


class TestNewPostflopStatsRegressionTests:
    """Regression tests to ensure new postflop stats functionality is not broken."""

    def test_all_new_stats_exception_handling(self) -> None:
        """Test all new postflop stats handle exceptions consistently."""
        stat_dict = {}

        assert float_bet(stat_dict, "nonexistent_player")[1] == "-"
        assert probe_bet(stat_dict, "nonexistent_player")[1] == "-"

    def test_tuple_format_consistency(self) -> None:
        """Test that all new stats return properly formatted 6-element tuples."""
        stat_dict = {
            "test_player": {
                "street1inposition": 10,
                "call_1": 8,
                "bet_2": 3,
                "saw_f": 10,
                "saw_2": 8,
                "bet_1": 2,
                "cb_opp_1": 10,
                "cb_1": 4,
            },
        }

        # Test tuple structure for all new stats
        stats_to_test = [float_bet, probe_bet]

        for stat_func in stats_to_test:
            result = stat_func(stat_dict, "test_player")
            assert len(result) == 6
            assert isinstance(result[0], float)  # stat value
            assert isinstance(result[1], str)  # percentage string
            assert isinstance(result[2], str)  # formatted string
            assert isinstance(result[3], str)  # formatted string
            assert isinstance(result[4], str)  # fraction string
            assert isinstance(result[5], str)  # description


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
