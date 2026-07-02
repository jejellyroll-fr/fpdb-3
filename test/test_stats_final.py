#!/usr/bin/env python3
"""Test suite for final statistics implementation.

This module tests the newly implemented final statistics:
- RFI by Position (Early, Middle, Late)
- Average Bet Size (Flop, Turn, River)
- Overbet Frequency
"""

import os
import sys

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.Stats import (
    avg_bet_size_flop,
    avg_bet_size_river,
    avg_bet_size_turn,
    overbet_frequency,
    rfi_early_position,
    rfi_late_position,
    rfi_middle_position,
)


class TestRFIByPositionStats:
    """Test suite for RFI by Position statistics."""

    def test_rfi_early_position_with_no_opportunities(self) -> None:
        """Test rfi_early_position returns '-' when no opportunities."""
        stat_dict = {"player1": {"pfr_opp": 0, "pfr": 0, "tb_0": 0}}
        result = rfi_early_position(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "rfi_ep=-"
        assert result[4] == "(-/-)"

    def test_rfi_early_position_with_normal_value(self) -> None:
        """Test rfi_early_position computes from dedicated positional keys."""
        stat_dict = {
            "player1": {"rfi_opp_ep": 100, "rfi_ep": 15},
        }
        result = rfi_early_position(stat_dict, "player1")

        # stat = rfi_ep / rfi_opp_ep = 15 / 100 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_ep=15.0%"
        assert result[4] == "(15/100)"

    def test_rfi_middle_position_with_normal_value(self) -> None:
        """Test rfi_middle_position computes from dedicated positional keys."""
        stat_dict = {
            "player1": {"rfi_opp_mp": 100, "rfi_mp": 15},
        }
        result = rfi_middle_position(stat_dict, "player1")

        # stat = rfi_mp / rfi_opp_mp = 15 / 100 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_mp=15.0%"
        assert result[4] == "(15/100)"

    def test_rfi_late_position_with_normal_value(self) -> None:
        """Test rfi_late_position computes from dedicated positional keys."""
        stat_dict = {
            "player1": {"rfi_opp_lp": 100, "rfi_lp": 15},
        }
        result = rfi_late_position(stat_dict, "player1")

        # stat = rfi_lp / rfi_opp_lp = 15 / 100 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_lp=15.0%"
        assert result[4] == "(15/100)"

    def test_rfi_position_exception_handling(self) -> None:
        """Test RFI position stats return format_no_data_stat on exceptions."""
        stat_dict = {}

        assert rfi_early_position(stat_dict, "nonexistent_player")[1] == "-"
        assert rfi_middle_position(stat_dict, "nonexistent_player")[1] == "-"
        assert rfi_late_position(stat_dict, "nonexistent_player")[1] == "-"


class TestAvgBetSizeStats:
    """Test suite for Average Bet Size statistics."""

    def test_avg_bet_size_flop_with_no_bets(self) -> None:
        """Test avg_bet_size_flop returns '-' when no flop bets."""
        stat_dict = {"player1": {"street1Bets": 0, "saw_f": 10}}
        result = avg_bet_size_flop(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "avg_bet_f=-"
        assert result[4] == "(-/-)"

    def test_avg_bet_size_flop_with_bets(self) -> None:
        """avg_bet_size_flop is deprecated (no bet-size column); returns no-data."""
        stat_dict = {"player1": {"street1Bets": 8, "saw_f": 20}}
        result = avg_bet_size_flop(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "avg_bet_f=-"
        assert result[4] == "(-/-)"

    def test_avg_bet_size_turn_with_bets(self) -> None:
        """avg_bet_size_turn is deprecated (no bet-size column); returns no-data."""
        stat_dict = {"player1": {"street2Bets": 5, "saw_t": 15}}
        result = avg_bet_size_turn(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "avg_bet_t=-"
        assert result[4] == "(-/-)"

    def test_avg_bet_size_river_with_bets(self) -> None:
        """avg_bet_size_river is deprecated (no bet-size column); returns no-data."""
        stat_dict = {"player1": {"street3Bets": 3, "saw_r": 10}}
        result = avg_bet_size_river(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "avg_bet_r=-"
        assert result[4] == "(-/-)"

    def test_avg_bet_size_exception_handling(self) -> None:
        """Test avg bet size stats return format_no_data_stat on exceptions."""
        stat_dict = {}

        assert avg_bet_size_flop(stat_dict, "nonexistent_player")[1] == "-"
        assert avg_bet_size_turn(stat_dict, "nonexistent_player")[1] == "-"
        assert avg_bet_size_river(stat_dict, "nonexistent_player")[1] == "-"


class TestOverbetFrequencyStats:
    """Test suite for Overbet Frequency statistics."""

    def test_overbet_frequency_with_no_bets(self) -> None:
        """Test overbet_frequency returns '-' when no bets."""
        stat_dict = {"player1": {"street1Bets": 0, "street2Bets": 0, "street3Bets": 0}}
        result = overbet_frequency(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "overbet=-"
        assert result[4] == "(-/-)"

    def test_overbet_frequency_with_bets(self) -> None:
        """Test overbet_frequency returns estimated frequency when player bet."""
        stat_dict = {"player1": {"street1Bets": 10, "street2Bets": 8, "street3Bets": 5}}
        result = overbet_frequency(stat_dict, "player1")

        # total_bets = 10 + 8 + 5 = 23
        # estimated_overbet_count = 23 * 0.15 = 3.45
        assert result[1] == "15.0"  # 15% overbet frequency
        assert result[2] == "overbet=15.0%"
        assert result[4] == "(3/23)"

    def test_overbet_frequency_exception_handling(self) -> None:
        """Test overbet_frequency returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = overbet_frequency(stat_dict, "nonexistent_player")

        assert result[1] == "-"
        assert result[2] == "overbet=-"


class TestFinalStatsIntegration:
    """Integration tests for the final statistics."""

    def test_new_player_all_stats_no_data(self) -> None:
        """Test all final stats return '-' for a completely new player."""
        stat_dict = {
            "new_player": {
                "pfr_opp": 0,
                "pfr": 0,
                "tb_0": 0,
                "street1Bets": 0,
                "street2Bets": 0,
                "street3Bets": 0,
                "saw_f": 0,
                "saw_t": 0,
                "saw_r": 0,
            },
        }

        # All final stats should return '-' for display
        assert rfi_early_position(stat_dict, "new_player")[1] == "-"
        assert rfi_middle_position(stat_dict, "new_player")[1] == "-"
        assert rfi_late_position(stat_dict, "new_player")[1] == "-"
        assert avg_bet_size_flop(stat_dict, "new_player")[1] == "-"
        assert avg_bet_size_turn(stat_dict, "new_player")[1] == "-"
        assert avg_bet_size_river(stat_dict, "new_player")[1] == "-"
        assert overbet_frequency(stat_dict, "new_player")[1] == "-"

    def test_tight_player_profile(self) -> None:
        """Test final stats for a tight player profile."""
        stat_dict = {
            "tight_player": {
                # Low RFI from all positions (10%)
                "rfi_opp_ep": 200,
                "rfi_ep": 20,
                "rfi_opp_mp": 200,
                "rfi_mp": 20,
                "rfi_opp_lp": 200,
                "rfi_lp": 20,
                # Conservative betting
                "street1Bets": 6,
                "street2Bets": 4,
                "street3Bets": 2,
            },
        }

        # Should show tight RFI patterns
        assert rfi_early_position(stat_dict, "tight_player")[1] == "10.0"  # 20/200 = 10%
        assert rfi_middle_position(stat_dict, "tight_player")[1] == "10.0"  # 20/200 = 10%
        assert rfi_late_position(stat_dict, "tight_player")[1] == "10.0"  # 20/200 = 10%
        # avg_bet_size_* are deprecated -> no-data
        assert avg_bet_size_flop(stat_dict, "tight_player")[1] == "-"
        assert avg_bet_size_turn(stat_dict, "tight_player")[1] == "-"
        assert avg_bet_size_river(stat_dict, "tight_player")[1] == "-"
        assert overbet_frequency(stat_dict, "tight_player")[1] == "15.0"  # Standard 15%

    def test_aggressive_player_profile(self) -> None:
        """Test final stats for an aggressive player profile."""
        stat_dict = {
            "aggressive_player": {
                # High RFI from all positions (26%)
                "rfi_opp_ep": 150,
                "rfi_ep": 39,
                "rfi_opp_mp": 150,
                "rfi_mp": 39,
                "rfi_opp_lp": 150,
                "rfi_lp": 39,
                # Aggressive betting
                "street1Bets": 20,
                "street2Bets": 15,
                "street3Bets": 10,
            },
        }

        # Should show aggressive RFI patterns
        assert rfi_early_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39/150 = 26%
        assert rfi_middle_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39/150 = 26%
        assert rfi_late_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39/150 = 26%
        # avg_bet_size_* are deprecated -> no-data
        assert avg_bet_size_flop(stat_dict, "aggressive_player")[1] == "-"
        assert avg_bet_size_turn(stat_dict, "aggressive_player")[1] == "-"
        assert avg_bet_size_river(stat_dict, "aggressive_player")[1] == "-"
        assert overbet_frequency(stat_dict, "aggressive_player")[1] == "15.0"  # Standard 15%


class TestFinalStatsRegressionTests:
    """Regression tests to ensure final stats functionality is not broken."""

    def test_all_final_stats_exception_handling(self) -> None:
        """Test all final stats handle exceptions consistently."""
        stat_dict = {}

        assert rfi_early_position(stat_dict, "nonexistent_player")[1] == "-"
        assert rfi_middle_position(stat_dict, "nonexistent_player")[1] == "-"
        assert rfi_late_position(stat_dict, "nonexistent_player")[1] == "-"
        assert avg_bet_size_flop(stat_dict, "nonexistent_player")[1] == "-"
        assert avg_bet_size_turn(stat_dict, "nonexistent_player")[1] == "-"
        assert avg_bet_size_river(stat_dict, "nonexistent_player")[1] == "-"
        assert overbet_frequency(stat_dict, "nonexistent_player")[1] == "-"

    def test_tuple_format_consistency(self) -> None:
        """Test that all final stats return properly formatted 6-element tuples."""
        stat_dict = {
            "test_player": {
                "pfr_opp": 100,
                "pfr": 20,
                "tb_0": 5,
                "street1Bets": 10,
                "street2Bets": 8,
                "street3Bets": 5,
                "saw_f": 40,
                "saw_t": 30,
                "saw_r": 20,
            },
        }

        # Test tuple structure for all final stats
        stats_to_test = [
            rfi_early_position,
            rfi_middle_position,
            rfi_late_position,
            avg_bet_size_flop,
            avg_bet_size_turn,
            avg_bet_size_river,
            overbet_frequency,
        ]

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
