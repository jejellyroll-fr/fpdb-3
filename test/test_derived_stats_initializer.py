"""Shape of the per-player stat row every hand starts from."""

from __future__ import annotations

from fpdb_3_legacy.DerivedStats import _INIT_STATS, _buildStatsInitializer


def test_initializer_is_built_from_its_category_helpers() -> None:
    # Each helper owns one category and writes straight into the row, so the
    # assembled result must stay identical to what callers cache in _INIT_STATS.
    assert _buildStatsInitializer() == _INIT_STATS


def test_initializer_returns_a_fresh_row_each_time() -> None:
    first = _buildStatsInitializer()
    first["winnings"] = 999

    assert _buildStatsInitializer()["winnings"] == 0


def test_row_carries_every_stat_category() -> None:
    init = _buildStatsInitializer()

    # One representative key per helper: a category dropped from the assembly
    # would otherwise leave a silently missing stat.
    assert init["effStack"] == 0  # money and results
    assert init["startCards"] == 170  # hand outcome
    assert init["street0VPIChance"] is True  # preflop
    assert init["street1_3BChance"] is False  # postflop raise levels
    assert init["stealChance"] is False  # steal and blind defence
    assert init["street1Seen"] is False  # streets seen
    assert init["street0Calls"] == 0  # per-street counters
    assert init["flg_f_donk"] is False  # postflop street stats
    assert init["cnt_p_raise_made"] == 0  # raise sizing


def test_position_defaults_to_the_ante_all_in_sentinel() -> None:
    # 9 means "no position": stud hands where everyone is all in for the ante
    # keep it, so it must not be confused with a real seat.
    assert _buildStatsInitializer()["position"] == 9
