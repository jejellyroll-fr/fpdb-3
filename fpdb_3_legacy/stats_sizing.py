"""Bet amount and stack-to-pot sizing statistics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat


def average_bet_percentage(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    count_key: str,
    basis_points_key: str,
    abbreviation: str,
    description: str,
) -> StatTuple:
    """Format the mean size of a bet as a percentage of the pot."""
    try:
        count = float(stat_dict[player].get(count_key, 0))
        basis_points = float(stat_dict[player].get(basis_points_key, 0))
        if count == 0:
            return format_no_data_stat(abbreviation, description)
        stat = (basis_points / count) / 10000.0
        percent = 100.0 * stat
        display = f"{abbreviation}={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(basis_points)}/{int(count)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def f_bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_bet_facing_cnt", "f_bet_facing_bp", "FBvs", "avg flop bet faced (% pot)")


def t_bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_bet_facing_cnt", "t_bet_facing_bp", "TBvs", "avg turn bet faced (% pot)")


def r_bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_bet_facing_cnt", "r_bet_facing_bp", "RBvs", "avg river bet faced (% pot)")


def p_2bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_2bet_facing_cnt", "p_2bet_facing_bp", "2Bvs", "avg 2bet faced (% pot)")


def p_3bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_3bet_facing_cnt", "p_3bet_facing_bp", "3Bvs", "avg 3bet faced (% pot)")


def p_4bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_4bet_facing_cnt", "p_4bet_facing_bp", "4Bvs", "avg 4bet faced (% pot)")


def f_bet_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_bet_made_cnt", "f_bet_made_bp", "FBet", "avg flop bet made (% pot)")


def t_bet_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_bet_made_cnt", "t_bet_made_bp", "TBet", "avg turn bet made (% pot)")


def r_bet_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_bet_made_cnt", "r_bet_made_bp", "RBet", "avg river bet made (% pot)")


def p_raise_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_raise_made_cnt", "p_raise_made_bp", "PRz", "avg preflop raise made (% pot)")


def f_raise_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_raise_made_cnt", "f_raise_made_bp", "FRz", "avg flop raise made (% pot)")


def t_raise_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_raise_made_cnt", "t_raise_made_bp", "TRz", "avg turn raise made (% pot)")


def r_raise_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_raise_made_cnt", "r_raise_made_bp", "RRz", "avg river raise made (% pot)")


def p_raise_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_raise_facing_cnt", "p_raise_facing_bp", "PRvs", "avg preflop raise faced (% pot)")


def f_raise_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_raise_facing_cnt", "f_raise_facing_bp", "FRvs", "avg flop raise faced (% pot)")


def t_raise_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_raise_facing_cnt", "t_raise_facing_bp", "TRvs", "avg turn raise faced (% pot)")


def r_raise_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_raise_facing_cnt", "r_raise_facing_bp", "RRvs", "avg river raise faced (% pot)")


def f_2bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_2bet_facing_cnt", "f_2bet_facing_bp", "F2vs", "avg flop 2bet faced (% pot)")


def f_3bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_3bet_facing_cnt", "f_3bet_facing_bp", "F3vs", "avg flop 3bet faced (% pot)")


def f_4bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_4bet_facing_cnt", "f_4bet_facing_bp", "F4vs", "avg flop 4bet faced (% pot)")


def t_2bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_2bet_facing_cnt", "t_2bet_facing_bp", "T2vs", "avg turn 2bet faced (% pot)")


def t_3bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_3bet_facing_cnt", "t_3bet_facing_bp", "T3vs", "avg turn 3bet faced (% pot)")


def t_4bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_4bet_facing_cnt", "t_4bet_facing_bp", "T4vs", "avg turn 4bet faced (% pot)")


def r_2bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_2bet_facing_cnt", "r_2bet_facing_bp", "R2vs", "avg river 2bet faced (% pot)")


def r_3bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_3bet_facing_cnt", "r_3bet_facing_bp", "R3vs", "avg river 3bet faced (% pot)")


def r_4bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_4bet_facing_cnt", "r_4bet_facing_bp", "R4vs", "avg river 4bet faced (% pot)")


def p_raise_made_2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_raise_made_2_cnt", "p_raise_made_2_bp", "PRz2", "avg 2nd preflop raise made (% pot)")


def f_raise_made_2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "f_raise_made_2_cnt", "f_raise_made_2_bp", "FRz2", "avg 2nd flop raise made (% pot)")


def t_raise_made_2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "t_raise_made_2_cnt", "t_raise_made_2_bp", "TRz2", "avg 2nd turn raise made (% pot)")


def r_raise_made_2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "r_raise_made_2_cnt", "r_raise_made_2_bp", "RRz2", "avg 2nd river raise made (% pot)")


def p_5bet_facing(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return average_bet_percentage(stat_dict, player, "p_5bet_facing_cnt", "p_5bet_facing_bp", "5Bvs", "avg 5bet faced (% pot)")


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


def avg_bet_size_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for the deprecated aggregate flop bet-size stat."""
    return format_no_data_stat("avg_bet_f", "avg bet size flop (deprecated)")


def avg_bet_size_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for the deprecated aggregate turn bet-size stat."""
    return format_no_data_stat("avg_bet_t", "avg bet size turn (deprecated)")


def avg_bet_size_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for the deprecated aggregate river bet-size stat."""
    return format_no_data_stat("avg_bet_r", "avg bet size river (deprecated)")


def overbet_frequency(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical estimated overbet frequency when betting data exists."""
    try:
        total_bets = sum(
            float(stat_dict[player].get(key, 0)) for key in ("street1Bets", "street2Bets", "street3Bets")
        )
        if total_bets == 0:
            return format_no_data_stat("overbet", "% overbet frequency")
        percent = 15.0
        estimated_count = total_bets * percent / 100.0
        return (
            percent / 100.0,
            f"{percent:3.1f}",
            f"overbet={percent:3.1f}%",
            f"overbet_freq={percent:3.1f}%",
            f"({int(estimated_count)}/{int(total_bets)})",
            "% overbet frequency",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("overbet", "% overbet frequency")
