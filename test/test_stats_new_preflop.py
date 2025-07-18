#!/usr/bin/env python3
"""
Test suite for new preflop statistics implementation.

This module tests the newly implemented preflop statistics:
- Cold Call (CC)
- Limp 
- ISO (Isolation)
- RFI Total
- 3-bet vs Steal
- Call vs Steal
- Fold vs 4bet
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    cold_call,
    limp,
    iso,
    rfi_total,
    three_bet_vs_steal,
    call_vs_steal,
    fold_vs_4bet,
)


class TestColdCallStat:
    """Test suite for Cold Call statistic."""

    def test_cold_call_with_no_opportunities(self):
        """Test cold_call returns '-' when no opportunities to cold call."""
        stat_dict = {
            'player1': {'CAR_opp_0': 0, 'CAR_0': 0}
        }
        result = cold_call(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cc=-"
        assert result[4] == "(-/-)"

    def test_cold_call_with_zero_but_opportunities(self):
        """Test cold_call returns '0.0' when player never cold called but had opportunities."""
        stat_dict = {
            'player1': {'CAR_opp_0': 8, 'CAR_0': 0}
        }
        result = cold_call(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cc=0.0%"
        assert result[4] == "(0/8)"

    def test_cold_call_with_normal_value(self):
        """Test cold_call returns normal percentage when player cold called."""
        stat_dict = {
            'player1': {'CAR_opp_0': 10, 'CAR_0': 3}
        }
        result = cold_call(stat_dict, 'player1')
        
        assert result[1] == "30.0"
        assert result[2] == "cc=30.0%"
        assert result[4] == "(3/10)"

    def test_cold_call_exception_handling(self):
        """Test cold_call returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = cold_call(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "cc=-"


class TestLimpStat:
    """Test suite for Limp statistic."""

    def test_limp_with_no_opportunities(self):
        """Test limp returns '-' when no preflop opportunities."""
        stat_dict = {
            'player1': {'vpip_opp': 0, 'vpip': 0, 'pfr': 0}
        }
        result = limp(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "limp=-"
        assert result[4] == "(-/-)"

    def test_limp_with_zero_but_opportunities(self):
        """Test limp returns '0.0' when player never limped but had opportunities."""
        stat_dict = {
            'player1': {'vpip_opp': 20, 'vpip': 5, 'pfr': 5}  # All VPIP were raises
        }
        result = limp(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "limp=0.0%"
        assert result[4] == "(0/20)"

    def test_limp_with_normal_value(self):
        """Test limp returns normal percentage when player limped."""
        stat_dict = {
            'player1': {'vpip_opp': 20, 'vpip': 8, 'pfr': 3}  # 5 limps out of 20 opportunities
        }
        result = limp(stat_dict, 'player1')
        
        assert result[1] == "25.0"  # 5/20 = 25%
        assert result[2] == "limp=25.0%"
        assert result[4] == "(5/20)"

    def test_limp_exception_handling(self):
        """Test limp returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = limp(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "limp=-"


class TestISOStat:
    """Test suite for ISO (Isolation) statistic."""

    def test_iso_with_no_opportunities(self):
        """Test iso returns '-' when no PFR opportunities."""
        stat_dict = {
            'player1': {'pfr_opp': 0, 'pfr': 0}
        }
        result = iso(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "iso=-"
        assert result[4] == "(-/-)"

    def test_iso_with_zero_but_opportunities(self):
        """Test iso returns '0.0' when player never raised but had opportunities."""
        stat_dict = {
            'player1': {'pfr_opp': 15, 'pfr': 0}
        }
        result = iso(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "iso=0.0%"
        assert result[4] == "(0/15)"

    def test_iso_with_normal_value(self):
        """Test iso returns normal percentage when player isolated."""
        stat_dict = {
            'player1': {'pfr_opp': 20, 'pfr': 6}  # 30% of 6 = 1.8 isolation raises
        }
        result = iso(stat_dict, 'player1')
        
        assert result[1] == "9.0"  # 1.8/20 = 9%
        assert result[2] == "iso=9.0%"

    def test_iso_exception_handling(self):
        """Test iso returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = iso(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "iso=-"


class TestRFITotalStat:
    """Test suite for RFI Total statistic."""

    def test_rfi_total_with_no_opportunities(self):
        """Test rfi_total returns '-' when no PFR opportunities."""
        stat_dict = {
            'player1': {'pfr_opp': 0, 'pfr': 0, '3bet': 0}
        }
        result = rfi_total(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "rfi=-"
        assert result[4] == "(-/-)"

    def test_rfi_total_with_zero_but_opportunities(self):
        """Test rfi_total returns '0.0' when player never raised first in."""
        stat_dict = {
            'player1': {'pfr_opp': 15, 'pfr': 0, '3bet': 0}
        }
        result = rfi_total(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "rfi=0.0%"
        assert result[4] == "(0/15)"

    def test_rfi_total_with_normal_value(self):
        """Test rfi_total returns normal percentage when player raised first in."""
        stat_dict = {
            'player1': {'pfr_opp': 20, 'pfr': 8, '3bet': 2}  # 6 RFI out of 20 opportunities
        }
        result = rfi_total(stat_dict, 'player1')
        
        assert result[1] == "30.0"  # 6/20 = 30%
        assert result[2] == "rfi=30.0%"
        assert result[4] == "(6/20)"

    def test_rfi_total_exception_handling(self):
        """Test rfi_total returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = rfi_total(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "rfi=-"


class TestThreeBetVsStealStat:
    """Test suite for 3-bet vs Steal statistic."""

    def test_three_bet_vs_steal_with_no_opportunities(self):
        """Test three_bet_vs_steal returns '-' when no 3bet opportunities."""
        stat_dict = {
            'player1': {'3bet_opp': 0, '3bet': 0}
        }
        result = three_bet_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "3bvs=-"
        assert result[4] == "(-/-)"

    def test_three_bet_vs_steal_with_zero_but_opportunities(self):
        """Test three_bet_vs_steal returns '0.0' when player never 3bet."""
        stat_dict = {
            'player1': {'3bet_opp': 12, '3bet': 0}
        }
        result = three_bet_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "3bvs=0.0%"
        assert result[4] == "(0/12)"

    def test_three_bet_vs_steal_with_normal_value(self):
        """Test three_bet_vs_steal returns normal percentage when player 3bet vs steal."""
        stat_dict = {
            'player1': {'3bet_opp': 15, '3bet': 5}  # 40% of 5 = 2 3bets vs steal
        }
        result = three_bet_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "13.3"  # 2/15 = 13.3%
        assert result[2] == "3bvs=13.3%"

    def test_three_bet_vs_steal_exception_handling(self):
        """Test three_bet_vs_steal returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = three_bet_vs_steal(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "3bvs=-"


class TestCallVsStealStat:
    """Test suite for Call vs Steal statistic."""

    def test_call_vs_steal_with_no_opportunities(self):
        """Test call_vs_steal returns '-' when no cold call opportunities."""
        stat_dict = {
            'player1': {'CAR_opp_0': 0, 'CAR_0': 0}
        }
        result = call_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cvs=-"
        assert result[4] == "(-/-)"

    def test_call_vs_steal_with_zero_but_opportunities(self):
        """Test call_vs_steal returns '0.0' when player never called vs steal."""
        stat_dict = {
            'player1': {'CAR_opp_0': 10, 'CAR_0': 0}
        }
        result = call_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cvs=0.0%"
        assert result[4] == "(0/10)"

    def test_call_vs_steal_with_normal_value(self):
        """Test call_vs_steal returns normal percentage when player called vs steal."""
        stat_dict = {
            'player1': {'CAR_opp_0': 12, 'CAR_0': 4}  # 50% of 4 = 2 calls vs steal
        }
        result = call_vs_steal(stat_dict, 'player1')
        
        assert result[1] == "16.7"  # 2/12 = 16.7%
        assert result[2] == "cvs=16.7%"

    def test_call_vs_steal_exception_handling(self):
        """Test call_vs_steal returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = call_vs_steal(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "cvs=-"


class TestFoldVs4BetStat:
    """Test suite for Fold vs 4bet statistic."""

    def test_fold_vs_4bet_with_no_opportunities(self):
        """Test fold_vs_4bet returns '-' when no 4bet opportunities."""
        stat_dict = {
            'player1': {'F4B_opp_0': 0, 'F4B_0': 0}
        }
        result = fold_vs_4bet(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "f4b=-"
        assert result[4] == "(-/-)"

    def test_fold_vs_4bet_with_zero_but_opportunities(self):
        """Test fold_vs_4bet returns '0.0' when player never folded to 4bet."""
        stat_dict = {
            'player1': {'F4B_opp_0': 5, 'F4B_0': 0}
        }
        result = fold_vs_4bet(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "f4b=0.0%"
        assert result[4] == "(0/5)"

    def test_fold_vs_4bet_with_normal_value(self):
        """Test fold_vs_4bet returns normal percentage when player folded to 4bet."""
        stat_dict = {
            'player1': {'F4B_opp_0': 6, 'F4B_0': 4}
        }
        result = fold_vs_4bet(stat_dict, 'player1')
        
        assert result[1] == "66.7"  # 4/6 = 66.7%
        assert result[2] == "f4b=66.7%"
        assert result[4] == "(4/6)"

    def test_fold_vs_4bet_exception_handling(self):
        """Test fold_vs_4bet returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = fold_vs_4bet(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "f4b=-"


class TestNewPreflopStatsIntegration:
    """Integration tests for the new preflop statistics."""

    def test_new_player_all_stats_no_data(self):
        """Test all new preflop stats return '-' for a completely new player."""
        stat_dict = {
            'new_player': {
                'CAR_opp_0': 0, 'CAR_0': 0,
                'vpip_opp': 0, 'vpip': 0, 'pfr': 0,
                'pfr_opp': 0, '3bet': 0, '3bet_opp': 0,
                'F4B_opp_0': 0, 'F4B_0': 0,
            }
        }
        
        # All new preflop stats should return '-' for display
        assert cold_call(stat_dict, 'new_player')[1] == "-"
        assert limp(stat_dict, 'new_player')[1] == "-"
        assert iso(stat_dict, 'new_player')[1] == "-"
        assert rfi_total(stat_dict, 'new_player')[1] == "-"
        assert three_bet_vs_steal(stat_dict, 'new_player')[1] == "-"
        assert call_vs_steal(stat_dict, 'new_player')[1] == "-"
        assert fold_vs_4bet(stat_dict, 'new_player')[1] == "-"

    def test_active_player_with_real_zeros(self):
        """Test new preflop stats return correct values for an active player."""
        stat_dict = {
            'active_player': {
                # Has opportunities but never performed actions
                'CAR_opp_0': 8, 'CAR_0': 0,           # Never cold called
                'vpip_opp': 25, 'vpip': 5, 'pfr': 5,  # Never limped (all VPIP were raises)
                'pfr_opp': 25, '3bet': 1, '3bet_opp': 10,  # Some 3bets
                'F4B_opp_0': 3, 'F4B_0': 0,           # Never folded to 4bet
            }
        }
        
        # These should show 0.0 (real zero values with opportunities)
        assert cold_call(stat_dict, 'active_player')[1] == "0.0"
        assert limp(stat_dict, 'active_player')[1] == "0.0"  # (5-5)/25 = 0%
        assert fold_vs_4bet(stat_dict, 'active_player')[1] == "0.0"
        
        # These should show calculated values
        assert iso(stat_dict, 'active_player')[1] == "6.0"  # (5*0.3)/25 = 6%
        assert rfi_total(stat_dict, 'active_player')[1] == "16.0"  # (5-1)/25 = 16%
        assert three_bet_vs_steal(stat_dict, 'active_player')[1] == "4.0"  # (1*0.4)/10 = 4%
        assert call_vs_steal(stat_dict, 'active_player')[1] == "0.0"  # (0*0.5)/8 = 0%

    def test_mixed_scenario_preflop_stats(self):
        """Test realistic scenario with some stats having data, others not."""
        stat_dict = {
            'mixed_player': {
                # Has cold call opportunities and uses them
                'CAR_opp_0': 10, 'CAR_0': 3,
                # Has VPIP opportunities, some limps
                'vpip_opp': 30, 'vpip': 12, 'pfr': 8,  # 4 limps
                # Has PFR opportunities
                'pfr_opp': 30, '3bet': 3, '3bet_opp': 8,
                # No 4bet opportunities
                'F4B_opp_0': 0, 'F4B_0': 0,
            }
        }
        
        # Should show percentages (has data)
        assert cold_call(stat_dict, 'mixed_player')[1] == "30.0"  # 3/10
        assert limp(stat_dict, 'mixed_player')[1] == "13.3"  # 4/30
        assert iso(stat_dict, 'mixed_player')[1] == "8.0"  # (8*0.3)/30
        assert rfi_total(stat_dict, 'mixed_player')[1] == "16.7"  # (8-3)/30
        assert three_bet_vs_steal(stat_dict, 'mixed_player')[1] == "15.0"  # (3*0.4)/8
        assert call_vs_steal(stat_dict, 'mixed_player')[1] == "15.0"  # (3*0.5)/10
        
        # Should show '-' (no opportunities)
        assert fold_vs_4bet(stat_dict, 'mixed_player')[1] == "-"


class TestNewPreflopStatsRegressionTests:
    """Regression tests to ensure new preflop stats functionality is not broken."""

    def test_all_new_stats_exception_handling(self):
        """Test all new preflop stats handle exceptions consistently."""
        stat_dict = {}
        
        assert cold_call(stat_dict, 'nonexistent_player')[1] == "-"
        assert limp(stat_dict, 'nonexistent_player')[1] == "-"
        assert iso(stat_dict, 'nonexistent_player')[1] == "-"
        assert rfi_total(stat_dict, 'nonexistent_player')[1] == "-"
        assert three_bet_vs_steal(stat_dict, 'nonexistent_player')[1] == "-"
        assert call_vs_steal(stat_dict, 'nonexistent_player')[1] == "-"
        assert fold_vs_4bet(stat_dict, 'nonexistent_player')[1] == "-"

    def test_tuple_format_consistency(self):
        """Test that all new stats return properly formatted 6-element tuples."""
        stat_dict = {
            'test_player': {
                'CAR_opp_0': 10, 'CAR_0': 3,
                'vpip_opp': 20, 'vpip': 8, 'pfr': 4,
                'pfr_opp': 20, '3bet': 2, '3bet_opp': 8,
                'F4B_opp_0': 5, 'F4B_0': 3,
            }
        }
        
        # Test tuple structure for all new stats
        stats_to_test = [
            cold_call, limp, iso, rfi_total, 
            three_bet_vs_steal, call_vs_steal, fold_vs_4bet
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