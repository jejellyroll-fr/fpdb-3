import pytest
from fpdb_3_legacy.PlayerProfiler import classify_player, PlayerProfile
from fpdb_3_legacy.Stats import do_stat


def test_insufficient_hands():
    # Less than 10 hands should result in unknown
    stat_dict = {
        1: {
            "n": 5,
            "vpip_opp": 5,
            "vpip": 4,  # 80% VPIP
            "pfr_opp": 5,
            "pfr": 1,  # 20% PFR
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.UNKNOWN


def test_nit():
    # Tight (VPIP < 15, PFR < 12)
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 12,
            "pfr_opp": 100,
            "pfr": 8,
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.NIT
    assert icon == "🐌"
    assert color == "#0000FF"


def test_calling_station():
    # Calling Station: VPIP > 30, vpip_pfr_gap > 15, agg_pct < 25, wtsd > 33
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 35,
            "pfr_opp": 100,
            "pfr": 10,  # gap = 25
            "aggr_1": 2,
            "aggr_2": 2,
            "aggr_3": 1,
            "aggr_4": 0,  # bet_raise = 5
            "call_1": 10,
            "call_2": 5,
            "call_3": 5,
            "call_4": 0,  # post_call = 20
            # agg_pct = 5 / 25 = 20% (< 25)
            "sd": 15,
            "saw_f": 30,  # wtsd = 15/30 = 50% (> 33)
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.CALLING_STATION
    assert icon == "📞"


def test_fish():
    # Fish: VPIP > 35, gap > 20
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 45,
            "pfr_opp": 100,
            "pfr": 10,  # gap = 35
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.FISH
    assert icon == "🐟"


def test_maniac():
    # Maniac: VPIP > 40, PFR > 30, (agg_pct > 60 or agg_factor > 3.0)
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 45,
            "pfr_opp": 100,
            "pfr": 35,
            "aggr_1": 15,
            "aggr_2": 10,
            "aggr_3": 5,
            "aggr_4": 5,  # bet_raise = 35
            "call_1": 2,
            "call_2": 1,
            "call_3": 1,
            "call_4": 1,  # post_call = 5
            # agg_pct = 35 / 40 = 87.5% (> 60%)
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.MANIAC
    assert icon == "🌪️"


def test_lag():
    # LAG: VPIP > 28, PFR > 22, gap < 12, agg_pct > 45
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 32,
            "pfr_opp": 100,
            "pfr": 25,  # gap = 7
            "aggr_1": 10,
            "aggr_2": 5,
            "aggr_3": 3,
            "aggr_4": 2,  # bet_raise = 20
            "call_1": 5,
            "call_2": 3,
            "call_3": 2,
            "call_4": 0,  # post_call = 10
            # agg_pct = 20 / 30 = 66.7% (> 45%)
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.LAG
    assert icon == "⚡"


def test_reg():
    # Reg: 21 <= VPIP <= 28, 18 <= PFR <= 24, gap < 10, agg_pct > 40
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 24,
            "pfr_opp": 100,
            "pfr": 20,  # gap = 4
            "aggr_1": 10,
            "aggr_2": 5,
            "aggr_3": 2,
            "aggr_4": 1,  # bet_raise = 18
            "call_1": 5,
            "call_2": 3,
            "call_3": 2,
            "call_4": 0,  # post_call = 10
            # agg_pct = 18 / 28 = 64% (> 40%)
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.REG
    assert icon == "💼"


def test_tag():
    # TAG: 15 <= VPIP <= 25, 12 <= PFR <= 20, agg_pct > 35
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 18,
            "pfr_opp": 100,
            "pfr": 14,
            "aggr_1": 8,
            "aggr_2": 4,
            "aggr_3": 1,
            "aggr_4": 1,  # bet_raise = 14
            "call_1": 5,
            "call_2": 3,
            "call_3": 2,
            "call_4": 0,  # post_call = 10
            # agg_pct = 14 / 24 = 58% (> 35%)
        }
    }
    profile, icon, color = classify_player(stat_dict, 1)
    assert profile == PlayerProfile.TAG
    assert icon == "🎯"


def test_do_stat_playerprofile():
    # Test that Stats.do_stat handles the playerprofile virtual stat
    stat_dict = {
        1: {
            "n": 100,
            "vpip_opp": 100,
            "vpip": 12,
            "pfr_opp": 100,
            "pfr": 8,
        }
    }
    result = do_stat(stat_dict, 1, "playerprofile")
    assert result is not None
    assert result[0] == "nit"
    assert result[1] == "🐌"
    assert result[5] == "Player Profile"

    # Test None safety directly on playerprofile (which get_valid_stats uses)
    from fpdb_3_legacy.Stats import playerprofile
    result_none = playerprofile(None, None)
    assert result_none is not None
    assert result_none[0] == "unknown"
    assert result_none[1] == "❓"
    assert result_none[5] == "Player Profile"
