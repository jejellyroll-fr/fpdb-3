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

from Stats import (
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
        """Test rfi_early_position returns normal percentage when player RFI early."""
        stat_dict = {
            "player1": {"pfr_opp": 100, "pfr": 20, "tb_0": 5},  # RFI = 15
        }
        result = rfi_early_position(stat_dict, "player1")

        # early_position_opportunities = 100 * 0.25 = 25
        # early_position_rfi = 15 * 0.25 = 3.75
        # stat = 3.75 / 25 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_ep=15.0%"
        assert result[4] == "(3/25)"

    def test_rfi_middle_position_with_normal_value(self) -> None:
        """Test rfi_middle_position returns normal percentage when player RFI middle."""
        stat_dict = {
            "player1": {"pfr_opp": 100, "pfr": 20, "tb_0": 5},  # RFI = 15
        }
        result = rfi_middle_position(stat_dict, "player1")

        # middle_position_opportunities = 100 * 0.30 = 30
        # middle_position_rfi = 15 * 0.30 = 4.5
        # stat = 4.5 / 30 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_mp=15.0%"
        assert result[4] == "(4/30)"

    def test_rfi_late_position_with_normal_value(self) -> None:
        """Test rfi_late_position returns normal percentage when player RFI late."""
        stat_dict = {
            "player1": {"pfr_opp": 100, "pfr": 20, "tb_0": 5},  # RFI = 15
        }
        result = rfi_late_position(stat_dict, "player1")

        # late_position_opportunities = 100 * 0.45 = 45
        # late_position_rfi = 15 * 0.45 = 6.75
        # stat = 6.75 / 45 = 15%
        assert result[1] == "15.0"
        assert result[2] == "rfi_lp=15.0%"
        assert result[4] == "(6/45)"

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
        """Test avg_bet_size_flop returns estimated size when player bet flop."""
        stat_dict = {"player1": {"street1Bets": 8, "saw_f": 20}}
        result = avg_bet_size_flop(stat_dict, "player1")

        assert result[1] == " 65"  # 65% of pot
        assert result[2] == "avg_bet_f= 65%"
        assert result[4] == "(8 bets)"

    def test_avg_bet_size_turn_with_bets(self) -> None:
        """Test avg_bet_size_turn returns estimated size when player bet turn."""
        stat_dict = {"player1": {"street2Bets": 5, "saw_t": 15}}
        result = avg_bet_size_turn(stat_dict, "player1")

        assert result[1] == " 70"  # 70% of pot
        assert result[2] == "avg_bet_t= 70%"
        assert result[4] == "(5 bets)"

    def test_avg_bet_size_river_with_bets(self) -> None:
        """Test avg_bet_size_river returns estimated size when player bet river."""
        stat_dict = {"player1": {"street3Bets": 3, "saw_r": 10}}
        result = avg_bet_size_river(stat_dict, "player1")

        assert result[1] == " 75"  # 75% of pot
        assert result[2] == "avg_bet_r= 75%"
        assert result[4] == "(3 bets)"

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
                # Low RFI from all positions
                "pfr_opp": 200,
                "pfr": 24,
                "tb_0": 4,  # RFI = 20, 10% total
                # Conservative betting
                "street1Bets": 6,
                "street2Bets": 4,
                "street3Bets": 2,
                "saw_f": 40,
                "saw_t": 25,
                "saw_r": 15,
            },
        }

        # Should show tight patterns
        assert rfi_early_position(stat_dict, "tight_player")[1] == "10.0"  # 20*0.25 / 200*0.25 = 10%
        assert rfi_middle_position(stat_dict, "tight_player")[1] == "10.0"  # 20*0.30 / 200*0.30 = 10%
        assert rfi_late_position(stat_dict, "tight_player")[1] == "10.0"  # 20*0.45 / 200*0.45 = 10%
        assert avg_bet_size_flop(stat_dict, "tight_player")[1] == " 65"  # Standard 65%
        assert avg_bet_size_turn(stat_dict, "tight_player")[1] == " 70"  # Standard 70%
        assert avg_bet_size_river(stat_dict, "tight_player")[1] == " 75"  # Standard 75%
        assert overbet_frequency(stat_dict, "tight_player")[1] == "15.0"  # Standard 15%

    def test_aggressive_player_profile(self) -> None:
        """Test final stats for an aggressive player profile."""
        stat_dict = {
            "aggressive_player": {
                # High RFI from all positions
                "pfr_opp": 150,
                "pfr": 45,
                "tb_0": 6,  # RFI = 39, 26% total
                # Aggressive betting
                "street1Bets": 20,
                "street2Bets": 15,
                "street3Bets": 10,
                "saw_f": 60,
                "saw_t": 45,
                "saw_r": 30,
            },
        }

        # Should show aggressive patterns
        assert rfi_early_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39*0.25 / 150*0.25 = 26%
        assert rfi_middle_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39*0.30 / 150*0.30 = 26%
        assert rfi_late_position(stat_dict, "aggressive_player")[1] == "26.0"  # 39*0.45 / 150*0.45 = 26%
        assert avg_bet_size_flop(stat_dict, "aggressive_player")[1] == " 65"  # Standard 65%
        assert avg_bet_size_turn(stat_dict, "aggressive_player")[1] == " 70"  # Standard 70%
        assert avg_bet_size_river(stat_dict, "aggressive_player")[1] == " 75"  # Standard 75%
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
