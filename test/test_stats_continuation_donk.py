#!/usr/bin/env python3
"""
Test suite for continuation bet and donk bet "no data" feature implementations.

This module tests the newly implemented format_no_data_stat functionality
for cb1, cb2, cb3, cb4, dbr1, and dbr2 statistics.
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    cb1,
    cb2,
    cb3,
    cb4,
    dbr1,
    dbr2,
)


class TestContinuationBetNoDataFeature:
    """Test suite for continuation bet statistics no data feature."""

    def test_cb1_with_no_opportunities(self):
        """Test cb1 returns '-' when no continuation bet opportunities on flop."""
        stat_dict = {
            'player1': {'cb_opp_1': 0, 'cb_1': 0}
        }
        result = cb1(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb1=-"
        assert result[4] == "(-/-)"

    def test_cb1_with_zero_but_opportunities(self):
        """Test cb1 returns '0.0' when player never cbets but had opportunities."""
        stat_dict = {
            'player1': {'cb_opp_1': 5, 'cb_1': 0}
        }
        result = cb1(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cb1=0.0%"
        assert result[4] == "(0/5)"

    def test_cb1_with_normal_value(self):
        """Test cb1 returns normal percentage when player cbets."""
        stat_dict = {
            'player1': {'cb_opp_1': 5, 'cb_1': 3}
        }
        result = cb1(stat_dict, 'player1')
        
        assert result[1] == "60.0"
        assert result[2] == "cb1=60.0%"
        assert result[4] == "(3/5)"

    def test_cb1_exception_handling(self):
        """Test cb1 returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = cb1(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "cb1=-"

    def test_cb2_with_no_opportunities(self):
        """Test cb2 returns '-' when no continuation bet opportunities on turn."""
        stat_dict = {
            'player1': {'cb_opp_2': 0, 'cb_2': 0}
        }
        result = cb2(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb2=-"
        assert result[4] == "(-/-)"

    def test_cb2_with_zero_but_opportunities(self):
        """Test cb2 returns '0.0' when player never cbets but had opportunities."""
        stat_dict = {
            'player1': {'cb_opp_2': 4, 'cb_2': 0}
        }
        result = cb2(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cb2=0.0%"
        assert result[4] == "(0/4)"

    def test_cb2_with_normal_value(self):
        """Test cb2 returns normal percentage when player cbets."""
        stat_dict = {
            'player1': {'cb_opp_2': 4, 'cb_2': 2}
        }
        result = cb2(stat_dict, 'player1')
        
        assert result[1] == "50.0"
        assert result[2] == "cb2=50.0%"
        assert result[4] == "(2/4)"

    def test_cb3_with_no_opportunities(self):
        """Test cb3 returns '-' when no continuation bet opportunities on river."""
        stat_dict = {
            'player1': {'cb_opp_3': 0, 'cb_3': 0}
        }
        result = cb3(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb3=-"
        assert result[4] == "(-/-)"

    def test_cb3_with_zero_but_opportunities(self):
        """Test cb3 returns '0.0' when player never cbets but had opportunities."""
        stat_dict = {
            'player1': {'cb_opp_3': 3, 'cb_3': 0}
        }
        result = cb3(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cb3=0.0%"
        assert result[4] == "(0/3)"

    def test_cb3_with_normal_value(self):
        """Test cb3 returns normal percentage when player cbets."""
        stat_dict = {
            'player1': {'cb_opp_3': 3, 'cb_3': 1}
        }
        result = cb3(stat_dict, 'player1')
        
        assert result[1] == "33.3"
        assert result[2] == "cb3=33.3%"
        assert result[4] == "(1/3)"

    def test_cb4_with_no_opportunities(self):
        """Test cb4 returns '-' when no continuation bet opportunities on 7th street."""
        stat_dict = {
            'player1': {'cb_opp_4': 0, 'cb_4': 0}
        }
        result = cb4(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb4=-"
        assert result[4] == "(-/-)"

    def test_cb4_with_zero_but_opportunities(self):
        """Test cb4 returns '0.0' when player never cbets but had opportunities."""
        stat_dict = {
            'player1': {'cb_opp_4': 2, 'cb_4': 0}
        }
        result = cb4(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cb4=0.0%"
        assert result[4] == "(0/2)"

    def test_cb4_with_normal_value(self):
        """Test cb4 returns normal percentage when player cbets."""
        stat_dict = {
            'player1': {'cb_opp_4': 2, 'cb_4': 1}
        }
        result = cb4(stat_dict, 'player1')
        
        assert result[1] == "50.0"
        assert result[2] == "cb4=50.0%"
        assert result[4] == "(1/2)"


class TestDonkBetNoDataFeature:
    """Test suite for donk bet statistics no data feature."""

    def test_dbr1_with_no_opportunities(self):
        """Test dbr1 returns '-' when no donk opportunities on flop."""
        stat_dict = {
            'player1': {
                'aggr_1': 2, 'cb_1': 2, 'saw_f': 5, 'cb_opp_1': 5
            }  # saw_f - cb_opp_1 = 0 (no donk opportunities)
        }
        result = dbr1(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "dbr1=-"
        assert result[4] == "(-/-)"

    def test_dbr1_with_zero_but_opportunities(self):
        """Test dbr1 returns '0.0' when player never donks but had opportunities."""
        stat_dict = {
            'player1': {
                'aggr_1': 2, 'cb_1': 2, 'saw_f': 8, 'cb_opp_1': 3
            }  # donk_opp = 5, donk_bets = 0
        }
        result = dbr1(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "dbr1=0.0%"
        assert result[4] == "(0/5)"

    def test_dbr1_with_normal_value(self):
        """Test dbr1 returns normal percentage when player donks."""
        stat_dict = {
            'player1': {
                'aggr_1': 5, 'cb_1': 2, 'saw_f': 10, 'cb_opp_1': 2
            }  # donk_opp = 8, donk_bets = 3
        }
        result = dbr1(stat_dict, 'player1')
        
        assert result[1] == "37.5"  # 3/8 = 0.375
        assert result[2] == "dbr1=37.5%"
        assert result[4] == "(3/8)"

    def test_dbr1_exception_handling(self):
        """Test dbr1 returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = dbr1(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "dbr1=-"

    def test_dbr2_with_no_opportunities(self):
        """Test dbr2 returns '-' when no donk opportunities on turn."""
        stat_dict = {
            'player1': {
                'aggr_2': 1, 'cb_2': 1, 'saw_2': 3, 'cb_opp_2': 3
            }  # saw_2 - cb_opp_2 = 0 (no donk opportunities)
        }
        result = dbr2(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "dbr2=-"
        assert result[4] == "(-/-)"

    def test_dbr2_with_zero_but_opportunities(self):
        """Test dbr2 returns '0.0' when player never donks but had opportunities."""
        stat_dict = {
            'player1': {
                'aggr_2': 1, 'cb_2': 1, 'saw_2': 6, 'cb_opp_2': 2
            }  # donk_opp = 4, donk_bets = 0
        }
        result = dbr2(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "dbr2=0.0%"
        assert result[4] == "(0/4)"

    def test_dbr2_with_normal_value(self):
        """Test dbr2 returns normal percentage when player donks."""
        stat_dict = {
            'player1': {
                'aggr_2': 4, 'cb_2': 1, 'saw_2': 8, 'cb_opp_2': 2
            }  # donk_opp = 6, donk_bets = 3
        }
        result = dbr2(stat_dict, 'player1')
        
        assert result[1] == "50.0"  # 3/6 = 0.5
        assert result[2] == "dbr2=50.0%"
        assert result[4] == "(3/6)"

    def test_dbr2_exception_handling(self):
        """Test dbr2 returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = dbr2(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "dbr2=-"


class TestContinuationDonkIntegration:
    """Integration tests for continuation bet and donk bet stats."""

    def test_new_player_all_stats_no_data(self):
        """Test all continuation and donk stats return '-' for a completely new player."""
        stat_dict = {
            'new_player': {
                'cb_opp_1': 0, 'cb_1': 0, 'cb_opp_2': 0, 'cb_2': 0,
                'cb_opp_3': 0, 'cb_3': 0, 'cb_opp_4': 0, 'cb_4': 0,
                'aggr_1': 0, 'cb_1': 0, 'saw_f': 0, 'cb_opp_1': 0,
                'aggr_2': 0, 'cb_2': 0, 'saw_2': 0, 'cb_opp_2': 0,
            }
        }
        
        # All continuation bet stats should return '-' for display
        assert cb1(stat_dict, 'new_player')[1] == "-"
        assert cb2(stat_dict, 'new_player')[1] == "-"
        assert cb3(stat_dict, 'new_player')[1] == "-"
        assert cb4(stat_dict, 'new_player')[1] == "-"
        
        # All donk bet stats should return '-' for display
        assert dbr1(stat_dict, 'new_player')[1] == "-"
        assert dbr2(stat_dict, 'new_player')[1] == "-"

    def test_active_player_with_real_zeros(self):
        """Test continuation and donk stats return correct values for an active player."""
        stat_dict = {
            'active_player': {
                # Has cbet opportunities but never cbets
                'cb_opp_1': 5, 'cb_1': 0, 'cb_opp_2': 4, 'cb_2': 0,
                'cb_opp_3': 3, 'cb_3': 0, 'cb_opp_4': 2, 'cb_4': 0,
                # Has donk opportunities but never donks (aggr = cb for donk calculation)
                'aggr_1': 0, 'saw_f': 8, 
                'aggr_2': 0, 'saw_2': 6,
            }
        }
        
        # These should show 0.0 (real zero values with opportunities)
        assert cb1(stat_dict, 'active_player')[1] == "0.0"
        assert cb2(stat_dict, 'active_player')[1] == "0.0"
        assert cb3(stat_dict, 'active_player')[1] == "0.0"
        assert cb4(stat_dict, 'active_player')[1] == "0.0"
        assert dbr1(stat_dict, 'active_player')[1] == "0.0"  # donk_opp = 3, donk_bets = 0
        assert dbr2(stat_dict, 'active_player')[1] == "0.0"  # donk_opp = 2, donk_bets = 0

    def test_mixed_scenario_cbet_donk_stats(self):
        """Test realistic scenario with some stats having data, others not."""
        stat_dict = {
            'mixed_player': {
                # Has flop cbet opportunities and uses them
                'cb_opp_1': 6, 'cb_1': 4,  # 66.7% flop cbet
                # No turn opportunities
                'cb_opp_2': 0, 'cb_2': 0,
                # River opportunities but never cbets
                'cb_opp_3': 2, 'cb_3': 0,  # 0% river cbet
                # No 7th street opportunities
                'cb_opp_4': 0, 'cb_4': 0,
                # Donk opportunities on flop (saw_f=8, cb_opp_1=6 -> donk_opp=2)
                'aggr_1': 6, 'saw_f': 8,  # donk_opp = 2, donk_bets = 2 (aggr_1 - cb_1 = 6-4=2)
                # No donk opportunities on turn (saw_2=0, cb_opp_2=0 -> donk_opp=0)
                'aggr_2': 0, 'saw_2': 0,  # donk_opp = 0
            }
        }
        
        # Should show percentages (has data)
        assert cb1(stat_dict, 'mixed_player')[1] == "66.7"  # 4/6
        assert cb3(stat_dict, 'mixed_player')[1] == "0.0"   # 0/2
        assert dbr1(stat_dict, 'mixed_player')[1] == "100.0"  # 2/2
        
        # Should show '-' (no opportunities)
        assert cb2(stat_dict, 'mixed_player')[1] == "-"
        assert cb4(stat_dict, 'mixed_player')[1] == "-"
        assert dbr2(stat_dict, 'mixed_player')[1] == "-"


class TestContinuationDonkRegressionTests:
    """Regression tests to ensure continuation and donk bet functionality is not broken."""

    def test_all_cb_functions_exception_handling(self):
        """Test all cb functions handle exceptions consistently."""
        stat_dict = {}
        
        assert cb1(stat_dict, 'nonexistent_player')[1] == "-"
        assert cb2(stat_dict, 'nonexistent_player')[1] == "-"
        assert cb3(stat_dict, 'nonexistent_player')[1] == "-"
        assert cb4(stat_dict, 'nonexistent_player')[1] == "-"

    def test_all_dbr_functions_exception_handling(self):
        """Test all dbr functions handle exceptions consistently."""
        stat_dict = {}
        
        assert dbr1(stat_dict, 'nonexistent_player')[1] == "-"
        assert dbr2(stat_dict, 'nonexistent_player')[1] == "-"

    def test_tuple_format_consistency(self):
        """Test that all functions return properly formatted 6-element tuples."""
        stat_dict = {
            'test_player': {
                'cb_opp_1': 5, 'cb_1': 3,
                'aggr_1': 4, 'saw_f': 6, 'cb_opp_1': 2,
            }
        }
        
        # Test tuple structure for cb1
        result = cb1(stat_dict, 'test_player')
        assert len(result) == 6
        assert isinstance(result[0], float)  # stat value
        assert isinstance(result[1], str)    # percentage string
        assert isinstance(result[2], str)    # formatted string
        assert isinstance(result[3], str)    # formatted string
        assert isinstance(result[4], str)    # fraction string
        assert isinstance(result[5], str)    # description

        # Test tuple structure for dbr1
        result = dbr1(stat_dict, 'test_player')
        assert len(result) == 6
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert isinstance(result[2], str)
        assert isinstance(result[3], str)
        assert isinstance(result[4], str)
        assert isinstance(result[5], str)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])