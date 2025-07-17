#!/usr/bin/env python3
"""
Test suite for Stats.py regression testing.

This module tests potential regressions introduced by the "no data" feature
modifications to ensure compatibility with existing functionality.
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    format_no_data_stat,
    vpip,
    pfr,
    three_B,
    steal,
    cbet,
    a_freq1,
    a_freq2,
    a_freq3,
    a_freq4,
    agg_fact,
    agg_fact_pct,
    ffreq1,
    ffreq2,
    ffreq3,
    ffreq4,
    f_cb1,
    f_cb2,
    f_cb3,
    f_cb4,
    cr1,
    cr2,
    cr3,
    cr4,
)


class TestStatsRegression:
    """Test potential regressions in Stats.py modifications."""

    def test_format_no_data_stat_consistency(self):
        """Test format_no_data_stat returns consistent format."""
        result = format_no_data_stat("test", "Test stat")
        
        # Should return tuple with 6 elements
        assert len(result) == 6
        assert result[0] == 0.0  # Stat value
        assert result[1] == "-"  # Display value
        assert result[2] == "test=-"  # Short display
        assert result[3] == "test=-"  # Long display
        assert result[4] == "(-/-)"  # Fraction
        assert result[5] == "Test stat"  # Description

    def test_zero_vs_no_data_distinction(self):
        """Test that 0 values and no data are handled differently."""
        # Test VPIP: 0 opportunities should show "-"
        stat_dict_no_data = {
            'player1': {'vpip': 0, 'vpip_opp': 0}
        }
        result_no_data = vpip(stat_dict_no_data, 'player1')
        assert result_no_data[1] == "-"
        
        # Test VPIP: 0 actions but opportunities should show "0.0"
        stat_dict_zero = {
            'player1': {'vpip': 0, 'vpip_opp': 10}
        }
        result_zero = vpip(stat_dict_zero, 'player1')
        assert result_zero[1] == "0.0"

    def test_all_stats_no_data_consistency(self):
        """Test all modified stats return consistent no-data format."""
        stat_dict_empty = {
            'player1': {
                'vpip': 0, 'vpip_opp': 0,
                'pfr': 0, 'pfr_opp': 0,
                'tb_0': 0, 'tb_opp_0': 0,
                'steal': 0, 'steal_opp': 0,
                'cb_1': 0, 'cb_2': 0, 'cb_3': 0, 'cb_4': 0,
                'cb_opp_1': 0, 'cb_opp_2': 0, 'cb_opp_3': 0, 'cb_opp_4': 0,
                'aggr_1': 0, 'aggr_2': 0, 'aggr_3': 0, 'aggr_4': 0,
                'call_1': 0, 'call_2': 0, 'call_3': 0, 'call_4': 0,
                'saw_f': 0, 'saw_2': 0, 'saw_3': 0, 'saw_4': 0,
                'was_raised_1': 0, 'was_raised_2': 0, 'was_raised_3': 0, 'was_raised_4': 0,
                'f_freq_1': 0, 'f_freq_2': 0, 'f_freq_3': 0, 'f_freq_4': 0,
                'f_cb_opp_1': 0, 'f_cb_opp_2': 0, 'f_cb_opp_3': 0, 'f_cb_opp_4': 0,
                'f_cb_1': 0, 'f_cb_2': 0, 'f_cb_3': 0, 'f_cb_4': 0,
                'ccr_opp_1': 0, 'ccr_opp_2': 0, 'ccr_opp_3': 0, 'ccr_opp_4': 0,
                'cr_1': 0, 'cr_2': 0, 'cr_3': 0, 'cr_4': 0,
            }
        }
        
        # All these should return "-" for no data
        stats_functions = [
            vpip, pfr, three_B, steal, cbet,
            a_freq1, a_freq2, a_freq3, a_freq4,
            agg_fact, agg_fact_pct,
            ffreq1, ffreq2, ffreq3, ffreq4,
            f_cb1, f_cb2, f_cb3, f_cb4,
            cr1, cr2, cr3, cr4,
        ]
        
        for stat_func in stats_functions:
            result = stat_func(stat_dict_empty, 'player1')
            assert result[1] == "-", f"Function {stat_func.__name__} should return '-' for no data"

    def test_exception_handling_preserved(self):
        """Test that exception handling still works correctly."""
        # Test with missing player
        empty_dict = {}
        
        # These should return "NA" on exceptions, not crash
        result_vpip = vpip(empty_dict, 'nonexistent_player')
        assert result_vpip[1] == "NA"
        
        result_pfr = pfr(empty_dict, 'nonexistent_player')
        assert result_pfr[1] == "NA"
        
        result_3b = three_B(empty_dict, 'nonexistent_player')
        assert result_3b[1] == "NA"

    def test_normal_stats_calculation_preserved(self):
        """Test that normal stats calculations still work correctly."""
        stat_dict_normal = {
            'player1': {
                'vpip': 15, 'vpip_opp': 50,  # 30% VPIP
                'pfr': 10, 'pfr_opp': 50,    # 20% PFR
                'tb_0': 5, 'tb_opp_0': 25,   # 20% 3bet
                'steal': 8, 'steal_opp': 20, # 40% steal
                'cb_1': 5, 'cb_2': 3, 'cb_3': 2, 'cb_4': 0,
                'cb_opp_1': 8, 'cb_opp_2': 5, 'cb_opp_3': 3, 'cb_opp_4': 0,  # 62.5% cbet
                'aggr_1': 6, 'aggr_2': 4, 'aggr_3': 2, 'aggr_4': 0,
                'call_1': 2, 'call_2': 1, 'call_3': 1, 'call_4': 0,
                'saw_f': 12, 'saw_2': 8, 'saw_3': 4, 'saw_4': 0,
            }
        }
        
        # Test VPIP
        result_vpip = vpip(stat_dict_normal, 'player1')
        assert result_vpip[1] == "30.0"
        
        # Test PFR
        result_pfr = pfr(stat_dict_normal, 'player1')
        assert result_pfr[1] == "20.0"
        
        # Test 3-bet
        result_3b = three_B(stat_dict_normal, 'player1')
        assert result_3b[1] == "20.0"
        
        # Test steal
        result_steal = steal(stat_dict_normal, 'player1')
        assert result_steal[1] == "40.0"
        
        # Test cbet
        result_cbet = cbet(stat_dict_normal, 'player1')
        assert result_cbet[1] == "62.5"
        
        # Test aggression frequency
        result_a1 = a_freq1(stat_dict_normal, 'player1')
        assert result_a1[1] == "50.0"  # 6/12

    def test_fraction_display_consistency(self):
        """Test that fraction displays are consistent across all stats."""
        # Test with actual data
        stat_dict = {
            'player1': {
                'vpip': 5, 'vpip_opp': 20,
                'pfr': 3, 'pfr_opp': 20,
                'tb_0': 2, 'tb_opp_0': 10,
                'steal': 4, 'steal_opp': 15,
            }
        }
        
        # Test VPIP fraction
        result_vpip = vpip(stat_dict, 'player1')
        assert result_vpip[4] == "(5/20)"
        
        # Test PFR fraction
        result_pfr = pfr(stat_dict, 'player1')
        assert result_pfr[4] == "(3/20)"
        
        # Test 3-bet fraction
        result_3b = three_B(stat_dict, 'player1')
        assert result_3b[4] == "(2/10)"
        
        # Test steal fraction
        result_steal = steal(stat_dict, 'player1')
        assert result_steal[4] == "(4/15)"

    def test_missing_keys_handling(self):
        """Test that missing keys are handled gracefully."""
        # Test with partial data
        stat_dict_partial = {
            'player1': {
                'vpip': 5,  # Missing vpip_opp
                'pfr': 3,   # Missing pfr_opp
            }
        }
        
        # Should return no data format when required keys are missing
        result_vpip = vpip(stat_dict_partial, 'player1')
        assert result_vpip[1] == "-"
        
        result_pfr = pfr(stat_dict_partial, 'player1')
        assert result_pfr[1] == "-"

    def test_edge_case_zero_opportunities(self):
        """Test edge cases with zero opportunities."""
        stat_dict_edge = {
            'player1': {
                'vpip': 5, 'vpip_opp': 0,     # Had actions but no opportunities
                'pfr': 0, 'pfr_opp': 0,       # No actions, no opportunities
                'tb_0': 10, 'tb_opp_0': 0,    # Actions but no opportunities (edge case)
            }
        }
        
        # All should return "-" for no opportunities
        assert vpip(stat_dict_edge, 'player1')[1] == "-"
        assert pfr(stat_dict_edge, 'player1')[1] == "-"
        assert three_B(stat_dict_edge, 'player1')[1] == "-"

    def test_stats_return_format_consistency(self):
        """Test that all stats return the expected 6-element tuple format."""
        stat_dict = {
            'player1': {
                'vpip': 10, 'vpip_opp': 50,
                'pfr': 5, 'pfr_opp': 50,
                'tb_0': 3, 'tb_opp_0': 20,
                'steal': 8, 'steal_opp': 25,
                'cb_1': 4, 'cb_2': 2, 'cb_3': 1, 'cb_4': 0,
                'cb_opp_1': 6, 'cb_opp_2': 4, 'cb_opp_3': 2, 'cb_opp_4': 0,
                'aggr_1': 5, 'aggr_2': 3, 'aggr_3': 1, 'aggr_4': 0,
                'call_1': 2, 'call_2': 1, 'call_3': 1, 'call_4': 0,
                'saw_f': 15, 'saw_2': 10, 'saw_3': 5, 'saw_4': 0,
            }
        }
        
        stats_functions = [
            vpip, pfr, three_B, steal, cbet,
            a_freq1, a_freq2, a_freq3, a_freq4,
            agg_fact, agg_fact_pct,
        ]
        
        for stat_func in stats_functions:
            result = stat_func(stat_dict, 'player1')
            assert len(result) == 6, f"Function {stat_func.__name__} should return 6-element tuple"
            assert isinstance(result[0], (int, float)), f"Element 0 should be numeric in {stat_func.__name__}"
            assert isinstance(result[1], str), f"Element 1 should be string in {stat_func.__name__}"
            assert isinstance(result[2], str), f"Element 2 should be string in {stat_func.__name__}"
            assert isinstance(result[3], str), f"Element 3 should be string in {stat_func.__name__}"
            assert isinstance(result[4], str), f"Element 4 should be string in {stat_func.__name__}"
            assert isinstance(result[5], str), f"Element 5 should be string in {stat_func.__name__}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])