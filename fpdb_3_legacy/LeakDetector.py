#!/usr/bin/env python
"""Leak Buster - rule based leak detection from player statistics.

Turns raw player statistics into exploitable decisions, inspired by the
DriveHUD "Leak Buster". This first version is a simple engine based on
**configurable static thresholds**: a leak is flagged when a player crosses a
threshold for a given stat, provided the sample is large enough.

Design
------
- :class:`LeakRule` describes a detectable leak (key, title, requirements,
  minimum sample, severity, exploit advice) plus a pure ``predicate`` and a
  ``score`` callable used to rank leaks. No ``eval`` is used, in line with the
  security refactor of :func:`Stats.do_stat`.
- :func:`compute_leak_metrics` normalises a per-player ``stat_dict`` entry
  (the canonical HUD keys such as ``cb_opp_2``/``f_cb_2``/``wmsd``...) into a
  metrics dict of percentages and sample sizes. Formulas mirror ``Stats.py``
  exactly so the engine stays aligned with the HUD.
- :func:`detect_leaks` evaluates every rule against a metrics dict and returns
  the detected leaks sorted by dynamic severity. :func:`top_leak` returns the
  single most marked leak (the replacement for the ad-hoc ``pick_exploit``).

``thresholds`` is always an optional argument defaulting to
:data:`DEFAULT_THRESHOLDS`; this is the hook for a future pool-calibration
(percentile based) layer without changing the public API.
"""
# Copyright 2008-2011 Steffen Schaumburg
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Configurable static thresholds (percentages). These are the floors used by
# the engine; a future pool-calibration layer can override them per population.
# ---------------------------------------------------------------------------
DEFAULT_THRESHOLDS: dict[str, float] = {
    "fold_bb_vs_steal_high": 65.0,
    "fold_to_3bet_high": 65.0,
    "fold_to_3bet_low": 40.0,
    "cbet_flop_high": 75.0,
    "give_up_cbet_flop_high": 70.0,
    "give_up_cbet_turn_low": 40.0,
    "fold_to_turn_cbet_high": 55.0,
    "wtsd_high": 32.0,
    "wsd_low": 47.0,
    "river_aggr_low": 20.0,
    "river_bet_high": 45.0,
}


def _pct(done, chance) -> float | None:
    """Return ``100 * done / chance`` or ``None`` when there is no opportunity.

    ``None`` (rather than ``0``) signals "no data", so a rule requiring this
    stat is skipped instead of mis-firing on an absent sample.
    """
    try:
        chance = float(chance or 0)
        done = float(done or 0)
    except (TypeError, ValueError):
        return None
    if chance <= 0:
        return None
    return 100.0 * done / chance


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Metric extraction from a per-player stat_dict entry (canonical HUD keys)
# ---------------------------------------------------------------------------
def compute_leak_metrics(player_stats: dict) -> dict:
    """Normalise one ``stat_dict[player]`` entry into leak metrics.

    Returns a dict with percentage metrics and their sample-size counterparts
    (``*_opp`` keys). Formulas mirror the matching functions in ``Stats.py``:

    ============================  =================================  ==============
    metric                        formula (raw keys)                 sample key
    ============================  =================================  ==============
    ``fold_bb_vs_steal``          ``bbnotdef / bbstolen``            ``bbstolen``
    ``fold_to_3bet``              ``f3b_0 / f3b_opp_0``              ``f3b_opp``
    ``cbet_flop``                 ``cb_1 / cb_opp_1``               ``cb_opp_1``
    ``cbet_turn``                 ``cb_2 / cb_opp_2``               ``cb_opp_2``
    ``fold_to_turn_cbet``         ``f_cb_2 / f_cb_opp_2``           ``f_cb_opp_2``
    ``wtsd``                      ``sd / saw_f``                    ``saw_f``
    ``wsd`` (W$SD)                ``wmsd / sd``                     ``sd``
    ``river_aggr_freq``           ``aggr_4 / saw_4``                ``saw_4``
    ``river_bet_freq``            ``cb_3 / cb_opp_3``               ``cb_opp_3``
    ============================  =================================  ==============
    """
    s = player_stats or {}

    bbstolen = _int(s.get("bbstolen"))
    f3b_opp = _int(s.get("f3b_opp_0"))
    cb_opp_1 = _int(s.get("cb_opp_1"))
    cb_opp_2 = _int(s.get("cb_opp_2"))
    f_cb_opp_2 = _int(s.get("f_cb_opp_2"))
    saw_f = _int(s.get("saw_f"))
    sd = _int(s.get("sd"))
    saw_4 = _int(s.get("saw_4"))
    cb_opp_3 = _int(s.get("cb_opp_3"))

    return {
        "fold_bb_vs_steal": _pct(s.get("bbnotdef"), bbstolen),
        "fold_bb_vs_steal_opp": bbstolen,
        "fold_to_3bet": _pct(s.get("f3b_0"), f3b_opp),
        "f3b_opp": f3b_opp,
        "cbet_flop": _pct(s.get("cb_1"), cb_opp_1),
        "cb_opp": cb_opp_1,
        "cbet_turn": _pct(s.get("cb_2"), cb_opp_2),
        "cb2_opp": cb_opp_2,
        "fold_to_turn_cbet": _pct(s.get("f_cb_2"), f_cb_opp_2),
        "f_cb2_opp": f_cb_opp_2,
        "wtsd": _pct(sd, saw_f),
        "saw_f": saw_f,
        "wsd": _pct(s.get("wmsd"), sd),
        "sd": sd,
        "river_aggr_freq": _pct(s.get("aggr_4"), saw_4),
        "saw_4": saw_4,
        "river_bet_freq": _pct(s.get("cb_3"), cb_opp_3),
        "cb3_opp": cb_opp_3,
    }


# ---------------------------------------------------------------------------
# Leak rule model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LeakRule:
    """A detectable leak and its associated exploit.

    Attributes:
        key: stable identifier (e.g. ``"overfold_to_3bet"``).
        title: short human label.
        description: longer explanation of the leak.
        stat_requirements: metric keys that must be present (not ``None``).
        sample_key: metrics key holding the relevant opportunity count.
        min_sample: minimum opportunities before the leak is trusted.
        severity: base severity 1..10 (table 8.2).
        exploit_advice: how to exploit the leak.
        predicate: ``(metrics, thresholds) -> bool`` trigger condition.
        score: ``(metrics, thresholds) -> float`` dynamic severity for ranking.
    """

    key: str
    title: str
    description: str
    stat_requirements: list[str]
    sample_key: str
    min_sample: int
    severity: int
    exploit_advice: str
    predicate: Callable[[dict, dict], bool]
    score: Callable[[dict, dict], float] = field(
        default=lambda metrics, thresholds: 0.0,
    )


@dataclass(frozen=True)
class DetectedLeak:
    """A leak detected for a player."""

    rule: LeakRule
    value: float
    sample: int
    score: float

    @property
    def key(self) -> str:
        return self.rule.key

    @property
    def title(self) -> str:
        return self.rule.title

    @property
    def exploit_advice(self) -> str:
        return self.rule.exploit_advice


def _m(metrics: dict, key: str) -> float:
    """Return ``metrics[key]`` as float (0.0 when missing/None)."""
    value = metrics.get(key)
    return float(value) if value is not None else 0.0


# ---------------------------------------------------------------------------
# Leak catalogue (table 8.2)
# ---------------------------------------------------------------------------
LEAK_RULES: list[LeakRule] = [
    LeakRule(
        key="fold_bb_vs_steal",
        title="Overfolds BB vs steal",
        description="Folds the big blind too often against steal attempts.",
        stat_requirements=["fold_bb_vs_steal"],
        sample_key="fold_bb_vs_steal_opp",
        min_sample=30,
        severity=6,
        exploit_advice="Steal the button more often.",
        predicate=lambda m, t: _m(m, "fold_bb_vs_steal") > t["fold_bb_vs_steal_high"],
        score=lambda m, t: (_m(m, "fold_bb_vs_steal") - t["fold_bb_vs_steal_high"]) / 35.0 + 1.0,
    ),
    LeakRule(
        key="overfold_to_3bet",
        title="Overfolds to 3-bets",
        description="Folds too often against preflop 3-bets.",
        stat_requirements=["fold_to_3bet"],
        sample_key="f3b_opp",
        min_sample=40,
        severity=7,
        exploit_advice="Increase bluff 3-bets against this player, especially in position.",
        predicate=lambda m, t: _m(m, "fold_to_3bet") > t["fold_to_3bet_high"],
        score=lambda m, t: (_m(m, "fold_to_3bet") - t["fold_to_3bet_high"]) / 35.0 + 1.0,
    ),
    LeakRule(
        key="call_too_much_3bet",
        title="Calls 3-bets too much",
        description="Does not fold enough against 3-bets and defends too wide.",
        stat_requirements=["fold_to_3bet"],
        sample_key="f3b_opp",
        min_sample=40,
        severity=5,
        exploit_advice="Use a more merged, value-heavy 3-bet range against this player.",
        predicate=lambda m, t: _m(m, "fold_to_3bet") < t["fold_to_3bet_low"],
        score=lambda m, t: (t["fold_to_3bet_low"] - _m(m, "fold_to_3bet")) / 40.0 + 0.8,
    ),
    LeakRule(
        key="cbet_flop_high",
        title="Flop c-bet too high",
        description="Continuation-bets the flop too frequently, often with an insufficiently polarised range.",
        stat_requirements=["cbet_flop"],
        sample_key="cb_opp",
        min_sample=20,
        severity=6,
        exploit_advice="Float or raise the flop more often.",
        predicate=lambda m, t: _m(m, "cbet_flop") > t["cbet_flop_high"],
        score=lambda m, t: (_m(m, "cbet_flop") - t["cbet_flop_high"]) / 25.0 + 0.9,
    ),
    LeakRule(
        key="give_up_turn",
        title="Give up turn",
        description="C-bets the flop often but gives up too frequently on the turn.",
        stat_requirements=["cbet_flop", "cbet_turn"],
        sample_key="cb2_opp",
        min_sample=20,
        severity=6,
        exploit_advice="Call the flop, then bet the turn when they check.",
        predicate=lambda m, t: (
            _m(m, "cbet_flop") > t["give_up_cbet_flop_high"]
            and _m(m, "cbet_turn") < t["give_up_cbet_turn_low"]
        ),
        score=lambda m, t: (t["give_up_cbet_turn_low"] - _m(m, "cbet_turn")) / 40.0 + 0.9,
    ),
    LeakRule(
        key="overfold_turn_cbet",
        title="Overfolds turn",
        description="Folds too often against turn continuation bets.",
        stat_requirements=["fold_to_turn_cbet"],
        sample_key="f_cb2_opp",
        min_sample=20,
        severity=6,
        exploit_advice="Double-barrel bluff more often.",
        predicate=lambda m, t: _m(m, "fold_to_turn_cbet") > t["fold_to_turn_cbet_high"],
        score=lambda m, t: (_m(m, "fold_to_turn_cbet") - t["fold_to_turn_cbet_high"]) / 45.0 + 0.9,
    ),
    LeakRule(
        key="wtsd_high",
        title="WTSD too high",
        description="Goes to showdown too often and calls too wide.",
        stat_requirements=["wtsd"],
        sample_key="saw_f",
        min_sample=30,
        severity=5,
        exploit_advice="Value bet thinner.",
        predicate=lambda m, t: _m(m, "wtsd") > t["wtsd_high"],
        score=lambda m, t: (_m(m, "wtsd") - t["wtsd_high"]) / 30.0 + 0.5,
    ),
    LeakRule(
        key="wsd_low",
        title="W$SD too low",
        description="Wins too little money at showdown, often arriving too light.",
        stat_requirements=["wsd"],
        sample_key="sd",
        min_sample=25,
        severity=5,
        exploit_advice="They arrive too light at showdown: value bet and bluff-catch more.",
        predicate=lambda m, t: _m(m, "wsd") < t["wsd_low"],
        score=lambda m, t: (t["wsd_low"] - _m(m, "wsd")) / 47.0 + 0.6,
    ),
    LeakRule(
        key="river_aggr_low",
        title="River aggression too low",
        description="Rarely bets or raises on the river.",
        stat_requirements=["river_aggr_freq"],
        sample_key="saw_4",
        min_sample=20,
        severity=5,
        exploit_advice="Overfold versus large river bets and bluff more often when checked to.",
        predicate=lambda m, t: _m(m, "river_aggr_freq") < t["river_aggr_low"],
        score=lambda m, t: (t["river_aggr_low"] - _m(m, "river_aggr_freq")) / 20.0 + 0.5,
    ),
    LeakRule(
        key="river_bluff_high",
        title="River bluff too high",
        description="Bets the river often while W$SD is low, suggesting over-bluffing.",
        stat_requirements=["river_bet_freq", "wsd"],
        sample_key="cb3_opp",
        min_sample=20,
        severity=6,
        exploit_advice="Bluff-catch more often against their river bets.",
        predicate=lambda m, t: (
            _m(m, "river_bet_freq") > t["river_bet_high"]
            and _m(m, "wsd") < t["wsd_low"]
        ),
        score=lambda m, t: (_m(m, "river_bet_freq") - t["river_bet_high"]) / 45.0 + 0.7,
    ),
]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def detect_leaks(
    metrics: dict,
    thresholds: dict | None = None,
    rules: list[LeakRule] | None = None,
) -> list[DetectedLeak]:
    """Return the leaks detected in ``metrics``, sorted by score (desc).

    A rule fires when:
    - all its ``stat_requirements`` are present (not ``None``);
    - its sample (``metrics[sample_key]``) is at least ``min_sample``;
    - its ``predicate`` is satisfied against ``thresholds``.

    ``thresholds`` defaults to :data:`DEFAULT_THRESHOLDS`. This is the hook for
    a future pool-calibrated set of cutoffs.
    """
    t = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        t.update(thresholds)
    catalogue = rules if rules is not None else LEAK_RULES

    detected: list[DetectedLeak] = []
    for rule in catalogue:
        if any(metrics.get(req) is None for req in rule.stat_requirements):
            continue
        sample = _int(metrics.get(rule.sample_key))
        if sample < rule.min_sample:
            continue
        if not rule.predicate(metrics, t):
            continue
        primary = rule.stat_requirements[0]
        detected.append(
            DetectedLeak(
                rule=rule,
                value=_m(metrics, primary),
                sample=sample,
                score=float(rule.score(metrics, t)),
            ),
        )

    detected.sort(key=lambda d: d.score, reverse=True)
    return detected


def top_leak(metrics: dict, thresholds: dict | None = None) -> DetectedLeak | None:
    """Return the single most marked leak, or ``None`` when none is detected."""
    leaks = detect_leaks(metrics, thresholds)
    return leaks[0] if leaks else None
