"""Postflop frequency statistics extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat


def postflop_ratio(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunity_key: str,
    done_key: str,
    abbreviation: str,
    description: str,
) -> StatTuple:
    """Format a per-street postflop done/opportunity percentage."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(opportunity_key, 0))
        done = float(stat_dict[player].get(done_key, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"{abbreviation}={percent:3.1f}%"
        return (
            stat,
            f"{percent:3.1f}",
            display,
            display,
            f"({int(done)}/{int(opportunities)})",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{abbreviation}=NA", "(0/0)", description


def three_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the flop 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "fl3b_opp", "fl3b", "F3B", "% 3 bet flop")


def three_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "tn3b_opp", "tn3b", "T3B", "% 3 bet turn")


def three_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "rv3b_opp", "rv3b", "R3B", "% 3 bet river")


def fold_to_three_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-flop-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "ff3b_opp", "ff3b", "FF3B", "% fold to flop 3bet")


def fold_to_three_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-turn-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "ft3b_opp", "ft3b", "FT3B", "% fold to turn 3bet")


def fold_to_three_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-river-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "fr3b_opp", "fr3b", "FR3B", "% fold to river 3bet")


def four_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the flop 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "fl4b_opp", "fl4b", "F4B", "% 4 bet flop")


def four_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "tn4b_opp", "tn4b", "T4B", "% 4 bet turn")


def four_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "rv4b_opp", "rv4b", "R4B", "% 4 bet river")


def open_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened flop."""
    return postflop_ratio(stat_dict, player, "flopen_opp", "flopen", "OPf", "% open flop")


def open_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened turn."""
    return postflop_ratio(stat_dict, player, "tnopen_opp", "tnopen", "OPt", "% open turn")


def open_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened river."""
    return postflop_ratio(stat_dict, player, "rvopen_opp", "rvopen", "OPr", "% open river")


def float_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn continuation frequency after floating the flop."""
    return postflop_ratio(stat_dict, player, "float_turn_chance", "float_turn_done", "FltT", "% float turn")


def float_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river continuation frequency after floating the turn."""
    return postflop_ratio(stat_dict, player, "float_river_chance", "float_river_done", "FltR", "% float river")
