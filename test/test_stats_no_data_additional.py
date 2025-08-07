#!/usr/bin/env python3
"""Test suite for additional Stats.py "no data" feature implementations.

This module tests the newly implemented format_no_data_stat functionality
for additional steal and ratio statistics.
"""

import os
import sys

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Stats import (
    f_steal,
    raiseToSteal,
    s_steal,
    vpip_pfr_ratio,
)


class TestFoldStealNoDataFeature:
    """Test suite for Fold to Steal (all positions) statistic no data feature."""

    def test_f_steal_with_no_opportunities(self) -> None:
        """Test f_steal returns '-' when no steal attempts."""
        stat_dict = {"player1": {"sbstolen": 0, "bbstolen": 0, "sbnotdef": 0, "bbnotdef": 0}}
        result = f_steal(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "fB=-"
        assert result[4] == "(-/-)"

    def test_f_steal_with_zero_but_opportunities(self) -> None:
        """Test f_steal returns '0.0' when player never folded but had steal attempts."""
        stat_dict = {"player1": {"sbstolen": 3, "bbstolen": 2, "sbnotdef": 0, "bbnotdef": 0}}
        result = f_steal(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "fB=0.0%"
        assert result[4] == "(0/5)"

    def test_f_steal_with_normal_value(self) -> None:
        """Test f_steal returns normal percentage when player folded to steals."""
        stat_dict = {"player1": {"sbstolen": 3, "bbstolen": 2, "sbnotdef": 2, "bbnotdef": 1}}
        result = f_steal(stat_dict, "player1")

        assert result[1] == "60.0"
        assert result[2] == "fB=60.0%"
        assert result[4] == "(3/5)"

    def test_f_steal_exception_handling(self) -> None:
        """Test f_steal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = f_steal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "fB=NA"


class TestStealSuccessNoDataFeature:
    """Test suite for Steal Success statistic no data feature."""

    def test_s_steal_with_no_attempts(self) -> None:
        """Test s_steal returns '-' when no steal attempts."""
        stat_dict = {"player1": {"steal": 0, "suc_st": 0}}
        result = s_steal(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "s_st=-"
        assert result[4] == "(-/-)"

    def test_s_steal_with_zero_but_attempts(self) -> None:
        """Test s_steal returns '0.0' when player never succeeded but attempted steals."""
        stat_dict = {"player1": {"steal": 8, "suc_st": 0}}
        result = s_steal(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "s_st=0.0%"
        assert result[4] == "(0/8)"

    def test_s_steal_with_normal_value(self) -> None:
        """Test s_steal returns normal percentage when player succeeded steals."""
        stat_dict = {"player1": {"steal": 8, "suc_st": 5}}
        result = s_steal(stat_dict, "player1")

        assert result[1] == "62.5"
        assert result[2] == "s_st=62.5%"
        assert result[4] == "(5/8)"

    def test_s_steal_exception_handling(self) -> None:
        """Test s_steal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = s_steal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "s_st=NA"


class TestRaiseToStealNoDataFeature:
    """Test suite for Raise to Steal statistic no data feature."""

    def test_raise_to_steal_with_no_opportunities(self) -> None:
        """Test raiseToSteal returns '-' when no opportunities."""
        stat_dict = {"player1": {"rts_opp": 0, "rts": 0}}
        result = raiseToSteal(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "RST=-"
        assert result[4] == "(-/-)"

    def test_raise_to_steal_with_zero_but_opportunities(self) -> None:
        """Test raiseToSteal returns '0.0' when player never raised but had opportunities."""
        stat_dict = {"player1": {"rts_opp": 6, "rts": 0}}
        result = raiseToSteal(stat_dict, "player1")

        assert result[1] == "0.0"
        assert result[2] == "RST=0.0%"
        assert result[4] == "(0/6)"

    def test_raise_to_steal_with_normal_value(self) -> None:
        """Test raiseToSteal returns normal percentage when player raised to steal."""
        stat_dict = {"player1": {"rts_opp": 6, "rts": 2}}
        result = raiseToSteal(stat_dict, "player1")

        assert result[1] == "33.3"
        assert result[2] == "RST=33.3%"
        assert result[4] == "(2/6)"

    def test_raise_to_steal_exception_handling(self) -> None:
        """Test raiseToSteal still returns 'NA' on exceptions."""
        stat_dict = {}
        result = raiseToSteal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "RST=NA"


class TestVPIPPFRRatioNoDataFeature:
    """Test suite for VPIP/PFR Ratio statistic no data feature."""

    def test_vpip_pfr_ratio_with_no_opportunities(self) -> None:
        """Test vpip_pfr_ratio returns '-' when no preflop opportunities."""
        stat_dict = {"player1": {"vpip_opp": 0, "pfr_opp": 0, "vpip": 0, "pfr": 0}}
        result = vpip_pfr_ratio(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "v/p=-"
        assert result[4] == "(-/-)"

    def test_vpip_pfr_ratio_with_vpip_only_opportunities(self) -> None:
        """Test vpip_pfr_ratio returns '-' when only VPIP opportunities."""
        stat_dict = {"player1": {"vpip_opp": 10, "pfr_opp": 0, "vpip": 3, "pfr": 0}}
        result = vpip_pfr_ratio(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "v/p=-"
        assert result[4] == "(-/-)"

    def test_vpip_pfr_ratio_with_pfr_only_opportunities(self) -> None:
        """Test vpip_pfr_ratio returns '-' when only PFR opportunities."""
        stat_dict = {"player1": {"vpip_opp": 0, "pfr_opp": 10, "vpip": 0, "pfr": 2}}
        result = vpip_pfr_ratio(stat_dict, "player1")

        assert result[1] == "-"
        assert result[2] == "v/p=-"
        assert result[4] == "(-/-)"

    def test_vpip_pfr_ratio_with_normal_value(self) -> None:
        """Test vpip_pfr_ratio returns normal ratio when player has both stats."""
        stat_dict = {"player1": {"vpip_opp": 20, "pfr_opp": 20, "vpip": 6, "pfr": 4}}
        result = vpip_pfr_ratio(stat_dict, "player1")

        assert result[1] == "1.50"  # 30% VPIP / 20% PFR = 1.5
        assert result[2] == "v/p=1.50"

    def test_vpip_pfr_ratio_with_zero_pfr(self) -> None:
        """Test vpip_pfr_ratio handles zero PFR correctly."""
        stat_dict = {"player1": {"vpip_opp": 20, "pfr_opp": 20, "vpip": 4, "pfr": 0}}
        result = vpip_pfr_ratio(stat_dict, "player1")

        assert result[1] == "inf"  # Should handle division by zero
        assert result[2] == "v/p=inf"

    def test_vpip_pfr_ratio_exception_handling(self) -> None:
        """Test vpip_pfr_ratio still returns 'NA' on exceptions."""
        stat_dict = {}
        result = vpip_pfr_ratio(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "v/p=NA"


class TestAdditionalStatsIntegration:
    """Integration tests for the additional no data stats."""

    def test_new_player_additional_stats_no_data(self) -> None:
        """Test all new additional stats return '-' for a completely new player."""
        stat_dict = {
            "new_player": {
                "sbstolen": 0,
                "bbstolen": 0,
                "sbnotdef": 0,
                "bbnotdef": 0,
                "steal": 0,
                "suc_st": 0,
                "rts_opp": 0,
                "rts": 0,
                "vpip_opp": 0,
                "pfr_opp": 0,
                "vpip": 0,
                "pfr": 0,
            },
        }

        # All additional stats should return '-' for display
        assert f_steal(stat_dict, "new_player")[1] == "-"
        assert s_steal(stat_dict, "new_player")[1] == "-"
        assert raiseToSteal(stat_dict, "new_player")[1] == "-"
        assert vpip_pfr_ratio(stat_dict, "new_player")[1] == "-"

    def test_active_player_with_real_zeros(self) -> None:
        """Test additional stats return correct values for an active player."""
        stat_dict = {
            "active_player": {
                "sbstolen": 5,
                "bbstolen": 3,
                "sbnotdef": 0,
                "bbnotdef": 0,  # Always defended
                "steal": 12,
                "suc_st": 0,  # Steals but never successful
                "rts_opp": 8,
                "rts": 0,  # Never raised to steal
                "vpip_opp": 50,
                "pfr_opp": 50,
                "vpip": 15,
                "pfr": 5,  # 30% VPIP, 10% PFR
            },
        }

        # These should show 0.0 (real zero values with opportunities)
        assert f_steal(stat_dict, "active_player")[1] == "0.0"
        assert s_steal(stat_dict, "active_player")[1] == "0.0"
        assert raiseToSteal(stat_dict, "active_player")[1] == "0.0"
        assert vpip_pfr_ratio(stat_dict, "active_player")[1] == "3.00"  # 30/10 = 3.0

    def test_mixed_scenario_additional_stats(self) -> None:
        """Test realistic scenario with some additional stats having data, others not."""
        stat_dict = {
            "mixed_player": {
                "sbstolen": 0,
                "bbstolen": 0,
                "sbnotdef": 0,
                "bbnotdef": 0,  # No steal attempts
                "steal": 8,
                "suc_st": 5,  # Some steal success
                "rts_opp": 6,
                "rts": 2,  # Some raise to steal
                "vpip_opp": 40,
                "pfr_opp": 40,
                "vpip": 12,
                "pfr": 8,  # 30% VPIP, 20% PFR
            },
        }

        # Should show percentages (has data)
        assert s_steal(stat_dict, "mixed_player")[1] == "62.5"  # 5/8
        assert raiseToSteal(stat_dict, "mixed_player")[1] == "33.3"  # 2/6
        assert vpip_pfr_ratio(stat_dict, "mixed_player")[1] == "1.50"  # 30/20 = 1.5

        # Should show '-' (no opportunities)
        assert f_steal(stat_dict, "mixed_player")[1] == "-"


class TestAdditionalStatsRegressionTests:
    """Regression tests to ensure additional stats functionality is not broken."""

    def test_f_steal_exception_handling_complete(self) -> None:
        """Test f_steal comprehensive exception handling."""
        stat_dict = {}
        result = f_steal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "fB=NA"
        assert result[4] == "(0/0)"

    def test_s_steal_exception_handling_complete(self) -> None:
        """Test s_steal comprehensive exception handling."""
        stat_dict = {}
        result = s_steal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "s_st=NA"
        assert result[4] == "(0/0)"

    def test_raise_to_steal_exception_handling_complete(self) -> None:
        """Test raiseToSteal comprehensive exception handling."""
        stat_dict = {}
        result = raiseToSteal(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "RST=NA"
        assert result[4] == "(0/0)"

    def test_vpip_pfr_ratio_exception_handling_complete(self) -> None:
        """Test vpip_pfr_ratio comprehensive exception handling."""
        stat_dict = {}
        result = vpip_pfr_ratio(stat_dict, "nonexistent_player")

        assert result[1] == "NA"
        assert result[2] == "v/p=NA"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
