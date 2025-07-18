#!/usr/bin/env python3
"""
Test suite for extended Stats.py "no data" feature implementations.

This module tests the newly implemented format_no_data_stat functionality
for additional statistics like wtsd, wmsd, 4bet, etc.
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    wtsd,
    wmsd,
    four_B,
    cfour_B,
    f_SB_steal,
    f_BB_steal,
)


class TestWTSDNoDataFeature:
    """Test suite for WTSD (Went to Showdown) statistic no data feature."""

    def test_wtsd_with_no_opportunities(self):
        """Test WTSD returns '-' when no flops seen."""
        stat_dict = {
            'player1': {'saw_f': 0, 'sd': 0}
        }
        result = wtsd(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "wtsd=-"
        assert result[4] == "(-/-)"

    def test_wtsd_with_zero_but_opportunities(self):
        """Test WTSD returns '0.0' when player never went to showdown but saw flops."""
        stat_dict = {
            'player1': {'saw_f': 10, 'sd': 0}
        }
        result = wtsd(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "w=0.0%"
        assert result[4] == "(0/10)"

    def test_wtsd_with_normal_value(self):
        """Test WTSD returns normal percentage when player has showdowns."""
        stat_dict = {
            'player1': {'saw_f': 10, 'sd': 3}
        }
        result = wtsd(stat_dict, 'player1')
        
        assert result[1] == "30.0"
        assert result[2] == "w=30.0%"
        assert result[4] == "(3/10)"

    def test_wtsd_exception_handling(self):
        """Test WTSD still returns 'NA' on exceptions."""
        stat_dict = {}
        result = wtsd(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "w=NA"


class TestWMSDNoDataFeature:
    """Test suite for WMSD (Won Money at Showdown) statistic no data feature."""

    def test_wmsd_with_no_showdowns(self):
        """Test WMSD returns '-' when no showdowns."""
        stat_dict = {
            'player1': {'sd': 0, 'wmsd': 0}
        }
        result = wmsd(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "wmsd=-"
        assert result[4] == "(-/-)"

    def test_wmsd_with_zero_but_showdowns(self):
        """Test WMSD returns '0.0' when player never won at showdown but had showdowns."""
        stat_dict = {
            'player1': {'sd': 5, 'wmsd': 0}
        }
        result = wmsd(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "w=0.0%"
        assert result[4] == "(  0.0/5)"

    def test_wmsd_with_normal_value(self):
        """Test WMSD returns normal percentage when player won at showdown."""
        stat_dict = {
            'player1': {'sd': 5, 'wmsd': 3.5}
        }
        result = wmsd(stat_dict, 'player1')
        
        assert result[1] == "70.0"
        assert result[2] == "w=70.0%"
        assert result[4] == "(  3.5/5)"

    def test_wmsd_exception_handling(self):
        """Test WMSD still returns 'NA' on exceptions."""
        stat_dict = {}
        result = wmsd(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "w=NA"


class TestFourBetNoDataFeature:
    """Test suite for 4-bet statistic no data feature."""

    def test_four_b_with_no_opportunities(self):
        """Test 4-bet returns '-' when no opportunities."""
        stat_dict = {
            'player1': {'fb_opp_0': 0, 'fb_0': 0}
        }
        result = four_B(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "4B=-"
        assert result[4] == "(-/-)"

    def test_four_b_with_zero_but_opportunities(self):
        """Test 4-bet returns '0.0' when player never 4bet but had opportunities."""
        stat_dict = {
            'player1': {'fb_opp_0': 10, 'fb_0': 0}
        }
        result = four_B(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "4B=0.0%"
        assert result[4] == "(0/10)"

    def test_four_b_with_normal_value(self):
        """Test 4-bet returns normal percentage when player has 4bets."""
        stat_dict = {
            'player1': {'fb_opp_0': 10, 'fb_0': 2}
        }
        result = four_B(stat_dict, 'player1')
        
        assert result[1] == "20.0"
        assert result[2] == "4B=20.0%"
        assert result[4] == "(2/10)"

    def test_four_b_exception_handling(self):
        """Test 4-bet still returns 'NA' on exceptions."""
        stat_dict = {}
        result = four_B(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "4B=NA"


class TestColdFourBetNoDataFeature:
    """Test suite for Cold 4-bet statistic no data feature."""

    def test_cfour_b_with_no_opportunities(self):
        """Test Cold 4-bet returns '-' when no opportunities."""
        stat_dict = {
            'player1': {'cfb_opp_0': 0, 'cfb_0': 0}
        }
        result = cfour_B(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "C4B=-"
        assert result[4] == "(-/-)"

    def test_cfour_b_with_zero_but_opportunities(self):
        """Test Cold 4-bet returns '0.0' when player never cold 4bet but had opportunities."""
        stat_dict = {
            'player1': {'cfb_opp_0': 8, 'cfb_0': 0}
        }
        result = cfour_B(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "C4B=0.0%"
        assert result[4] == "(0/8)"

    def test_cfour_b_with_normal_value(self):
        """Test Cold 4-bet returns normal percentage when player has cold 4bets."""
        stat_dict = {
            'player1': {'cfb_opp_0': 8, 'cfb_0': 1}
        }
        result = cfour_B(stat_dict, 'player1')
        
        assert result[1] == "12.5"
        assert result[2] == "C4B=12.5%"
        assert result[4] == "(1/8)"

    def test_cfour_b_exception_handling(self):
        """Test Cold 4-bet still returns 'NA' on exceptions."""
        stat_dict = {}
        result = cfour_B(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "C4B=NA"


class TestFoldSBStealNoDataFeature:
    """Test suite for Fold SB to Steal statistic no data feature."""

    def test_f_sb_steal_with_no_opportunities(self):
        """Test Fold SB to steal returns '-' when no steal attempts."""
        stat_dict = {
            'player1': {'sbstolen': 0, 'sbnotdef': 0}
        }
        result = f_SB_steal(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "fSB=-"
        assert result[4] == "(-/-)"

    def test_f_sb_steal_with_zero_but_opportunities(self):
        """Test Fold SB to steal returns '0.0' when player never folded but had steal attempts."""
        stat_dict = {
            'player1': {'sbstolen': 5, 'sbnotdef': 0}
        }
        result = f_SB_steal(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "fSB=0.0%"
        assert result[4] == "(0/5)"

    def test_f_sb_steal_with_normal_value(self):
        """Test Fold SB to steal returns normal percentage when player folded."""
        stat_dict = {
            'player1': {'sbstolen': 5, 'sbnotdef': 3}
        }
        result = f_SB_steal(stat_dict, 'player1')
        
        assert result[1] == "60.0"
        assert result[2] == "fSB=60.0%"
        assert result[4] == "(3/5)"

    def test_f_sb_steal_exception_handling(self):
        """Test Fold SB to steal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = f_SB_steal(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "fSB=NA"


class TestFoldBBStealNoDataFeature:
    """Test suite for Fold BB to Steal statistic no data feature."""

    def test_f_bb_steal_with_no_opportunities(self):
        """Test Fold BB to steal returns '-' when no steal attempts."""
        stat_dict = {
            'player1': {'bbstolen': 0, 'bbnotdef': 0}
        }
        result = f_BB_steal(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "fBB=-"
        assert result[4] == "(-/-)"

    def test_f_bb_steal_with_zero_but_opportunities(self):
        """Test Fold BB to steal returns '0.0' when player never folded but had steal attempts."""
        stat_dict = {
            'player1': {'bbstolen': 8, 'bbnotdef': 0}
        }
        result = f_BB_steal(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "fBB=0.0%"
        assert result[4] == "(0/8)"

    def test_f_bb_steal_with_normal_value(self):
        """Test Fold BB to steal returns normal percentage when player folded."""
        stat_dict = {
            'player1': {'bbstolen': 8, 'bbnotdef': 5}
        }
        result = f_BB_steal(stat_dict, 'player1')
        
        assert result[1] == "62.5"
        assert result[2] == "fBB=62.5%"
        assert result[4] == "(5/8)"

    def test_f_bb_steal_exception_handling(self):
        """Test Fold BB to steal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = f_BB_steal(stat_dict, 'nonexistent_player')
        
        assert result[1] == "NA"
        assert result[2] == "fBB=NA"


class TestExtendedStatsIntegration:
    """Integration tests for the extended no data stats."""

    def test_new_player_extended_stats_no_data(self):
        """Test all new extended stats return '-' for a completely new player."""
        stat_dict = {
            'new_player': {
                'saw_f': 0, 'sd': 0,
                'wmsd': 0,
                'fb_opp_0': 0, 'fb_0': 0,
                'cfb_opp_0': 0, 'cfb_0': 0,
                'sbstolen': 0, 'sbnotdef': 0,
                'bbstolen': 0, 'bbnotdef': 0,
            }
        }
        
        # All extended stats should return '-' for display
        assert wtsd(stat_dict, 'new_player')[1] == "-"
        assert wmsd(stat_dict, 'new_player')[1] == "-"
        assert four_B(stat_dict, 'new_player')[1] == "-"
        assert cfour_B(stat_dict, 'new_player')[1] == "-"
        assert f_SB_steal(stat_dict, 'new_player')[1] == "-"
        assert f_BB_steal(stat_dict, 'new_player')[1] == "-"

    def test_active_player_with_real_zeros(self):
        """Test extended stats return '0.0' for an active player with real zero values."""
        stat_dict = {
            'active_player': {
                'saw_f': 20, 'sd': 0,      # Saw flops but never went to showdown
                'wmsd': 0,                  # Never won at showdown
                'fb_opp_0': 10, 'fb_0': 0, # Had 4bet opportunities but never 4bet
                'cfb_opp_0': 5, 'cfb_0': 0, # Had cold 4bet opportunities but never cold 4bet
                'sbstolen': 8, 'sbnotdef': 0, # Had steal attempts but always defended SB
                'bbstolen': 6, 'bbnotdef': 0, # Had steal attempts but always defended BB
            }
        }
        
        # These should show 0.0 (real zero values with opportunities)
        assert wtsd(stat_dict, 'active_player')[1] == "0.0"
        assert wmsd(stat_dict, 'active_player')[1] == "-"  # No showdowns
        assert four_B(stat_dict, 'active_player')[1] == "0.0"
        assert cfour_B(stat_dict, 'active_player')[1] == "0.0"
        assert f_SB_steal(stat_dict, 'active_player')[1] == "0.0"
        assert f_BB_steal(stat_dict, 'active_player')[1] == "0.0"

    def test_mixed_scenario_extended_stats(self):
        """Test realistic scenario with some extended stats having data, others not."""
        stat_dict = {
            'mixed_player': {
                'saw_f': 30, 'sd': 8,       # Went to showdown sometimes
                'wmsd': 5.5,                # Won some at showdown
                'fb_opp_0': 0, 'fb_0': 0,   # No 4bet opportunities
                'cfb_opp_0': 3, 'cfb_0': 1, # Some cold 4bet activity
                'sbstolen': 12, 'sbnotdef': 7, # Mixed SB defense
                'bbstolen': 0, 'bbnotdef': 0,  # No BB steal attempts
            }
        }
        
        # Should show percentages (has data)
        assert wtsd(stat_dict, 'mixed_player')[1] == "26.7"  # 8/30
        assert wmsd(stat_dict, 'mixed_player')[1] == "68.8"  # 5.5/8
        assert cfour_B(stat_dict, 'mixed_player')[1] == "33.3"  # 1/3
        assert f_SB_steal(stat_dict, 'mixed_player')[1] == "58.3"  # 7/12
        
        # Should show '-' (no opportunities)
        assert four_B(stat_dict, 'mixed_player')[1] == "-"
        assert f_BB_steal(stat_dict, 'mixed_player')[1] == "-"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])