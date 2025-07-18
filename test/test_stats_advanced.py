#!/usr/bin/env python3
"""
Test suite for advanced statistics implementation.

This module tests the newly implemented advanced statistics:
- CB IP (Continuation bet In Position)
- CB OOP (Continuation bet Out of Position)
- Triple Barrel (Bet flop/turn/river)
- Resteal (Re-raise contre steal)
- Probe Bet Turn
- Probe Bet River
"""

import pytest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Stats import (
    cb_ip,
    cb_oop,
    triple_barrel,
    resteal,
    probe_bet_turn,
    probe_bet_river,
)


class TestCBInPositionStat:
    """Test suite for CB IP (Continuation bet In Position) statistic."""

    def test_cb_ip_with_no_opportunities(self):
        """Test cb_ip returns '-' when no flop or IP opportunities."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 0, 'cb_1': 0, 'street1InPosition': 0, 'saw_f': 0
            }
        }
        result = cb_ip(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb_ip=-"
        assert result[4] == "(-/-)"

    def test_cb_ip_with_zero_but_opportunities(self):
        """Test cb_ip returns '0.0' when player had IP opportunities but never c-bet."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 10, 'cb_1': 0, 'street1InPosition': 8, 'saw_f': 10
            }
        }
        result = cb_ip(stat_dict, 'player1')
        
        assert result[1] == "0.0"  # (0 * 0.8) / (10 * 0.8) = 0/8 = 0%
        assert result[2] == "cb_ip=0.0%"
        assert result[4] == "(0/8)"

    def test_cb_ip_with_normal_value(self):
        """Test cb_ip returns normal percentage when player c-bet IP."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 15, 'cb_1': 9, 'street1InPosition': 12, 'saw_f': 15
            }
        }
        result = cb_ip(stat_dict, 'player1')
        
        assert result[1] == "60.0"  # (9 * 0.8) / (15 * 0.8) = 7.2/12 = 60%
        assert result[2] == "cb_ip=60.0%"
        assert result[4] == "(7/12)"

    def test_cb_ip_exception_handling(self):
        """Test cb_ip returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = cb_ip(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "cb_ip=-"


class TestCBOutOfPositionStat:
    """Test suite for CB OOP (Continuation bet Out of Position) statistic."""

    def test_cb_oop_with_no_opportunities(self):
        """Test cb_oop returns '-' when no flop or OOP opportunities."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 0, 'cb_1': 0, 'street1InPosition': 0, 'saw_f': 0
            }
        }
        result = cb_oop(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "cb_oop=-"
        assert result[4] == "(-/-)"

    def test_cb_oop_with_normal_value(self):
        """Test cb_oop returns normal percentage when player c-bet OOP."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 20, 'cb_1': 12, 'street1InPosition': 8, 'saw_f': 20
            }
        }
        result = cb_oop(stat_dict, 'player1')
        
        assert result[1] == "60.0"  # (12 * 0.6) / (20 * 0.6) = 7.2/12 = 60%
        assert result[2] == "cb_oop=60.0%"
        assert result[4] == "(7/12)"

    def test_cb_oop_exception_handling(self):
        """Test cb_oop returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = cb_oop(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "cb_oop=-"


class TestTripleBarrelStat:
    """Test suite for Triple Barrel statistic."""

    def test_triple_barrel_with_no_opportunities(self):
        """Test triple_barrel returns '-' when no opportunities on all three streets."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 0, 'cb_1': 0, 'cb_opp_2': 0, 'cb_2': 0, 
                'cb_opp_3': 0, 'cb_3': 0
            }
        }
        result = triple_barrel(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "3barrel=-"
        assert result[4] == "(-/-)"

    def test_triple_barrel_with_zero_but_opportunities(self):
        """Test triple_barrel returns '0.0' when player had opportunities but never triple barreled."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 10, 'cb_1': 0, 'cb_opp_2': 8, 'cb_2': 0, 
                'cb_opp_3': 6, 'cb_3': 0
            }
        }
        result = triple_barrel(stat_dict, 'player1')
        
        assert result[1] == "0.0"  # 6 * 0 * 0 * 0 = 0/6 = 0%
        assert result[2] == "3barrel=0.0%"
        assert result[4] == "(0/6)"

    def test_triple_barrel_with_normal_value(self):
        """Test triple_barrel returns normal percentage when player triple barreled."""
        stat_dict = {
            'player1': {
                'cb_opp_1': 20, 'cb_1': 16, 'cb_opp_2': 15, 'cb_2': 12, 
                'cb_opp_3': 10, 'cb_3': 6
            }
        }
        result = triple_barrel(stat_dict, 'player1')
        
        # cb_rate_1 = 16/20 = 0.8, cb_rate_2 = 12/15 = 0.8, cb_rate_3 = 6/10 = 0.6
        # triple_barrel_count = 10 * 0.8 * 0.8 * 0.6 = 3.84
        assert result[1] == "38.4"  # 3.84/10 = 38.4%
        assert result[2] == "3barrel=38.4%"

    def test_triple_barrel_exception_handling(self):
        """Test triple_barrel returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = triple_barrel(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "3barrel=-"


class TestRestealStat:
    """Test suite for Resteal statistic."""

    def test_resteal_with_no_opportunities(self):
        """Test resteal returns '-' when no 3-bet opportunities."""
        stat_dict = {
            'player1': {'tb_opp_0': 0, 'tb_0': 0}
        }
        result = resteal(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "resteal=-"
        assert result[4] == "(-/-)"

    def test_resteal_with_zero_but_opportunities(self):
        """Test resteal returns '0.0' when player had opportunities but never restealed."""
        stat_dict = {
            'player1': {'tb_opp_0': 15, 'tb_0': 0}
        }
        result = resteal(stat_dict, 'player1')
        
        assert result[1] == "0.0"  # (0 * 0.7) / (15 * 0.6) = 0/9 = 0%
        assert result[2] == "resteal=0.0%"
        assert result[4] == "(0/9)"

    def test_resteal_with_normal_value(self):
        """Test resteal returns normal percentage when player restealed."""
        stat_dict = {
            'player1': {'tb_opp_0': 20, 'tb_0': 4}
        }
        result = resteal(stat_dict, 'player1')
        
        assert result[1] == "23.3"  # (4 * 0.7) / (20 * 0.6) = 2.8/12 = 23.3%
        assert result[2] == "resteal=23.3%"
        assert result[4] == "(2/12)"

    def test_resteal_exception_handling(self):
        """Test resteal returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = resteal(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "resteal=-"


class TestProbeBetTurnStat:
    """Test suite for Probe Bet Turn statistic."""

    def test_probe_bet_turn_with_no_opportunities(self):
        """Test probe_bet_turn returns '-' when no turn opportunities."""
        stat_dict = {
            'player1': {
                'street2Bets': 0, 'saw_t': 0, 'cb_opp_2': 0, 'cb_2': 0
            }
        }
        result = probe_bet_turn(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "probe_t=-"
        assert result[4] == "(-/-)"

    def test_probe_bet_turn_with_zero_but_opportunities(self):
        """Test probe_bet_turn returns '0.0' when player had opportunities but never probed turn."""
        stat_dict = {
            'player1': {
                'street2Bets': 0, 'saw_t': 12, 'cb_opp_2': 10, 'cb_2': 3
            }
        }
        result = probe_bet_turn(stat_dict, 'player1')
        
        assert result[1] == "0.0"  # 0/(12-3) = 0/9 = 0%
        assert result[2] == "probe_t=0.0%"
        assert result[4] == "(0/9)"

    def test_probe_bet_turn_with_normal_value(self):
        """Test probe_bet_turn returns normal percentage when player probed turn."""
        stat_dict = {
            'player1': {
                'street2Bets': 3, 'saw_t': 15, 'cb_opp_2': 12, 'cb_2': 5
            }
        }
        result = probe_bet_turn(stat_dict, 'player1')
        
        assert result[1] == "30.0"  # 3/(15-5) = 3/10 = 30%
        assert result[2] == "probe_t=30.0%"
        assert result[4] == "(3/10)"

    def test_probe_bet_turn_exception_handling(self):
        """Test probe_bet_turn returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = probe_bet_turn(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "probe_t=-"


class TestProbeBetRiverStat:
    """Test suite for Probe Bet River statistic."""

    def test_probe_bet_river_with_no_opportunities(self):
        """Test probe_bet_river returns '-' when no river opportunities."""
        stat_dict = {
            'player1': {
                'street3Bets': 0, 'saw_r': 0, 'cb_opp_3': 0, 'cb_3': 0
            }
        }
        result = probe_bet_river(stat_dict, 'player1')
        
        assert result[1] == "-"
        assert result[2] == "probe_r=-"
        assert result[4] == "(-/-)"

    def test_probe_bet_river_with_normal_value(self):
        """Test probe_bet_river returns normal percentage when player probed river."""
        stat_dict = {
            'player1': {
                'street3Bets': 2, 'saw_r': 10, 'cb_opp_3': 8, 'cb_3': 2
            }
        }
        result = probe_bet_river(stat_dict, 'player1')
        
        assert result[1] == "25.0"  # 2/(10-2) = 2/8 = 25%
        assert result[2] == "probe_r=25.0%"
        assert result[4] == "(2/8)"

    def test_probe_bet_river_exception_handling(self):
        """Test probe_bet_river returns format_no_data_stat on exceptions."""
        stat_dict = {}
        result = probe_bet_river(stat_dict, 'nonexistent_player')
        
        assert result[1] == "-"
        assert result[2] == "probe_r=-"


class TestAdvancedStatsIntegration:
    """Integration tests for the new advanced statistics."""

    def test_new_player_all_stats_no_data(self):
        """Test all new advanced stats return '-' for a completely new player."""
        stat_dict = {
            'new_player': {
                'cb_opp_1': 0, 'cb_1': 0, 'cb_opp_2': 0, 'cb_2': 0, 'cb_opp_3': 0, 'cb_3': 0,
                'street1InPosition': 0, 'saw_f': 0, 'saw_t': 0, 'saw_r': 0,
                'street2Bets': 0, 'street3Bets': 0, 'tb_opp_0': 0, 'tb_0': 0
            }
        }
        
        # All new advanced stats should return '-' for display
        assert cb_ip(stat_dict, 'new_player')[1] == "-"
        assert cb_oop(stat_dict, 'new_player')[1] == "-"
        assert triple_barrel(stat_dict, 'new_player')[1] == "-"
        assert resteal(stat_dict, 'new_player')[1] == "-"
        assert probe_bet_turn(stat_dict, 'new_player')[1] == "-"
        assert probe_bet_river(stat_dict, 'new_player')[1] == "-"

    def test_aggressive_player_profile(self):
        """Test advanced stats for an aggressive player."""
        stat_dict = {
            'aggressive_player': {
                # High c-bet rates on all streets
                'cb_opp_1': 20, 'cb_1': 16, 'cb_opp_2': 15, 'cb_2': 12, 'cb_opp_3': 10, 'cb_3': 6,
                # Often in position
                'street1InPosition': 14, 'saw_f': 20, 'saw_t': 15, 'saw_r': 10,
                # High betting frequency
                'street2Bets': 8, 'street3Bets': 4,
                # Active 3-betting
                'tb_opp_0': 25, 'tb_0': 8
            }
        }
        
        # Should show high aggression patterns
        assert cb_ip(stat_dict, 'aggressive_player')[1] == "80.0"  # (16 * 0.7) / (20 * 0.7) = 80%
        assert cb_oop(stat_dict, 'aggressive_player')[1] == "80.0"  # (16 * 0.3) / (20 * 0.3) = 80%
        assert triple_barrel(stat_dict, 'aggressive_player')[1] == "38.4"  # 10 * 0.8 * 0.8 * 0.6 = 38.4%
        assert resteal(stat_dict, 'aggressive_player')[1] == "37.3"  # (8 * 0.7) / (25 * 0.6) = 37.3%

    def test_conservative_player_profile(self):
        """Test advanced stats for a conservative player."""
        stat_dict = {
            'conservative_player': {
                # Lower c-bet rates
                'cb_opp_1': 18, 'cb_1': 9, 'cb_opp_2': 12, 'cb_2': 4, 'cb_opp_3': 8, 'cb_3': 2,
                # Mixed position
                'street1InPosition': 9, 'saw_f': 18, 'saw_t': 12, 'saw_r': 8,
                # Lower betting frequency
                'street2Bets': 2, 'street3Bets': 1,
                # Conservative 3-betting
                'tb_opp_0': 20, 'tb_0': 3
            }
        }
        
        # Should show more conservative patterns
        assert cb_ip(stat_dict, 'conservative_player')[1] == "50.0"  # (9 * 0.5) / (18 * 0.5) = 50%
        assert cb_oop(stat_dict, 'conservative_player')[1] == "50.0"  # (9 * 0.5) / (18 * 0.5) = 50%
        assert triple_barrel(stat_dict, 'conservative_player')[1] == "4.2"  # 8 * 0.5 * 0.33 * 0.25 = 4.2%
        assert resteal(stat_dict, 'conservative_player')[1] == "17.5"  # (3 * 0.7) / (20 * 0.6) = 17.5%


class TestAdvancedStatsRegressionTests:
    """Regression tests to ensure new advanced stats functionality is not broken."""

    def test_all_new_stats_exception_handling(self):
        """Test all new advanced stats handle exceptions consistently."""
        stat_dict = {}
        
        assert cb_ip(stat_dict, 'nonexistent_player')[1] == "-"
        assert cb_oop(stat_dict, 'nonexistent_player')[1] == "-"
        assert triple_barrel(stat_dict, 'nonexistent_player')[1] == "-"
        assert resteal(stat_dict, 'nonexistent_player')[1] == "-"
        assert probe_bet_turn(stat_dict, 'nonexistent_player')[1] == "-"
        assert probe_bet_river(stat_dict, 'nonexistent_player')[1] == "-"

    def test_tuple_format_consistency(self):
        """Test that all new stats return properly formatted 6-element tuples."""
        stat_dict = {
            'test_player': {
                'cb_opp_1': 20, 'cb_1': 12, 'cb_opp_2': 15, 'cb_2': 8, 'cb_opp_3': 10, 'cb_3': 4,
                'street1InPosition': 12, 'saw_f': 20, 'saw_t': 15, 'saw_r': 10,
                'street2Bets': 5, 'street3Bets': 3, 'tb_opp_0': 25, 'tb_0': 6
            }
        }
        
        # Test tuple structure for all new stats
        stats_to_test = [
            cb_ip, cb_oop, triple_barrel, resteal, probe_bet_turn, probe_bet_river
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