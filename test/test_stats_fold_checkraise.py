#!/usr/bin/env python3
"""
Test suite for fold and check-raise statistics no data feature.

This module tests the fold frequency and check-raise statistics to ensure
proper distinction between 0 (real value) and "-" (no data available).
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    ffreq1, ffreq2, ffreq3, ffreq4,
    f_cb1, f_cb2, f_cb3, f_cb4,
    cr1, cr2, cr3, cr4,
)


class TestFoldFrequencyNoDataFeature:
    """Test suite for fold frequency statistics no data feature."""

    def test_ffreq1_with_no_opportunities(self):
        """Test ffreq1 returns '-' when no raise opportunities available."""
        stat_dict = {
            'player1': {'f_freq_1': 0, 'was_raised_1': 0}
        }
        result = ffreq1(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "ff1=-"
        assert result[4] == "(-/-)"

    def test_ffreq1_with_zero_but_opportunities(self):
        """Test ffreq1 returns '0.0' when player never folds but faced raises."""
        stat_dict = {
            'player1': {'f_freq_1': 0, 'was_raised_1': 10}
        }
        result = ffreq1(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "ff1=0.0%"
        assert result[4] == "(0/10)"

    def test_ffreq1_with_normal_value(self):
        """Test ffreq1 returns normal percentage when player has stats."""
        stat_dict = {
            'player1': {'f_freq_1': 3, 'was_raised_1': 10}
        }
        result = ffreq1(stat_dict, 'player1')
        
        assert result[1] == "30.0"
        assert result[2] == "ff1=30.0%"
        assert result[4] == "(3/10)"

    def test_ffreq2_with_no_opportunities(self):
        """Test ffreq2 returns '-' when no raise opportunities available."""
        stat_dict = {
            'player1': {'f_freq_2': 0, 'was_raised_2': 0}
        }
        result = ffreq2(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "ff2=-"
        assert result[4] == "(-/-)"

    def test_ffreq3_with_no_opportunities(self):
        """Test ffreq3 returns '-' when no raise opportunities available."""
        stat_dict = {
            'player1': {'f_freq_3': 0, 'was_raised_3': 0}
        }
        result = ffreq3(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "ff3=-"
        assert result[4] == "(-/-)"

    def test_ffreq4_with_no_opportunities(self):
        """Test ffreq4 returns '-' when no raise opportunities available."""
        stat_dict = {
            'player1': {'f_freq_4': 0, 'was_raised_4': 0}
        }
        result = ffreq4(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "ff4=-"
        assert result[4] == "(-/-)"

    def test_all_streets_fold_frequency_consistency(self):
        """Test all fold frequency stats behave consistently."""
        stat_dict = {
            'player1': {
                'f_freq_1': 2, 'was_raised_1': 10,
                'f_freq_2': 1, 'was_raised_2': 5,
                'f_freq_3': 0, 'was_raised_3': 2,
                'f_freq_4': 0, 'was_raised_4': 0  # No opportunities
            }
        }
        
        # Streets 1-3 should show percentages
        assert ffreq1(stat_dict, 'player1')[1] == "20.0"
        assert ffreq2(stat_dict, 'player1')[1] == "20.0"
        assert ffreq3(stat_dict, 'player1')[1] == "0.0"  # Had opps but didn't fold
        
        # Street 4 should show '-' (no opportunities)
        assert ffreq4(stat_dict, 'player1')[1] == "-"


class TestFoldToCBetNoDataFeature:
    """Test suite for fold to continuation bet statistics no data feature."""

    def test_f_cb1_with_no_opportunities(self):
        """Test f_cb1 returns '-' when no cbet opportunities available."""
        stat_dict = {
            'player1': {'f_cb_1': 0, 'f_cb_opp_1': 0}
        }
        result = f_cb1(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "f_cb1=-"
        assert result[4] == "(-/-)"

    def test_f_cb1_with_zero_but_opportunities(self):
        """Test f_cb1 returns '0.0' when player never folds to cbet but faced them."""
        stat_dict = {
            'player1': {'f_cb_1': 0, 'f_cb_opp_1': 8}
        }
        result = f_cb1(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "f_cb1=0.0%"
        assert result[4] == "(0/8)"

    def test_f_cb1_with_normal_value(self):
        """Test f_cb1 returns normal percentage when player has stats."""
        stat_dict = {
            'player1': {'f_cb_1': 4, 'f_cb_opp_1': 8}
        }
        result = f_cb1(stat_dict, 'player1')
        
        assert result[1] == "50.0"
        assert result[2] == "f_cb1=50.0%"
        assert result[4] == "(4/8)"

    def test_f_cb2_with_no_opportunities(self):
        """Test f_cb2 returns '-' when no cbet opportunities available."""
        stat_dict = {
            'player1': {'f_cb_2': 0, 'f_cb_opp_2': 0}
        }
        result = f_cb2(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "f_cb2=-"
        assert result[4] == "(-/-)"

    def test_f_cb3_with_no_opportunities(self):
        """Test f_cb3 returns '-' when no cbet opportunities available."""
        stat_dict = {
            'player1': {'f_cb_3': 0, 'f_cb_opp_3': 0}
        }
        result = f_cb3(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "f_cb3=-"
        assert result[4] == "(-/-)"

    def test_f_cb4_with_no_opportunities(self):
        """Test f_cb4 returns '-' when no cbet opportunities available."""
        stat_dict = {
            'player1': {'f_cb_4': 0, 'f_cb_opp_4': 0}
        }
        result = f_cb4(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "f_cb4=-"
        assert result[4] == "(-/-)"

    def test_all_streets_fold_cbet_consistency(self):
        """Test all fold to cbet stats behave consistently."""
        stat_dict = {
            'player1': {
                'f_cb_1': 3, 'f_cb_opp_1': 6,    # 50% fold to flop cbet
                'f_cb_2': 1, 'f_cb_opp_2': 4,    # 25% fold to turn cbet
                'f_cb_3': 0, 'f_cb_opp_3': 2,    # 0% fold to river cbet
                'f_cb_4': 0, 'f_cb_opp_4': 0     # No 7th street cbet opportunities
            }
        }
        
        # Streets 1-3 should show percentages
        assert f_cb1(stat_dict, 'player1')[1] == "50.0"
        assert f_cb2(stat_dict, 'player1')[1] == "25.0"
        assert f_cb3(stat_dict, 'player1')[1] == "0.0"  # Had opps but didn't fold
        
        # Street 4 should show '-' (no opportunities)
        assert f_cb4(stat_dict, 'player1')[1] == "-"


class TestCheckRaiseNoDataFeature:
    """Test suite for check-raise statistics no data feature."""

    def test_cr1_with_no_opportunities(self):
        """Test cr1 returns '-' when no check-raise opportunities available."""
        stat_dict = {
            'player1': {'cr_1': 0, 'cr_opp_1': 0}
        }
        result = cr1(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cr1=-"
        assert result[4] == "(-/-)"

    def test_cr1_with_zero_but_opportunities(self):
        """Test cr1 returns '0.0' when player never check-raises but had opportunities."""
        stat_dict = {
            'player1': {'cr_1': 0, 'ccr_opp_1': 5}
        }
        result = cr1(stat_dict, 'player1')
        
        assert result[1] == "0.0"
        assert result[2] == "cr1=0.0%"
        assert result[4] == "(0/5)"

    def test_cr1_with_normal_value(self):
        """Test cr1 returns normal percentage when player has stats."""
        stat_dict = {
            'player1': {'cr_1': 1, 'ccr_opp_1': 5}
        }
        result = cr1(stat_dict, 'player1')
        
        assert result[1] == "20.0"
        assert result[2] == "cr1=20.0%"
        assert result[4] == "(1/5)"

    def test_cr2_with_no_opportunities(self):
        """Test cr2 returns '-' when no check-raise opportunities available."""
        stat_dict = {
            'player1': {'cr_2': 0, 'cr_opp_2': 0}
        }
        result = cr2(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cr2=-"
        assert result[4] == "(-/-)"

    def test_cr3_with_no_opportunities(self):
        """Test cr3 returns '-' when no check-raise opportunities available."""
        stat_dict = {
            'player1': {'cr_3': 0, 'cr_opp_3': 0}
        }
        result = cr3(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cr3=-"
        assert result[4] == "(-/-)"

    def test_cr4_with_no_opportunities(self):
        """Test cr4 returns '-' when no check-raise opportunities available."""
        stat_dict = {
            'player1': {'cr_4': 0, 'cr_opp_4': 0}
        }
        result = cr4(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cr4=-"
        assert result[4] == "(-/-)"

    def test_all_streets_check_raise_consistency(self):
        """Test all check-raise stats behave consistently."""
        stat_dict = {
            'player1': {
                'cr_1': 1, 'ccr_opp_1': 10,    # 10% check-raise flop
                'cr_2': 0, 'ccr_opp_2': 5,     # 0% check-raise turn
                'cr_3': 0, 'ccr_opp_3': 2,     # 0% check-raise river
                'cr_4': 0, 'ccr_opp_4': 0      # No 7th street check-raise opportunities
            }
        }
        
        # Streets 1-3 should show percentages
        assert cr1(stat_dict, 'player1')[1] == "10.0"
        assert cr2(stat_dict, 'player1')[1] == "0.0"  # Had opps but didn't check-raise
        assert cr3(stat_dict, 'player1')[1] == "0.0"  # Had opps but didn't check-raise
        
        # Street 4 should show '-' (no opportunities)
        assert cr4(stat_dict, 'player1')[1] == "-"


class TestFoldCheckRaiseIntegration:
    """Integration tests for fold and check-raise statistics together."""

    def test_defensive_aggressive_player_profile(self):
        """Test a player who is defensive (folds a lot) but aggressive when not folding."""
        stat_dict = {
            'def_agg_player': {
                # Fold frequency - folds often when raised
                'f_freq_1': 7, 'was_raised_1': 10,    # 70% fold to flop raise
                'f_freq_2': 4, 'was_raised_2': 5,     # 80% fold to turn raise
                'f_freq_3': 2, 'was_raised_3': 2,     # 100% fold to river raise
                'f_freq_4': 0, 'was_raised_4': 0,     # No 7th street raises faced
                
                # Fold to cbet - also folds often to cbets
                'f_cb_1': 6, 'f_cb_opp_1': 8,         # 75% fold to flop cbet
                'f_cb_2': 3, 'f_cb_opp_2': 4,         # 75% fold to turn cbet
                'f_cb_3': 1, 'f_cb_opp_3': 1,         # 100% fold to river cbet
                'f_cb_4': 0, 'f_cb_opp_4': 0,         # No 7th street cbets faced
                
                # Check-raise - when doesn't fold, can be aggressive
                'cr_1': 2, 'ccr_opp_1': 8,             # 25% check-raise flop
                'cr_2': 1, 'ccr_opp_2': 3,             # 33% check-raise turn
                'cr_3': 0, 'ccr_opp_3': 1,             # 0% check-raise river
                'cr_4': 0, 'ccr_opp_4': 0              # No 7th street check-raise opps
            }
        }
        
        # Fold frequencies should show high percentages (defensive)
        assert ffreq1(stat_dict, 'def_agg_player')[1] == "70.0"
        assert ffreq2(stat_dict, 'def_agg_player')[1] == "80.0"
        assert ffreq3(stat_dict, 'def_agg_player')[1] == "100.0"
        assert ffreq4(stat_dict, 'def_agg_player')[1] == "-"  # No opportunities
        
        # Fold to cbet should show high percentages (defensive)
        assert f_cb1(stat_dict, 'def_agg_player')[1] == "75.0"
        assert f_cb2(stat_dict, 'def_agg_player')[1] == "75.0"
        assert f_cb3(stat_dict, 'def_agg_player')[1] == "100.0"
        assert f_cb4(stat_dict, 'def_agg_player')[1] == "-"  # No opportunities
        
        # Check-raise should show moderate percentages (aggressive when not folding)
        assert cr1(stat_dict, 'def_agg_player')[1] == "25.0"
        assert cr2(stat_dict, 'def_agg_player')[1] == "33.3"
        assert cr3(stat_dict, 'def_agg_player')[1] == "0.0"
        assert cr4(stat_dict, 'def_agg_player')[1] == "-"  # No opportunities

    def test_new_player_no_defensive_stats(self):
        """Test a new player with no defensive opportunities."""
        stat_dict = {
            'new_player': {
                # No fold opportunities
                'f_freq_1': 0, 'was_raised_1': 0,
                'f_freq_2': 0, 'was_raised_2': 0,
                'f_freq_3': 0, 'was_raised_3': 0,
                'f_freq_4': 0, 'was_raised_4': 0,
                
                # No cbet opportunities
                'f_cb_1': 0, 'f_cb_opp_1': 0,
                'f_cb_2': 0, 'f_cb_opp_2': 0,
                'f_cb_3': 0, 'f_cb_opp_3': 0,
                'f_cb_4': 0, 'f_cb_opp_4': 0,
                
                # No check-raise opportunities
                'cr_1': 0, 'ccr_opp_1': 0,
                'cr_2': 0, 'ccr_opp_2': 0,
                'cr_3': 0, 'ccr_opp_3': 0,
                'cr_4': 0, 'ccr_opp_4': 0
            }
        }
        
        # All stats should show '-' (no opportunities)
        for street in [1, 2, 3, 4]:
            ffreq_func = [ffreq1, ffreq2, ffreq3, ffreq4][street - 1]
            f_cb_func = [f_cb1, f_cb2, f_cb3, f_cb4][street - 1]
            cr_func = [cr1, cr2, cr3, cr4][street - 1]
            
            assert ffreq_func(stat_dict, 'new_player')[1] == "-"
            assert f_cb_func(stat_dict, 'new_player')[1] == "-"
            assert cr_func(stat_dict, 'new_player')[1] == "-"

    def test_calling_station_profile(self):
        """Test a calling station (never folds, never check-raises)."""
        stat_dict = {
            'calling_station': {
                # Never folds to raises
                'f_freq_1': 0, 'was_raised_1': 15,
                'f_freq_2': 0, 'was_raised_2': 8,
                'f_freq_3': 0, 'was_raised_3': 4,
                'f_freq_4': 0, 'was_raised_4': 1,
                
                # Never folds to cbets
                'f_cb_1': 0, 'f_cb_opp_1': 12,
                'f_cb_2': 0, 'f_cb_opp_2': 6,
                'f_cb_3': 0, 'f_cb_opp_3': 3,
                'f_cb_4': 0, 'f_cb_opp_4': 0,  # No 7th street cbets
                
                # Never check-raises
                'cr_1': 0, 'ccr_opp_1': 20,
                'cr_2': 0, 'ccr_opp_2': 10,
                'cr_3': 0, 'ccr_opp_3': 5,
                'cr_4': 0, 'ccr_opp_4': 0   # No 7th street check-raise opps
            }
        }
        
        # All stats should show 0.0 (had opportunities but was passive)
        assert ffreq1(stat_dict, 'calling_station')[1] == "0.0"
        assert ffreq2(stat_dict, 'calling_station')[1] == "0.0"
        assert ffreq3(stat_dict, 'calling_station')[1] == "0.0"
        assert ffreq4(stat_dict, 'calling_station')[1] == "0.0"
        
        assert f_cb1(stat_dict, 'calling_station')[1] == "0.0"
        assert f_cb2(stat_dict, 'calling_station')[1] == "0.0"
        assert f_cb3(stat_dict, 'calling_station')[1] == "0.0"
        assert f_cb4(stat_dict, 'calling_station')[1] == "-"  # No opportunities
        
        assert cr1(stat_dict, 'calling_station')[1] == "0.0"
        assert cr2(stat_dict, 'calling_station')[1] == "0.0"
        assert cr3(stat_dict, 'calling_station')[1] == "0.0"
        assert cr4(stat_dict, 'calling_station')[1] == "-"  # No opportunities


class TestFoldCheckRaiseRegressionTests:
    """Regression tests for fold and check-raise statistics."""

    def test_exception_handling_fold_frequency(self):
        """Test fold frequency functions still return 'NA' on exceptions."""
        stat_dict = {}
        
        assert ffreq1(stat_dict, 'nonexistent_player')[1] == "NA"
        assert ffreq2(stat_dict, 'nonexistent_player')[1] == "NA"
        assert ffreq3(stat_dict, 'nonexistent_player')[1] == "NA"
        assert ffreq4(stat_dict, 'nonexistent_player')[1] == "NA"

    def test_exception_handling_fold_cbet(self):
        """Test fold to cbet functions still return 'NA' on exceptions."""
        stat_dict = {}
        
        assert f_cb1(stat_dict, 'nonexistent_player')[1] == "NA"
        assert f_cb2(stat_dict, 'nonexistent_player')[1] == "NA"
        assert f_cb3(stat_dict, 'nonexistent_player')[1] == "NA"
        assert f_cb4(stat_dict, 'nonexistent_player')[1] == "NA"

    def test_exception_handling_check_raise(self):
        """Test check-raise functions still return 'NA' on exceptions."""
        stat_dict = {}
        
        assert cr1(stat_dict, 'nonexistent_player')[1] == "NA"
        assert cr2(stat_dict, 'nonexistent_player')[1] == "NA"
        assert cr3(stat_dict, 'nonexistent_player')[1] == "NA"
        assert cr4(stat_dict, 'nonexistent_player')[1] == "NA"

    def test_missing_keys_handling(self):
        """Test proper handling of missing keys in stat_dict."""
        stat_dict = {
            'player1': {
                # Missing some keys to test .get() default behavior
                'f_freq_1': 5,
                # 'was_raised_1': missing
                'f_cb_1': 3,
                'f_cb_opp_1': 10,
                'cr_1': 1,
                # 'cr_opp_1': missing
            }
        }
        
        # Should handle missing keys gracefully
        result_ffreq = ffreq1(stat_dict, 'player1')
        result_fcb = f_cb1(stat_dict, 'player1')
        result_cr = cr1(stat_dict, 'player1')
        
        # Missing 'was_raised_1' should be treated as 0, so no opportunities
        assert result_ffreq[1] == "-"
        
        # f_cb1 should work normally
        assert result_fcb[1] == "30.0"
        
        # Missing 'ccr_opp_1' should be treated as 0, so no opportunities
        assert result_cr[1] == "-"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])