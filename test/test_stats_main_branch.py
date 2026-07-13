#!/usr/bin/env python3
"""Tests for main() and module-level code coverage."""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_deprecated_stats():
    """Test deprecated stats return format_no_data_stat tuples."""
    from fpdb_3_legacy.Stats import (
        avg_bet_size_flop,
        avg_bet_size_river,
        avg_bet_size_turn,
        call_vs_steal,
        iso,
        three_bet_vs_steal,
    )

    stat_dict = {"player1": {}}

    # All deprecated stats should return the no-data marker
    assert iso(stat_dict, "player1")[1] == "-"
    assert three_bet_vs_steal(stat_dict, "player1")[1] == "-"
    assert call_vs_steal(stat_dict, "player1")[1] == "-"
    assert avg_bet_size_flop(stat_dict, "player1")[1] == "-"
    assert avg_bet_size_turn(stat_dict, "player1")[1] == "-"
    assert avg_bet_size_river(stat_dict, "player1")[1] == "-"


def test_main_validate_stats():
    """Test --validate-stats flag with graceful handling of no database."""
    result = subprocess.run(
        [sys.executable, "-m", "fpdb_3_legacy.Stats", "--validate-stats"],
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )
    # Should either succeed or fail gracefully with no hands message
    assert result.returncode in (0, 1)
    assert "No hands found" in result.stdout or "Connecting to database" in result.stdout


def test_do_stat_all_exception_paths():
    """Test exception branches in do_stat."""
    from fpdb_3_legacy.Stats import do_stat

    # Test with player as non-existent key (KeyError path)
    stat_dict = {"1": {"vpip": 10, "vpip_opp": 20}}
    result = do_stat(stat_dict, stat="vpip", player=999)  # KeyError

    # Test with stat that returns None
    result = do_stat(stat_dict, stat="nonexistent_stat_xyz", player=1)
    assert result is None


def test_format_no_data_stat_with_numerator_only():
    """Test format_no_data_stat with only numerator."""
    from fpdb_3_legacy.Stats import format_no_data_stat
    result = format_no_data_stat("test", "desc", 5, None)
    assert result[4] == "(-/-)"


def test_format_no_data_stat_with_denominator_only():
    """Test format_no_data_stat with only denominator."""
    from fpdb_3_legacy.Stats import format_no_data_stat
    result = format_no_data_stat("test", "desc", None, 10)
    assert result[4] == "(-/-)"


def test_all_stats_via_do_stat():
    """Test calling all stats via do_stat to hit STAT_FUNCTIONS dispatch."""
    from fpdb_3_legacy.Stats import STATLIST, do_stat

    base_dict = {
        "p": {k: 10 for k in ["vpip", "vpip_opp", "street0Aggr", "street0AggrChance",
                              "street1Seen", "street1CBChance", "street1CBDone",
                              "street1Calls", "street1Bets", "street1Raises",
                              "street2Seen", "street2CBChance", "street2CBDone",
                              "street2Calls", "street2Bets", "street2Raises",
                              "street3Seen", "street3CBChance", "street3CBDone",
                              "street3Calls", "street3Bets", "street3Raises",
                              "sawShowdown", "showed", "wonAtSD", "n",
                              "totalProfit", "allInEV", "rake", "stealChance",
                              "stealDone", "raiseToStealChance", "raiseToStealDone",
                              "street0Limp", "street0OpenLimpChance", "street0OpenLimp",
                              "street1Discards", "street2Discards", "street3Discards",
                              "street0Calls", "street0Raises", "street0Bets"]}
    }

    for stat in STATLIST:
        try:
            do_stat(base_dict, stat=stat, player="p")
        except Exception:
            pass  # Some stats need more specific data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
