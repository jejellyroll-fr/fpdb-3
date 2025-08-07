#!/usr/bin/env python3
"""Test suite for the new HUD statistics "no data" feature.

This module tests the distinction between 0 (real value) and "-" (no data available)
in HUD statistics display, ensuring proper user experience.
"""

import os
import sys

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Stats import (
    a_freq1,
    a_freq2,
    a_freq3,
    a_freq4,
    agg_fact,
    agg_fact_pct,
    cbet,
    format_no_data_stat,
    pfr,
    steal,
    three_B,
    vpip,
)


class TestFormatNoDataStat:
    """Test suite for the format_no_data_stat utility function."""

    def test_basic_no_data_format(self) -> None:
        """Test basic no data formatting without fraction."""
        result = format_no_data_stat("vpip", "Voluntarily put in preflop/3rd street %")
        expected = (0.0, "-", "vpip=-", "vpip=-", "(-/-)", "Voluntarily put in preflop/3rd street %")
        assert result == expected

    def test_no_data_format_with_fraction(self) -> None:
        """Test no data formatting with specific numerator/denominator."""
        result = format_no_data_stat("pfr", "Preflop raise %", 0, 0)
        expected = (0.0, "-", "pfr=-", "pfr=-", "(0/0)", "Preflop raise %")
        assert result == expected

    def test_different_stat_names(self) -> None:
        """Test formatting with different statistic names."""
        stats = [
            ("3B", "3-bet percentage"),
            ("steal", "Steal percentage"),
            ("cbet", "Continuation bet percentage"),
            ("afa", "Aggression factor"),
        ]

        for stat_name, description in stats:
            result = format_no_data_stat(stat_name, description)
            assert result[0] == 0.0
            assert result[1] == "-"
            assert result[2] == f"{stat_name}=-"
            assert result[3] == f"{stat_name}=-"
            assert result[4] == "(-/-)"
            assert result[5] == description


class TestVPIPNoDataFeature:
    """Test suite for VPIP statistic no data feature."""

    def test_vpip_with_no_opportunities(self) -> None:
        """Test VPIP returns '-' when no opportunities available."""
        stat_dict = {"player1": {"vpip": 0, "vpip_opp": 0}}
        result = vpip(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "vpip=-"
        assert result[4] == "(-/-)"

    def test_vpip_with_zero_but_opportunities(self) -> None:
        """Test VPIP returns '0.0' when player is tight but had opportunities."""
        stat_dict = {"player1": {"vpip": 0, "vpip_opp": 10}}
        result = vpip(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "v=0.0%"
        assert result[4] == "(0/10)"

    def test_vpip_with_normal_value(self) -> None:
        """Test VPIP returns normal percentage when player has stats."""
        stat_dict = {"player1": {"vpip": 5, "vpip_opp": 10}}
        result = vpip(stat_dict, "player1")

        assert result[1] == "50.0"
        assert result[2] == "v=50.0%"
        assert result[4] == "(5/10)"

    def test_vpip_missing_keys(self) -> None:
        """Test VPIP handles missing keys gracefully."""
        stat_dict = {"player1": {}}
        result = vpip(stat_dict, "player1")

        # Should return no data format when keys are missing
        assert result[1] == "-"


class TestPFRNoDataFeature:
    """Test suite for PFR statistic no data feature."""

    def test_pfr_with_no_opportunities(self) -> None:
        """Test PFR returns '-' when no opportunities available."""
        stat_dict = {"player1": {"pfr": 0, "pfr_opp": 0}}
        result = pfr(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "pfr=-"
        assert result[4] == "(-/-)"

    def test_pfr_with_zero_but_opportunities(self) -> None:
        """Test PFR returns '0.0' when player is passive but had opportunities."""
        stat_dict = {"player1": {"pfr": 0, "pfr_opp": 10}}
        result = pfr(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "p=0.0%"
        assert result[4] == "(0/10)"

    def test_pfr_with_normal_value(self) -> None:
        """Test PFR returns normal percentage when player has stats."""
        stat_dict = {"player1": {"pfr": 3, "pfr_opp": 10}}
        result = pfr(stat_dict, "player1")

        assert result[1] == "30.0"
        assert result[2] == "p=30.0%"
        assert result[4] == "(3/10)"


class TestThreeBetNoDataFeature:
    """Test suite for 3-bet statistic no data feature."""

    def test_three_b_with_no_opportunities(self) -> None:
        """Test 3-bet returns '-' when no opportunities available."""
        stat_dict = {"player1": {"tb_0": 0, "tb_opp_0": 0}}
        result = three_B(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "3B=-"
        assert result[4] == "(-/-)"

    def test_three_b_with_zero_but_opportunities(self) -> None:
        """Test 3-bet returns '0.0' when player never 3-bets but had opportunities."""
        stat_dict = {"player1": {"tb_0": 0, "tb_opp_0": 10}}
        result = three_B(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "3B=0.0%"
        assert result[4] == "(0/10)"

    def test_three_b_with_normal_value(self) -> None:
        """Test 3-bet returns normal percentage when player has stats."""
        stat_dict = {"player1": {"tb_0": 2, "tb_opp_0": 10}}
        result = three_B(stat_dict, "player1")

        assert result[1] == "20.0"
        assert result[2] == "3B=20.0%"
        assert result[4] == "(2/10)"


class TestStealNoDataFeature:
    """Test suite for steal statistic no data feature."""

    def test_steal_with_no_opportunities(self) -> None:
        """Test steal returns '-' when no opportunities available."""
        stat_dict = {"player1": {"steal": 0, "steal_opp": 0}}
        result = steal(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "steal=-"
        assert result[4] == "(-/-)"

    def test_steal_with_zero_but_opportunities(self) -> None:
        """Test steal returns '0.0' when player never steals but had opportunities."""
        stat_dict = {"player1": {"steal": 0, "steal_opp": 10}}
        result = steal(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "st=0.0%"
        assert result[4] == "(0/10)"

    def test_steal_with_normal_value(self) -> None:
        """Test steal returns normal percentage when player has stats."""
        stat_dict = {"player1": {"steal": 4, "steal_opp": 10}}
        result = steal(stat_dict, "player1")

        assert result[1] == "40.0"
        assert result[2] == "st=40.0%"
        assert result[4] == "(4/10)"


class TestCBetNoDataFeature:
    """Test suite for continuation bet statistic no data feature."""

    def test_cbet_with_no_opportunities(self) -> None:
        """Test cbet returns '-' when no opportunities available."""
        stat_dict = {
            "player1": {
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 0,
                "cb_opp_2": 0,
                "cb_opp_3": 0,
                "cb_opp_4": 0,
            },
        }
        result = cbet(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "cbet=-"
        assert result[4] == "(-/-)"

    def test_cbet_with_zero_but_opportunities(self) -> None:
        """Test cbet returns '0.0' when player never cbets but had opportunities."""
        stat_dict = {
            "player1": {
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 5,
                "cb_opp_2": 3,
                "cb_opp_3": 2,
                "cb_opp_4": 0,
            },
        }
        result = cbet(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "cbet=0.0%"
        assert result[4] == "(0/10)"

    def test_cbet_with_normal_value(self) -> None:
        """Test cbet returns normal percentage when player has stats."""
        stat_dict = {
            "player1": {
                "cb_1": 3,
                "cb_2": 2,
                "cb_3": 1,
                "cb_4": 0,
                "cb_opp_1": 5,
                "cb_opp_2": 3,
                "cb_opp_3": 2,
                "cb_opp_4": 0,
            },
        }
        result = cbet(stat_dict, "player1")

        assert result[1] == "60.0"
        assert result[2] == "cbet=60.0%"
        assert result[4] == "(6/10)"


class TestAggressionFrequencyNoDataFeature:
    """Test suite for aggression frequency statistics no data feature."""

    def test_a_freq1_with_no_opportunities(self) -> None:
        """Test a_freq1 returns '-' when no opportunities available."""
        stat_dict = {"player1": {"aggr_1": 0, "saw_f": 0}}
        result = a_freq1(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "a1=-"
        assert result[4] == "(-/-)"

    def test_a_freq1_with_zero_but_opportunities(self) -> None:
        """Test a_freq1 returns '0.0' when player is passive but saw flops."""
        stat_dict = {"player1": {"aggr_1": 0, "saw_f": 10}}
        result = a_freq1(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "a1=0.0%"
        assert result[4] == "(0/10)"

    def test_a_freq2_with_no_opportunities(self) -> None:
        """Test a_freq2 returns '-' when no opportunities available."""
        stat_dict = {"player1": {"aggr_2": 0, "saw_2": 0}}
        result = a_freq2(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "a2=-"
        assert result[4] == "(-/-)"

    def test_a_freq3_with_no_opportunities(self) -> None:
        """Test a_freq3 returns '-' when no opportunities available."""
        stat_dict = {"player1": {"aggr_3": 0, "saw_3": 0}}
        result = a_freq3(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "a3=-"
        assert result[4] == "(-/-)"

    def test_a_freq4_with_no_opportunities(self) -> None:
        """Test a_freq4 returns '-' when no opportunities available."""
        stat_dict = {"player1": {"aggr_4": 0, "saw_4": 0}}
        result = a_freq4(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "a4=-"
        assert result[4] == "(-/-)"


class TestAggressionFactorNoDataFeature:
    """Test suite for aggression factor statistics no data feature."""

    def test_agg_fact_with_no_actions(self) -> None:
        """Test agg_fact returns '-' when no post-flop actions available."""
        stat_dict = {
            "player1": {
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 0,
                "call_2": 0,
                "call_3": 0,
                "call_4": 0,
            },
        }
        result = agg_fact(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "afa=-"
        assert result[4] == "(0/0)"

    def test_agg_fact_with_only_calls(self) -> None:
        """Test agg_fact returns '0.00' when player only calls (passive)."""
        stat_dict = {
            "player1": {
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 5,
                "call_2": 3,
                "call_3": 2,
                "call_4": 0,
            },
        }
        result = agg_fact(stat_dict, "player1")

        assert result[1] == "0.00"
        assert result[2] == "afa=0.00"
        assert result[4] == "(0/10)"

    def test_agg_fact_pct_with_no_actions(self) -> None:
        """Test agg_fact_pct returns '-' when no post-flop actions available."""
        stat_dict = {
            "player1": {
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 0,
                "call_2": 0,
                "call_3": 0,
                "call_4": 0,
            },
        }
        result = agg_fact_pct(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "afap=-"
        assert result[4] == "(0/0)"

    def test_agg_fact_pct_with_only_calls(self) -> None:
        """Test agg_fact_pct returns '0.00' when player only calls (passive)."""
        stat_dict = {
            "player1": {
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 5,
                "call_2": 3,
                "call_3": 2,
                "call_4": 0,
            },
        }
        result = agg_fact_pct(stat_dict, "player1")

        assert result[1] == "0.00"
        assert result[2] == "afap=0.00"
        assert result[4] == "(0/10)"


class TestRegressionNoDataFeature:
    """Regression tests to ensure existing functionality is not broken."""

    def test_vpip_exception_handling(self) -> None:
        """Test VPIP still returns 'NA' on exceptions."""
        stat_dict = {}
        result = vpip(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "v=NA"

    def test_pfr_exception_handling(self) -> None:
        """Test PFR still returns 'NA' on exceptions."""
        stat_dict = {}
        result = pfr(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "p=NA"

    def test_three_b_exception_handling(self) -> None:
        """Test 3-bet still returns 'NA' on exceptions."""
        stat_dict = {}
        result = three_B(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "3B=NA"

    def test_steal_exception_handling(self) -> None:
        """Test steal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = steal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "st=NA"

    def test_cbet_exception_handling(self) -> None:
        """Test cbet still returns 'NA' on exceptions."""
        stat_dict = {}
        result = cbet(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "cbet=NA"


class TestIntegrationScenarios:
    """Integration tests for realistic poker scenarios."""

    def test_new_player_all_stats_no_data(self) -> None:
        """Test all stats return '-' for a completely new player."""
        stat_dict = {
            "new_player": {
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

        # All stats should return '-' for display
        assert vpip(stat_dict, "new_player")[1] == "-"
        assert pfr(stat_dict, "new_player")[1] == "-"
        assert three_B(stat_dict, "new_player")[1] == "-"
        assert steal(stat_dict, "new_player")[1] == "-"
        assert cbet(stat_dict, "new_player")[1] == "-"
        assert a_freq1(stat_dict, "new_player")[1] == "-"
        assert agg_fact(stat_dict, "new_player")[1] == "-"
        assert agg_fact_pct(stat_dict, "new_player")[1] == "-"

    def test_tight_passive_player_real_zeros(self) -> None:
        """Test stats return '0.0' for a tight passive player with opportunities."""
        stat_dict = {
            "tight_player": {
                "vpip": 0,
                "vpip_opp": 20,  # Never played voluntarily
                "pfr": 0,
                "pfr_opp": 20,  # Never raised
                "tb_0": 0,
                "tb_opp_0": 5,  # Never 3-bet
                "steal": 0,
                "steal_opp": 8,  # Never stole
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 0,
                "cb_opp_2": 0,
                "cb_opp_3": 0,
                "cb_opp_4": 0,  # No c-bet opps
                "aggr_1": 0,
                "aggr_2": 0,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 2,
                "call_2": 1,
                "call_3": 0,
                "call_4": 0,  # Only called
                "saw_f": 5,
                "saw_2": 2,
                "saw_3": 1,
                "saw_4": 0,  # Saw some streets
            },
        }

        # These should show 0.0 (real tight/passive play)
        assert vpip(stat_dict, "tight_player")[1] == "0.0"
        assert pfr(stat_dict, "tight_player")[1] == "0.0"
        assert three_B(stat_dict, "tight_player")[1] == "0.0"
        assert steal(stat_dict, "tight_player")[1] == "0.0"

        # These should show '-' (no opportunities)
        assert cbet(stat_dict, "tight_player")[1] == "-"

        # Aggression frequency should show 0.0 (saw streets but was passive)
        assert a_freq1(stat_dict, "tight_player")[1] == "0.0"

    def test_mixed_scenario_some_data_some_not(self) -> None:
        """Test realistic scenario with some stats having data, others not."""
        stat_dict = {
            "mixed_player": {
                "vpip": 10,
                "vpip_opp": 50,  # 20% VPIP (has data)
                "pfr": 5,
                "pfr_opp": 50,  # 10% PFR (has data)
                "tb_0": 0,
                "tb_opp_0": 0,  # No 3-bet opportunities
                "steal": 2,
                "steal_opp": 8,  # 25% steal (has data)
                "cb_1": 0,
                "cb_2": 0,
                "cb_3": 0,
                "cb_4": 0,
                "cb_opp_1": 0,
                "cb_opp_2": 0,
                "cb_opp_3": 0,
                "cb_opp_4": 0,  # No c-bet opps
                "aggr_1": 3,
                "aggr_2": 1,
                "aggr_3": 0,
                "aggr_4": 0,
                "call_1": 2,
                "call_2": 1,
                "call_3": 0,
                "call_4": 0,
                "saw_f": 10,
                "saw_2": 4,
                "saw_3": 1,
                "saw_4": 0,
            },
        }

        # Should show percentages (has data)
        assert vpip(stat_dict, "mixed_player")[1] == "20.0"
        assert pfr(stat_dict, "mixed_player")[1] == "10.0"
        assert steal(stat_dict, "mixed_player")[1] == "25.0"

        # Should show '-' (no opportunities)
        assert three_B(stat_dict, "mixed_player")[1] == "-"
        assert cbet(stat_dict, "mixed_player")[1] == "-"

        # Should show percentages (saw streets and had some aggression)
        assert a_freq1(stat_dict, "mixed_player")[1] == "30.0"  # 3/10


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
