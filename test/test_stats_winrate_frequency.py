#!/usr/bin/env python3
"""
Test suite for winrate and frequency statistics implementation.

This module tests the newly implemented statistics:
- SD Winrate (Showdown Winrate)
- Non-SD Winrate (Non-Showdown Winrate) 
- Bet Frequency (Flop, Turn)
- Raise Frequency (Flop, Turn)
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    sd_winrate,
    non_sd_winrate,
    bet_frequency_flop,
    bet_frequency_turn,
    raise_frequency_flop,
    raise_frequency_turn,
)


class TestSDWinrateStat:
    """Test suite for SD Winrate (Showdown Winrate) statistic."""

    def test_sd_winrate_with_no_showdowns(self):
        """Test sd_winrate returns '-' when no showdown opportunities."""
        stat_dict = {
            'player1': {'sd': 0, 'wmsd': 0}  # sawShowdown=0, wonAtSD=0
        }
        result = sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "sd_wr=-"
        assert result[4] == "(-/-)"

    def test_sd_winrate_with_zero_but_showdowns(self):
        """Test sd_winrate returns '0.0' when player never won at showdown but had showdowns."""
        stat_dict = {
            'player1': {'sd': 8, 'wmsd': 0}  # sawShowdown=8, wonAtSD=0
        }
        result = sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "sd_wr=0.0%"
        assert result[4] == "(0/8)"

    def test_sd_winrate_with_normal_value(self):
        """Test sd_winrate returns normal percentage when player won at showdown."""
        stat_dict = {
            'player1': {'sd': 10, 'wmsd': 6}  # sawShowdown=10, wonAtSD=6
        }
        result = sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "60.0"  # 6/10 = 60%
        assert result[2] == "sd_wr=60.0%"
        assert result[4] == "(6/10)"

    def test_sd_winrate_exception_handling(self):
        """Test sd_winrate returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = sd_winrate(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "sd_wr=-"


class TestNonSDWinrateStat:
    """Test suite for Non-SD Winrate (Non-Showdown Winrate) statistic."""

    def test_non_sd_winrate_with_no_non_showdown_opportunities(self):
        """Test non_sd_winrate returns '-' when no non-showdown opportunities."""
        stat_dict = {
            'player1': {
                'saw_f': 5, 'sd': 5, 'wmsd': 3, 'w_w_s_1': 3  # All flops went to showdown
            }
        }
        result = non_sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "nsd_wr=-"
        assert result[4] == "(-/-)"

    def test_non_sd_winrate_with_zero_but_opportunities(self):
        """Test non_sd_winrate returns '0.0' when player never won non-showdown but had opportunities."""
        stat_dict = {
            'player1': {
                'saw_f': 10, 'sd': 3, 'wmsd': 2, 'w_w_s_1': 2  # 7 non-showdown opportunities, 0 wins
            }
        }
        result = non_sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "0.0"  # (2-2)/(10-3) = 0/7 = 0%
        assert result[2] == "nsd_wr=0.0%"
        assert result[4] == "(0/7)"

    def test_non_sd_winrate_with_normal_value(self):
        """Test non_sd_winrate returns normal percentage when player won non-showdown."""
        stat_dict = {
            'player1': {
                'saw_f': 15, 'sd': 5, 'wmsd': 3, 'w_w_s_1': 8  # 10 non-showdown opportunities, 5 wins
            }
        }
        result = non_sd_winrate(stat_dict, 'player1')
        
        assert result[1] == "50.0"  # (8-3)/(15-5) = 5/10 = 50%
        assert result[2] == "nsd_wr=50.0%"
        assert result[4] == "(5/10)"

    def test_non_sd_winrate_exception_handling(self):
        """Test non_sd_winrate returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = non_sd_winrate(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "nsd_wr=-"


class TestBetFrequencyStat:
    """Test suite for Bet Frequency statistics."""

    def test_bet_frequency_flop_with_no_opportunities(self):
        """Test bet_frequency_flop returns '-' when no flop opportunities."""
        stat_dict = {
            'player1': {'saw_f': 0, 'street1Bets': 0}
        }
        result = bet_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "bet_f=-"
        assert result[4] == "(-/-)"

    def test_bet_frequency_flop_with_zero_but_opportunities(self):
        """Test bet_frequency_flop returns '0.0' when player never bet flop but saw flop."""
        stat_dict = {
            'player1': {'saw_f': 12, 'street1Bets': 0}
        }
        result = bet_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "bet_f=0.0%"
        assert result[4] == "(0/12)"

    def test_bet_frequency_flop_with_normal_value(self):
        """Test bet_frequency_flop returns normal percentage when player bet flop."""
        stat_dict = {
            'player1': {'saw_f': 20, 'street1Bets': 8}
        }
        result = bet_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "40.0"  # 8/20 = 40%
        assert result[2] == "bet_f=40.0%"
        assert result[4] == "(8/20)"

    def test_bet_frequency_turn_with_normal_value(self):
        """Test bet_frequency_turn returns normal percentage when player bet turn."""
        stat_dict = {
            'player1': {'saw_t': 15, 'street2Bets': 6}
        }
        result = bet_frequency_turn(stat_dict, 'player1')
        
        assert result[1] == "40.0"  # 6/15 = 40%
        assert result[2] == "bet_t=40.0%"
        assert result[4] == "(6/15)"

    def test_bet_frequency_exception_handling(self):
        """Test bet_frequency functions return format_no_data_stat on exceptions."""
        stat_dict = {}
        
        result_flop = bet_frequency_flop(stat_dict, 'nonexistent_player')
        assert result_flop[1] == "-"
        assert result_flop[2] == "bet_f=-"
        
        result_turn = bet_frequency_turn(stat_dict, 'nonexistent_player')
        assert result_turn[1] == "-"
        assert result_turn[2] == "bet_t=-"


class TestRaiseFrequencyStat:
    """Test suite for Raise Frequency statistics."""

    def test_raise_frequency_flop_with_no_opportunities(self):
        """Test raise_frequency_flop returns '-' when no flop opportunities."""
        stat_dict = {
            'player1': {'saw_f': 0, 'street1Raises': 0}
        }
        result = raise_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "raise_f=-"
        assert result[4] == "(-/-)"

    def test_raise_frequency_flop_with_zero_but_opportunities(self):
        """Test raise_frequency_flop returns '0.0' when player never raised flop but saw flop."""
        stat_dict = {
            'player1': {'saw_f': 18, 'street1Raises': 0}
        }
        result = raise_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "raise_f=0.0%"
        assert result[4] == "(0/18)"

    def test_raise_frequency_flop_with_normal_value(self):
        """Test raise_frequency_flop returns normal percentage when player raised flop."""
        stat_dict = {
            'player1': {'saw_f': 25, 'street1Raises': 5}
        }
        result = raise_frequency_flop(stat_dict, 'player1')
        
        assert result[1] == "20.0"  # 5/25 = 20%
        assert result[2] == "raise_f=20.0%"
        assert result[4] == "(5/25)"

    def test_raise_frequency_turn_with_normal_value(self):
        """Test raise_frequency_turn returns normal percentage when player raised turn."""
        stat_dict = {
            'player1': {'saw_t': 12, 'street2Raises': 3}
        }
        result = raise_frequency_turn(stat_dict, 'player1')
        
        assert result[1] == "25.0"  # 3/12 = 25%
        assert result[2] == "raise_t=25.0%"
        assert result[4] == "(3/12)"

    def test_raise_frequency_exception_handling(self):
        """Test raise_frequency functions return format_no_data_stat on exceptions."""
        stat_dict = {}
        
        result_flop = raise_frequency_flop(stat_dict, 'nonexistent_player')
        assert result_flop[1] == "-"
        assert result_flop[2] == "raise_f=-"
        
        result_turn = raise_frequency_turn(stat_dict, 'nonexistent_player')
        assert result_turn[1] == "-"
        assert result_turn[2] == "raise_t=-"


class TestWinrateFrequencyStatsIntegration:
    """Integration tests for the new winrate and frequency statistics."""

    def test_new_player_all_stats_no_data(self):
        """Test all new stats return '-' for a completely new player."""
        stat_dict = {
            'new_player': {
                'sd': 0, 'wmsd': 0, 'saw_f': 0, 'w_w_s_1': 0,
                'saw_t': 0, 'street1Bets': 0, 'street2Bets': 0,
                'street1Raises': 0, 'street2Raises': 0
            }
        }
        
        # All new stats should return '-' for display
        assert sd_winrate(stat_dict, 'new_player')[1] == "-"
        assert non_sd_winrate(stat_dict, 'new_player')[1] == "-"
        assert bet_frequency_flop(stat_dict, 'new_player')[1] == "-"
        assert bet_frequency_turn(stat_dict, 'new_player')[1] == "-"
        assert raise_frequency_flop(stat_dict, 'new_player')[1] == "-"
        assert raise_frequency_turn(stat_dict, 'new_player')[1] == "-"

    def test_active_player_with_mixed_values(self):
        """Test new stats return correct values for an active player."""
        stat_dict = {
            'active_player': {
                # Showdown: 5 showdowns, won 3
                'sd': 5, 'wmsd': 3,
                # Non-showdown: 20 flops, 5 showdowns, won 12 overall = 9 non-showdown wins
                'saw_f': 20, 'w_w_s_1': 12,
                # Turn: saw 15 turns
                'saw_t': 15,
                # Betting: bet 8 flops, 6 turns
                'street1Bets': 8, 'street2Bets': 6,
                # Raising: raised 4 flops, 2 turns
                'street1Raises': 4, 'street2Raises': 2
            }
        }
        
        # Should show calculated values
        assert sd_winrate(stat_dict, 'active_player')[1] == "60.0"  # 3/5 = 60%
        assert non_sd_winrate(stat_dict, 'active_player')[1] == "60.0"  # (12-3)/(20-5) = 9/15 = 60%
        assert bet_frequency_flop(stat_dict, 'active_player')[1] == "40.0"  # 8/20 = 40%
        assert bet_frequency_turn(stat_dict, 'active_player')[1] == "40.0"  # 6/15 = 40%
        assert raise_frequency_flop(stat_dict, 'active_player')[1] == "20.0"  # 4/20 = 20%
        assert raise_frequency_turn(stat_dict, 'active_player')[1] == "13.3"  # 2/15 = 13.3%

    def test_conservative_player_profile(self):
        """Test stats for a conservative player who rarely bets/raises."""
        stat_dict = {
            'conservative_player': {
                # Good showdown winrate but few showdowns
                'sd': 3, 'wmsd': 2,
                # Many flops seen but few wins
                'saw_f': 30, 'w_w_s_1': 8,
                'saw_t': 18,
                # Very low betting/raising frequency
                'street1Bets': 2, 'street2Bets': 1,
                'street1Raises': 1, 'street2Raises': 0
            }
        }
        
        # Should show conservative patterns
        assert sd_winrate(stat_dict, 'conservative_player')[1] == "66.7"  # 2/3 = 66.7%
        assert non_sd_winrate(stat_dict, 'conservative_player')[1] == "22.2"  # (8-2)/(30-3) = 6/27 = 22.2%
        assert bet_frequency_flop(stat_dict, 'conservative_player')[1] == "6.7"  # 2/30 = 6.7%
        assert bet_frequency_turn(stat_dict, 'conservative_player')[1] == "5.6"  # 1/18 = 5.6%
        assert raise_frequency_flop(stat_dict, 'conservative_player')[1] == "3.3"  # 1/30 = 3.3%
        assert raise_frequency_turn(stat_dict, 'conservative_player')[1] == "0.0"  # 0/18 = 0%


class TestWinrateFrequencyStatsRegressionTests:
    """Regression tests to ensure new stats functionality is not broken."""

    def test_all_new_stats_exception_handling(self):
        """Test all new stats handle exceptions consistently."""
        stat_dict = {}
        
        assert sd_winrate(stat_dict, 'nonexistent_player')[1] == "-"
        assert non_sd_winrate(stat_dict, 'nonexistent_player')[1] == "-"
        assert bet_frequency_flop(stat_dict, 'nonexistent_player')[1] == "-"
        assert bet_frequency_turn(stat_dict, 'nonexistent_player')[1] == "-"
        assert raise_frequency_flop(stat_dict, 'nonexistent_player')[1] == "-"
        assert raise_frequency_turn(stat_dict, 'nonexistent_player')[1] == "-"

    def test_tuple_format_consistency(self):
        """Test that all new stats return properly formatted 6-element tuples."""
        stat_dict = {
            'test_player': {
                'sd': 10, 'wmsd': 6, 'saw_f': 20, 'w_w_s_1': 12,
                'saw_t': 15, 'street1Bets': 8, 'street2Bets': 6,
                'street1Raises': 4, 'street2Raises': 2
            }
        }
        
        # Test tuple structure for all new stats
        stats_to_test = [
            sd_winrate, non_sd_winrate, bet_frequency_flop, bet_frequency_turn,
            raise_frequency_flop, raise_frequency_turn
        ]
        
        for stat_func in stats_to_test:
            result = stat_func(stat_dict, 'test_player')
            assert len(result) == 6
            assert isinstance(result[0], float)  # stat value
            assert isinstance(result[1], str)    # percentage string
            assert isinstance(result[2], str)    # formatted string
            assert isinstance(result[3], str)    # formatted string
            assert isinstance(result[4], str)    # fraction string
            assert isinstance(result[5], str)    # description


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])