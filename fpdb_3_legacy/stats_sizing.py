"""Bet amount and stack-to-pot sizing statistics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat


def average_spr(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    count_key: str,
    value_key: str,
    abbreviation: str,
    description: str,
) -> StatTuple:
    """Format the mean stack-to-pot ratio at the start of a street."""
    try:
        count = float(stat_dict[player].get(count_key, 0))
        value = float(stat_dict[player].get(value_key, 0))
        if count == 0:
            return format_no_data_stat(abbreviation, description)
        stat = (value / count) / 100.0
        display = f"{abbreviation}={stat:3.1f}"
        return stat, f"{stat:3.1f}", display, display, f"({int(value)}/{int(count)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def average_amount(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    key: str,
    abbreviation: str,
    description: str,
) -> StatTuple:
    """Format a mean chip amount per hand in currency units."""
    try:
        hands = float(stat_dict[player].get("n", 0))
        total = float(stat_dict[player].get(key, 0))
        if hands == 0:
            return format_no_data_stat(abbreviation, description)
        stat = (total / hands) / 100.0
        display = f"{abbreviation}={stat:.2f}"
        return stat, f"{stat:.2f}", display, display, f"({int(total)}/{int(hands)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def amt_blind(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_blind", "Blind", "avg blinds posted")


def amt_bet_p(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_bet_p", "BetP", "avg preflop invested")


def amt_bet_f(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_bet_f", "BetF", "avg flop invested")


def amt_bet_t(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_bet_t", "BetT", "avg turn invested")


def amt_bet_r(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_bet_r", "BetR", "avg river invested")


def amt_bet_ttl(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_amount(stat_dict, player, "amt_bet_ttl", "BetTtl", "avg total invested")


def f_spr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_spr(stat_dict, player, "f_spr_cnt", "f_spr_val", "fSPR", "avg flop SPR")


def t_spr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_spr(stat_dict, player, "t_spr_cnt", "t_spr_val", "tSPR", "avg turn SPR")


def r_spr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_spr(stat_dict, player, "r_spr_cnt", "r_spr_val", "rSPR", "avg river SPR")
