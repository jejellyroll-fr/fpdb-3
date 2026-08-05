"""Unit tests for the legacy player profiler.

``classify_player`` buckets a player into one of eight archetypes (fish, reg,
nit, maniac, lag, tag, calling_station, unknown) from their statistics. The
tests cover every branch, the zero-division guards, the minimum-hands rule and
the unknown default.
"""

from __future__ import annotations

from fpdb_3_legacy.PlayerProfiler import (
    PROFILE_COLORS,
    PROFILE_ICONS,
    PlayerProfile,
    classify_player,
)


def make_stats(**overrides: float) -> dict[str, float]:
    stats: dict[str, float] = {
        "n": 100,
        "vpip_opp": 100,
        "vpip": 20,
        "pfr_opp": 100,
        "pfr": 15,
        "aggr_1": 8,
        "aggr_2": 4,
        "aggr_3": 1,
        "aggr_4": 1,
        "call_1": 5,
        "call_2": 3,
        "call_3": 2,
        "call_4": 0,
        "sd": 30,
        "saw_f": 60,
    }
    stats.update(overrides)
    return stats


def assert_profile(stats: dict[str, float], expected: str) -> None:
    profile, icon, color = classify_player({1: stats}, 1)
    assert profile == expected
    assert icon == PROFILE_ICONS[expected]
    assert color == PROFILE_COLORS[expected]


def test_unknown_for_missing_player() -> None:
    profile, icon, color = classify_player({}, 42)
    assert profile == PlayerProfile.UNKNOWN
    assert icon == PROFILE_ICONS[PlayerProfile.UNKNOWN]
    assert color == PROFILE_COLORS[PlayerProfile.UNKNOWN]


def test_unknown_below_min_hands() -> None:
    profile, _, _ = classify_player({1: make_stats(n=9)}, 1)
    assert profile == PlayerProfile.UNKNOWN


def test_min_hands_is_customisable() -> None:
    stats = make_stats(n=5, vpip=12, pfr=8)
    assert classify_player({1: stats}, 1, min_hands=10)[0] == PlayerProfile.UNKNOWN
    assert classify_player({1: stats}, 1, min_hands=5)[0] == PlayerProfile.NIT


def test_zero_division_guards() -> None:
    # vpip_opp/pfr_opp/saw_f are 0: the ratios default to 0.0 without crashing.
    assert_profile(make_stats(vpip_opp=0, pfr_opp=0, saw_f=0), PlayerProfile.NIT)


def test_nit() -> None:
    assert_profile(make_stats(vpip=12, pfr=8), PlayerProfile.NIT)


def test_calling_station() -> None:
    stats = make_stats(vpip=35, pfr=10, aggr_1=2, aggr_2=2, aggr_3=1, aggr_4=0, call_1=10, call_2=5, call_3=5, call_4=0, sd=15, saw_f=30)
    assert_profile(stats, PlayerProfile.CALLING_STATION)


def test_fish() -> None:
    assert_profile(make_stats(vpip=45, pfr=10), PlayerProfile.FISH)


def test_maniac_via_agg_pct() -> None:
    stats = make_stats(vpip=45, pfr=35, aggr_1=15, aggr_2=10, aggr_3=5, aggr_4=5, call_1=2, call_2=1, call_3=1, call_4=1)
    assert_profile(stats, PlayerProfile.MANIAC)


def test_maniac_via_agg_factor() -> None:
    # agg_pct below 60 but agg_factor = bet_raise / post_call > 3.0
    stats = make_stats(vpip=45, pfr=35, aggr_1=10, aggr_2=0, aggr_3=0, aggr_4=0, call_1=1, call_2=0, call_3=0, call_4=0)
    assert_profile(stats, PlayerProfile.MANIAC)


def test_lag() -> None:
    stats = make_stats(vpip=32, pfr=25, aggr_1=10, aggr_2=5, aggr_3=3, aggr_4=2, call_1=5, call_2=3, call_3=2)
    assert_profile(stats, PlayerProfile.LAG)


def test_reg() -> None:
    stats = make_stats(vpip=24, pfr=20, aggr_1=10, aggr_2=5, aggr_3=2, aggr_4=1, call_1=5, call_2=3, call_3=2)
    assert_profile(stats, PlayerProfile.REG)


def test_tag() -> None:
    assert_profile(make_stats(vpip=18, pfr=14), PlayerProfile.TAG)


def test_default_unknown() -> None:
    # Falls through every guard: moderate numbers, low aggression.
    assert_profile(make_stats(vpip=29, pfr=21, aggr_1=1, aggr_2=0, aggr_3=0, aggr_4=0, call_1=20, call_2=20, call_3=0), PlayerProfile.UNKNOWN)


def test_profile_tables_are_complete() -> None:
    for profile in (
        PlayerProfile.FISH,
        PlayerProfile.REG,
        PlayerProfile.NIT,
        PlayerProfile.MANIAC,
        PlayerProfile.LAG,
        PlayerProfile.TAG,
        PlayerProfile.CALLING_STATION,
        PlayerProfile.UNKNOWN,
    ):
        assert profile in PROFILE_ICONS
        assert profile in PROFILE_COLORS
