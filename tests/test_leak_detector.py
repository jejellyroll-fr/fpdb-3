"""Tests for the Leak Buster rule engine (:mod:`LeakDetector`).

Pure helpers only - no GUI, no DB. Covers metric extraction, every rule in the
catalogue (trigger / below-threshold / insufficient-sample), ranking, the
``top_leak`` selector and threshold configurability.
"""

import pytest

from fpdb_3_legacy.LeakDetector import (
    DEFAULT_THRESHOLDS,
    LEAK_RULES,
    DetectedLeak,
    LeakRule,
    compute_leak_metrics,
    detect_leaks,
    top_leak,
)


# ---------------------------------------------------------------------------
# compute_leak_metrics
# ---------------------------------------------------------------------------
def _stats(**overrides):
    base = {
        "bbstolen": 100,
        "bbnotdef": 70,
        "f3b_opp_0": 100,
        "f3b_0": 70,
        "cb_opp_1": 100,
        "cb_1": 80,
        "cb_opp_2": 100,
        "cb_2": 30,
        "f_cb_opp_2": 100,
        "f_cb_2": 60,
        "saw_f": 100,
        "sd": 40,
        "wmsd": 16,
        "saw_4": 50,
        "aggr_4": 5,
        "cb_opp_3": 40,
        "cb_3": 25,
    }
    base.update(overrides)
    return base


def test_compute_leak_metrics_percentages():
    m = compute_leak_metrics(_stats())
    assert m["fold_bb_vs_steal"] == pytest.approx(70.0)
    assert m["fold_to_3bet"] == pytest.approx(70.0)
    assert m["cbet_flop"] == pytest.approx(80.0)
    assert m["cbet_turn"] == pytest.approx(30.0)
    assert m["fold_to_turn_cbet"] == pytest.approx(60.0)
    assert m["wtsd"] == pytest.approx(40.0)
    assert m["wsd"] == pytest.approx(40.0)  # 16/40
    assert m["river_aggr_freq"] == pytest.approx(10.0)
    assert m["river_bet_freq"] == pytest.approx(62.5)


def test_compute_leak_metrics_missing_keys_are_none():
    m = compute_leak_metrics({})
    for key in (
        "fold_bb_vs_steal",
        "fold_to_3bet",
        "cbet_flop",
        "cbet_turn",
        "fold_to_turn_cbet",
        "wtsd",
        "wsd",
        "river_aggr_freq",
        "river_bet_freq",
    ):
        assert m[key] is None
    assert m["f3b_opp"] == 0


def test_compute_leak_metrics_zero_sample_is_none():
    m = compute_leak_metrics(_stats(f3b_opp_0=0, f3b_0=0))
    assert m["fold_to_3bet"] is None
    assert m["f3b_opp"] == 0


# ---------------------------------------------------------------------------
# Catalogue integrity
# ---------------------------------------------------------------------------
def test_rule_keys_unique():
    keys = [r.key for r in LEAK_RULES]
    assert len(keys) == len(set(keys))


def test_rules_reference_known_thresholds():
    # Every rule predicate must be callable and not raise on a full metrics set.
    metrics = compute_leak_metrics(_stats())
    for rule in LEAK_RULES:
        assert isinstance(rule, LeakRule)
        assert rule.predicate(metrics, DEFAULT_THRESHOLDS) in (True, False)


# ---------------------------------------------------------------------------
# Per-rule detection: trigger / below / insufficient sample
# ---------------------------------------------------------------------------
def _detect_key(metrics):
    return {d.key for d in detect_leaks(metrics)}


def test_fold_bb_vs_steal_fires():
    m = compute_leak_metrics(_stats(bbstolen=80, bbnotdef=60))  # 75%
    assert "fold_bb_vs_steal" in _detect_key(m)


def test_fold_bb_vs_steal_below_threshold():
    m = compute_leak_metrics(_stats(bbstolen=80, bbnotdef=40))  # 50%
    assert "fold_bb_vs_steal" not in _detect_key(m)


def test_overfold_to_3bet_fires_and_call_too_much_not():
    m = compute_leak_metrics(_stats(f3b_opp_0=100, f3b_0=70))  # 70%
    keys = _detect_key(m)
    assert "overfold_to_3bet" in keys
    assert "call_too_much_3bet" not in keys


def test_call_too_much_3bet_fires():
    m = compute_leak_metrics(_stats(f3b_opp_0=100, f3b_0=30))  # 30% < 40
    keys = _detect_key(m)
    assert "call_too_much_3bet" in keys
    assert "overfold_to_3bet" not in keys


def test_overfold_to_3bet_insufficient_sample():
    # 90% fold but only 5 opportunities (< min_sample 40) -> not flagged.
    m = compute_leak_metrics(_stats(f3b_opp_0=5, f3b_0=5))
    assert "overfold_to_3bet" not in _detect_key(m)


def test_cbet_flop_high_fires():
    m = compute_leak_metrics(_stats(cb_opp_1=100, cb_1=80))  # 80%
    assert "cbet_flop_high" in _detect_key(m)


def test_give_up_turn_fires():
    m = compute_leak_metrics(_stats(cb_opp_1=100, cb_1=85, cb_opp_2=100, cb_2=25))
    assert "give_up_turn" in _detect_key(m)


def test_give_up_turn_not_when_turn_cbet_high():
    m = compute_leak_metrics(_stats(cb_opp_1=100, cb_1=85, cb_opp_2=100, cb_2=70))
    assert "give_up_turn" not in _detect_key(m)


def test_overfold_turn_cbet_fires():
    m = compute_leak_metrics(_stats(f_cb_opp_2=100, f_cb_2=60))  # 60% > 55
    assert "overfold_turn_cbet" in _detect_key(m)


def test_wtsd_high_fires():
    m = compute_leak_metrics(_stats(saw_f=100, sd=40))  # 40% > 32
    assert "wtsd_high" in _detect_key(m)


def test_wsd_low_fires():
    m = compute_leak_metrics(_stats(sd=40, wmsd=16))  # 40% < 47
    assert "wsd_low" in _detect_key(m)


def test_wsd_low_not_when_high():
    m = compute_leak_metrics(_stats(sd=40, wmsd=24))  # 60% >= 47
    assert "wsd_low" not in _detect_key(m)


def test_river_aggr_low_fires():
    m = compute_leak_metrics(_stats(saw_4=50, aggr_4=5))  # 10% < 20
    assert "river_aggr_low" in _detect_key(m)


def test_river_bluff_high_fires():
    # bets river often (62.5%) with a low W$SD (40%) -> over-bluffs river.
    m = compute_leak_metrics(_stats(cb_opp_3=40, cb_3=25, sd=40, wmsd=16))
    assert "river_bluff_high" in _detect_key(m)


def test_river_bluff_high_not_when_wsd_ok():
    m = compute_leak_metrics(_stats(cb_opp_3=40, cb_3=25, sd=40, wmsd=24))  # W$SD 60%
    assert "river_bluff_high" not in _detect_key(m)


# ---------------------------------------------------------------------------
# detect_leaks ordering & top_leak
# ---------------------------------------------------------------------------
def test_detect_leaks_sorted_by_score_desc():
    m = compute_leak_metrics(_stats())
    leaks = detect_leaks(m)
    scores = [d.score for d in leaks]
    assert scores == sorted(scores, reverse=True)


def test_detect_leaks_returns_detectedleak_instances():
    m = compute_leak_metrics(_stats())
    leaks = detect_leaks(m)
    assert leaks and all(isinstance(d, DetectedLeak) for d in leaks)


def test_top_leak_none_when_no_leak():
    # Balanced reg, large sample, no threshold crossed.
    m = compute_leak_metrics(
        _stats(
            bbstolen=100,
            bbnotdef=50,
            f3b_opp_0=100,
            f3b_0=50,
            cb_opp_1=100,
            cb_1=60,
            cb_opp_2=100,
            cb_2=55,
            f_cb_opp_2=100,
            f_cb_2=45,
            saw_f=100,
            sd=28,
            wmsd=16,
            saw_4=50,
            aggr_4=20,
            cb_opp_3=40,
            cb_3=10,
        )
    )
    assert top_leak(m) is None


def test_top_leak_returns_highest():
    m = compute_leak_metrics(_stats())
    top = top_leak(m)
    assert top is not None
    assert top.score == max(d.score for d in detect_leaks(m))


# ---------------------------------------------------------------------------
# Threshold configurability
# ---------------------------------------------------------------------------
def test_custom_threshold_relaxes_detection():
    m = compute_leak_metrics(_stats(f3b_opp_0=100, f3b_0=70))  # 70%
    assert "overfold_to_3bet" in _detect_key(m)
    # Raise the floor above the observed value -> no longer flagged.
    keys = {d.key for d in detect_leaks(m, {"fold_to_3bet_high": 80.0})}
    assert "overfold_to_3bet" not in keys


def test_custom_threshold_does_not_mutate_defaults():
    detect_leaks(compute_leak_metrics(_stats()), {"fold_to_3bet_high": 99.0})
    assert DEFAULT_THRESHOLDS["fold_to_3bet_high"] == 65.0
