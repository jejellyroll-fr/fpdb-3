"""Preflop frequency statistics extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat
from fpdb_3_legacy.stats_postflop import postflop_ratio


def face_limpers(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the average number of limpers faced before acting preflop."""
    try:
        hands = float(stat_dict[player].get("n", 0))
        total = float(stat_dict[player].get("face_limpers", 0))
        if hands == 0:
            return format_no_data_stat("FLmp", "avg limpers faced preflop")
        stat = total / hands
        return (
            stat,
            f"{stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"({int(total)}/{int(hands)})",
            "avg limpers faced preflop",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("FLmp", "avg limpers faced preflop")


def straddle(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of voluntarily posting a straddle."""
    return postflop_ratio(stat_dict, player, "n", "straddle_done", "Str", "% straddle")


def gp_2x(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening for less than 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_2x", "2X", "% open-raise (<40% stack)")


def gp_os(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-shoving at least 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_os", "OS", "% open-shove (>=40% stack)")


def gp_limp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-limping."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_limp", "Limp", "% open-limp")


def fold_to_allin(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding when facing an all-in."""
    return postflop_ratio(stat_dict, player, "faced_allin", "fold_allin", "FvAI", "% fold to all-in")


def preflop_action_by_position(stat_dict: Mapping[int, Mapping[str, Any]], player: int, prefix: str, position: str, label: str) -> StatTuple:
    """Format a preflop action frequency in one HUD position bucket."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(f"{prefix}_opp_{position}", 0))
        done = float(stat_dict[player].get(f"{prefix}_{position}", 0))
        if opportunities == 0:
            return format_no_data_stat(label, f"% {label} preflop")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"{label}={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({done:.0f}/{opportunities:.0f})", f"% {label} preflop"
    except (AttributeError, KeyError, TypeError, ValueError):
        return stat, "NA", f"{label}=NA", f"{label}=NA", "(0/0)", f"% {label} preflop"


def three_bet_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "bb", "3B BB")
def three_bet_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "sb", "3B SB")
def three_bet_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "btn", "3B BTN")
def three_bet_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "co", "3B CO")
def three_bet_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "mp", "3B MP")
def three_bet_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "ep", "3B EP")
def four_bet_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "bb", "4B BB")
def four_bet_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "sb", "4B SB")
def four_bet_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "btn", "4B BTN")
def four_bet_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "co", "4B CO")
def four_bet_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "mp", "4B MP")
def four_bet_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "ep", "4B EP")
def squeeze_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "bb", "SQZ BB")
def squeeze_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "sb", "SQZ SB")
def squeeze_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "btn", "SQZ BTN")
def squeeze_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "co", "SQZ CO")
def squeeze_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "mp", "SQZ MP")
def squeeze_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "ep", "SQZ EP")
