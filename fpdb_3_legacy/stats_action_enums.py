"""HUD stats for the PT4 action enums: the F/C/R split of each spot faced.

``DerivedStats.calcActionEnums`` records one response char per situation and
``action_enum_stats`` counts them into HudCache. Each situation yields three
stats here -- called, raised, folded -- over the same denominator, the number
of times the spot was faced.

The fold leg is computed rather than stored: a faced situation resolves to
exactly one of F/C/R, so ``folded = faced - called - raised``. Storing it would
have added seventeen more cache columns that can never disagree with the three.

These read the same denominator for all three legs, so unlike the older
``foldToStreetNCB*`` pairs the three percentages of one spot always add up to
100. Where both exist they answer slightly different questions -- the legacy
chance flags and the enum's "situation arose" are computed separately -- so the
numbers are close but not interchangeable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.action_enum_stats import SITUATIONS
from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat
from fpdb_3_legacy.stats_postflop import postflop_ratio

_BY_ENUM = {situation.enum_key: situation for situation in SITUATIONS}


def _faced_ratio(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    enum_key: str,
    done_key_attr: str,
    prefix: str,
    verb: str,
) -> StatTuple:
    """Format one leg of a situation as done / faced."""
    situation = _BY_ENUM[enum_key]
    return postflop_ratio(
        stat_dict,
        player,
        situation.faced_key,
        getattr(situation, done_key_attr),
        f"{prefix}{situation.label}",
        f"% {verb} facing {situation.description}",
    )


def _fold_ratio(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    enum_key: str,
) -> StatTuple:
    """Format the fold leg, whose numerator is faced - called - raised."""
    situation = _BY_ENUM[enum_key]
    abbreviation = f"F{situation.label}"
    description = f"% folding facing {situation.description}"
    try:
        row = stat_dict[player]
        faced = float(row.get(situation.faced_key, 0))
        if faced == 0:
            return format_no_data_stat(abbreviation, description)
        folded = faced - float(row.get(situation.called_key, 0)) - float(row.get(situation.raised_key, 0))
        # Clamped because the three counters are summed independently across
        # cache rows: a partially rebuilt HudCache must not render as -12%.
        folded = max(folded, 0.0)
        stat = folded / faced
        percent = 100.0 * stat
        display = f"{abbreviation}={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(folded)}/{int(faced)})", description
    except (AttributeError, KeyError, TypeError, ValueError):
        return 0.0, "NA", f"{abbreviation}=NA", f"{abbreviation}=NA", "(0/0)", description


def call_vs_preflop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a preflop 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_p_3bet_action", "called_key", "C", "calling")


def raise_vs_preflop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a preflop 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_p_3bet_action", "raised_key", "R", "raising")


def fold_vs_preflop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a preflop 3-bet."""
    return _fold_ratio(stat_dict, player, "enum_p_3bet_action")


def call_vs_preflop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a preflop 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_p_4bet_action", "called_key", "C", "calling")


def raise_vs_preflop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a preflop 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_p_4bet_action", "raised_key", "R", "raising")


def fold_vs_preflop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a preflop 4-bet."""
    return _fold_ratio(stat_dict, player, "enum_p_4bet_action")


def call_vs_preflop_squeeze(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a preflop squeeze."""
    return _faced_ratio(stat_dict, player, "enum_p_squeeze_action", "called_key", "C", "calling")


def raise_vs_preflop_squeeze(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a preflop squeeze."""
    return _faced_ratio(stat_dict, player, "enum_p_squeeze_action", "raised_key", "R", "raising")


def fold_vs_preflop_squeeze(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a preflop squeeze."""
    return _fold_ratio(stat_dict, player, "enum_p_squeeze_action")


def call_vs_flop_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a flop c-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_cbet_action", "called_key", "C", "calling")


def raise_vs_flop_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a flop c-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_cbet_action", "raised_key", "R", "raising")


def fold_vs_flop_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a flop c-bet."""
    return _fold_ratio(stat_dict, player, "enum_f_cbet_action")


def call_vs_flop_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a flop donk bet."""
    return _faced_ratio(stat_dict, player, "enum_f_donk_action", "called_key", "C", "calling")


def raise_vs_flop_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a flop donk bet."""
    return _faced_ratio(stat_dict, player, "enum_f_donk_action", "raised_key", "R", "raising")


def fold_vs_flop_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a flop donk bet."""
    return _fold_ratio(stat_dict, player, "enum_f_donk_action")


def call_vs_flop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a flop 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_3bet_action", "called_key", "C", "calling")


def raise_vs_flop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a flop 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_3bet_action", "raised_key", "R", "raising")


def fold_vs_flop_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a flop 3-bet."""
    return _fold_ratio(stat_dict, player, "enum_f_3bet_action")


def call_vs_flop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a flop 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_4bet_action", "called_key", "C", "calling")


def raise_vs_flop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a flop 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_f_4bet_action", "raised_key", "R", "raising")


def fold_vs_flop_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a flop 4-bet."""
    return _fold_ratio(stat_dict, player, "enum_f_4bet_action")


def call_vs_turn_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a turn c-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_cbet_action", "called_key", "C", "calling")


def raise_vs_turn_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a turn c-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_cbet_action", "raised_key", "R", "raising")


def fold_vs_turn_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a turn c-bet."""
    return _fold_ratio(stat_dict, player, "enum_t_cbet_action")


def call_vs_turn_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a turn donk bet."""
    return _faced_ratio(stat_dict, player, "enum_t_donk_action", "called_key", "C", "calling")


def raise_vs_turn_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a turn donk bet."""
    return _faced_ratio(stat_dict, player, "enum_t_donk_action", "raised_key", "R", "raising")


def fold_vs_turn_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a turn donk bet."""
    return _fold_ratio(stat_dict, player, "enum_t_donk_action")


def call_vs_turn_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a turn 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_3bet_action", "called_key", "C", "calling")


def raise_vs_turn_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a turn 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_3bet_action", "raised_key", "R", "raising")


def fold_vs_turn_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a turn 3-bet."""
    return _fold_ratio(stat_dict, player, "enum_t_3bet_action")


def call_vs_turn_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a turn 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_4bet_action", "called_key", "C", "calling")


def raise_vs_turn_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a turn 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_t_4bet_action", "raised_key", "R", "raising")


def fold_vs_turn_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a turn 4-bet."""
    return _fold_ratio(stat_dict, player, "enum_t_4bet_action")


def call_float_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing the turn barrel, having called the flop c-bet in position."""
    return _faced_ratio(stat_dict, player, "enum_t_float_action", "called_key", "C", "calling")


def raise_float_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing the turn barrel, having called the flop c-bet in position."""
    return _faced_ratio(stat_dict, player, "enum_t_float_action", "raised_key", "R", "raising")


def fold_float_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing the turn barrel, having called the flop c-bet in position."""
    return _fold_ratio(stat_dict, player, "enum_t_float_action")


def call_vs_river_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a river c-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_cbet_action", "called_key", "C", "calling")


def raise_vs_river_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a river c-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_cbet_action", "raised_key", "R", "raising")


def fold_vs_river_cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a river c-bet."""
    return _fold_ratio(stat_dict, player, "enum_r_cbet_action")


def call_vs_river_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a river donk bet."""
    return _faced_ratio(stat_dict, player, "enum_r_donk_action", "called_key", "C", "calling")


def raise_vs_river_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a river donk bet."""
    return _faced_ratio(stat_dict, player, "enum_r_donk_action", "raised_key", "R", "raising")


def fold_vs_river_donk(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a river donk bet."""
    return _fold_ratio(stat_dict, player, "enum_r_donk_action")


def call_vs_river_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a river 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_3bet_action", "called_key", "C", "calling")


def raise_vs_river_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a river 3-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_3bet_action", "raised_key", "R", "raising")


def fold_vs_river_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a river 3-bet."""
    return _fold_ratio(stat_dict, player, "enum_r_3bet_action")


def call_vs_river_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing a river 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_4bet_action", "called_key", "C", "calling")


def raise_vs_river_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing a river 4-bet."""
    return _faced_ratio(stat_dict, player, "enum_r_4bet_action", "raised_key", "R", "raising")


def fold_vs_river_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing a river 4-bet."""
    return _fold_ratio(stat_dict, player, "enum_r_4bet_action")


def call_float_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player calls facing the river barrel, having called the turn bet in position."""
    return _faced_ratio(stat_dict, player, "enum_r_float_action", "called_key", "C", "calling")


def raise_float_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player raises facing the river barrel, having called the turn bet in position."""
    return _faced_ratio(stat_dict, player, "enum_r_float_action", "raised_key", "R", "raising")


def fold_float_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds facing the river barrel, having called the turn bet in position."""
    return _fold_ratio(stat_dict, player, "enum_r_float_action")
